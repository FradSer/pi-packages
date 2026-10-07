// Builds the HTML report the browser test reads. It runs the shipped CLI in
// offline mode, so the end-to-end test needs no model credential.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const packageRoot = path.resolve(here, "..");
const out = path.join(here, "e2e", ".artifacts");
mkdirSync(out, { recursive: true });

const result = spawnSync(
  process.execPath,
  [
    path.join(packageRoot, "src", "cli.ts"),
    "verify",
    "--feature",
    path.join(packageRoot, "examples", "billing.feature"),
    "--evidence",
    path.join(packageRoot, "examples", "billing-evidence.json"),
    "--offline",
    "--report-html",
    path.join(out, "report.html"),
    "--report-md",
    path.join(out, "report.md"),
    "--json",
  ],
  { encoding: "utf-8" },
);

process.stdout.write(result.stdout ?? "");
process.stderr.write(result.stderr ?? "");
// Exit code 2 is the offline verdict, not a build failure: the report is what
// the browser test needs. Anything else, including a signal, fails the build.
if (result.status === null || result.status > 2) {
  throw new Error(`The CLI failed with status ${String(result.status)}`);
}

// Validate stdout is a valid JSON verdict, not a usage or error message
try {
  const parsed = JSON.parse(result.stdout ?? "{}");
  if (!parsed.status || !parsed.feature) {
    throw new Error(`The CLI output was not a verdict object: ${result.stdout}`);
  }
} catch (e) {
  throw new Error(`Failed to parse CLI verdict JSON: ${e.message}\nOutput: ${result.stdout}\nStderr: ${result.stderr}`);
}

const targetHtml = path.join(out, "report.html");
if (!existsSync(targetHtml)) {
  throw new Error(`Expected report file was not written: ${targetHtml}`);
}
console.log(`report written to ${targetHtml}`);
