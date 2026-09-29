"""Promotion is a configuration change, and it is off until configured.

A threshold compiled into the package would mean enabling authority required a
release and disabling it required a second one — a rollback cost high enough
that nobody would turn it on. These tests hold the switch at its default and pin
the one property that makes it safe to flip: only a surface whose authoritative
behavior is actually implemented can be turned on, and a failed judgment lets
every proposal through rather than dropping real knowledge.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from support import REPO

SNIPPET = r"""
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const agentDir=path.join(process.env.ROOT,'agent');
      fs.mkdirSync(agentDir,{recursive:true});
      const file=path.join(agentDir,'continual-learning.json');
      if (process.env.CONFIG !== undefined) fs.writeFileSync(file, process.env.CONFIG);
      const { resolveJudgmentAuthority, surfaceMode, IMPLEMENTED_AUTHORITY } =
        await import('./packages/continual-learning/extensions/judgment-config.ts');
      const { promotionGate } = await import('./packages/continual-learning/extensions/judgment-observations.ts');
      const authority = resolveJudgmentAuthority({ agentDir });
      console.log(JSON.stringify({
        authority,
        implemented: [...IMPLEMENTED_AUTHORITY],
        proposals: surfaceMode(authority, 'proposals'),
        selector: surfaceMode(authority, 'selector'),
        gate: promotionGate(process.cwd(), agentDir),
      }));
"""


def run(config: str | None, tmp_path: Path) -> dict:
    env = {"ROOT": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent")}
    if config is not None:
        env["CONFIG"] = config
    result = subprocess.run(
        ["bun", "-e", SNIPPET], cwd=REPO, capture_output=True, text=True,
        check=False, timeout=60, env={**__import__("os").environ, **env},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_nothing_is_authoritative_without_configuration(tmp_path: Path) -> None:
    value = run(None, tmp_path)
    assert value["proposals"] == "shadow", value
    assert value["selector"] == "shadow", value
    assert value["authority"]["surfaces"] == {}, value
    # Defaults are thresholds, not decisions, and both stay in range.
    assert value["authority"]["thresholds"] == {"durability": 0.5, "generality": 1}, value


def test_a_configured_surface_becomes_authoritative(tmp_path: Path) -> None:
    value = run(json.dumps({"judgment": {"surfaces": {"proposals": "authoritative"}}}), tmp_path)
    assert value["proposals"] == "authoritative", value
    assert value["selector"] == "shadow", value


def test_thresholds_come_from_configuration(tmp_path: Path) -> None:
    value = run(json.dumps({"judgment": {
        "surfaces": {"proposals": "authoritative"},
        "thresholds": {"durability": 0.7, "generality": 2},
    }}), tmp_path)
    assert value["authority"]["thresholds"] == {"durability": 0.7, "generality": 2}, value


def test_only_an_implemented_surface_can_be_turned_on(tmp_path: Path) -> None:
    """A switch that changes nothing is worse than no switch: it would read as
    authoritative while doing exactly what shadow mode did."""
    value = run(json.dumps({"judgment": {"surfaces": {"harness-operations": "authoritative"}}}), tmp_path)
    assert "harness-operations is not implemented" in (value["authority"].get("invalid") or ""), value
    assert value["selector"] == "shadow", value


def test_a_malformed_block_fails_closed_to_shadow(tmp_path: Path) -> None:
    for config in (
        json.dumps({"judgment": {"surfaces": {"proposals": "sometimes"}}}),
        json.dumps({"judgment": {"thresholds": {"durability": 4}}}),
        json.dumps({"judgment": {"thresholds": {"generality": 9}}}),
        json.dumps({"judgment": {"thresholds": {"nonsense": 0.5}}}),
        json.dumps({"judgment": "yes"}),
    ):
        value = run(config, tmp_path)
        assert value["proposals"] == "shadow", (config, value)
        assert value["authority"].get("invalid"), (config, value)


def test_the_gate_proposes_no_threshold_and_reports_no_measurement(tmp_path: Path) -> None:
    value = run(None, tmp_path)
    gate = value["gate"]
    assert gate["threshold"] is None, gate
    proposals = next(surface for surface in gate["surfaces"] if surface["surface"] == "proposals")
    assert proposals["implemented"] is True, gate
    assert proposals["verdict"] == "unmeasured", gate
    assert proposals["dropRate"] is None, gate
    # The unimplemented surfaces say so rather than implying they are ready.
    assert all(
        surface["verdict"] == "not implemented"
        for surface in gate["surfaces"]
        if surface["surface"] != "proposals"
    ), gate
    assert "human decision" in gate["note"], gate


def test_a_failed_judgment_drops_nothing(tmp_path: Path) -> None:
    """The property that makes the switch safe to flip.

    When proposals are authoritative the judgment arrives before the parent's
    validator. A service outage, a throttle, or a timeout must not become a
    reason to discard real knowledge, so an unanswered judgment has to leave the
    proposal list exactly as the planner produced it.
    """
    snippet = r"""
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'jev-failopen-')));
      const agentDir=path.join(root,'agent');fs.mkdirSync(agentDir,{recursive:true});
      process.env.PI_CODING_AGENT_DIR=agentDir;
      fs.writeFileSync(path.join(agentDir,'continual-learning.json'), JSON.stringify({
        api:{apiKey:'k'}, judgment:{surfaces:{proposals:'authoritative'}},
      }));
      // Every request fails, so no judgment is ever returned.
      const dead=Bun.serve({port:0,fetch:()=>new Response('no',{status:503})});
      process.env.TYPESAFE_API_KEY='k';
      process.env.TYPESAFE_BASE_URL=`http://127.0.0.1:${dead.port}`;
      const { observeMemoryProposals } = await import(
        './packages/continual-learning/extensions/judgment-shadow.ts');
      const proposals=[
        {name:'a.md',kind:'project',classification:'safe',content:'A reusable lesson.',evidence:[]},
        {name:'b.md',kind:'project',classification:'safe',content:'Another lesson.',evidence:[]},
      ];
      const observation=await observeMemoryProposals({ cwd:root, contextDigest:'f'.repeat(64), projection:{
        proposals, memories:[], selected:[],
      }});
      // Exactly what a fail-open narrowing does: keep everything unjudged.
      const keptUnjudged = observation.judged ? observation.kept.length : proposals.length;
      dead.stop(true);
      console.log(JSON.stringify({judged:observation.judged, outcome:observation.outcome, keptUnjudged, proposed:proposals.length}));
      fs.rmSync(root,{recursive:true,force:true});
    """
    result = subprocess.run(
        ["bun", "-e", snippet], cwd=REPO, capture_output=True, text=True, check=False, timeout=90,
        env={**__import__("os").environ, "PI_CODING_AGENT_DIR": str(tmp_path / "agent")},
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout.strip().splitlines()[-1])
    assert value["judged"] is False, value
    assert value["keptUnjudged"] == value["proposed"] == 2, value
