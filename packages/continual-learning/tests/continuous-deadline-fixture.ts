import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { installStudyTaskDeadline } from "./continuous-task-deadline.ts";
import unlimitedFixture from "./continuous-unlimited-fixture.ts";

export default function fixture(pi: ExtensionAPI): void {
  const original = globalThis.setTimeout;
  let expire: (() => void) | undefined;
  globalThis.setTimeout = ((fn, ms, ...args) => {
    if (ms === 900_000) expire = () => fn(...args);
    return original(fn, ms, ...args);
  }) as typeof setTimeout;
  installStudyTaskDeadline(pi);
  unlimitedFixture(pi);
  let expired = false;
  pi.on("tool_result", () => {
    if (process.env.STUDY_DEADLINE_EXPIRE_MAIN === "1" && !expired) {
      expired = true;
      expire?.();
    }
  });
  pi.on("agent_settled", () => {
    pi.appendEntry("study-deadline-learner", {stage: "started"});
    // Simulate an already queued main timer while the actual later lifecycle
    // handler owns learning. The completed main deadline must have no authority.
    expire?.();
    pi.appendEntry("study-deadline-learner", {stage: "closed"});
  });
}
