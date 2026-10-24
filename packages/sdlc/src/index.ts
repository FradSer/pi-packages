import * as fs from "node:fs";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { notifyPi } from "@fradser/pi-kit";
import { recordLifecycle, type Lifecycle } from "./records.ts";
import { registerPlaybook } from "./playbook.ts";

interface Run {
  identity: string;
  cwd: string;
  prompt?: string;
  recordingError: boolean;
  modelError: boolean;
}

interface SessionState {
  active?: Run;
  managed: boolean;
  pending: { run?: Run; generated: boolean }[];
}

export default function sdlc(pi: ExtensionAPI): void {
  registerPlaybook(pi);
  const workflow = fs.readFileSync(new URL("../references/workflow.md", import.meta.url), "utf8");
  const templates = {
    intent: fs.readFileSync(new URL("../templates/INTENT.md", import.meta.url), "utf8"),
    handoff: fs.readFileSync(new URL("../templates/HANDOFF.md", import.meta.url), "utf8"),
  };
  const sessions = new Map<string, SessionState>();
  const sessionKey = (ctx: ExtensionContext): string => JSON.stringify([ctx.sessionManager.getSessionId(), ctx.cwd]);
  const stateFor = (ctx: ExtensionContext): SessionState => {
    const key = sessionKey(ctx);
    let state = sessions.get(key);
    if (!state) { state = { managed: false, pending: [] }; sessions.set(key, state); }
    return state;
  };
  const instance = randomUUID();
  let sequence = 0;
  const report = (ctx: ExtensionContext, error: unknown): string => {
    const message = `SDLC recording failed: ${error instanceof Error ? error.message : String(error)}`;
    if (ctx.hasUI) notifyPi(ctx.ui, message, "error");
    else console.error(message);
    return message;
  };
  const newRun = (ctx: ExtensionContext, prompt?: string): Run => ({
    identity: `${ctx.sessionManager.getSessionId()}:${instance}:${++sequence}`, cwd: ctx.cwd,
    prompt, recordingError: false, modelError: false,
  });
  const start = (run: Run, ctx: ExtensionContext): string => {
    try {
      recordLifecycle(run.cwd, run.identity, "started", templates, run.prompt);
      run.recordingError = false;
      return "";
    } catch (error) {
      run.recordingError = true;
      return report(ctx, error);
    }
  };
  const finish = (ctx: ExtensionContext, lifecycle: Lifecycle): void => {
    const state = stateFor(ctx);
    const run = state.active;
    state.active = undefined;
    state.pending = [];
    if (!run) return;
    try { recordLifecycle(run.cwd, run.identity, lifecycle, templates); }
    catch (error) { report(ctx, error); }
  };

  pi.on("session_start", (_event, ctx) => {
    sessions.set(sessionKey(ctx), { managed: false, pending: [] });
  });
  // Capture actual input before host expansion, including steering delivered inside a run.
  pi.on("input", (event, ctx) => {
    const state = stateFor(ctx);
    if (!event.streamingBehavior) state.pending = [];
    if (event.source === "extension") {
      if (event.streamingBehavior !== "steer") state.pending.push({ generated: true });
      return;
    }
    const run = newRun(ctx, event.text);
    state.managed = true;
    start(run, ctx);
    if (state.active && run.recordingError) state.active.recordingError = true;
    if (event.streamingBehavior !== "steer") {
      state.pending.push({ run, generated: false });
      if (!state.active) state.active = run;
    }
  });
  pi.on("before_agent_start", (event, ctx) => {
    const options = event.systemPromptOptions;
    if (!("sections" in options) || !options.sections || typeof options.sections !== "object" || Array.isArray(options.sections)) {
      throw new Error("SDLC requires Pi structured prompt sections");
    }
    Reflect.deleteProperty(options.sections, "sdlc");
    const state = stateFor(ctx);
    const input = event.messageType === "user" ? state.pending.shift() : undefined;
    const user = event.messageType === "user" && !input?.generated;
    if (!user && !state.managed) return;
    state.managed = true;
    // SDK user runs without an input event fall back to the submitted user prompt.
    const run = input?.run ?? newRun(ctx, event.messageType === "user" && user ? event.prompt : undefined);
    state.active = run;
    const failure = start(run, ctx);
    Object.assign(options.sections, { sdlc: `Packaged SDLC references: ${fileURLToPath(new URL("../references/", import.meta.url))}.
${workflow}\n\nRequired INTENT.md template:\n\n${templates.intent}\n\nRequired HANDOFF.md template:\n\n${templates.handoff}${failure ? `\n\nRecording failure: ${failure}\nDo not claim the task records were saved.\n` : ""}` });
  });
  pi.on("message_end", (event, ctx) => {
    const active = stateFor(ctx).active;
    if (active && event.message.role === "assistant") {
      if (event.message.stopReason === "error") active.modelError = true;
      else if (event.message.stopReason === "stop") active.modelError = false;
    }
  });
  // agent_end may precede recovery or queued work. Settlement is the final boundary.
  pi.on("agent_settled", (event, ctx) => {
    const active = stateFor(ctx).active;
    finish(ctx, event.aborted ? "interrupted" : active?.recordingError || active?.modelError ? "error" : "ended");
  });
  pi.on("session_shutdown", (_event, ctx) => {
    finish(ctx, "interrupted"); sessions.delete(sessionKey(ctx));
  });
}
