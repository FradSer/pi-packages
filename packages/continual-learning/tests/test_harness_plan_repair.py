"""One bounded repair of a rejected Harness plan.

Three live pipeline runs failed on three different planner defects — a missing
plan, a negative case matching its own rule, and a case list of strings — so
this is a recoverable authoring mistake seen repeatedly, not random noise. The
repair is handed the exact errors and the rejected plan and may change nothing
else: identity, evidence, and the authoritative selected scope still have to
survive revalidation.
"""

from __future__ import annotations

import json
from pathlib import Path

from support import run_bun_script

HARNESS = Path(__file__).with_name("harness-repair-harness.ts")


def run(scenario: str) -> dict:
    return run_bun_script(HARNESS, scenario)


def test_a_rejected_plan_gets_one_repair_attempt_and_is_applied() -> None:
    value = run("repaired")
    assert value["repairRequested"] is True, value
    # Initial plan plus exactly one repair. A second retry would be unbounded
    # spend on a child that is already failing to hold the contract.
    assert value["spawned"] == 2, value
    assert value["ok"] is True, value
    assert value["operations"] == 1, value


def test_a_repair_that_is_still_invalid_fails_the_phase() -> None:
    value = run("repair-also-fails")
    assert value["repairRequested"] is True, value
    assert value["spawned"] == 2, value
    assert value["ok"] is False, value
    # The diagnostic names the real defect, so the failure is actionable rather
    # than a bare "rejected".
    assert "must remain unmatched" in value["detail"], value


def test_the_repair_is_bounded_to_one_attempt() -> None:
    for scenario in ("repaired", "repair-also-fails"):
        assert run(scenario)["spawned"] == 2, (scenario, run(scenario))


def test_every_generative_phase_runs_on_the_configured_consolidation_model() -> None:
    """The package header promises consolidation uses the separately selected
    model. Only the Memory phase honoured it: the Harness planner and the
    AGENTS.md extractor inherited the session default, so a run could propose a
    Memory with one model and a rule with another."""
    import subprocess
    from support import REPO

    result = subprocess.run(
        ["bun", "-e", r"""
      import fs from 'node:fs';
      const read = (file) => fs.readFileSync(file, 'utf8');
      const harness = read('./packages/continual-learning/extensions/harness-consolidation.ts');
      const agents = read('./packages/continual-learning/extensions/agents-md-consolidation.ts');
      const pipeline = read('./packages/continual-learning/extensions/inject-memory.ts');
      // The child must be able to receive --model at all.
      const bindsHarness = /options\.model \? \["--model", options\.model\]/.test(harness);
      const bindsAgents = /opts\.model \? \["--model", opts\.model\]/.test(agents);
      // And both phases must actually be given one, from a single resolution.
      const resolvesOnce = /const consolidationModel = memoryConfig\.provider/.test(pipeline);
      const passes = (pipeline.match(/consolidationModel \? \{ model: consolidationModel \}/g) ?? []).length;
      // Memory already bound it directly.
      const memoryBinds = (pipeline.match(/model: memoryConfig\.provider/g) ?? []).length;
      console.log(JSON.stringify({ bindsHarness, bindsAgents, resolvesOnce, passes, memoryBinds }));
    """],
        cwd=REPO, capture_output=True, text=True, check=True, timeout=60,
    )
    value = json.loads(result.stdout.strip().splitlines()[-1])
    assert value["bindsHarness"] is True, value
    assert value["bindsAgents"] is True, value
    # One resolution, used by both phases, so they cannot drift apart.
    assert value["resolvesOnce"] is True, value
    assert value["passes"] == 2, value
    assert value["memoryBinds"] >= 2, value
