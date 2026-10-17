// Real macOS osascript smoke: dialogs are cancelled by deadlines/signals, so
// this never requires a user click and never changes system permissions.
import { isNativeDialogSupported, macosChooseFromList, macosInputDialog, macosPrompt } from "../../src/native-dialog.ts";

const cases = [
  ["list-timeout", () => macosChooseFromList({ prompt: "Pi native smoke timeout", items: ["A", "B"], timeoutSeconds: 0.2 })],
  ["input-timeout", () => macosInputDialog({ prompt: "Pi native smoke timeout", timeoutSeconds: 0.2 })],
  ["prompt-timeout", () => macosPrompt({ message: "Pi native smoke timeout", timeoutSeconds: 0.2 })],
] as const;

if (!isNativeDialogSupported()) {
  console.log(JSON.stringify({ native: "osascript", skipped: true, reason: "requires local macOS with native dialogs enabled" }));
  process.exit(0);
}

for (const [name, run] of cases) {
  const start = performance.now();
  const result = await run();
  const elapsedMs = Math.round(performance.now() - start);
  if (elapsedMs > 1000 || result.action !== "timed_out" || (name === "prompt-timeout" && (!("gaveUp" in result) || result.gaveUp !== true))) {
    throw new Error(`${name} did not produce the expected bounded timeout: ${JSON.stringify({ result, elapsedMs })}`);
  }
  console.log(JSON.stringify({ name, result, elapsedMs, passed: true }));
}

const controller = new AbortController();
setTimeout(() => controller.abort(), 0.1 * 1000);
const start = performance.now();
const result = await macosChooseFromList({ prompt: "Pi native smoke abort", items: ["A", "B"], timeoutSeconds: 10, signal: controller.signal });
const elapsedMs = Math.round(performance.now() - start);
if (elapsedMs > 1000 || result.action !== "cancelled") {
  throw new Error(`list-abort did not cleanly cancel: ${JSON.stringify({ result, elapsedMs })}`);
}
console.log(JSON.stringify({ name: "list-abort", result, elapsedMs, passed: true }));
