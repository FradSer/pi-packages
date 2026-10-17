/** Study-only main-task deadline. Load before learning's agent_settled handler. */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export function installStudyTaskDeadline(pi: ExtensionAPI, limitMs = 900_000): void {
  let state: "idle" | "active" | "settled" | "expired" | "shutdown" = "idle";
  let timer: ReturnType<typeof setTimeout> | undefined;
  let started = 0;
  const record = () => pi.appendEntry("continuous-study-task-deadline", {
    stage: state === "active" ? "started" : state, limitMs, elapsedMs: Math.round(performance.now() - started),
  });
  const close = (next: "settled" | "shutdown") => {
    if (state !== "active") return;
    state = next;
    clearTimeout(timer);
    timer = undefined;
    record();
  };
  pi.on("before_agent_start", (_event, ctx) => {
    if (state !== "idle") return;
    state = "active";
    started = performance.now();
    record();
    timer = setTimeout(() => {
      if (state !== "active") return;
      state = "expired";
      clearTimeout(timer);
      timer = undefined;
      record();
      ctx.abort();
    }, limitMs);
  });
  // Automatic learning also runs on agent_settled. Registration order ensures
  // its existing independent bounds begin after the main task timer is closed.
  pi.on("agent_settled", () => close("settled"));
  pi.on("session_shutdown", () => close("shutdown"));
  pi.on("tool_call", () => state === "expired"
    ? {block: true, reason: "The study main task deadline expired."} : undefined);
}

export default function studyTaskDeadline(pi: ExtensionAPI): void {
  installStudyTaskDeadline(pi);
}
