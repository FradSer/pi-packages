/** Offline audit of hash-bound actual generated candidates. No new inference or writes. */
import fs from "node:fs/promises";
import { createHash } from "node:crypto";
import { validateHarnessPlan } from "../extensions/harness-consolidation";
import { createJevJudge } from "../extensions/jev-learning";
interface Input { id: string; proposal: string; snapshot: string; report: string; proposalHash: string; snapshotHash: string; reportHash: string }
const inputs: Input[] = JSON.parse(await fs.readFile(new URL("./jev-actual-generated-risk-manifest.json", import.meta.url), "utf8"));
const rows = [];
for (const input of inputs) {
  const texts = await Promise.all([fs.readFile(input.proposal, "utf8"), fs.readFile(input.snapshot, "utf8"), fs.readFile(input.report, "utf8")]);
  for (const [i, expected] of [input.proposalHash, input.snapshotHash, input.reportHash].entries()) {
    if (createHash("sha256").update(texts[i]).digest("hex") !== expected) throw new Error("Frozen actual generation changed");
  }
  const proposal = JSON.parse(texts[0]).proposal, snapshot = JSON.parse(texts[1]), report = JSON.parse(texts[2]);
  const errors = validateHarnessPlan(proposal, { snapshot, automatic: true, availableSkills: [] });
  let outboundRequests = 0;
  const disabled = createJevJudge({ enabled: false, fetch: async () => { outboundRequests++; throw new Error("Offline audit must not transport"); } });
  const baseline = await disabled.validate("harness", snapshot, proposal.operations, [], undefined, proposal.evidence);
  const quoteOnly = "printf '%s' 'x;git push --dry-run'";
  const observedRisks = input.id === "quoted-compound-overmatch"
    ? { printsOnlyButMatcherMatches: new RegExp(proposal.operations[0].rule.bash).test(quoteOnly) }
    : { python3ActuallyPresent: typeof report.runtime?.python === "string" && report.runtime.python.startsWith("Python 3."), python3CoveredByClaimedMissingInterpreterRule: new RegExp(proposal.operations[1].rule.bash).test("python3 -m pytest -q") };
  rows.push({ ...input, structuralErrors: errors, withoutSemanticGate: baseline,
    actualOutcome: report.status, actualStage: report.stage, actualHarnessJudgments: report.jevJudgments.filter((item: { stage: string }) => item.stage === "harness"), observedRisks, outboundRequests });
}
console.log(JSON.stringify({ evidence: "offline-audit-of-real-generated-candidates-and-real-receipts", actualInferenceReplayed: false, productionWriteEligible: false,
  comparisonLimit: "Structure/evidence candidate gate versus retained actual Jev receipt; no baseline mutation, no regeneration and no claim of whole-workflow superiority", rows }, null, 2));
if (rows.some(row => row.outboundRequests || row.structuralErrors.length || Object.values(row.observedRisks).some(value => !value))) process.exitCode = 1;
