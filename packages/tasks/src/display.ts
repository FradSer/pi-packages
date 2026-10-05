/** Human-readable task labels. Runtime tool names and statuses remain unchanged. */
export const TASK_DISPLAY_LABEL = "tasks";

export function taskStatusText(status: string): string {
  return status.replace(/_/g, " ");
}

export function taskDependencyLines(task: {
  dependsOn: readonly string[];
  blockedBy?: readonly string[];
}): string[] {
  return [
    ...(task.dependsOn.length ? [`depends · ${task.dependsOn.join(", ")}`] : []),
    ...(task.blockedBy?.length ? [`blocked · ${task.blockedBy.join(", ")}`] : []),
  ];
}

export function taskSummaryText(task: {
  subject: string;
  status: string;
  dependsOn: readonly string[];
  blockedBy?: readonly string[];
}): string {
  return [
    `${task.subject} · ${taskStatusText(task.status)}`,
    ...taskDependencyLines(task),
  ].join(" · ");
}
