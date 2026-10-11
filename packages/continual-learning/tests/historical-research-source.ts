/** Historical studies retain their certified source hashes. Unit transport and
 * forged-policy probes read verified pre-audit bytes; runtime tests use current
 * code. These snapshots do not certify the repaired runtime's model efficacy. */
const frozen = new Set([
  "guardrails.ts", "output-checks.ts", "harness-guidance.ts",
  "agents-md-consolidation.ts", "consolidation-run.ts", "guardrail-config.ts",
  "harness-consolidation.ts", "harness-menu.ts", "learning-controls.ts",
  "memory-files.ts", "memory-menu.ts", "memory-paths.ts", "planner-prompts.ts",
  "learning-history.ts", "incremental-memory-plan.ts", "incremental-learning.ts",
  "automatic-learning.ts", "learning-backlog.ts", "learning-input.ts",
]);
export function historicalResearchPath(file: string | URL): string | URL {
  const value = String(file);
  const name = value.split("/").at(-1)!;
  if ((value.includes("/extensions/") && frozen.has(name)) || value.endsWith("/pnpm-lock.yaml")) {
    return new URL(`./fixtures/audit-preintegration/${name}`, import.meta.url);
  }
  return file;
}
