import type { JevJudge } from "../extensions/jev-learning";
/** The production cited path must receive the original plan evidence. */
export function validateHarnessResearch(judge: Pick<JevJudge, "validate">,
  input: { snapshot: unknown; plan: { operations: unknown[]; evidence?: unknown } }) {
  if (!Array.isArray(input.plan.evidence) || !input.plan.evidence.length) throw new Error("Research requires original citations");
  return judge.validate("harness", input.snapshot, input.plan.operations, [], undefined, input.plan.evidence);
}
