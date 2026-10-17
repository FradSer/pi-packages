/**
 * A throwaway agent directory for one harness.
 *
 * Goal state lives under Pi's own agent directory, so a harness that does not
 * redirect it writes into the machine's real `~/.pi/agent/goals`. Every harness
 * that builds a store or runs the extension calls this before its first store,
 * so a test run touches no user state.
 *
 * One directory serves the whole harness: each fixture uses its own temporary
 * project root, and the project key keeps those goals apart.
 */

import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const created: string[] = [];

process.on("exit", () => {
  for (const dir of created) rmSync(dir, { recursive: true, force: true });
});

export function isolatedAgentDir(): string {
  const dir = mkdtempSync(join(tmpdir(), "goal-agent-"));
  process.env.PI_CODING_AGENT_DIR = dir;
  created.push(dir);
  return dir;
}