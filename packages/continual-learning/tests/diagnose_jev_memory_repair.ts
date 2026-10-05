/** Actual worker + Jev inference over an unchanged public native rejection.
 * This checks correction, not application or a paired end-to-end workflow.
 */
import fs from "node:fs/promises";
import {createJevJudge} from "../extensions/jev-learning";
import {repairIncrementalMemoryPlan} from "../extensions/inject-memory";

const artifact = "jev-sparse-native-en-first-complete.json";
const report = JSON.parse(await fs.readFile(new URL(artifact, import.meta.url), "utf8"));
const run = report.runs.find((r: {enabled: boolean}) => r.enabled);
const original = run.plans.find((p: {newMemories: Array<{name: string}>}) => p.newMemories.some(m => m.name === "team_glossary.md"));
const frozen = run.snapshots.find((s: {runId: string}) => s.runId === original.runId);
if (!frozen) throw new Error("Missing archived frozen evidence");
const identity = {runId:original.runId,scopeKey:original.scopeKey,scopeDigest:original.scopeDigest,artifactHash:original.artifactHash,snapshotDigest:original.snapshotDigest};
const rejectedPlan = {kind:"incremental-memory-plan",version:1,schemaVersion:1,...identity,operations:original.operations,newMemories:original.newMemories};
const judge = createJevJudge({enabled:true,defaultModel:"jev-1.13.0"});
const before = await judge.validate("memory", frozen, original.newMemories, []);
const repair = await repairIncrementalMemoryPlan({rejectedPlan, errors:["Semantic verification: unsupported inferences about a maintained glossary and contextual consistency. Retain the exact naming relationship and entrypoint supported by the frozen evidence."],selectedNames:[],identity,model:`${run.provider}/${run.model}`,semanticContext:{frozenEvidence:frozen,existingMemories:[]}});
const corrected = repair.plan as {newMemories: unknown[]} | undefined;
const after = corrected ? await judge.validate("memory", frozen, corrected.newMemories, []) : undefined;
console.log(JSON.stringify({evidence:"real-worker-and-jev-over-archived-native-candidate",sourceArtifact:artifact,applicationVerified:false,before,repair,after},null,2));
