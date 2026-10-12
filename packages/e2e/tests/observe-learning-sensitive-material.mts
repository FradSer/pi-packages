/** Fresh observations for the learning-controls sensitive-material scenario.
 * A passing linked suite is not clause evidence: this producer drives the real
 * detector and the real history writer in a disposable agent root, so an
 * ordinary configuration literal stays ordinary while a real credential is
 * still refused and never echoed. */
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = await mkdtemp(path.join(tmpdir(), "e2e-learning-sensitive-"));
// Isolation is a test condition: the real agent root is never touched.
process.env.PI_CODING_AGENT_DIR = path.join(root, "agent");
const cwd = path.join(root, "project");
const target = path.join(cwd, "AGENTS.md");

try {
  await mkdir(cwd, { recursive: true });
  const { containsSensitiveMemoryMaterial } = await import("../../continual-learning/extensions/consolidation-run.ts");
  const { recordLearningMutation, recordLearningProposal, listLearningHistory } = await import("../../continual-learning/extensions/learning-history.ts");
  const corpus = JSON.parse(await readFile(fileURLToPath(new URL("../../continual-learning/tests/sensitive_memory_corpus.json", import.meta.url)), "utf8"));

  const benign = corpus.benign as string[];
  const sensitive = corpus.sensitive as string[];
  const configurationLiteral = 'plugins.entries.brave = {enabled:true, config:{webSearch:{apiKey:{source:"file",provider:"localfiles",id:"/brave_api_key"}}}}';
  const nestedSecret = 'apiKey: {client_secret: "Xq7bN2mP4kL9vR3s"}';
  const lesson = "- Recorded during learning.";

  await writeFile(target, `${benign.join("\n")}\n`);
  let benignMutation = "";
  try {
    const result = await recordLearningMutation(cwd, "agents", [target], async () => {
      await writeFile(target, `${benign.join("\n")}\n${lesson}\n`);
      return { outcome: "applied" };
    });
    benignMutation = result.outcome;
  } catch (error) {
    benignMutation = `refused: ${error instanceof Error ? error.message : String(error)}`;
  }
  const benignHistoryRecorded = (await listLearningHistory(cwd)).length > 0;
  const benignFileCarriesLesson = (await readFile(target, "utf8")).includes(lesson);
  let benignProposal = "recorded";
  try {
    await recordLearningProposal(cwd, "memory", { report: benign.map(quote => ({ quote })) });
  } catch {
    benignProposal = "refused";
  }

  await writeFile(target, `${sensitive.join("\n")}\n`);
  let sensitiveMutation = "applied";
  let refusalMessage = "";
  try {
    await recordLearningMutation(cwd, "agents", [target], async () => ({ outcome: "applied" }));
  } catch (error) {
    sensitiveMutation = "refused";
    refusalMessage = error instanceof Error ? error.message : String(error);
  }
  let sensitiveProposal = "recorded";
  try {
    await recordLearningProposal(cwd, "memory", { report: sensitive.map(quote => ({ quote })) });
  } catch {
    sensitiveProposal = "refused";
  }

  const observations = {
    benignOrdinary: benign.every(value => !containsSensitiveMemoryMaterial(value)) && !containsSensitiveMemoryMaterial(configurationLiteral),
    benignHistoryRecorded,
    benignMutationApplied: benignMutation === "applied",
    benignFileCarriesLesson,
    benignProposalRecorded: benignProposal === "recorded",
    sensitiveMutationRefused: sensitiveMutation === "refused",
    sensitiveProposalRefused: sensitiveProposal === "refused",
    literalKeyJudgedByMembers: !containsSensitiveMemoryMaterial(configurationLiteral),
    literalMemberSecretRefused: containsSensitiveMemoryMaterial(nestedSecret),
    refusalNamesSurface: refusalMessage.includes("refuses sensitive material") && refusalMessage.includes("project/AGENTS.md"),
    refusalHidesBytes: sensitive.every(value => !refusalMessage.includes(value)) && !refusalMessage.includes("Xq7bN2mP4kL9vR3s"),
  };
  console.log(JSON.stringify({ observations, checks: [
    // Clause indexes address Then clauses only; a Given or When step cannot carry a check.
    { clause: 1, path: "benignHistoryRecorded", op: "equals", value: true },
    { clause: 1, path: "benignMutationApplied", op: "equals", value: true },
    { clause: 1, path: "benignFileCarriesLesson", op: "equals", value: true },
    { clause: 2, path: "sensitiveMutationRefused", op: "equals", value: true },
    { clause: 2, path: "sensitiveProposalRefused", op: "equals", value: true },
    { clause: 3, path: "literalKeyJudgedByMembers", op: "equals", value: true },
    { clause: 4, path: "literalMemberSecretRefused", op: "equals", value: true },
    { clause: 5, path: "refusalNamesSurface", op: "equals", value: true },
    { clause: 5, path: "refusalHidesBytes", op: "equals", value: true },
  ] }));
} finally {
  await rm(root, { recursive: true, force: true });
}