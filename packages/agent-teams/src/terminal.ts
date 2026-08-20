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
  const summary = [input.nodeResult, input.nodeError, input.result.stdout, input.result.stderr]
    .find((value) => value?.trim()) ?? "No worker summary was produced.";
  const worktree = input.patchText ? "\nWorktree diff captured; inspect the node result before integration." : "";
  return `${summary}${worktree}`;
}
