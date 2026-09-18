"""Contract checks on the actual prompt projection, not a new scheduling engine."""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path

import pytest

from test_teammate_package import PACKAGE, SRC, run_node


@pytest.fixture(scope="module")
def prompts(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    root = tmp_path_factory.mktemp("orchestration-prompts")
    return run_node(f'''
      import {{ buildIdleLeaderGuidance, buildTeamLeaderGuidance, WORKER_GUIDANCE }} from "{(SRC / 'guidance.ts').as_uri()}";
      console.log(JSON.stringify({{
        idle: buildIdleLeaderGuidance({str(root)!r}),
        active: buildTeamLeaderGuidance({str(root)!r}),
        worker: WORKER_GUIDANCE,
      }}));
    ''', env_overrides={"HOME": str(root), "PI_CODING_AGENT_DIR": str(root / "agent")})


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text)


@pytest.mark.parametrize("state", ["idle", "active"])
def test_leader_prompts_expose_candidate_bound_completion(prompts: dict[str, str], state: str) -> None:
    guidance = normalized(prompts[state])
    for rule in (
        "one integration owner",
        "same candidate",
        "blocking reviews",
        "findings resolved",
        "completed review Work is not a PASS verdict",
        "yield without declaring completion",
        "resources",
        "dependsOn",
        "independent reviewer prompt, not a shell command",
        "reopen",
        "closed assignment",
    ):
        assert rule in guidance, (state, rule)
    assert "coordination-only" in guidance
    assert "verification gate" in guidance


@pytest.mark.parametrize("state", ["idle", "active"])
def test_leader_preserves_findings_and_refreshes_review_context_before_assignment(prompts: dict[str, str], state: str) -> None:
    text = normalized(prompts[state])
    for rule in ("preserve prior findings", "authoritative brief", "before reopening", "does not update the description", "candidate fingerprint", "correction delta", "bounded follow-up", "dependsOn"):
        assert rule in text, (state, rule)


def test_worker_prompt_keeps_local_scope_and_review_verdict_distinct(prompts: dict[str, str]) -> None:
    worker = normalized(prompts["worker"])
    for rule in ("assigned checks", "candidate", "REWORK", "implementation acceptance", 'outcome: "failed"', "without editing", "without waiting for repairs", "authoritative brief"):
        assert rule in worker


def test_packaged_role_reference_discloses_bounded_assignment_contract() -> None:
    roles = (PACKAGE / "references" / "agent-roles.md").read_text()
    for rule in ("baseline", "dependencies", "verification owner", "candidate", "REWORK", "reviewer prompt"):
        assert rule.lower() in roles.lower(), rule


def test_work_recheck_needs_explicit_refreshed_context(tmp_path: Path) -> None:
    from test_accepted_work_reporting import machine_case

    payload = machine_case(tmp_path, '''
      const { completeTask } = await import("''' + (SRC / "state.ts").as_uri() + '''");
      task.description = "Inspect candidate v1 against baseline B0";
      const priorReport = "Spec REWORK: reviewer scope and stale candidate brief";
      assert.ok(completeTask(task.id, priorReport));
      const before = await call("work", { action: "list" });
      const saved = before.details.works.find(entry => entry.id === task.id);
      assert.equal(saved.result, priorReport);
      await call("work", { action: "reopen", id: task.id, reason: "Inspect candidate v2 instead" });
      const after = await call("work", { action: "list" });
      const reopened = after.details.works.find(entry => entry.id === task.id);
      assert.equal(reopened.description, "Inspect candidate v1 against baseline B0");
      assert.equal(reopened.result, undefined);
      // This synthetic original is completed again only to exercise a linked follow-up.
      assert.ok(setTaskClaimed(task.id, "reviewer"));
      assert.ok(completeTask(task.id, saved.result));
      const description = `Bounded recheck: baseline B0; candidate v2; delta fixes two findings. Prior findings: ${saved.result}. Safe checks: prompt contract only.`;
      const followUp = await call("work", { action: "create", subject: "Recheck review corrections",
        description, dependsOn: [task.id], resources: ["review:scope"] });
      assert.equal(followUp.details.claimable, true);
      console.log(JSON.stringify({ oldDescription: reopened.description, clearedResult: reopened.result ?? null,
        followUp: followUp.details.work }));
    ''')
    assert payload["clearedResult"] is None
    assert payload["oldDescription"].startswith("Inspect candidate v1")
    assert "candidate v2" in payload["followUp"]["description"]
    assert "reviewer scope and stale candidate brief" in payload["followUp"]["description"]
    assert payload["followUp"]["dependsOn"] == ["work:review"]


def test_registered_extension_injects_contract_in_idle_and_active_contexts(tmp_path: Path) -> None:
    payload = run_node(f'''
      import register from "{(SRC / 'index.ts').as_uri()}";
      import {{ createTask, resetState }} from "{(SRC / 'state.ts').as_uri()}";
      const events = new Map();
      register({{
        on(name, handler) {{ events.set(name, handler); }}, registerTool() {{}}, registerCommand() {{}},
        registerMessageRenderer() {{}}, registerEntryRenderer() {{}},
      }});
      const ctx = {{ cwd: {str(tmp_path)!r} }};
      resetState();
      const idle = await events.get("before_agent_start")({{ systemPrompt: "base" }}, ctx);
      createTask({{ subject: "candidate review" }});
      const active = await events.get("before_agent_start")({{ systemPrompt: "base" }}, ctx);
      console.log(JSON.stringify({{ idle: idle.systemPrompt, active: active.systemPrompt }}));
    ''', env_overrides={"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent")})
    for text in payload.values():
        assert text.startswith("base")
        assert text.count("### Delivery contract") == 1
        assert "yield without declaring completion" in text


def test_real_pi_receives_orchestration_and_review_instructions(tmp_path: Path) -> None:
    pi = shutil.which("pi")
    if pi is None:
        pytest.skip("Pi CLI is required for live prompt-delivery verification")
    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "settings.json").write_text(json.dumps({"quietStartup": True}))
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    env.update({"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(agent), "PI_OFFLINE": "1",
                "PI_ORCHESTRATION_AUTH": secrets.token_hex(16)})
    result = subprocess.run([
        pi, "--print", "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates",
        "--no-themes", "--no-context-files", "--no-approve", "--no-builtin-tools",
        "--extension", str(PACKAGE / "tests" / "orchestration-live-fixture.ts"),
        "--provider", "orchestration-guidance-fixture", "--model", "deterministic", "--thinking", "off",
        "Verify instruction delivery without delegating or changing source files.",
    ], cwd=tmp_path, env=env, input="", text=True, capture_output=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ORCHESTRATION_PROMPT_DELIVERY_OK" in result.stdout, result.stdout + result.stderr
    assert "Extension error" not in result.stderr
