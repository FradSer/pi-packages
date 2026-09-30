"""Can it learn a Harness rule, and how reliably?

`live_smoke.py` proves a rule was learned once: it was written, ownership was
bound, the prohibited command was blocked, and a safe command was allowed. That
is correctness on a single sample. It says nothing about whether the phase
*reliably* learns, and the Harness planner has failed in this workspace with
three different defects across ten live runs — a missing plan, a negative case
matching its own rule, and a case list of strings where objects were required. A
bounded repair was added for those and has never been measured.

This runs the Harness phase in isolation, repeatedly, against a real planner
child, and reports the success rate. It is a measurement script, not a gate: the
number it prints is the answer to "can it learn harness", and a run where the
rule is learned and enforced correctly counts as a success regardless of how many
repairs it took.

Not collected by pytest; it spends real provider tokens per trial.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]

PROHIBITED = "retired-smoke-compiler build"
ALLOWED = "printf safe"
STATEMENT = "never run retired-smoke-compiler through bash: it is prohibited in this project"

TRIALS = int(os.environ.get("HARNESS_TRIALS", "4"))

PROBE = r"""
      import fs from 'node:fs';
      import path from 'node:path';
      const { planHarnessConsolidationPhase, applyHarnessConsolidationPlan } = await import(
        PKG + '/extensions/harness-consolidation.ts');
      const { mergeLayers, evaluateBash } = await import(PKG + '/extensions/guardrail-engine.ts');
      const root = ROOT, project = path.join(root, 'project'), agent = path.join(root, 'agent');
      process.env.PI_CODING_AGENT_DIR = agent;
      fs.mkdirSync(project, { recursive: true });
      fs.mkdirSync(agent, { recursive: true });
      // The planner child needs credentials. Copied privately, the way the live
      // smoke does it, so a runtime refresh cannot alter the source files.
      const source = process.env.SOURCE_AGENT_DIR;
      for (const name of ['auth.json', 'models.json', 'memory.json']) {
        if (fs.existsSync(path.join(source, name))) {
          fs.copyFileSync(path.join(source, name), path.join(agent, name));
        }
      }
      fs.mkdirSync(path.join(agent, 'memory'), { recursive: true });
      fs.mkdirSync(path.join(project, '.pi'), { recursive: true });
      const entries = [{ message: { role: 'user', content: STATEMENT } }];
      const ctx = {
        cwd: project, mode: 'json', hasUI: false,
        ui: { notify: () => {}, setWidget: () => {} },
        sessionManager: { getBranch: () => entries, buildContextEntries: () => entries },
      };
      const planning = await planHarnessConsolidationPhase(ctx, {
        pkgDir: PKG, cwd: project, reason: 'learn a prohibited command', availableSkills: [],
      });
      if (!planning.ok) {
        console.log(JSON.stringify({ learned: false, stage: 'plan', detail: planning.detail.slice(0, 200) }));
      } else {
        const applied = await applyHarnessConsolidationPlan(planning.value);
        const file = path.join(project, '.pi', 'harness.json');
        let outcome = { learned: false, stage: 'apply', detail: JSON.stringify(applied).slice(0, 200) };
        if (fs.existsSync(file)) {
          const config = mergeLayers([{ ...JSON.parse(fs.readFileSync(file, 'utf8')), source: 'project' }], []);
          const blocked = evaluateBash(config, PROHIBITED).decision;
          const allowed = evaluateBash(config, ALLOWED).decision;
          const rules = JSON.parse(fs.readFileSync(file, 'utf8')).rules ?? [];
          outcome = {
            learned: true, rules: rules.length, blocked, allowed,
            ownershipBound: Boolean(JSON.parse(fs.readFileSync(file, 'utf8')).learnedRules),
            // A rule that blocks the prohibited command but also blocks a safe
            // one has not generalised; it has over-matched.
            correct: blocked === 'block' && allowed === 'execute',
          };
        }
        console.log(JSON.stringify(outcome));
      }
"""


def trial() -> dict:
    with tempfile.TemporaryDirectory(prefix="cl-harness-learn-") as raw:
        source = (PROBE
                  .replace("PKG", json.dumps(str(PACKAGE)))
                  .replace("ROOT", json.dumps(raw))
                  .replace("PROHIBITED", json.dumps(PROHIBITED))
                  .replace("ALLOWED", json.dumps(ALLOWED))
                  .replace("STATEMENT", json.dumps(STATEMENT)))
        result = subprocess.run(
            ["bun", "-e", source], cwd=REPO, capture_output=True, text=True,
            check=False, timeout=900,
            env={**os.environ, "SOURCE_AGENT_DIR": os.environ.get("PI_CODING_AGENT_DIR", str(Path.home() / ".pi" / "agent"))},
        )
        assert result.returncode == 0, f"{result.stderr[-1500:]}"
        return json.loads(result.stdout.strip().splitlines()[-1])


if __name__ == "__main__":
    outcomes = []
    for index in range(TRIALS):
        try:
            outcome = trial()
        except Exception as error:  # a crashed trial is a failed trial
            outcome = {"learned": False, "stage": "crash", "detail": str(error)[:200]}
        outcome["trial"] = index
        outcomes.append(outcome)
        print(f"trial {index}: {json.dumps(outcome)}", flush=True)

    learned = [o for o in outcomes if o.get("learned")]
    correct = [o for o in learned if o.get("correct")]
    summary = {
        "trials": TRIALS,
        "learned": len(learned),
        "learnedAndCorrect": len(correct),
        "learnRate": round(len(learned) / TRIALS, 3) if TRIALS else None,
        "correctRate": round(len(correct) / TRIALS, 3) if TRIALS else None,
        "failStages": sorted({o.get("stage", "?") for o in outcomes if not o.get("learned")}),
        "failures": [{"stage": o.get("stage"), "detail": o.get("detail", "")[:200]} for o in outcomes if not o.get("learned")],
    }
    print("summary " + json.dumps(summary, ensure_ascii=False), flush=True)
