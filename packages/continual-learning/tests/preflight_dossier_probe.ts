// Read-only re-measurement of the privacy guard over retained learning dossiers.
//
// Zero model, service and network calls. It walks every taskSlice entry of every
// retained incremental-learning dossier and reports how many entries the exported
// Memory guard classifies as sensitive. Run with bun:
//
//   bun packages/continual-learning/tests/preflight_dossier_probe.ts [root]
//
// The default root is ~/.cache/pi-continual-learning/docker. A nonzero trip count
// is not automatically a defect: check the entry against the documented
// placeholder rule and the corpus in tests/sensitive_memory_corpus.json first.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {containsSensitiveMemoryMaterial} from "../extensions/consolidation-run.ts";

const root = process.argv[2] ?? path.join(os.homedir(), ".cache", "pi-continual-learning", "docker");
const dossiers: string[] = [];
const walk = (dir: string, depth: number): void => {
  if (depth > 8) return;
  let entries: fs.Dirent[];
  try { entries = fs.readdirSync(dir, {withFileTypes: true}); } catch { return; }
  for (const entry of entries) {
    if (entry.isSymbolicLink()) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, depth + 1);
    else if (entry.name === "incremental-learning-dossier.json") dossiers.push(full);
  }
};
walk(root, 0);

let entries = 0, trips = 0;
const samples: {file: string; index: number; role: unknown}[] = [];
for (const file of dossiers) {
  let dossier: unknown;
  try { dossier = JSON.parse(fs.readFileSync(file, "utf8")); } catch { continue; }
  const slice = (dossier as {taskSlice?: {entries?: unknown}})?.taskSlice;
  const list = slice?.entries;
  if (!Array.isArray(list)) continue;
  list.forEach((entry: unknown, index: number) => {
    entries++;
    if (!containsSensitiveMemoryMaterial(JSON.stringify(entry))) return;
    trips++;
    if (samples.length < 5) samples.push({file, index, role: (entry as {role?: unknown})?.role ?? null});
  });
}
console.log(JSON.stringify({root, dossiers: dossiers.length, entries, trips, samples}, null, 1));