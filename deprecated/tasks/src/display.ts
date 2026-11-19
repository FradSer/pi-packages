/** Human-readable task labels. Runtime tool names and statuses remain unchanged. */
export const TASK_DISPLAY_LABEL = "tasks";

export interface TaskDisplayRecord {
  id: string;
  subject: string;
}

export type TaskDisplayIndex = ReadonlyMap<string, { number: number; subject: string }>;

/** Number tasks in the store's public list order. These are display references;
 *  storage ids stay in the model-facing tool contract. */
export function taskDisplayIndex(tasks: readonly TaskDisplayRecord[]): TaskDisplayIndex {
  const index = new Map<string, { number: number; subject: string }>();
  for (const task of tasks) {
    if (index.has(task.id)) continue;
    index.set(task.id, { number: index.size + 1, subject: task.subject });
  }
  return index;
}

export function taskDisplayReference(id: string, index: TaskDisplayIndex): string {
  const task = index.get(id);
  return task ? `${task.subject} #${task.number}` : "unknown task";
}

export function taskDisplayNumber(id: string, index: TaskDisplayIndex): string {
  const task = index.get(id);
  return task ? `#${task.number}` : "unknown task";
}

export function taskStatusText(status: string): string {
  return status.replace(/_/g, " ");
}

export function taskDisplayHeading(
  task: { id: string; subject: string; status: string },
  index: TaskDisplayIndex,
): string {
  const number = index.get(task.id)?.number;
  return `${number ? `#${number} ` : ""}${task.subject} (${taskStatusText(task.status)})`;
}

export function taskDependencyLines(
  task: { dependsOn: readonly string[] },
  index: TaskDisplayIndex,
): string[] {
  if (task.dependsOn.length === 0) return [];
  const references = task.dependsOn.map(id => taskDisplayNumber(id, index));
  return [`Depends on ${references.join(", ")}`];
}

export function taskBlockedByLines(
  task: { blockedBy?: readonly string[] },
  index: TaskDisplayIndex,
): string[] {
  if (!task.blockedBy?.length) return [];
  const references = task.blockedBy.map(id => taskDisplayNumber(id, index));
  return [`Blocked by ${references.join(", ")}`];
}

/** The concise relationship line shared by collapsed and settlement summaries. */
export function taskRelationText(dependencies: readonly string[], blockedBy: readonly string[] = []): string {
  return [
    ...(dependencies.length ? [`Depends on ${dependencies.join(", ")}`] : []),
    ...(blockedBy.length ? [`Blocked by ${blockedBy.join(", ")}`] : []),
  ].join("; ");
}

export function taskRelationSummary(
  task: { dependsOn: readonly string[]; blockedBy?: readonly string[] },
  index: TaskDisplayIndex,
): string {
  return taskRelationText(
    task.dependsOn.map(id => taskDisplayNumber(id, index)),
    (task.blockedBy ?? []).map(id => taskDisplayNumber(id, index)),
  );
}

export function taskSummaryLines(
  task: {
    id: string;
    subject: string;
    status: string;
    dependsOn: readonly string[];
    blockedBy?: readonly string[];
    supersededBy?: string;
    replacementUnresolved?: boolean;
    blockedReason?: string;
  },
  index: TaskDisplayIndex,
): string[] {
  const relations = taskRelationSummary(task, index);
  return [
    `${taskDisplayHeading(task, index)}${relations ? ` · ${relations}` : ""}${task.supersededBy ? ` · Replaced by ${taskDisplayNumber(task.supersededBy, index)}` : ""}`,
    ...(task.replacementUnresolved ? ["Replacement target unresolved; history is inactive."] : []),
    ...(task.blockedReason ? [`Blocker: ${task.blockedReason}`] : []),
  ];
}
