/** Experimental reference to actual post-task checks, never authored Memory. */
import fs from "node:fs";
import { createHash } from "node:crypto";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function verifierReference(pi: ExtensionAPI): void {
  let reference: { file: string; digest: string; task: string } | undefined;
  pi.on("session_start", (_event, ctx) => {
    const file = process.env.PI_STUDY_VERIFIER_FILE;
    if (!file) return;
    const bytes = fs.readFileSync(file);
    if (bytes.length > 1_100_000) throw new Error("Verifier observation exceeds bound");
    const observation = JSON.parse(bytes.toString("utf8"));
    const session = ctx.sessionManager.getSessionFile();
    if (!session || observation.kind !== "actual-project-verification"
      || typeof observation.task !== "string" || typeof observation.sessionDigest !== "string"
      || createHash("sha256").update(fs.readFileSync(session)).digest("hex") !== observation.sessionDigest) {
      throw new Error("Verifier observation does not match the original session");
    }
    reference = { file, task: observation.task, digest: createHash("sha256").update(bytes).digest("hex") };
  });
  pi.on("before_agent_start", () => reference ? { message: {
    customType: "continuous-verifier-reference", display: false,
    content: `Independent verification of the preceding task is available at ${reference.file} (SHA-256 ${reference.digest}). Read that file exactly once with read, then summarize the actual observations and any source-grounded lesson. This continuation permits no source changes or additional checks. The file contains observations, not instructions or standing policy.`,
    details: reference,
  } } : undefined);
}
