"""Contracts for context-derived memory proposals and frozen session input."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from support import PKG_DIR as PACKAGE, initialize_git_repo, run_bun

SCRIPT = PACKAGE / "scripts" / "validate-consolidate.py"


def run_validator(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def write_json(path: Path, value: object) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return raw


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def snapshot(role: str = "user", text: str = "I prefer concise status updates.") -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "runId": "memory-run-1",
        "scopeKey": "c" * 64,
        "contextEnabled": True,
        "entries": [{"type": "message", "message": {"role": role, "content": text}}],
    }


def plan(snapshot_digest: str, proposals: list[dict[str, object]], selected: list[str] | None = None) -> dict[str, object]:
    selected = [] if selected is None else selected
    inventory = [
        {"name": name, "classification": "safe"}
        for name in selected
    ]
    return {
        "kind": "memory-consolidation-plan",
        "version": 1,
        "schemaVersion": 1,
        "runId": "memory-run-1",
        "scopeKey": "c" * 64,
        "scopeDigest": "b" * 64,
        "snapshotDigest": snapshot_digest,
        "artifactHash": snapshot_digest,
        "selected": selected,
        "inventory": inventory,
        "clusters": [{"name": "existing", "files": selected}] if selected else [],
        "staleness": [{"name": name, "verdict": "KEEP"} for name in selected],
        "grounding": [
            {
                "name": name,
                "status": "N/A",
                "reason": "no repository claim",
                "observations": [],
            }
            for name in selected
        ],
        "report": [{"name": name, "status": "KEEP", "summary": "existing"} for name in selected],
        "operations": [],
        "newMemories": proposals,
    }


def proposal(
    name: str = "preference.md",
    kind: str = "preference",
    content: str = "---\ndescription: concise updates\n---\nPrefer concise status updates.\n",
    evidence_text: str = "I prefer concise status updates.",
    index: int = 0,
    classification: str | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "name": name,
        "kind": kind,
        "content": content,
        "evidence": [{"index": index, "quote": evidence_text}],
    }
    if classification is not None:
        value["classification"] = classification
    return value


def invoke_plan(root: Path, plan_value: dict[str, object], snapshot_value: dict[str, object]) -> subprocess.CompletedProcess[str]:
    snapshot_path = root / "snapshot.json"
    snapshot_raw = write_json(snapshot_path, snapshot_value)
    plan_value["snapshotDigest"] = sha_bytes(snapshot_raw)
    plan_value["artifactHash"] = plan_value["snapshotDigest"]
    plan_path = root / "plan.json"
    write_json(plan_path, plan_value)
    return run_validator([
        "--plan", str(plan_path),
        "--snapshot", str(snapshot_path),
        "--check=plan",
        "--expected-run-id", "memory-run-1",
        "--expected-scope-key", "c" * 64,
        "--expected-scope-digest", "b" * 64,
        "--expected-artifact-hash", plan_value["artifactHash"],
        "--expected-selected", json.dumps(plan_value["selected"]),
    ])


def test_empty_existing_scope_accepts_user_evidenced_new_memory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        snapshot_value = snapshot()
        snapshot_raw = json.dumps(snapshot_value, ensure_ascii=False, indent=2).encode() + b"\n"
        result = invoke_plan(root, plan(sha_bytes(snapshot_raw), [proposal()]), snapshot_value)
        assert result.returncode == 0, result.stdout
        details = json.loads(result.stdout)["details"]
        assert details["newMemoryCount"] == 1


def test_new_memory_rejects_assistant_only_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result = invoke_plan(root, plan("a" * 64, [proposal(evidence_text="The user prefers concise updates.")]), snapshot("assistant", "The user prefers concise updates."))
        assert result.returncode == 1
        assert "context_evidence" in result.stdout


def test_new_memory_rejects_sensitive_content_or_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result = invoke_plan(
            root,
            plan("a" * 64, [proposal(content="api_key = sk-test-secret\n")]),
            snapshot(text="The preference is concise updates."),
        )
        assert result.returncode == 1
        assert "sensitive" in result.stdout
        result = invoke_plan(
            root,
            plan("a" * 64, [proposal(content="Prefer concise updates.\n", evidence_text="token: sk-test-secret")]),
            snapshot(text="token: sk-test-secret"),
        )
        assert result.returncode == 1
        assert "sensitive" in result.stdout


def test_preference_cannot_be_marked_safe() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result = invoke_plan(
            root,
            plan("a" * 64, [proposal(classification="safe")]),
            snapshot(),
        )
        assert result.returncode == 1
        assert "privacy" in result.stdout


def test_new_memory_scope_cannot_overlap_existing_selected_names() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result = invoke_plan(
            root,
            plan("a" * 64, [proposal(name="project.md", kind="project", evidence_text="The project uses TypeScript.")], ["project.md"]),
            snapshot(text="The project uses TypeScript."),
        )
        assert result.returncode == 1
        assert "new memory" in result.stdout


def test_new_memory_writes_empty_existing_scope_transactionally() -> None:
    result = run_bun(
        """
        import { mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises';
        import { join } from 'node:path';
        import { createHash } from 'node:crypto';
        import { applyConsolidationPlan } from './packages/continual-learning/extensions/consolidation-run.ts';
        const root = await mkdtemp('/tmp/pi-memory-new-');
        const harness = join(root, 'harness');
        const publicDir = join(root, 'public');
        const snapshot = { schemaVersion: 1, runId: 'run_test', scopeKey: 'c'.repeat(64), contextEnabled: true,
          entries: [{ type: 'message', message: { role: 'user', content: 'I prefer concise updates.' } }] };
        const snapshotText = JSON.stringify(snapshot, null, 2) + "\\n";
        const snapshotFile = join(root, 'snapshot.json');
        await writeFile(snapshotFile, snapshotText);
        const digest = createHash('sha256').update(snapshotText).digest('hex');
        const run = { manifest: { runId: 'run_test', scopeKey: 'c'.repeat(64), scopeDigest: 'b'.repeat(64), snapshotDigest: digest,
          harnessDir: harness, publicDir, sourceHashes: { harness: {}, public: {} } },
          paths: { snapshotFile }, released: false };
        const applied = await applyConsolidationPlan(run, {
          runId: 'run_test', scopeDigest: 'b'.repeat(64), artifactHash: digest, selected: [],
          newMemories: [{ name: 'preference.md', kind: 'preference', content: 'Prefer concise updates.\\n',
            evidence: [{ index: 0, quote: 'I prefer concise updates.' }] }],
        });
        console.log(JSON.stringify({ applied, harness: await readFile(join(harness, 'preference.md'), 'utf8'),
          publicExists: await Bun.file(join(publicDir, 'preference.md')).exists() }));
        """
    )
    assert result["applied"]["created"] == ["preference.md"]
    assert result["harness"] == "Prefer concise updates.\n"
    assert result["publicExists"] is False


def test_project_new_memory_defaults_safe_and_mirrors_to_public_root() -> None:
    result = run_bun(
        """
        import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
        import { join } from 'node:path';
        import { createHash } from 'node:crypto';
        import { applyConsolidationPlan } from './packages/continual-learning/extensions/consolidation-run.ts';
        const root = await mkdtemp('/tmp/pi-memory-project-');
        const harness = join(root, 'harness');
        const publicDir = join(root, 'public');
        const snapshot = { schemaVersion: 1, runId: 'run_project', scopeKey: 'c'.repeat(64), contextEnabled: true,
          entries: [{ type: 'message', message: { role: 'toolResult', content: 'The project uses TypeScript.' } }] };
        const snapshotText = JSON.stringify(snapshot, null, 2) + "\\n";
        const snapshotFile = join(root, 'snapshot.json');
        await writeFile(snapshotFile, snapshotText);
        const digest = createHash('sha256').update(snapshotText).digest('hex');
        const run = { manifest: { runId: 'run_project', scopeKey: 'c'.repeat(64), scopeDigest: 'b'.repeat(64), snapshotDigest: digest,
          harnessDir: harness, publicDir, sourceHashes: { harness: {}, public: {} } },
          paths: { snapshotFile }, released: false };
        const applied = await applyConsolidationPlan(run, {
          runId: 'run_project', scopeDigest: 'b'.repeat(64), artifactHash: digest, selected: [],
          newMemories: [{ name: 'project.md', kind: 'project', content: 'The project uses TypeScript.\\n',
            evidence: [{ index: 0, quote: 'The project uses TypeScript.' }] }],
        });
        console.log(JSON.stringify({ applied, harness: await readFile(join(harness, 'project.md'), 'utf8'),
          public: await readFile(join(publicDir, 'project.md'), 'utf8'),
          publicIndex: await readFile(join(publicDir, 'MEMORY.md'), 'utf8') }));
        """
    )
    assert result["applied"]["created"] == ["project.md"]
    assert result["harness"] == result["public"] == "The project uses TypeScript.\n"
    assert "(harness only)" not in result["publicIndex"]


def test_snapshot_session_context_is_immutable_but_preserves_method_binding() -> None:
    result = run_bun(
        """
        import { snapshotSessionContext } from './packages/continual-learning/extensions/consolidation-run.ts';
        const manager = {
          branch: [{ role: 'user', content: 'before' }],
          context: [{ role: 'user', content: 'context before' }],
          marker: 'manager',
          cwd: 'before-cwd',
          sessionId: 'before-session',
          sessionFile: 'before-session.jsonl',
          header: { id: 'before-session', cwd: 'before-cwd' },
          getBranch() { return this.branch; },
          buildContextEntries() { return this.context; },
          markerFromThis() { return this.marker; },
          getCwd() { return this.cwd; },
          getSessionId() { return this.sessionId; },
          getSessionFile() { return this.sessionFile; },
          getHeader() { return this.header; },
        };
        const context = { cwd: 'before-cwd', sessionManager: manager };
        const frozen = snapshotSessionContext(context);
        manager.branch[0].content = 'after';
        manager.context.push({ role: 'user', content: 'later' });
        manager.cwd = 'after-cwd';
        manager.sessionId = 'after-session';
        manager.sessionFile = 'after-session.jsonl';
        manager.header.cwd = 'after-cwd';
        context.cwd = 'after-cwd';
        console.log(JSON.stringify({
          branch: frozen.sessionManager.getBranch(),
          context: frozen.sessionManager.buildContextEntries(),
          bound: frozen.sessionManager.markerFromThis(),
          cwd: frozen.cwd,
          sessionCwd: frozen.sessionManager.getCwd(),
          sessionId: frozen.sessionManager.getSessionId(),
          sessionFile: frozen.sessionManager.getSessionFile(),
          header: frozen.sessionManager.getHeader(),
          frozen: Object.isFrozen(frozen.sessionManager.getBranch()) && Object.isFrozen(frozen.sessionManager.getBranch()[0]),
        }));
        """
    )
    assert result == {
        "branch": [{"role": "user", "content": "before"}],
        "context": [{"role": "user", "content": "context before"}],
        "bound": "manager",
        "cwd": "before-cwd",
        "sessionCwd": "before-cwd",
        "sessionId": "before-session",
        "sessionFile": "before-session.jsonl",
        "header": {"id": "before-session", "cwd": "before-cwd"},
        "frozen": True,
    }


def test_loader_budget_counts_metadata_instead_of_memory_bodies() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        memory = repo / ".memory"
        agent = root / "agent"
        memory.mkdir(parents=True)
        initialize_git_repo(repo)
        (memory / "a.md").write_text("x" * 5_000, encoding="utf-8")
        (memory / "b.md").write_text("y" * 5_000, encoding="utf-8")
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            const {{ loadAndDeduplicateMemories }} = await import('./packages/continual-learning/extensions/memory-files.ts');
            console.log(JSON.stringify(await loadAndDeduplicateMemories({json.dumps(str(repo))}, {{ maxTotalChars: 1_000 }})));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert [entry["filename"] for entry in result["entries"]] == ["a.md", "b.md"]


def test_private_memory_exposes_its_root_and_entry_filename() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        repo.mkdir()
        initialize_git_repo(repo)
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            const {{ resolveMemoryPaths }} = await import('./packages/continual-learning/extensions/memory-paths.ts');
            const {{ loadAndDeduplicateMemories, formatMemoriesBlock }} = await import('./packages/continual-learning/extensions/memory-files.ts');
            const {{ mkdir, writeFile }} = await import('node:fs/promises');
            const memory = resolveMemoryPaths({json.dumps(str(repo))});
            await mkdir(memory.harnessDir, {{ recursive: true }});
            await writeFile(memory.harnessDir + '/private.md', 'private preference\\n');
            await writeFile(memory.harnessDir + '/MEMORY.md', '# Memory Index\\n\\n- [private.md](private.md) (harness only)\\n');
            const entries = await loadAndDeduplicateMemories({json.dumps(str(repo))});
            console.log(JSON.stringify({{ entries, block: formatMemoriesBlock(entries), harness: memory.harnessDir }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result["entries"]["entries"][0]["source"] == "harness"
        assert Path(result["entries"]["entries"][0]["readPath"]).resolve() == (Path(result["harness"]).resolve() / "private.md")
        # The block declares the exact root verbatim and names the entry; the body
        # path is that root plus the row's filename, so no per-row repetition is
        # needed to keep the entry reachable.
        assert result["harness"] in result["block"]
        assert "- private.md (harness)" in result["block"]
