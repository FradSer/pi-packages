/**
 * pi-loop — repeat one message into this session on a schedule.
 *
 * /loop <request> parses the request, schedules a repeating injection, and
 * delivers each repetition through pi.sendUserMessage, so every repetition is a
 * real user turn in the transcript and in the model context.
 *
 * Two input forms:
 *   1. Explicit flags. Every parameter is written out, so no model is called:
 *      /loop --every 5m --times 3 check the build
 *   2. Free natural language. The cadence, the run limit, the stopping condition
 *      and the repeated text are chosen by TypeSafe Jev decisions over candidates
 *      that this code builds. No step asks a model to write the message.
 *
 * Lifecycle: one loop per session. A tick whose previous injection has not
 * settled is skipped, never queued. Stopping releases the only timer.
 */

import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { keyHint } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import {
  bindLifecycleRenderers,
  clearPiStatus,
  extractTextContent,
  notifyPi,
  safeDisplayText,
  setPiStatus,
  startedToolLifecycle,
} from "@fradser/pi-kit";
import { readDecisionConfig } from "./config.ts";
import { PlanDecisionError, judgeStopCondition, resolveSemanticPlan } from "./decide.ts";
import { formatDuration } from "./duration.ts";
import { parseParameterized } from "./params.ts";
import { LoopRunner, nodeTimers } from "./scheduler.ts";
import type { LoopPlan, ResolvedLoop } from "./types.ts";

const PROCEDURE_ENTRY = "loop-lifecycle";
const NOTICE_ENTRY = "loop-notice";
const STATUS_KEY = "loop";
/** Bound the text sent for one stopping judgment. */
const MAX_JUDGED_CHARS = 8000;

const loopRows = bindLifecycleRenderers({
  fit: truncateToWidth,
  visibleWidth,
  wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
  expandHint: () => keyHint("app.tools.expand", "to expand"),
});

const USAGE = [
  "Usage:",
  "  /loop --every 5m [--times 3] [--until \"condition\"] [--message \"text\"] [text]",
  "  /loop <free request>",
  "  /loop status",
  "  /loop stop",
].join("\n");

/** One row that names the loop without dumping its text into the transcript. */
function planSummary(plan: LoopPlan): string {
  const parts = ["every " + formatDuration(plan.intervalMs)];
  if (plan.maxRuns !== undefined) parts.push(plan.maxRuns === 1 ? "once" : plan.maxRuns + " times");
  else if (plan.until !== undefined) parts.push("until " + plan.until);
  else parts.push("until stopped");
  parts.push(safeDisplayText(plan.message));
  return parts.join(" · ");
}

/** The last assistant message in a finished run, or an empty string. */
function lastAssistantTextFrom(messages: readonly unknown[]): string {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message === null || typeof message !== "object") continue;
    const record = message as { role?: unknown; content?: unknown };
    if (record.role !== "assistant") continue;
    const text = extractTextContent(record.content).trim();
    if (text) return text;
  }
  return "";
}

/** Report to the user, with a transcript notice when no dialog UI exists. */
function feedback(pi: ExtensionAPI, ctx: ExtensionCommandContext, text: string, level: "info" | "warning" | "error"): void {
  const content = safeDisplayText(text);
  if (ctx.hasUI) {
    ctx.ui.notify(content, level);
    return;
  }
  pi.sendMessage({ customType: NOTICE_ENTRY, content, display: true }, { triggerTurn: false });
}

export function registerLoop(pi: ExtensionAPI): void {
  let runner: LoopRunner | undefined;
  let config = readDecisionConfig();
  let ui: ExtensionContext["ui"] | undefined;
  let lastAssistantText = "";
  let judging = false;

  /**
   * The below-editor row, read as `<verb> · <detail>`. The verb already names
   * the loop, so the value carries no package tag.
   */
  const statusValue = (): string | undefined => {
    if (runner === undefined || !runner.active) return undefined;
    const progress = runner.plan.maxRuns === undefined
      ? runner.injections + " sent"
      : runner.injections + "/" + runner.plan.maxRuns;
    const skipped = runner.skipped > 0 ? " · " + runner.skipped + " skipped" : "";
    return "Looping · every " + runner.intervalLabel + " · " + progress + skipped;
  };

  const publish = (): void => {
    if (ui === undefined) return;
    const value = statusValue();
    if (value === undefined) clearPiStatus(ui, STATUS_KEY);
    else setPiStatus(ui, STATUS_KEY, value);
  };

  /** The command report, which must also answer when no loop runs. */
  const statusReport = (): string => statusValue() ?? "No loop is running.";

  const announce = (resolved: ResolvedLoop): void => {
    const plan = resolved.plan;
    const limits = plan.maxRuns !== undefined
      ? " Repetitions: " + plan.maxRuns + "."
      : plan.until !== undefined
        ? " Stopping condition: " + plan.until + "."
        : " It runs until the user stops it.";
    const content = "The user started a repeating loop. Each repetition arrives as a separate user turn. Message: "
      + plan.message + ". Cadence: every " + formatDuration(plan.intervalMs) + "." + limits
      + " Stop it with /loop stop.";
    const details = {
      subject: planSummary(plan),
      message: plan.message,
      interval: formatDuration(plan.intervalMs),
      runs: plan.maxRuns ?? null,
      until: plan.until ?? null,
      mode: resolved.mode,
      model: resolved.report?.model ?? null,
      inputTokens: resolved.report?.inputTokens ?? 0,
      confidence: resolved.report
        ? {
            interval: resolved.report.interval.confidence,
            runs: resolved.report.runs.confidence,
            stop: resolved.report.stop.confidence,
            message: resolved.report.message?.confidence ?? null,
          }
        : null,
    };
    pi.sendMessage({ customType: PROCEDURE_ENTRY, content, display: true, details }, { triggerTurn: false });
  };

  const start = (resolved: ResolvedLoop): void => {
    let created: LoopRunner;
    try {
      created = new LoopRunner({
        plan: resolved.plan,
        timers: nodeTimers(),
        send: (text) => pi.sendUserMessage(text, { deliverAs: "followUp" }),
        onEvent: (event) => {
          if (event.type !== "stopped") {
            publish();
            return;
          }
          if (ui !== undefined) clearPiStatus(ui, STATUS_KEY);
          const injections = event.injections + (event.injections === 1 ? " injection" : " injections");
          const skipped = event.skipped > 0 ? ", " + event.skipped + " skipped while busy" : "";
          if (ui !== undefined) notifyPi(ui, "loop: stopped after " + injections + skipped + " (" + event.reason + ")", "info");
        },
      });
    } catch (error) {
      // A rejected plan is a report, never a throw out of the command.
      if (ui !== undefined) {
        notifyPi(ui, "loop: " + (error instanceof Error ? error.message : String(error)), "error");
      }
      return;
    }
    runner = created;
    created.start();
    announce(resolved);
    publish();
  };

  /**
   * Ask the decision service whether the stopping condition is met. The loop
   * continues on any failure: a service fault must never end the user's work.
   */
  const evaluateStop = async (active: LoopRunner): Promise<void> => {
    const condition = active.plan.until;
    if (condition === undefined || !active.active || judging) return;
    const text = lastAssistantText.trim();
    if (!text) return;
    const activeConfig = config;
    if (activeConfig === undefined) return;
    judging = true;
    try {
      const verdict = await judgeStopCondition({
        config: activeConfig,
        condition,
        lastAssistantMessage: text.slice(0, MAX_JUDGED_CHARS),
      });
      if (verdict.met && runner === active && active.active) active.stop("condition");
    } catch (error) {
      const failure = error instanceof PlanDecisionError ? error.failure : "unreachable";
      if (ui !== undefined) notifyPi(ui, "loop: the stopping judgment failed (" + failure + "); the loop continues.", "warning");
    } finally {
      judging = false;
    }
  };

  pi.on("agent_end", (event) => {
    if (runner === undefined || !runner.active) return;
    lastAssistantText = lastAssistantTextFrom(event.messages);
  });

  pi.on("agent_settled", () => {
    const active = runner;
    if (active === undefined || !active.active) return;
    active.markSettled();
    void evaluateStop(active);
  });

  pi.on("session_start", () => {
    config = readDecisionConfig();
    runner?.stop("shutdown");
    runner = undefined;
    lastAssistantText = "";
  });

  pi.on("session_shutdown", () => {
    runner?.stop("shutdown");
    runner = undefined;
    if (ui !== undefined) clearPiStatus(ui, STATUS_KEY);
  });

  pi.registerCommand("loop", {
    description:
      "Repeat one message into this session on a schedule, with explicit flags or a free request: /loop --every 5m check the build",
    handler: async (args, ctx) => {
      ui = ctx.ui;
      config = readDecisionConfig();
      const request = args.trim();
      const control = request.toLowerCase();

      if (!request || control === "status") {
        feedback(pi, ctx, statusReport() + "\n" + USAGE, "info");
        return;
      }
      if (control === "stop" || control === "cancel") {
        if (runner === undefined || !runner.active) {
          feedback(pi, ctx, "loop: no loop is running.", "info");
          return;
        }
        runner.stop("user");
        return;
      }
      if (runner !== undefined && runner.active) {
        feedback(pi, ctx, "loop: a loop is already running. Run /loop stop first.", "warning");
        return;
      }

      const parsed = parseParameterized(request);
      if (parsed.kind === "invalid") {
        feedback(pi, ctx, "loop: " + parsed.error + "\n" + USAGE, "error");
        return;
      }
      if (parsed.kind === "plan") {
        if (parsed.plan.until !== undefined && config === undefined) {
          feedback(pi, ctx, "loop: --until needs a decision credential (TYPESAFE_API_KEY), because Pi judges the condition after each turn.", "error");
          return;
        }
        start({ plan: parsed.plan, mode: "parameterized" });
        return;
      }

      if (config === undefined) {
        feedback(pi, ctx, "loop: a free request needs a decision credential. Set TYPESAFE_API_KEY, or state the schedule with flags, for example: /loop --every 5m " + request, "error");
        return;
      }

      let resolved: ResolvedLoop;
      try {
        resolved = await resolveSemanticPlan(request, { config });
      } catch (error) {
        const detail = error instanceof PlanDecisionError
          ? error.message + " (" + error.failure + ")"
          : "the decision request failed: " + (error instanceof Error ? error.message : String(error));
        feedback(pi, ctx, "loop: " + detail + "\n" + USAGE, "error");
        return;
      }
      start(resolved);
    },
  });

  if (typeof pi.registerMessageRenderer === "function") {
    pi.registerMessageRenderer(PROCEDURE_ENTRY, (message, { expanded }, theme) => {
      const details = (message.details ?? {}) as { subject?: string };
      const subject = safeDisplayText(details.subject ?? "loop");
      return loopRows.message(() => startedToolLifecycle("loop", subject, { label: "started" }))(
        message,
        { expanded },
        theme,
      );
    });
  }
}

export default registerLoop;
