/** Research-only generation checks; no apply or mutation API is imported. */
import {createHash} from 'node:crypto';
import {normalizeNewMemoryProposals,validatePlanIdentity,type NewMemoryProposal} from '../extensions/consolidation-run';
import type {SelectedMemory} from '../extensions/incremental-learning';

export const DURABLE_CORE_CLARIFICATION = 'Separate durable facts from incidental run narrative in each original candidate. Prefer verified stable configuration or a lasting user statement. Omit counts, errors and recovery details only when incidental. Preserve explicitly requested historical results, exact versions/counts, useful verified diagnostic history with established future relevance, ongoing compatibility conditions, later corrections, duration, permission exceptions and private sharing exclusions. If no stable fact is supported, do not invent a durable fact. Preserve each name, kind, operation, privacy classification and original (index, quote) citations; do not omit candidates. Keep description and body consistent; cleaner wording is not new evidence.';

export interface DurableCoreCase {
  id: string; scenario: string; language: 'en' | 'zh';
  identity: {runId: string; scopeKey: string; scopeDigest: string; artifactHash: string; snapshotDigest: string};
  snapshot: unknown; existingMemories: SelectedMemory[]; rejectedPlan: unknown;
  errors: string[]; expectedRequirements: string[];
}
const hash = (value: unknown): string => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);

function frontmatter(content: unknown): Map<string, string> | undefined {
  if (typeof content !== 'string') return;
  const text = /^---\r?\n([\s\S]*?)\r?\n---\r?\n/.exec(content)?.[1];
  if (!text) return;
  const fields = new Map<string, string>();
  for (const line of text.split(/\r?\n/)) {
    const match = /^(name|description|type):[ \t]*(.+)$/.exec(line);
    if (!match || fields.has(match[1])) return;
    fields.set(match[1], match[2].trim());
  }
  return fields.size === 3 ? fields : undefined;
}

export function checkDurableCoreRepair(plan: unknown, input: DurableCoreCase):
  {category: 'ready'; candidates: NewMemoryProposal[]} | {category: 'rejected'} {
  try {
    if (!record(plan) || !record(input.snapshot) || !record(input.rejectedPlan)
      || hash(input.snapshot) !== input.identity.snapshotDigest
      || input.snapshot.runId !== input.identity.runId || input.snapshot.scopeKey !== input.identity.scopeKey
      || validatePlanIdentity(plan, input.identity).length
      || plan.scopeKey !== input.identity.scopeKey || plan.snapshotDigest !== input.identity.snapshotDigest
      || plan.kind !== 'incremental-memory-plan' || plan.version !== 1 || plan.schemaVersion !== 1
      || !Array.isArray(plan.operations) || plan.operations.length !== 0
      || Object.keys(plan).some(key => !['kind','version','schemaVersion','runId','scopeKey','scopeDigest','artifactHash','snapshotDigest','operations','newMemories'].includes(key))) {
      return {category: 'rejected'};
    }
    const originals = input.rejectedPlan.newMemories;
    if (!Array.isArray(originals) || !Array.isArray(plan.newMemories) || plan.newMemories.length !== originals.length) return {category: 'rejected'};
    for (let i = 0; i < originals.length; i++) {
      const prior = originals[i], candidate = plan.newMemories[i];
      if (!record(prior) || !record(candidate)
        || Object.keys(candidate).some(key => !['name','kind','classification','content','evidence'].includes(key))
        || candidate.name !== prior.name || candidate.kind !== prior.kind || candidate.classification !== prior.classification
        || !Array.isArray(prior.evidence) || !Array.isArray(candidate.evidence) || candidate.evidence.length !== prior.evidence.length) return {category: 'rejected'};
      for (let j = 0; j < prior.evidence.length; j++) {
        const before = prior.evidence[j], after = candidate.evidence[j];
        if (!record(before) || !record(after) || Object.keys(after).some(key => !['index','quote'].includes(key))
          || after.index !== before.index || after.quote !== before.quote) return {category: 'rejected'};
      }
      const before = frontmatter(prior.content), after = frontmatter(candidate.content);
      if (!before || !after || before.get('name') !== after.get('name') || before.get('type') !== after.get('type')
        || !after.get('description') || after.get('description')!.length > 120) return {category: 'rejected'};
    }
    const original = normalizeNewMemoryProposals(input.rejectedPlan, input.snapshot);
    const candidates = normalizeNewMemoryProposals(plan, input.snapshot);
    if (candidates.length !== original.length || candidates.some((candidate, i) => {
      const prior = original[i];
      // This bounded study compares exactly the original order and identities.
      return candidate.name !== prior.name || candidate.kind !== prior.kind || candidate.classification !== prior.classification;
    })) return {category: 'rejected'};
    return {category: 'ready', candidates};
  } catch {
    // Controlled classification only: never leak model output or private text.
    return {category: 'rejected'};
  }
}

export function validDurableCoreFreezeSet(hashes: Record<string, string>, required: readonly string[]): boolean {
  return required.length > 0 && required.every(file => Object.hasOwn(hashes,file))
    && Object.entries(hashes).every(([file,digest]) =>
      (file.startsWith('/opt/experiment/') || file === '/home/node/research/cases.json')
      && !file.split('/').some(part => part === '..' || part === '.')
      && /^[a-f0-9]{64}$/.test(digest));
}
