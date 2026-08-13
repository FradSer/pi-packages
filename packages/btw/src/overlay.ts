/**
 * btw overlay — the interactive popup that hosts the side question.
 *
 * Rendered as a full-width panel anchored to the bottom of the terminal
 * (just above the input box), with height adapting to the content: short
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
  Key,
  Markdown,
  type MarkdownTheme,
  matchesKey,
  truncateToWidth,
  visibleWidth,
  type Component,
  type TUI,
} from "@earendil-works/pi-tui";
import type { BtwUsage } from "./spawner";

export interface BtwOverlayStyle {
  accent: (s: string) => string;
  muted: (s: string) => string;
  dim: (s: string) => string;
  border: (s: string) => string;
  success: (s: string) => string;
  error: (s: string) => string;
  fg: (color: string, text: string) => string;
}

export interface BtwOverlayOptions {
  /** The side question as asked. */
  question: string;
  /** Model label shown in the loading line (optional). */
  modelLabel?: string;
  /** Called when the overlay should close (escape, or cancel while loading). */
  onCancel: () => void;
  /** Called once with the abort signal that kills the child process. */
  onSpawn: (signal: AbortSignal) => void;
}

export interface BtwAnswerMeta {
  usage?: BtwUsage;
  elapsedMs?: number;
}

export interface BtwOverlay extends Component {
  dispose(): void;
  showAnswer(text: string, meta?: BtwAnswerMeta): void;
  showError(text: string): void;
}

type OverlayState = "loading" | "answer" | "error";

/** Cap the answer body at ~40% of the terminal height (adaptive, scrollable). */
export function maxAnswerBody(rows: number): number {
  return Math.max(3, Math.floor(rows * 0.4));
}

/** Build a MarkdownTheme from the overlay style callbacks. */
function buildMarkdownTheme(style: BtwOverlayStyle): MarkdownTheme {
  return {
    heading: (t) => style.accent(t),
    link: (t) => style.accent(t),
    linkUrl: (t) => style.dim(t),
    code: (t) => style.accent(t),
    codeBlock: (t) => t,
    codeBlockBorder: (t) => style.border(t),
    quote: (t) => style.muted(t),
    quoteBorder: (t) => style.border(t),
    hr: (t) => style.dim(t),
    listBullet: (t) => style.accent(t),
    bold: (t) => style.accent(t),
    italic: (t) => style.muted(t),
    strikethrough: (t) => style.dim(t),
    underline: (t) => t,
  };
}

export function createBtwOverlay(
  tui: TUI,
  style: BtwOverlayStyle,
  options: BtwOverlayOptions,
): BtwOverlay {
  const loader = new CancellableLoader(
    tui,
    style.accent,
    style.muted,
    options.modelLabel ? `Answering (read-only, ${options.modelLabel})…` : "Answering (read-only)…",
  );
  loader.onAbort = () => {
    if (!closed) options.onCancel();
  };

  // Kick off the read-only child immediately, wired to the loader's abort signal.
  options.onSpawn(loader.signal);

  const mdTheme = buildMarkdownTheme(style);

  let state: OverlayState = "loading";
  let meta: BtwAnswerMeta | undefined;
  let closed = false;

  let scroll = 0;
  let markdown: Markdown | undefined;

  const setBody = (next: OverlayState, text: string, m?: BtwAnswerMeta) => {
    if (closed) return;
    state = next;
    meta = m;
    scroll = 0;
    if (markdown) {
      markdown.setText(text);
      markdown.invalidate();
    } else {
      markdown = new Markdown(text, 0, 0, mdTheme, undefined, { renderLatex: true });
    }
    loader.stop();
    tui.requestRender();
  };

  const scrollBy = (delta: number, maxBody: number) => {
    const contentWidth = Math.max(20, tui.terminal.columns - 4);
    const lines = markdown?.render(contentWidth) ?? [];
    const max = Math.max(0, lines.length - maxBody);
    const next = Math.max(0, Math.min(max, scroll + delta));
    if (next !== scroll) {
      scroll = next;
      tui.requestRender();
    }
  };

  const pad = (line: string, width: number): string => {
    const visible = visibleWidth(line);
    return visible >= width ? line : line + " ".repeat(width - visible);
  };

  return {
    showAnswer(text: string, m?: BtwAnswerMeta) {
      setBody("answer", text, m);
    },
    showError(text: string) {
      setBody("error", text);
    },

    handleInput(data: string) {
      if (state === "loading") {
        // Escape → loader.onAbort → options.onCancel
        loader.handleInput(data);
        return;
      }
      if (matchesKey(data, Key.escape)) {
        if (!closed) options.onCancel();
        return;
      }
      // SGR mouse wheel (\x1b[<64;col;rowM up / \x1b[<65;col;rowM down).
      // The fullscreen TUI delivers wheel events to a focused overlay's
      // handleInput when it defers viewport scrolling to the overlay.
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
    },

    render(width: number): string[] {
      const maxBody = maxAnswerBody(tui.terminal.rows);
      const contentWidth = Math.max(20, width - 4);

      const border = style.border("─".repeat(Math.max(1, width)));
      const lines: string[] = [];

      // Top border + header
      lines.push(border);
      lines.push(style.accent(truncateToWidth(`btw  ${options.question}`, width)));

      if (state === "loading") {
        lines.push("");
        for (const line of loader.render(contentWidth)) lines.push(pad(line, contentWidth));
        while (lines.length < 2 + 2) lines.push("");
      } else if (markdown) {
        const mdLines = markdown.render(contentWidth);
        // Adaptive body: short answers fill the panel; long ones cap and scroll.
        const viewport = Math.min(mdLines.length, maxBody);
        const max = Math.max(0, mdLines.length - viewport);
        if (scroll > max) scroll = max;
        const windowLines = mdLines.slice(scroll, scroll + viewport);
        lines.push("");
        for (const line of windowLines) lines.push(pad("  " + line, contentWidth));
        if (mdLines.length > maxBody) {
          lines.push(style.dim(`  … ${mdLines.length - maxBody} more lines`));
        }
        lines.push("");
      }

      // Footer
      let footer: string;
      if (state === "loading") {
        footer = "esc cancel";
      } else {
        const parts: string[] = [];
        if (state === "error") parts.push(style.error("error"));
        if (meta?.usage) {
          const u = meta.usage;
          parts.push(`${u.totalTokens} tokens · $${u.cost.toFixed(4)}`);
        }
        if (meta?.elapsedMs !== undefined) parts.push(`${Math.round(meta.elapsedMs / 1000)}s`);
        parts.push("esc close · ↑↓ scroll · pgup/pgdn page · home/end jump");
        footer = parts.join("   ");
      }
      lines.push(style.dim(footer));
      lines.push(border);

      return lines;
    },

    invalidate() {
      loader.stop();
      markdown?.invalidate();
    },

    dispose() {
      closed = true;
      loader.stop();
      markdown = undefined;
    },
  };
}
