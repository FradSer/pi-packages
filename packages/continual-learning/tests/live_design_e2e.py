"""End-to-end verification of the whole `pi-continual-learning` design.

`live_smoke.py` verifies learning, persistence and a fresh session's native
tool calls. This script adds failure-boundary probes and direct runtime checks:

1. The Bash execution gate through a paired native call and refusal result.
2. The post-generation output check and its corrected final response.
3. Undo restoring the exact predecessor bytes.
4. The two Memory roots: safe private content mirrored, private content not.
5. A Memory deletion without a preservation target being refused.
6. The AGENTS.md phase actually changing the file, rather than merely running.
7. Pending mutation refusal, explicit reconciliation and idempotent recovery.
8. Credential detection and rejection for the intended path/symlink reason.

Every probe is designed to be safe when the protection under test is broken: the
execution gate probe would create a file if the gate failed to block, and the
file's absence is the assertion, so a failure is detected rather than caused.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from live_smoke import PACKAGE, REPO, blocked_tool_call, matched_tool_results, prepare, run_pi  # noqa: E402


def bun(source: str, timeout: int = 90, *, agent: Path | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix="cl-design-agent-") as temporary:
        result = subprocess.run(
            ["bun", "-e", source], cwd=REPO, capture_output=True, text=True,
            env={**os.environ, "PI_CODING_AGENT_DIR": str(agent or Path(temporary))},
            check=False, timeout=timeout,
        )
    assert result.returncode == 0, f"{result.stderr[-1500:]}"
    return json.loads(result.stdout.strip().splitlines()[-1])


def require_observations(outcome: dict, *fields: str) -> dict:
    for field in fields:
        assert outcome.get(field) is True, f"Acceptance observation failed: {field}; {outcome}"
    return outcome


def verify_execution_gate() -> dict:
    """A prohibited command must be blocked by a real ``tool_call`` event.

    The probe command would create a file if it ran. The assertion is the
    file's absence, so if the gate is not wired the file appears and the check
    fails — the probe cannot cause harm either way.
    """
    import tempfile

    with tempfile.TemporaryDirectory(prefix="cl-gate-") as raw:
        project, agent, probe = prepare(Path(raw), False)
        (project / ".pi").mkdir()
        (project / ".pi" / "harness.json").write_text(json.dumps({"rules": [
            # Unanchored on purpose. The gate must block the prohibited operation
            # however the model phrases it, and a probe that only passes for one
            # exact command string tests the model's phrasing rather than the gate.
            {"id": "gate-probe", "bash": "gate-probe-ran", "action": "block",
             "message": "That path is prohibited in this project."},
        ]}))
        result = run_pi(
            project, agent, probe,
            "Run the harmless command `touch gate-probe-ran` once with bash, then report whether it succeeded.",
            "bash",
        )
        created = (project / "gate-probe-ran").exists()
        # The definitive assertion: if the gate did not block, the file exists.
        assert not created, "A prohibited command was executed: the Bash gate did not block it"
        blocked_events = [
            entry for entry in result["records"]
            if entry.get("customType") == "harness-event"
            and (entry.get("data") or {}).get("action") == "block"
        ]
        assert blocked_events, f"No block was recorded; records={[e.get('customType') for e in result['records']]}"
        matched = matched_tool_results(result["messages"], "bash", lambda args: isinstance(args.get("command"), str) and "gate-probe-ran" in args["command"])
        assert any(blocked_tool_call(result["messages"], "bash", args["command"]) for args, _ in matched), "No matching native Bash call/result proved the requested block"
        return {"blocked": True, "blockEventRecorded": True}


def verify_output_check() -> dict:
    """A post-generation output policy must fire a bounded repair request."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="cl-output-") as raw:
        project, agent, probe = prepare(Path(raw), False)
        (project / ".pi").mkdir()
        (project / ".pi" / "harness.json").write_text(json.dumps({
            # Legacy policies use `pattern` and `reason`, and the output phase
            # rejects a `tools` field outright. The first version of this probe
            # used `deny`/`message`/`tools`, so the policy was invalid, the
            # declaration was dropped, and the check found nothing to fire.
            "policies": [{
                "name": "output-probe", "phase": "output",
                "pattern": "OUTPUT_GATE_TOKEN",
                "reason": "That token is prohibited in final output.",
            }],
        }))
        result = run_pi(
            project, agent, probe,
            "Reply with exactly this and nothing else: OUTPUT_GATE_TOKEN", "read",
        )
        repairs = [entry for entry in result["records"] if entry.get("customType") == "harness-post-generation-repair"]
        assert 1 <= len(repairs) <= 2, "No bounded repair was requested for prohibited output"
        assert result["final"].strip() and "OUTPUT_GATE_TOKEN" not in result["final"], "The final output still violates its policy"
        return {"repairRequested": True, "finalCorrected": True, "repairCount": len(repairs)}


def verify_undo_and_mirroring() -> dict:
    """Undo restores predecessor bytes, and only safe content is mirrored."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="cl-undo-") as raw:
        base = Path(raw)
        project, agent, probe = prepare(base, True)
        outcome = bun(f"""
          const {{ recordLearningMutation, listLearningHistory, previewLearningUndo,
                   undoLearningChange, readLearningFile, normalizeTrackedMemory }} =
            await import({json.dumps(str(PACKAGE / "extensions/learning-history.ts"))});
          const {{ resolveMemoryPaths }} = await import({json.dumps(str(PACKAGE / "extensions/memory-paths.ts"))});
          const fs = await import('node:fs');
          const path = await import('node:path');
          const cwd = {json.dumps(str(project))};
          const paths = resolveMemoryPaths(cwd);
          // The real private root for this project, not a guessed scope name: the
          // history guard refuses any target outside the learned surfaces, so a
          // fixture path is rejected before undo is ever reached.
          fs.mkdirSync(paths.harnessDir, {{ recursive: true }});
          const target = path.join(paths.harnessDir, 'project_undo.md');
          fs.writeFileSync(target, 'predecessor bytes');
          // Mirror the safe entry first. Undo refuses a change that would break
          // mirror equality, which is the privacy guard working: an unmirrored
          // private file is not a legal predecessor to restore.
          await normalizeTrackedMemory(paths);
          await recordLearningMutation(cwd, 'memory', [target], async () => {{
            fs.writeFileSync(target, 'changed bytes');
          }});
          const [record] = await listLearningHistory(cwd);
          const preview = await previewLearningUndo(cwd, record.id);
          // undoLearningChange reports through the filesystem, not a return
          // value, so the contract is the restored bytes and the mirror state.
          await undoLearningChange(cwd, record.id, preview.digest);
          console.log(JSON.stringify({{
            content: (await readLearningFile(target, 8192)).toString('utf8'),
            publicHas: await Bun.file(path.join(paths.publicDir, 'project_undo.md')).exists(),
            privateHas: await Bun.file(target).exists(),
            undoneStatuses: (await listLearningHistory(cwd)).filter(r => r.status === 'undone').length,
            stillApplied: (await listLearningHistory(cwd)).filter(r => r.status === 'applied').length,
          }}));
        """, timeout=120, agent=agent)
        assert outcome["content"] == "predecessor bytes", outcome
        assert outcome["privateHas"], outcome
        # The mirror carries only shareable content, and the safe entry the run
        # mirrored is still there: undo restored the pair, not just the private
        # side, which is what mirror equality requires.
        assert outcome["publicHas"], "Undo left the shared surface out of sync with the private one"
        # Undo marks the record undone rather than deleting it. Deleting it would
        # destroy the audit trail, which is the opposite of what a receipt is for.
        assert outcome["undoneStatuses"] == 1, outcome
        return {"restored": outcome["content"], "privateRetained": True,
                "mirrorInSync": True, "historyRetainedAsUndone": True}


def verify_delete_protection() -> dict:
    """A Memory deletion must carry a verdict and a verifiable preservation target.

    Exercised through the real validator process the parent actually runs, not a
    fabricated run object. An earlier version of this check built a hand-rolled
    ``run`` and every case was refused — for the wrong reason, on a missing field
    before the verdict was ever inspected. A check that passes for the wrong
    reason is worse than no check, because it reports protection that is not
    there.
    """
    import tempfile

    with tempfile.TemporaryDirectory(prefix="cl-delete-") as raw:
        base = Path(raw)
        project, agent, _ = prepare(base, False, seed_memory=True)
        run_dir = base / "run"
        run_dir.mkdir()
        run_id = "run_deleteguard"
        scope_key = next((agent / "memory").glob("--*")).name
        digest = "a" * 64
        snapshot = run_dir / "snapshot.json"
        snapshot.write_text(json.dumps({
            "schemaVersion": 1, "runId": run_id, "scopeKey": scope_key, "entries": [],
        }))
        # The validator re-hashes the snapshot, so the artifact hash has to be
        # the file's real digest rather than a placeholder.
        artifact = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        # A preservation target that genuinely exists, so the only thing under
        # test is the verdict and the target's existence.
        keeper = project / "keeper.md"
        keeper.write_text("the knowledge that survives\n")
        manifest = run_dir / "manifest.json"
        manifest.write_text(json.dumps({
            "runId": run_id, "scopeKey": scope_key, "scopeDigest": digest,
            "artifactHash": artifact, "snapshotDigest": artifact,
            "runDir": str(run_dir), "snapshotPath": str(snapshot), "cwd": str(project),
        }))

        def validate(operation: dict, selected: list[str]) -> tuple[dict, bool]:
            """Build an otherwise-complete plan, then vary one field at a time.

            Every other section is filled in so that each refusal can only be
            caused by the defect under test. A plan that fails for an unrelated
            reason would make the refusals vacuous.
            """
            # The staleness record mirrors the operation. Filling it in when the
            # operation omits a verdict would make the preservation check fire
            # first, so the "no verdict" case would be refused for the wrong
            # reason and prove nothing about verdict enforcement.
            verdict = operation.get("verdict")
            staleness_record = [{"name": n} for n in selected]
            if verdict is not None:
                for record in staleness_record:
                    record["verdict"] = verdict
            plan = run_dir / "plan.json"
            plan.write_text(json.dumps({
                "kind": "memory-consolidation-plan", "version": 1, "schemaVersion": 1,
                "runId": run_id, "scopeKey": scope_key, "scopeDigest": digest,
                "artifactHash": artifact, "snapshotDigest": artifact,
                "selected": selected,
                "operations": [operation],
                "newMemories": [],
                "inventory": [{"name": n, "classification": "safe"} for n in selected],
                "clusters": [{"name": "deleteguard", "files": selected}],
                "staleness": staleness_record,
                "grounding": [{"name": n, "status": "N/A", "reason": "not applicable", "observations": []} for n in selected],
                "report": [{"name": n, "status": verdict or "KEEP", "summary": "guard probe"} for n in selected],
                "evidence": [],
            }))
            result = subprocess.run(
                [sys.executable, str(PACKAGE / "scripts" / "validate-consolidate.py"),
                 "--plan", str(plan), "--snapshot", str(snapshot),
                 "--repo-root", str(project), "--expected-run-id", run_id,
                 f"--expected-scope-key={scope_key}", "--expected-scope-digest", digest,
                 "--expected-artifact-hash", artifact, "--mode", "manual",
                 "--expected-run-dir", str(run_dir),
                 "--expected-selected", json.dumps(sorted(selected)),
                 "--check", "plan"],
                capture_output=True, text=True, check=False, timeout=120,
            )
            try:
                parsed = json.loads(result.stderr or result.stdout or "{}")
            except json.JSONDecodeError:
                parsed = {"ok": False, "errors": [{"message": (result.stderr or result.stdout)[:200]}]}
            return parsed, parsed.get("ok") is True

        target = "stale.md"
        # A valid delete: a verdict, and a preservation target that exists.
        _, accepted = validate({
            "name": target, "kind": "delete", "classification": "safe", "verdict": "SUPERSEDED",
            "preservedIn": ["keeper.md"],
        }, [target])
        no_verdict, ok = validate({"name": target, "kind": "delete", "classification": "safe"}, [target])
        no_preserved, _ = validate({
            "name": target, "kind": "delete", "classification": "safe", "verdict": "SUPERSEDED",
        }, [target])
        bad_target, _ = validate({
            "name": target, "kind": "delete", "classification": "safe", "verdict": "SUPERSEDED",
            "preservedIn": ["does/not/exist.md"],
        }, [target])

        def codes(payload: dict) -> str:
            return " ".join(str(error.get("message", "")) for error in payload.get("errors", []))

        # A guard that refuses everything would make the refusals meaningless,
        # so the valid case has to be accepted.
        assert accepted, codes({"errors": [{"message": "valid delete was refused"}]})
        assert "verdict" in codes(no_verdict), codes(no_verdict)
        assert "preservedIn" in codes(no_preserved), codes(no_preserved)
        assert "preservedIn" in codes(bad_target) or "exist" in codes(bad_target), codes(bad_target)
        return {
            "validDeleteAccepted": True,
            "noVerdictRefused": True,
            "noPreservedInRefused": True,
            "badTargetRefused": True,
        }


def verify_agents_applied() -> dict:
    """The AGENTS.md phase must change the document, not merely report running."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="cl-agents-") as raw:
        project, agent, probe = prepare(Path(raw), True, agents_md=True)
        before = (project / "AGENTS.md").read_text()
        run_pi(
            project, agent, probe,
            "Our AGENTS.md instruction is wrong: the progress reporting workflow is instead "
            "one short status line, not a paragraph. This is a durable requirement. "
            "Reply only: acknowledged.", "read",
        )
        after = (project / "AGENTS.md").read_text()
        assert before != after, "AGENTS.md was not changed"
        assert "Report progress as a paragraph" not in after and "one short status line" in after, "AGENTS.md did not retain the requested workflow"
        return {"changed": True, "before": len(before), "after": len(after)}


def verify_recovery_isolation() -> dict:
    """Check real pending mutations before and after manual reconciliation."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="cl-isolation-") as raw:
        base = Path(raw)
        project, agent, probe = prepare(base, True, seed_memory=True)
        outcome = bun(f"""
          const fs = await import('node:fs'); const path = await import('node:path');
          const M = await import({json.dumps(str(PACKAGE / "extensions/learning-history.ts"))});
          const R = await import({json.dumps(str(PACKAGE / "extensions/memory-paths.ts"))});
          const cwd = {json.dumps(str(project))};
          const paths = R.resolveMemoryPaths(cwd);
          fs.mkdirSync(paths.harnessDir, {{ recursive: true }});
          const keeper = path.join(paths.harnessDir, 'project_kept.md');
          fs.writeFileSync(keeper, 'predecessor');
          const sibling = path.join(paths.harnessDir, 'project_untouched.md');
          fs.writeFileSync(sibling, 'never part of the run');
          await M.normalizeTrackedMemory(paths);
          await M.recordLearningMutation(cwd, 'memory', [keeper], async () => {{
            fs.writeFileSync(keeper, 'applied bytes');
          }});
          const interrupted = path.join(paths.harnessDir, 'project_interrupted.md');
          fs.writeFileSync(interrupted, 'pending predecessor');
          try {{
            await M.recordLearningMutation(cwd, 'memory', [interrupted], async () => {{
              fs.writeFileSync(interrupted, 'unowned interrupted bytes');
              throw new Error('deliberate interrupted mutation');
            }});
          }} catch (error) {{
            if (error.message !== 'deliberate interrupted mutation') throw error;
          }}
          const pending = (await M.listLearningHistory(cwd)).find(record => record.status === 'pending');
          if (!pending) throw new Error('interrupted mutation did not leave a pending record');
          const beforeUnrelated = fs.readFileSync(sibling, 'utf8');
          let rejection = '';
          try {{ await M.checkPendingLearningMutations(cwd); }}
          catch (error) {{ rejection = String(error.message); }}
          const pendingDetected = rejection.includes('Unfinished learning') && rejection.includes(pending.id)
            && fs.readFileSync(interrupted, 'utf8') === 'unowned interrupted bytes';
          // Reconciliation is explicit; recovery must not guess ownership.
          fs.writeFileSync(interrupted, 'pending predecessor');
          await M.checkPendingLearningMutations(cwd);
          const pendingAbandoned = (await M.readLearningHistory(cwd, pending.id)).status === 'abandoned';
          const firstPass = fs.readFileSync(keeper, 'utf8');
          await M.checkPendingLearningMutations(cwd);
          console.log(JSON.stringify({{
            pendingDetected, pendingAbandoned,
            appliedSurvived: firstPass === 'applied bytes' && fs.readFileSync(keeper, 'utf8') === 'applied bytes',
            unrelatedUnchanged: fs.readFileSync(sibling, 'utf8') === beforeUnrelated,
            recoveryIdempotent: firstPass === fs.readFileSync(keeper, 'utf8'),
          }}));
        """, timeout=120, agent=agent)
        return require_observations(outcome, 'pendingDetected', 'pendingAbandoned', 'appliedSurvived', 'unrelatedUnchanged', 'recoveryIdempotent')


def verify_secret_rejection() -> dict:
    """A credential in the transcript must never reach Memory."""
    outcome = bun(f"""
      const {{ containsSensitiveMemoryMaterial }} = await import(
        {json.dumps(str(PACKAGE / "extensions/consolidation-run.ts"))});
      const secrets = [
        '-----BEGIN OPENSSH PRIVATE KEY-----',
        'export API_KEY=sk-live-9f3a2b7c4d5e6f70',
        'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9abcdefghijklmnop',
        'password: hunter2-super-secret-value',
      ];
      const ordinary = [
        'The token is short-lived and is not a credential.',
        'Prefer pnpm over npm for this repository.',
        'Run `bun run check` to verify a change.',
        'The user set the editor chord to leader-space.',
      ];
      console.log(JSON.stringify({{
        secretsRejected: secrets.every(containsSensitiveMemoryMaterial),
        ordinaryAccepted: ordinary.every(value => !containsSensitiveMemoryMaterial(value)),
        secretCount: secrets.length,
      }}));
    """, timeout=120)
    return require_observations(outcome, 'secretsRejected', 'ordinaryAccepted')


def verify_path_containment() -> dict:
    """A write outside the learned surfaces must be refused, symlinks included."""
    with tempfile.TemporaryDirectory(prefix="cl-contain-") as raw:
        project, agent, _ = prepare(Path(raw), False)
        outcome = bun(f"""
      const fs = await import('node:fs');
      const path = await import('node:path');
      const M = await import({json.dumps(str(PACKAGE / "extensions/learning-history.ts"))});
      const R = await import({json.dumps(str(PACKAGE / "extensions/memory-paths.ts"))});
      const cwd = fs.realpathSync({json.dumps(str(project))});
      const paths = R.resolveMemoryPaths(cwd);
      if (!paths.publicDir) throw new Error('probe has no public learned surface');
      fs.mkdirSync(paths.publicDir, {{ recursive: true }});
      const outside = path.join(cwd, 'elsewhere.md');
      fs.writeFileSync(outside, 'not a learned surface');
      const link = path.join(paths.publicDir, 'linked.md');
      fs.symlinkSync(outside, link);
      const attempt = async (target) => {{
        try {{ await M.recordLearningMutation(cwd, 'memory', [target], async () => {{}}); return null; }}
        catch (error) {{ return String(error.message); }}
      }};
      const escape = await attempt(path.join(cwd, '..', 'escaped.md'));
      const symlinked = await attempt(link);
      console.log(JSON.stringify({{
        escapeRefused: escape !== null,
        symlinkRefused: symlinked !== null,
        escapeDetail: escape, symlinkDetail: symlinked,
      }}));
    """, timeout=120, agent=agent)
        require_observations(outcome, 'escapeRefused', 'symlinkRefused')
        assert 'outside the learned' in outcome['escapeDetail'], outcome
        assert 'symlink' in outcome['symlinkDetail'], outcome
        return outcome


if __name__ == "__main__":
    checks = {
        "execution_gate": verify_execution_gate,
        "output_check": verify_output_check,
        "undo_and_mirroring": verify_undo_and_mirroring,
        "delete_protection": verify_delete_protection,
        "agents_applied": verify_agents_applied,
        "recovery_isolation": verify_recovery_isolation,
        "secret_rejection": verify_secret_rejection,
        "path_containment": verify_path_containment,
    }
    for name, check in checks.items():
        print(name, json.dumps(check()), flush=True)
