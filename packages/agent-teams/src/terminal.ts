export interface NodeTerminalResultInput {
  runId: string;
  nodeId: string;
  agent: string;
  result: {
    stdout: string;
    stderr: string;
    signal: NodeJS.Signals | null;
    timedOut: boolean;
  };
  nodeResult?: string;
  nodeError?: string;
  cancelled: boolean;
  completedAfterShutdown?: boolean;
  patchText: string;
}

export function buildNodeTerminalResult(input: NodeTerminalResultInput): string {
  const status = input.cancelled
    ? "cancelled"
    : input.completedAfterShutdown
      ? "completed"
      : input.result.timedOut
        ? "timed out"
        : input.result.signal
          ? `terminated by ${input.result.signal}`
          : input.nodeError
            ? "failed"
            : "completed";
  const summary = [input.nodeResult, input.nodeError, input.result.stdout, input.result.stderr]
    .find((value) => value?.trim()) ?? "No worker summary was produced.";
  const worktree = input.patchText ? "\nWorktree diff captured; inspect the node result before integration." : "";
  return `Node [${input.runId}/${input.nodeId}] ${status} — agent ${input.agent}.\n${summary}${worktree}`;
}
