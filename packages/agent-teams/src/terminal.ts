export interface TerminalResultInput {
  taskId: string;
  teammate: string;
  result: {
    stdout: string;
    stderr: string;
    signal: NodeJS.Signals | null;
    timedOut: boolean;
  };
  taskResult?: string;
  taskError?: string;
  cancelled: boolean;
  patchText: string;
}

export function buildTerminalResult(input: TerminalResultInput): string {
  const status = input.cancelled
    ? "cancelled"
    : input.result.timedOut
      ? "timed out"
      : input.result.signal
        ? `terminated by ${input.result.signal}`
        : input.taskError
          ? "failed"
          : "completed";
  const summary = [input.taskResult, input.taskError, input.result.stdout, input.result.stderr]
    .find((value) => value?.trim()) ?? "No worker summary was produced.";
  const worktree = input.patchText ? "\nWorktree diff captured; inspect the task result before integration." : "";
  return `Task [${input.taskId}] ${status} — teammate ${input.teammate}.\n${summary}${worktree}`;
}
