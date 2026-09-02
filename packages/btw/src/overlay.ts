/**
 * btw overlay — the interactive popup that hosts the side question.
 *
 * Rendered as a full-width panel anchored to the bottom of the terminal
 * (covering the main session input area), with height adapting to the content: short
 * answers shrink the panel, long answers cap at ~40% of the terminal and
 * scroll with the arrow/page keys. Escape closes (or cancels while loading).
 *
 * Note: mouse-wheel scrolling is not available — in pi's fullscreen TUI the
 * wheel belongs to the chat viewport (TuiAltScreen consumes all mouse events
 * before extensions see them). Scrolling is keyboard-driven instead.
 *
 * Style callbacks are passed in (instead of the Theme object) so this module
 * does not depend on pi's internal Theme type.
 */

import {
  CancellableLoader,
  type Component,
  Input,
  Key,
  Markdown,
  type MarkdownTheme,
  matchesKey,
  type TUI,
  truncateToWidth,
  visibleWidth,
} from "@earendil-works/pi-tui";
import {
  buildMarkdownThemeCallbacks,
  computeScrollWindow,
  maxBodyHeight,
  renderPiPanel,
  type PiThemeStyle,
} from "@fradser/pi-kit";
import type { BtwResult, BtwTurn, BtwUsage } from "./spawner";

/** The shared pi-kit theme style language — btw's overlay style is that shape. */
export type BtwOverlayStyle = PiThemeStyle;

export interface BtwOverlayOptions {
  /** The initial side question as asked. */
  question: string;
  /** Model label shown in the loading line (optional). */
  modelLabel?: string;
  /** Called when the overlay should close (escape, or cancel while loading initial question). */
  onCancel: () => void;
  /**
   * Called to run a turn (initial or follow-up).
   * Receives question, history of completed turns, and an AbortSignal.
   * Returns Promise with the result.
   */
  onAsk?: (
    question: string,
    history: BtwTurn[],
    signal: AbortSignal,
  ) => Promise<BtwResult>;
  /** Optional legacy callback for single-turn caller. */
  onSpawn?: (signal: AbortSignal) => void;
}

export interface BtwAnswerMeta {
  usage?: BtwUsage;
  elapsedMs?: number;
}

export interface BtwTurnState {
  question: string;
  answer?: string;
  error?: string;
  usage?: BtwUsage;
  elapsedMs?: number;
}

export interface BtwOverlay extends Component {
  dispose(): void;
  showAnswer(text: string, meta?: BtwAnswerMeta): void;
  showError(text: string): void;
}

type OverlayState = "loading" | "idle" | "error";

/** Cap the answer body at ~40% of the terminal height (adaptive, scrollable). */
export function maxAnswerBody(rows: number): number {
  return maxBodyHeight(rows, 0.4);
}

/** Build a MarkdownTheme from the overlay style callbacks. */
function buildMarkdownTheme(style: BtwOverlayStyle): MarkdownTheme {
  return buildMarkdownThemeCallbacks(style) as MarkdownTheme;
}

export function createBtwOverlay(
  tui: TUI,
  style: BtwOverlayStyle,
  options: BtwOverlayOptions,
): BtwOverlay {
  const input = new Input();
  input.focused = true;

  const loader = new CancellableLoader(
    tui,
    style.accent,
    style.muted,
    options.modelLabel ? `Answering (read-only, ${options.modelLabel})…` : "Answering (read-only)…",
  );

  const mdTheme = buildMarkdownTheme(style);

  const turns: BtwTurnState[] = [];
  let state: OverlayState = "loading";
  let closed = false;
  let scroll = 0;
  let markdown: Markdown | undefined;
  let currentAbortController: AbortController | undefined;

  const formatAnswer = (answer: string): string => {
    // Keep inline answers compact, but separate a block-level construct from
    // the label so headings, lists, quotes, and fenced code are parsed as Markdown.
    const startsWithBlock = /^(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|>\s|```|~~~)/.test(answer);
    return startsWithBlock ? `**btw**\n\n${answer}` : `**btw**  ${answer}`;
  };

  const buildConversationMarkdown = (): string => {
    if (turns.length === 0) return "";
    const parts: string[] = [];
    for (const turn of turns) {
      const turnParts: string[] = [`**You**  ${turn.question}`];
      if (turn.error) {
        turnParts.push(`*Error: ${turn.error}*`);
      } else if (turn.answer !== undefined) {
        turnParts.push(formatAnswer(turn.answer));
      }
      parts.push(turnParts.join("\n\n"));
    }
    return parts.join("\n\n---\n\n");
  };

  const updateMarkdown = () => {
    const text = buildConversationMarkdown();
    if (markdown) {
      markdown.setText(text);
      markdown.invalidate();
    } else if (text) {
      markdown = new Markdown(text, 0, 0, mdTheme, undefined, { renderLatex: true });
    }
  };

  const scrollToBottom = () => {
    const contentWidth = Math.max(20, tui.terminal.columns - 4);
    const maxBody = maxAnswerBody(tui.terminal.rows);
    const lines = markdown?.render(contentWidth) ?? [];
    scroll = computeScrollWindow(lines, Number.MAX_SAFE_INTEGER, maxBody).clampedScroll;
  };

  const scrollBy = (delta: number, maxBody: number) => {
    const contentWidth = Math.max(20, tui.terminal.columns - 4);
    const lines = markdown?.render(contentWidth) ?? [];
    const next = computeScrollWindow(lines, scroll + delta, maxBody).clampedScroll;
    if (next !== scroll) {
      scroll = next;
      tui.requestRender();
    }
  };

  const renderComposer = (width: number): string[] => {
    const lineWidth = Math.max(1, width);
    const separator = style.border("─".repeat(lineWidth));
    const inputWidth = Math.max(4, lineWidth - 4);
    const inputLines = input.render(inputWidth);
    const lines = [separator, ""];

    for (const line of inputLines) {
      const value = line.startsWith("> ") ? line.slice(2) : line;
      const prompt = truncateToWidth(`${style.accent("btw")} ${style.muted("›")} ${value}`, lineWidth);
      const promptWidth = visibleWidth(prompt);
      const leftSpace = Math.floor(Math.max(0, lineWidth - promptWidth) / 2);
      const rightSpace = Math.max(0, lineWidth - promptWidth - leftSpace);
      lines.push(`${" ".repeat(leftSpace)}${prompt}${" ".repeat(rightSpace)}`);
    }

    lines.push("", separator);
    return lines;
  };

  const askQuestion = (question: string) => {
    if (closed) return;
    const abortController = new AbortController();
    currentAbortController = abortController;

    turns.push({ question });
    state = "loading";
    updateMarkdown();
    scrollToBottom();
    loader.start();
    tui.requestRender();

    const startedAt = Date.now();

    if (options.onAsk) {
      const history: BtwTurn[] = turns
        .slice(0, -1)
        .filter((t) => t.answer !== undefined)
        .map((t) => ({ question: t.question, answer: t.answer ?? "" }));

      options
        .onAsk(question, history, abortController.signal)
        .then((result) => {
          if (closed || abortController.signal.aborted) return;
          const currentTurn = turns[turns.length - 1];
          if (!currentTurn) return;

          if (result.timedOut) {
            currentTurn.error = "The side question timed out. Try again or make the question more specific.";
            state = "error";
          } else if (result.exitCode !== 0 && !result.text) {
            currentTurn.error = result.stderr.trim()
              ? `The side question failed:\n${result.stderr.trim()}`
              : `The side question failed with exit code ${result.exitCode}.`;
            state = "error";
          } else {
            currentTurn.answer = result.text || "(no answer)";
            currentTurn.usage = result.usage;
            currentTurn.elapsedMs = Date.now() - startedAt;
            state = "idle";
          }
          loader.stop();
          updateMarkdown();
          scrollToBottom();
          input.focused = true;
          tui.requestRender();
        })
        .catch((error: unknown) => {
          if (closed || abortController.signal.aborted) return;
          const currentTurn = turns[turns.length - 1];
          if (currentTurn) {
            currentTurn.error = error instanceof Error ? error.message : String(error);
          }
          state = "error";
          loader.stop();
          updateMarkdown();
          scrollToBottom();
          input.focused = true;
          tui.requestRender();
        });
    } else if (options.onSpawn) {
      options.onSpawn(abortController.signal);
    }
  };

  loader.onAbort = () => {
    if (closed) return;
    currentAbortController?.abort();
    if (turns.length <= 1) {
      closed = true;
      options.onCancel();
    } else {
      turns.pop();
      state = "idle";
      updateMarkdown();
      scrollToBottom();
      input.focused = true;
      tui.requestRender();
    }
  };

  input.onSubmit = (value: string) => {
    if (state === "loading") return;
    const nextQuestion = value.trim();
    if (!nextQuestion) return;
    input.setValue("");
    askQuestion(nextQuestion);
  };

  input.onEscape = () => {
    if (!closed) {
      closed = true;
      loader.stop();
      currentAbortController?.abort();
      options.onCancel();
    }
  };

  askQuestion(options.question);

  return {
    showAnswer(text: string, m?: BtwAnswerMeta) {
      if (closed) return;
      let currentTurn = turns[turns.length - 1];
      if (!currentTurn) {
        currentTurn = { question: options.question };
        turns.push(currentTurn);
      }
      currentTurn.answer = text;
      currentTurn.usage = m?.usage;
      currentTurn.elapsedMs = m?.elapsedMs;
      state = "idle";
      loader.stop();
      updateMarkdown();
      scrollToBottom();
      input.focused = true;
      tui.requestRender();
    },
    showError(text: string) {
      if (closed) return;
      let currentTurn = turns[turns.length - 1];
      if (!currentTurn) {
        currentTurn = { question: options.question };
        turns.push(currentTurn);
      }
      currentTurn.error = text;
      state = "error";
      loader.stop();
      updateMarkdown();
      scrollToBottom();
      input.focused = true;
      tui.requestRender();
    },

    handleInput(data: string) {
      if (state === "loading") {
        if (matchesKey(data, Key.escape)) {
          currentAbortController?.abort();
          loader.stop();
          if (turns.length <= 1) {
            if (!closed) {
              closed = true;
              options.onCancel();
            }
          } else {
            turns.pop();
            state = "idle";
            updateMarkdown();
            scrollToBottom();
            input.focused = true;
            tui.requestRender();
          }
          return;
        }

        const sgrWheel = /^\x1b\[<(\d+);(\d+);(\d+)[Mm]$/.exec(data);
        if (sgrWheel) {
          const button = Number.parseInt(sgrWheel[1], 10);
          if ((button & 64) !== 0) {
            const direction = button & 3;
            const maxBody = maxAnswerBody(tui.terminal.rows);
            if (direction === 0) scrollBy(-3, maxBody);
            else if (direction === 1) scrollBy(3, maxBody);
          }
          return;
        }
        const maxBody = maxAnswerBody(tui.terminal.rows);
        if (matchesKey(data, Key.up)) scrollBy(-1, maxBody);
        else if (matchesKey(data, Key.down)) scrollBy(1, maxBody);
        else if (matchesKey(data, Key.pageUp)) scrollBy(-Math.max(1, maxBody - 1), maxBody);
        else if (matchesKey(data, Key.pageDown)) scrollBy(Math.max(1, maxBody - 1), maxBody);
        else if (matchesKey(data, Key.home)) {
          scroll = 0;
          tui.requestRender();
        } else if (matchesKey(data, Key.end)) {
          scroll = Number.MAX_SAFE_INTEGER;
          const contentWidth = Math.max(20, tui.terminal.columns - 4);
          const lines = markdown?.render(contentWidth) ?? [];
          const max = Math.max(0, lines.length - maxBody);
          scroll = Math.min(scroll, max);
          tui.requestRender();
        }
        return;
      }

      if (matchesKey(data, Key.escape)) {
        if (!closed) {
          closed = true;
          loader.stop();
          currentAbortController?.abort();
          options.onCancel();
        }
        return;
      }

      const sgrWheel = /^\x1b\[<(\d+);(\d+);(\d+)[Mm]$/.exec(data);
      if (sgrWheel) {
        const button = Number.parseInt(sgrWheel[1], 10);
        if ((button & 64) !== 0) {
          const direction = button & 3;
          const maxBody = maxAnswerBody(tui.terminal.rows);
          if (direction === 0) scrollBy(-3, maxBody);
          else if (direction === 1) scrollBy(3, maxBody);
        }
        return;
      }
      const maxBody = maxAnswerBody(tui.terminal.rows);
      if (matchesKey(data, Key.up)) scrollBy(-1, maxBody);
      else if (matchesKey(data, Key.down)) scrollBy(1, maxBody);
      else if (matchesKey(data, Key.pageUp)) scrollBy(-Math.max(1, maxBody - 1), maxBody);
      else if (matchesKey(data, Key.pageDown)) scrollBy(Math.max(1, maxBody - 1), maxBody);
      else if (matchesKey(data, Key.home)) {
        scroll = 0;
        tui.requestRender();
      } else if (matchesKey(data, Key.end)) {
        scroll = Number.MAX_SAFE_INTEGER;
        const contentWidth = Math.max(20, tui.terminal.columns - 4);
        const lines = markdown?.render(contentWidth) ?? [];
        const max = Math.max(0, lines.length - maxBody);
        scroll = Math.min(scroll, max);
        tui.requestRender();
      } else {
        input.handleInput(data);
        tui.requestRender();
      }
    },

    render(width: number): string[] {
      const maxBody = maxAnswerBody(tui.terminal.rows);
      const contentWidth = Math.max(20, width - 4);

      const body: string[] = [];

      if (markdown) {
        const mdLines = markdown.render(contentWidth).map((line) =>
          line.includes("__OVERLAY_SEPARATOR__") ? "__OVERLAY_SEPARATOR__" : line,
        );
        // Adaptive body: short answers fill the panel; long ones cap and scroll.
        const { start, end, clampedScroll } = computeScrollWindow(mdLines, scroll, maxBody);
        scroll = clampedScroll;
        const windowLines = mdLines.slice(start, end);
        body.push("");
        for (const line of windowLines) {
          if (line === "__OVERLAY_SEPARATOR__") {
            body.push(style.dim("─".repeat(Math.max(1, width - 4))));
          } else {
            body.push(line);
          }
        }
        body.push("");
      }

      if (state === "loading") {
        for (const line of loader.render(contentWidth)) body.push(line);
        body.push("");
      }

      if (state !== "loading") {
        body.push("");
        for (const line of renderComposer(width - 2)) body.push(line);
        body.push("");
      }

      // Footer
      let footer: string;
      if (state === "loading" && turns.length <= 1) {
        footer = "esc cancel";
      } else {
        const parts: string[] = [];
        if (state === "error") parts.push(style.error("error"));

        let totalTokens = 0;
        let totalCost = 0;
        let totalElapsedMs = 0;
        for (const turn of turns) {
          if (turn.usage) {
            totalTokens += turn.usage.totalTokens;
            totalCost += turn.usage.cost;
          }
          if (turn.elapsedMs !== undefined) {
            totalElapsedMs += turn.elapsedMs;
          }
        }

        if (totalTokens > 0) {
          parts.push(`${totalTokens} tokens · $${totalCost.toFixed(4)}`);
        }
        if (totalElapsedMs > 0) {
          parts.push(`${Math.round(totalElapsedMs / 1000)}s`);
        }
        if (turns.length > 1) {
          parts.push(`${turns.length} turns`);
        }

        if (state === "loading") {
          parts.push("esc cancel · ↑↓ scroll");
        } else {
          parts.push("esc close · enter ask · ↑↓ scroll · pgup/pgdn page · home/end jump");
        }
        footer = parts.join("   ");
      }
      return renderPiPanel({
        width,
        style,
        fit: truncateToWidth,
        title: "btw",
        body,
        footer,
      });
    },

    invalidate() {
      loader.stop();
      markdown?.invalidate();
    },

    dispose() {
      closed = true;
      loader.stop();
      currentAbortController?.abort();
      markdown = undefined;
    },
  };
}
