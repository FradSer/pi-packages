/** Research only: flatten validated targets, without extracting facts or granting writes. */
import {noul, type Questions} from '@typesafe-ai/sdk';
import {requestCompletenessQuestions, type FrozenRequirement} from './request-completeness-research.ts';

export function focusedRequirementQuestions(snapshot: unknown, requirements: readonly FrozenRequirement[], resultingMemoryContents: readonly string[]): Questions {
  const baseline = requestCompletenessQuestions(snapshot, requirements, resultingMemoryContents);
  const entries = (snapshot as {entries: {content: string}[]}).entries;
  const questions: Questions = {};
  for (const [index, requirement] of requirements.entries()) {
    const original = baseline[`preserved_${index}`];
    if (original.type !== 'noul' || original.instructions === null || typeof original.instructions !== 'object'
      || Array.isArray(original.instructions) || typeof original.instructions.question !== 'string') {
      throw Error('Unexpected requirement question contract');
    }
    questions[`preserved_${index}`] = noul({
      question: original.instructions.question.replaceAll('requirement.quote', 'requestedFragment'),
      requestedFragment: requirement.quote,
      originalUserEntry: entries[requirement.index].content,
      resultingMemoryContents: [...resultingMemoryContents],
    }, original.criteria);
  }
  return questions;
}
