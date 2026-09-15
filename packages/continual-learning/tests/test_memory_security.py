from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]


def run_bun(source: str, env: dict[str, str] | None = None) -> dict[str, object]:
    result = subprocess.run(
        ["bun", "-e", source],
        cwd=REPO,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def initialize_git_repo(repo: Path) -> None:
    subprocess.run(["git", "init", "-q", str(repo)], check=True)


def test_private_directory_uses_only_the_readable_project_path() -> None:
    result = run_bun(
        """
        import { escapedProjectPath, resolveMemoryPaths } from './packages/continual-learning/extensions/memory-paths.ts';
        const memory = resolveMemoryPaths('/tmp/a-b/c');
        console.log(JSON.stringify({ readable: escapedProjectPath('/tmp/a-b/c'), memory }));
        """
    )
    assert result["memory"]["harnessDir"].endswith(result["readable"])
    assert "--" not in result["memory"]["harnessDir"].split("/")[-1]


def test_readable_private_path_uses_canonical_project_path_and_shared_scope_lock() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        physical = root / "physical"
        alias = root / "alias"
        physical.mkdir()
        alias.symlink_to(physical, target_is_directory=True)
        result = run_bun(
            f"""
            import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            const physical = resolveMemoryPaths({json.dumps(str(physical))});
            const alias = resolveMemoryPaths({json.dumps(str(alias))});
            console.log(JSON.stringify({{ physical, alias }}));
            """
        )
        assert result["physical"]["cwd"] == result["alias"]["cwd"]
        assert result["physical"]["scopeKey"] == result["alias"]["scopeKey"]
        assert result["physical"]["lockFile"] == result["alias"]["lockFile"]
        expected_name = str(physical.resolve()).replace("/", "-").replace(" ", "-")
        assert result["physical"]["harnessDir"] == str(Path(result["physical"]["agentDir"]) / "memory" / expected_name)
        assert result["alias"]["harnessDir"] == result["physical"]["harnessDir"]


def test_readable_private_root_replaces_whitespace_with_dashes() -> None:
    result = run_bun(
        """
        import { escapedProjectPath, resolveMemoryPaths } from './packages/continual-learning/extensions/memory-paths.ts';
        const memory = resolveMemoryPaths('/Users/FradSer/Documents/Home Lab');
        console.log(JSON.stringify({
          prefix: escapedProjectPath('/Users/FradSer/Documents/Home Lab'),
          name: memory.harnessDir.split('/').at(-1),
          scopeKey: memory.scopeKey,
        }));
        """
    )
    assert result["prefix"] == "-Users-FradSer-Documents-Home-Lab"
    assert result["name"] == result["prefix"]


def test_overlong_private_directory_name_fails_closed() -> None:
    result = run_bun(
        """
        import { resolveMemoryPaths } from './packages/continual-learning/extensions/memory-paths.ts';
        const cwd = '/tmp/' + '项目 home/'.repeat(80) + 'alpha';
        let error = '';
        try { resolveMemoryPaths(cwd); } catch (cause) { error = String(cause); }
        console.log(JSON.stringify({ error }));
        """
    )
    assert "portable component limit" in result["error"]


def test_non_project_without_existing_mirror_disables_public_memory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        agent = root / "agent"
        workspace.mkdir()
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            const memory = resolveMemoryPaths({json.dumps(str(workspace))});
            console.log(JSON.stringify({{ publicDir: memory.publicDir }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result == {}


def test_non_project_with_legacy_mirror_disables_public_memory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        agent = root / "agent"
        (workspace / ".memory").mkdir(parents=True)
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            const memory = resolveMemoryPaths({json.dumps(str(workspace))});
            console.log(JSON.stringify({{ publicDir: memory.publicDir }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result == {}


def test_nested_directory_with_legacy_mirror_disables_public_memory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        nested = repo / "nested"
        agent = root / "agent"
        (repo / ".git").mkdir(parents=True)
        (nested / ".memory").mkdir(parents=True)
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            const memory = resolveMemoryPaths({json.dumps(str(nested))});
            console.log(JSON.stringify({{ publicDir: memory.publicDir }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result == {}


def test_git_project_root_that_contains_agent_directory_keeps_public_memory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = repo / ".pi" / "agent"
        repo.mkdir()
        initialize_git_repo(repo)
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            const memory = resolveMemoryPaths({json.dumps(str(repo))});
            console.log(JSON.stringify({{ publicDir: memory.publicDir }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result == {"publicDir": str(repo.resolve() / ".memory")}


def test_agent_directory_disables_public_memory_even_when_legacy_mirror_exists() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        agent = root / "agent"
        (agent / ".memory").mkdir(parents=True)
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            const memory = resolveMemoryPaths({json.dumps(str(agent))});
            console.log(JSON.stringify({{ publicDir: memory.publicDir }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result == {}


def test_first_run_lock_race_reports_contention() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        repo.mkdir()
        result = run_bun(
            f"""
            import {{
              acquireConsolidationLock,
              ConsolidationLockContentionError,
              resolveConsolidationRunPaths,
            }} from './packages/continual-learning/extensions/consolidation-run.ts';
            const first = resolveConsolidationRunPaths({json.dumps(str(repo))}, 'run_first', {json.dumps(str(agent))});
            const second = resolveConsolidationRunPaths({json.dumps(str(repo))}, 'run_second', {json.dumps(str(agent))});
            const outcomes = await Promise.allSettled([
              acquireConsolidationLock(first),
              acquireConsolidationLock(second),
            ]);
            for (const outcome of outcomes) if (outcome.status === 'fulfilled') await outcome.value.release();
            console.log(JSON.stringify({{
              acquired: outcomes.filter((outcome) => outcome.status === 'fulfilled').length,
              contention: outcomes.some((outcome) => outcome.status === 'rejected' && outcome.reason instanceof ConsolidationLockContentionError),
            }}));
            """
        )
        assert result == {"acquired": 1, "contention": True}


def test_loader_rejects_symlinked_memory_files_and_orders_entries() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        (repo / ".memory").mkdir(parents=True)
        initialize_git_repo(repo)
        (root / "secret.md").write_text("private", encoding="utf-8")
        (repo / ".memory" / "z.md").write_text("z", encoding="utf-8")
        (repo / ".memory" / "a.md").write_text("a", encoding="utf-8")
        (repo / ".memory" / "leak.md").symlink_to(root / "secret.md")
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            const {{ loadAndDeduplicateMemories }} = await import('./packages/continual-learning/extensions/memory-files.ts');
            const values = await loadAndDeduplicateMemories({json.dumps(str(repo))});
            console.log(JSON.stringify(values));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert [entry["filename"] for entry in result] == ["a.md", "z.md"]
        assert all("private" not in entry["content"] for entry in result)


def test_loader_uses_strict_memory_filename_policy() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        (repo / ".memory").mkdir(parents=True)
        initialize_git_repo(repo)
        (repo / ".memory" / "valid_name.md").write_text("valid", encoding="utf-8")
        (repo / ".memory" / "prompt!.md").write_text("punctuation", encoding="utf-8")
        (repo / ".memory" / "upper.MD").write_text("upper", encoding="utf-8")
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            const {{ loadAndDeduplicateMemories }} = await import('./packages/continual-learning/extensions/memory-files.ts');
            console.log(JSON.stringify(await loadAndDeduplicateMemories({json.dumps(str(repo))})));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert [entry["filename"] for entry in result] == ["valid_name.md"]
        truncated = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            const {{ loadAndDeduplicateMemories }} = await import('./packages/continual-learning/extensions/memory-files.ts');
            console.log(JSON.stringify(await loadAndDeduplicateMemories({json.dumps(str(repo))}, {{ maxFileChars: 3 }})));
            """
        )
        assert truncated[0]["content"] == "val\n… [truncated]"


def test_invalid_memory_config_is_reported_without_crashing_or_overwriting() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        agent = Path(tmp) / "agent"
        agent.mkdir()
        (agent / "memory.json").write_text("null\n", encoding="utf-8")
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            const {{ readMemoryConfigState }} = await import('./packages/continual-learning/extensions/config.ts');
            const state = readMemoryConfigState();
            console.log(JSON.stringify({{ state, raw: await Bun.file({json.dumps(str(agent / 'memory.json'))}).text() }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result["state"]["invalid"]
        assert result["state"]["config"] == {}
        assert result["raw"] == "null\n"


def test_realpath_aliases_share_scope_for_var_tmp() -> None:
    result = run_bun(
        """
        import { resolveMemoryPaths } from './packages/continual-learning/extensions/memory-paths.ts';
        const left = resolveMemoryPaths('/var/tmp');
        const right = resolveMemoryPaths('/private/var/tmp');
        console.log(JSON.stringify({ left, right }));
        """
    )
    assert result["left"]["cwd"] == result["right"]["cwd"]
    assert result["left"]["scopeKey"] == result["right"]["scopeKey"]


def test_loader_reads_only_bounded_bytes_before_truncating() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        memory = repo / ".memory"
        memory.mkdir(parents=True)
        initialize_git_repo(repo)
        (memory / "large.md").write_bytes(b"x" * 1_000_000)
        result = run_bun(
            f"""
            import fs from 'node:fs/promises';
            const originalOpen = fs.open.bind(fs);
            let bytesRequested = 0;
            fs.open = async (target, ...args) => {{
              const handle = await originalOpen(target, ...args);
              if (String(target).endsWith('/large.md')) {{
                const originalRead = handle.read.bind(handle);
                handle.read = async (buffer, offset, length, position) => {{
                  bytesRequested += length;
                  return originalRead(buffer, offset, length, position);
                }};
              }}
              return handle;
            }};
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            const {{ loadAndDeduplicateMemories }} = await import('./packages/continual-learning/extensions/memory-files.ts');
            const values = await loadAndDeduplicateMemories({json.dumps(str(repo))}, {{ maxFileChars: 3 }});
            console.log(JSON.stringify({{ values, bytesRequested }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result["bytesRequested"] <= 16
        assert result["values"][0]["content"] == "xxx\n… [truncated]"


def test_loader_fails_closed_when_root_is_replaced_by_a_symlink() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        memory = repo / ".memory"
        outside = root / "outside"
        memory.mkdir(parents=True)
        outside.mkdir()
        (memory / "a.md").write_text("safe", encoding="utf-8")
        (outside / "a.md").write_text("secret", encoding="utf-8")
        result = run_bun(
            f"""
            import fs from 'node:fs/promises';
            const originalOpen = fs.open.bind(fs);
            let swapped = false;
            fs.open = async (target, ...args) => {{
              if (!swapped && String(target).endsWith('/a.md')) {{
                await fs.rename({json.dumps(str(memory))}, {json.dumps(str(root / 'original-memory'))});
                await fs.symlink({json.dumps(str(outside))}, {json.dumps(str(memory))}, 'dir');
                swapped = true;
              }}
              return originalOpen(target, ...args);
            }};
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(root / 'agent'))};
            const {{ loadAndDeduplicateMemories }} = await import('./packages/continual-learning/extensions/memory-files.ts');
            console.log(JSON.stringify(await loadAndDeduplicateMemories({json.dumps(str(repo))})));
            """,
            {"PI_CODING_AGENT_DIR": str(root / "agent")},
        )
        assert result == []


def test_loader_skips_a_child_replaced_by_a_symlink() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        memory = repo / ".memory"
        secret = root / "secret.md"
        memory.mkdir(parents=True)
        secret.write_text("secret", encoding="utf-8")
        (memory / "a.md").write_text("safe", encoding="utf-8")
        result = run_bun(
            f"""
            import fs from 'node:fs/promises';
            const originalOpen = fs.open.bind(fs);
            let swapped = false;
            fs.open = async (target, ...args) => {{
              if (!swapped && String(target).endsWith('/a.md')) {{
                await fs.unlink(target);
                await fs.symlink({json.dumps(str(secret))}, target);
                swapped = true;
              }}
              return originalOpen(target, ...args);
            }};
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(root / 'agent'))};
            const {{ loadAndDeduplicateMemories }} = await import('./packages/continual-learning/extensions/memory-files.ts');
            console.log(JSON.stringify(await loadAndDeduplicateMemories({json.dumps(str(repo))})));
            """,
            {"PI_CODING_AGENT_DIR": str(root / "agent")},
        )
        assert result == []


def test_memory_config_rejects_symlinked_roots_and_targets() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        outside = root / "outside"
        outside.mkdir()
        symlinked_agent = root / "agent-link"
        symlinked_agent.symlink_to(outside, target_is_directory=True)
        root_result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(symlinked_agent))};
            const {{ writeMemoryConfig }} = await import('./packages/continual-learning/extensions/config.ts');
            let error = '';
            try {{ writeMemoryConfig({{ provider: 'openai', model: 'gpt-5' }}); }} catch (cause) {{ error = String(cause); }}
            console.log(JSON.stringify({{ error, exists: await Bun.file({json.dumps(str(outside / 'memory.json'))}).exists() }}));
            """,
            {"PI_CODING_AGENT_DIR": str(symlinked_agent)},
        )
        assert root_result["error"]
        assert root_result["exists"] is False

        agent = root / "agent"
        agent.mkdir()
        target = outside / "memory.json"
        target.write_text("outside\\n", encoding="utf-8")
        (agent / "memory.json").symlink_to(target)
        target_result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            const {{ writeMemoryConfig }} = await import('./packages/continual-learning/extensions/config.ts');
            let error = '';
            try {{ writeMemoryConfig({{ provider: 'openai', model: 'gpt-5' }}); }} catch (cause) {{ error = String(cause); }}
            console.log(JSON.stringify({{ error, raw: await Bun.file({json.dumps(str(target))}).text() }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert target_result["error"]
        assert target_result["raw"] == "outside\\n"


def test_memory_config_writes_atomically_under_a_safe_agent_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        agent = Path(tmp) / "agent"
        agent.mkdir()
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            const {{ writeMemoryConfig }} = await import('./packages/continual-learning/extensions/config.ts');
            writeMemoryConfig({{ provider: 'openai', model: 'gpt-5' }});
            console.log(JSON.stringify({{ raw: await Bun.file({json.dumps(str(agent / 'memory.json'))}).text(), files: await (await import('node:fs/promises')).readdir({json.dumps(str(agent))}) }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert json.loads(result["raw"]) == {"provider": "openai", "model": "gpt-5"}
        assert result["files"] == ["memory.json"]


def test_stale_dead_owner_lock_is_reclaimed_but_live_owner_is_contention() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        repo.mkdir()
        result = run_bun(
            f"""
            import {{
              acquireConsolidationLock,
              ConsolidationLockContentionError,
              resolveConsolidationRunPaths,
            }} from './packages/continual-learning/extensions/consolidation-run.ts';
            import {{ readFileSync, writeFileSync, mkdirSync }} from 'node:fs';
            import {{ hostname }} from 'node:os';
            import {{ spawnSync }} from 'node:child_process';
            import {{ join }} from 'node:path';
            const paths = resolveConsolidationRunPaths({json.dumps(str(repo))}, 'run_stale', {json.dumps(str(agent))});
            mkdirSync(paths.memory.runsDir, {{ recursive: true }});
            const exited = spawnSync('true');
            const deadPid = exited.pid ?? 999999;
            const owner = {{
              runId: 'run_stale', scopeKey: paths.memory.scopeKey, cwd: {json.dumps(str(repo))},
              pid: deadPid, hostname: hostname(),
              acquiredAt: new Date().toISOString(), nonce: 'deadbeef',
            }};
            writeFileSync(paths.lockFile, JSON.stringify(owner) + '\\n');
            const reclaimed = await acquireConsolidationLock(paths);
            const reclaimWorked = reclaimed.owner.pid === process.pid;
            await reclaimed.release();

            const liveOwner = {{ ...owner, pid: process.pid, nonce: 'livebeef' }};
            writeFileSync(paths.lockFile, JSON.stringify(liveOwner) + '\\n');
            let contention = false;
            try {{ await acquireConsolidationLock(paths); }} catch (error) {{
              contention = error instanceof ConsolidationLockContentionError && error.owner?.nonce === 'livebeef';
            }}
            console.log(JSON.stringify({{ reclaimWorked, contention }}));
            """
        )
        assert result == {"reclaimWorked": True, "contention": True}


def test_lock_reclaim_is_atomic_quarantine_with_bounded_retry() -> None:
    security_source = (PACKAGE / "extensions" / "consolidation-run.ts").read_text(encoding="utf-8")
    # Reclaim renames the lock aside and verifies the nonce before discarding.
    assert "async function quarantineDeadOwnerLock(" in security_source
    assert 'await fsp.rename(paths.lockFile, quarantine);' in security_source
    assert "quarantined.nonce !== deadOwner.nonce" in security_source
    assert ".reclaim`" in security_source
    # Retry after reclaim is bounded to a single attempt.
    assert "for (let attempt = 0; ; attempt += 1) {" in security_source
    assert "attempt === 0 ? await readConsolidationLock(paths.lockFile) : undefined" in security_source
    assert "return acquireConsolidationLock(" not in security_source


def test_mirror_drift_is_normalized_before_the_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        repo.mkdir()
        initialize_git_repo(repo)
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ normalizeMirrorDrift }} from './packages/continual-learning/extensions/consolidation-run.ts';
            import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            import {{ mkdirSync, writeFileSync, readFileSync, rmSync, existsSync, utimesSync }} from 'node:fs';
            const memory = resolveMemoryPaths({json.dumps(str(repo))});
            mkdirSync(memory.harnessDir, {{ recursive: true }});
            mkdirSync(memory.publicDir, {{ recursive: true }});
            // Drifted safe file A: harness newer (session wrote harness only).
            writeFileSync(memory.harnessDir + '/a.md', 'v2\\n');
            writeFileSync(memory.publicDir + '/a.md', 'v1\\n');
            utimesSync(memory.harnessDir + '/a.md', 2000, 2000);
            utimesSync(memory.publicDir + '/a.md', 1000, 1000);
            // Drifted safe file B: public newer (git-tracked update never reached harness).
            writeFileSync(memory.harnessDir + '/b.md', 'old\\n');
            writeFileSync(memory.publicDir + '/b.md', 'new\\n');
            utimesSync(memory.harnessDir + '/b.md', 1000, 1000);
            utimesSync(memory.publicDir + '/b.md', 3000, 3000);
            // Private-marked file leaked into public.
            writeFileSync(memory.harnessDir + '/secret.md', 'private\\n');
            writeFileSync(memory.harnessDir + '/MEMORY.md', '# Memory Index\\n\\n- [a.md](a.md)\\n- [secret.md](secret.md) (harness only)\\n');
            writeFileSync(memory.publicDir + '/secret.md', 'private\\n');
            writeFileSync(memory.publicDir + '/MEMORY.md', '# Memory Index\\n');
            // Orphan public file with no harness copy.
            writeFileSync(memory.publicDir + '/orphan.md', 'orphan\\n');
            // Safe file missing from public entirely.
            writeFileSync(memory.harnessDir + '/d.md', 'd\\n');

            const outcome = await normalizeMirrorDrift(memory);
            console.log(JSON.stringify({{
              repaired: outcome.repaired,
              removed: outcome.removed,
              aMatches: readFileSync(memory.harnessDir + '/a.md', 'utf8') === readFileSync(memory.publicDir + '/a.md', 'utf8'),
              bHarnessUpdated: readFileSync(memory.harnessDir + '/b.md', 'utf8'),
              dMirrored: readFileSync(memory.publicDir + '/d.md', 'utf8'),
              secretGone: !existsSync(memory.publicDir + '/secret.md'),
              orphanGone: !existsSync(memory.publicDir + '/orphan.md'),
              publicIndex: readFileSync(memory.publicDir + '/MEMORY.md', 'utf8'),
            }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result["repaired"] == [
            {"name": "a.md", "direction": "harness-to-public"},
            {"name": "b.md", "direction": "public-to-harness"},
            {"name": "d.md", "direction": "harness-to-public"},
        ]
        assert result["removed"] == ["orphan.md", "secret.md"]
        assert result["aMatches"] is True
        assert result["bHarnessUpdated"] == "new\n"
        assert result["dMirrored"] == "d\n"
        assert result["secretGone"] is True
        assert result["orphanGone"] is True
        assert "- [a.md](a.md)" in result["publicIndex"]
        assert "(harness only)" not in result["publicIndex"]


def test_missing_harness_root_imports_public_instead_of_deleting() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        repo.mkdir()
        initialize_git_repo(repo)
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ normalizeMirrorDrift }} from './packages/continual-learning/extensions/consolidation-run.ts';
            import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            import {{ mkdirSync, writeFileSync, readFileSync }} from 'node:fs';
            const memory = resolveMemoryPaths({json.dumps(str(repo))});
            mkdirSync(memory.publicDir, {{ recursive: true }});
            writeFileSync(memory.publicDir + '/kept.md', 'kept\\n');
            const outcome = await normalizeMirrorDrift(memory);
            console.log(JSON.stringify({{
              repaired: outcome.repaired,
              removed: outcome.removed,
              imported: readFileSync(memory.harnessDir + '/kept.md', 'utf8'),
            }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result == {
            "repaired": [{"name": "kept.md", "direction": "public-to-harness"}],
            "removed": [],
            "imported": "kept\n",
        }


def test_legacy_migration_keeps_conflicting_source_when_destination_bytes_differ() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        repo.mkdir()
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ migrateLegacyMemoryDirs }} from './packages/continual-learning/extensions/memory-files.ts';
            import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            import {{ existsSync, mkdirSync, readFileSync, writeFileSync }} from 'node:fs';
            const memory = resolveMemoryPaths({json.dumps(str(repo))});
            const legacyDir = memory.agentDir + '/memory/' + memory.scopeKey;
            mkdirSync(memory.harnessDir, {{ recursive: true }});
            mkdirSync(legacyDir, {{ recursive: true }});
            writeFileSync(memory.harnessDir + '/conflict.md', 'destination\\n');
            writeFileSync(legacyDir + '/conflict.md', 'legacy\\n');
            const removed = await migrateLegacyMemoryDirs(memory);
            console.log(JSON.stringify({{
              removed,
              legacyKept: existsSync(legacyDir + '/conflict.md'),
              destination: readFileSync(memory.harnessDir + '/conflict.md', 'utf8'),
            }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result["removed"] == []
        assert result["legacyKept"] is True
        assert result["destination"] == "destination\n"


def test_legacy_migration_rejects_symlinked_source_files_and_keeps_all_sources() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        outside = root / "outside.md"
        repo.mkdir()
        outside.write_text("outside\n", encoding="utf-8")
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ migrateLegacyMemoryDirs }} from './packages/continual-learning/extensions/memory-files.ts';
            import {{ escapedProjectPath, resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            import {{ existsSync, mkdirSync, readFileSync, symlinkSync, writeFileSync }} from 'node:fs';
            const memory = resolveMemoryPaths({json.dumps(str(repo))});
            const hashedDir = memory.agentDir + '/memory/' + memory.scopeKey;
            const readableDir = memory.agentDir + '/memory/' + escapedProjectPath(memory.cwd);
            mkdirSync(hashedDir, {{ recursive: true }});
            mkdirSync(readableDir, {{ recursive: true }});
            writeFileSync(hashedDir + '/valid.md', 'valid\\n');
            symlinkSync({json.dumps(str(outside))}, readableDir + '/linked.md');
            let error = '';
            try {{ await migrateLegacyMemoryDirs(memory); }} catch (cause) {{ error = String(cause); }}
            console.log(JSON.stringify({{
              error,
              hashedKept: existsSync(hashedDir + '/valid.md'),
              readableKept: existsSync(readableDir + '/linked.md'),
              destinationCreated: existsSync(memory.harnessDir),
              outside: readFileSync({json.dumps(str(outside))}, 'utf8'),
            }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result["error"]
        assert result["hashedKept"] is True
        assert result["readableKept"] is True
        assert result["destinationCreated"] is True
        assert result["outside"] == "outside\n"


def test_legacy_migration_rejects_any_symlinked_destination_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        outside = root / "outside.md"
        repo.mkdir()
        outside.write_text("outside\n", encoding="utf-8")
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ migrateLegacyMemoryDirs }} from './packages/continual-learning/extensions/memory-files.ts';
            import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            import {{ existsSync, mkdirSync, readFileSync, symlinkSync, writeFileSync }} from 'node:fs';
            const memory = resolveMemoryPaths({json.dumps(str(repo))});
            const legacyDir = memory.agentDir + '/memory/' + memory.scopeKey;
            mkdirSync(legacyDir, {{ recursive: true }});
            mkdirSync(memory.harnessDir, {{ recursive: true }});
            writeFileSync(legacyDir + '/keep.md', 'legacy\\n');
            symlinkSync({json.dumps(str(outside))}, memory.harnessDir + '/unrelated.md');
            let error = '';
            try {{ await migrateLegacyMemoryDirs(memory); }} catch (cause) {{ error = String(cause); }}
            console.log(JSON.stringify({{
              error,
              legacyKept: existsSync(legacyDir + '/keep.md'),
              outside: readFileSync({json.dumps(str(outside))}, 'utf8'),
            }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result["error"]
        assert result["legacyKept"] is True
        assert result["outside"] == "outside\n"


def test_legacy_hashed_scope_migration_unions_destination_private_markers_on_conflict() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        repo.mkdir()
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ migrateLegacyMemoryDirs }} from './packages/continual-learning/extensions/memory-files.ts';
            import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            import {{ mkdirSync, writeFileSync, readFileSync }} from 'node:fs';
            const memory = resolveMemoryPaths({json.dumps(str(repo))});
            const legacyDir = memory.agentDir + '/memory/' + memory.scopeKey;
            mkdirSync(memory.harnessDir, {{ recursive: true }});
            mkdirSync(legacyDir, {{ recursive: true }});
            writeFileSync(memory.harnessDir + '/conflict.md', 'destination private\\n');
            writeFileSync(memory.harnessDir + '/MEMORY.md', '# Memory Index\\n\\n- [conflict.md](conflict.md) (harness only)\\n');
            writeFileSync(legacyDir + '/conflict.md', 'legacy safe\\n');
            writeFileSync(legacyDir + '/source-secret.md', 'legacy private\\n');
            writeFileSync(legacyDir + '/MEMORY.md', '# Memory Index\\n\\n- [conflict.md](conflict.md)\\n- [source-secret.md](source-secret.md) (harness only)\\n');
            await migrateLegacyMemoryDirs(memory);
            console.log(JSON.stringify({{
              conflict: readFileSync(memory.harnessDir + '/conflict.md', 'utf8'),
              index: readFileSync(memory.harnessDir + '/MEMORY.md', 'utf8'),
            }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result["conflict"] == "destination private\n"
        assert "- [conflict.md](conflict.md) (harness only)" in result["index"]
        assert "- [source-secret.md](source-secret.md) (harness only)" in result["index"]


def test_old_hashed_and_whitespace_scopes_migrate_into_readable_root() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "Home Lab"
        agent = root / "agent"
        repo.mkdir()
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ loadAndDeduplicateMemories }} from './packages/continual-learning/extensions/memory-files.ts';
            import {{ migrateLegacyMemoryDirs }} from './packages/continual-learning/extensions/memory-files.ts';
            import {{ escapedProjectPath, resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            import {{ mkdirSync, writeFileSync, readFileSync, existsSync }} from 'node:fs';
            const memory = resolveMemoryPaths({json.dumps(str(repo))});
            const hashedDir = memory.agentDir + '/memory/' + memory.scopeKey;
            const readableDir = memory.agentDir + '/memory/' + escapedProjectPath(memory.cwd);
            const whitespaceDir = memory.agentDir + '/memory/' + memory.cwd.replace(/[\\\\/]+/g, '-');
            mkdirSync(hashedDir, {{ recursive: true }});
            mkdirSync(readableDir, {{ recursive: true }});
            mkdirSync(whitespaceDir, {{ recursive: true }});
            writeFileSync(hashedDir + '/hashed.md', 'hashed legacy\\n');
            writeFileSync(hashedDir + '/MEMORY.md', '# Memory Index\\n\\n- [hashed.md](hashed.md)\\n');
            writeFileSync(readableDir + '/readable.md', 'readable legacy\\n');
            writeFileSync(readableDir + '/MEMORY.md', '# Memory Index\\n\\n- [readable.md](readable.md)\\n');
            writeFileSync(whitespaceDir + '/secret.md', 'private legacy\\n');
            writeFileSync(whitespaceDir + '/MEMORY.md', '# Memory Index\\n\\n- [secret.md](secret.md) (harness only)\\n');

            const entries = await loadAndDeduplicateMemories({json.dumps(str(repo))});
            console.log(JSON.stringify({{
              destinationName: memory.harnessDir.split('/').at(-1),
              expectedDestinationName: escapedProjectPath(memory.cwd),
              hashedGone: !existsSync(hashedDir),
              readableGone: !existsSync(readableDir),
              whitespaceGone: !existsSync(whitespaceDir),
              index: readFileSync(memory.harnessDir + '/MEMORY.md', 'utf8'),
              injected: entries.map((entry) => entry.filename),
              secondRunStable: (await migrateLegacyMemoryDirs(memory)).length === 0,
            }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result["destinationName"] == result["expectedDestinationName"]
        assert result["hashedGone"] is True
        assert result["readableGone"] is False
        assert result["whitespaceGone"] is True
        assert "- [hashed.md](hashed.md)" in result["index"]
        assert "- [readable.md](readable.md)" in result["index"]
        assert "- [secret.md](secret.md) (harness only)" in result["index"]
        assert result["injected"] == ["hashed.md", "readable.md", "secret.md"]
        assert result["secondRunStable"] is True


def test_legacy_migration_rejects_a_symlinked_destination() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        outside = root / "outside"
        repo.mkdir()
        outside.mkdir()
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ migrateLegacyMemoryDirs }} from './packages/continual-learning/extensions/memory-files.ts';
            import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            import {{ existsSync, mkdirSync, readFileSync, symlinkSync, writeFileSync }} from 'node:fs';
            const memory = resolveMemoryPaths({json.dumps(str(repo))});
            const legacyDir = memory.agentDir + '/memory/' + memory.scopeKey;
            mkdirSync(legacyDir, {{ recursive: true }});
            writeFileSync(legacyDir + '/keep.md', 'legacy\\n');
            writeFileSync({json.dumps(str(outside / 'sentinel.md'))}, 'outside\\n');
            symlinkSync({json.dumps(str(outside))}, memory.harnessDir, 'dir');
            let error = '';
            try {{ await migrateLegacyMemoryDirs(memory); }} catch (cause) {{ error = String(cause); }}
            console.log(JSON.stringify({{
              error,
              legacyKept: existsSync(legacyDir + '/keep.md'),
              outside: readFileSync({json.dumps(str(outside / 'sentinel.md'))}, 'utf8'),
              outsideMigrated: existsSync({json.dumps(str(outside / 'keep.md'))}),
            }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result["error"]
        assert result["legacyKept"] is True
        assert result["outside"] == "outside\n"
        assert result["outsideMigrated"] is False


def test_legacy_migration_rejects_a_symlinked_source() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        outside = root / "outside"
        repo.mkdir()
        outside.mkdir()
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ migrateLegacyMemoryDirs }} from './packages/continual-learning/extensions/memory-files.ts';
            import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            import {{ existsSync, mkdirSync, readFileSync, symlinkSync, writeFileSync }} from 'node:fs';
            const memory = resolveMemoryPaths({json.dumps(str(repo))});
            const legacyDir = memory.agentDir + '/memory/' + memory.scopeKey;
            mkdirSync(memory.agentDir + '/memory', {{ recursive: true }});
            writeFileSync({json.dumps(str(outside / 'keep.md'))}, 'outside\\n');
            symlinkSync({json.dumps(str(outside))}, legacyDir, 'dir');
            let error = '';
            try {{ await migrateLegacyMemoryDirs(memory); }} catch (cause) {{ error = String(cause); }}
            console.log(JSON.stringify({{
              error,
              sourceKept: existsSync(legacyDir),
              destinationCreated: existsSync(memory.harnessDir),
              outside: readFileSync({json.dumps(str(outside / 'keep.md'))}, 'utf8'),
            }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result["error"]
        assert result["sourceKept"] is True
        assert result["destinationCreated"] is False
        assert result["outside"] == "outside\n"


def test_failed_legacy_application_restores_the_destination_predecessor() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        repo.mkdir()
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ rename }} from 'node:fs/promises';
            const {{ migrateLegacyMemoryDirsForTest }} = await import('./packages/continual-learning/extensions/memory-files.ts');
            const {{ resolveMemoryPaths }} = await import('./packages/continual-learning/extensions/memory-paths.ts');
            const {{ existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync }} = await import('node:fs');
            const memory = resolveMemoryPaths({json.dumps(str(repo))});
            const legacyDir = memory.agentDir + '/memory/' + memory.scopeKey;
            mkdirSync(legacyDir, {{ recursive: true }});
            mkdirSync(memory.harnessDir, {{ recursive: true }});
            writeFileSync(legacyDir + '/a.md', 'legacy a\\n');
            writeFileSync(legacyDir + '/b.md', 'legacy b\\n');
            writeFileSync(memory.harnessDir + '/existing.md', 'existing\\n');
            writeFileSync(memory.harnessDir + '/MEMORY.md', '# predecessor\\n');
            let error = '';
            try {{
              await migrateLegacyMemoryDirsForTest(memory, [], async (source, target) => {{
                if (String(target).endsWith('/MEMORY.md')) throw new Error('injected index failure');
                await rename(source, target);
              }});
            }} catch (cause) {{ error = String(cause); }}
            console.log(JSON.stringify({{
              error,
              legacyFiles: readdirSync(legacyDir).sort(),
              destinationFiles: readdirSync(memory.harnessDir).sort(),
              destinationIndex: readFileSync(memory.harnessDir + '/MEMORY.md', 'utf8'),
              existing: readFileSync(memory.harnessDir + '/existing.md', 'utf8'),
              aCreated: existsSync(memory.harnessDir + '/a.md'),
              bCreated: existsSync(memory.harnessDir + '/b.md'),
            }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result["error"]
        assert result["legacyFiles"] == ["a.md", "b.md"]
        assert result["destinationFiles"] == ["MEMORY.md", "existing.md"]
        assert result["destinationIndex"] == "# predecessor\n"
        assert result["existing"] == "existing\n"
        assert result["aCreated"] is False
        assert result["bCreated"] is False


def test_conflicting_legacy_private_marker_does_not_reclassify_canonical_bytes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        repo.mkdir()
        result = run_bun(
            f'''
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ migrateLegacyMemoryDirs }} from './packages/continual-learning/extensions/memory-files.ts';
            import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            import {{ existsSync, mkdirSync, readFileSync, writeFileSync }} from 'node:fs';
            const memory = resolveMemoryPaths({json.dumps(str(repo))});
            const legacyDir = memory.agentDir + '/memory/' + memory.scopeKey;
            mkdirSync(legacyDir, {{ recursive: true }}); mkdirSync(memory.harnessDir, {{ recursive: true }});
            writeFileSync(legacyDir + '/same.md', 'LEGACY PRIVATE\\n');
            writeFileSync(legacyDir + '/MEMORY.md', '# Memory Index\\n\\n- [same.md](same.md) (harness only)\\n');
            writeFileSync(memory.harnessDir + '/same.md', 'CURRENT SAFE\\n');
            writeFileSync(memory.harnessDir + '/MEMORY.md', '# Memory Index\\n\\n- [same.md](same.md)\\n');
            console.log(JSON.stringify({{
              removed: await migrateLegacyMemoryDirs(memory),
              destination: readFileSync(memory.harnessDir + '/same.md', 'utf8'),
              index: readFileSync(memory.harnessDir + '/MEMORY.md', 'utf8'),
              legacyStillExists: existsSync(legacyDir),
            }}));
            ''',
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result["removed"] == []
        assert result["destination"] == "CURRENT SAFE\n"
        assert "(harness only)" not in result["index"]
        assert result["legacyStillExists"] is True


def test_failed_legacy_source_quarantine_restores_source_and_destination() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        repo.mkdir()
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ rename }} from 'node:fs/promises';
            import {{ migrateLegacyMemoryDirsForTest }} from './packages/continual-learning/extensions/memory-files.ts';
            import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            import {{ existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync }} from 'node:fs';
            const memory = resolveMemoryPaths({json.dumps(str(repo))});
            const legacyDir = memory.agentDir + '/memory/' + memory.scopeKey;
            mkdirSync(legacyDir, {{ recursive: true }});
            mkdirSync(memory.harnessDir, {{ recursive: true }});
            writeFileSync(legacyDir + '/legacy.md', 'legacy\\n');
            writeFileSync(legacyDir + '/MEMORY.md', '# legacy index\\n');
            writeFileSync(memory.harnessDir + '/existing.md', 'existing\\n');
            writeFileSync(memory.harnessDir + '/MEMORY.md', '# predecessor\\n');
            let error = '';
            try {{
              await migrateLegacyMemoryDirsForTest(memory, [], async (source, target) => {{
                if (String(source) === legacyDir) throw new Error('injected quarantine failure');
                await rename(source, target);
              }});
            }} catch (cause) {{ error = String(cause); }}
            console.log(JSON.stringify({{
              error,
              sourceFiles: readdirSync(legacyDir).sort(),
              sourceMemory: readFileSync(legacyDir + '/legacy.md', 'utf8'),
              destinationFiles: readdirSync(memory.harnessDir).sort(),
              destinationIndex: readFileSync(memory.harnessDir + '/MEMORY.md', 'utf8'),
              destinationExisting: readFileSync(memory.harnessDir + '/existing.md', 'utf8'),
              destinationLegacyExists: existsSync(memory.harnessDir + '/legacy.md'),
              memoryRootEntries: readdirSync(memory.agentDir + '/memory').sort(),
              expectedMemoryRootEntries: [legacyDir.split('/').at(-1), memory.harnessDir.split('/').at(-1)].sort(),
            }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert "injected quarantine failure" in result["error"]
        assert result["sourceFiles"] == ["MEMORY.md", "legacy.md"]
        assert result["sourceMemory"] == "legacy\n"
        assert result["destinationFiles"] == ["MEMORY.md", "existing.md"]
        assert result["destinationIndex"] == "# predecessor\n"
        assert result["destinationExisting"] == "existing\n"
        assert result["destinationLegacyExists"] is False
        assert result["memoryRootEntries"] == result["expectedMemoryRootEntries"]


def test_later_legacy_source_quarantine_failure_restores_earlier_source_and_destination() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "Home Lab"
        agent = root / "agent"
        repo.mkdir()
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ rename }} from 'node:fs/promises';
            import {{ migrateLegacyMemoryDirsForTest }} from './packages/continual-learning/extensions/memory-files.ts';
            import {{ escapedProjectPath, resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            import {{ existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync }} from 'node:fs';
            const memory = resolveMemoryPaths({json.dumps(str(repo))});
            const sources = [
              memory.agentDir + '/memory/' + memory.scopeKey,
              memory.agentDir + '/memory/' + memory.cwd.replace(/[\\/]+/g, '-'),
            ].sort();
            mkdirSync(sources[0], {{ recursive: true }});
            mkdirSync(sources[1], {{ recursive: true }});
            mkdirSync(memory.harnessDir, {{ recursive: true }});
            writeFileSync(sources[0] + '/first.md', 'first\\n');
            writeFileSync(sources[1] + '/second.md', 'second\\n');
            writeFileSync(memory.harnessDir + '/existing.md', 'existing\\n');
            writeFileSync(memory.harnessDir + '/MEMORY.md', '# predecessor\\n');
            let error = '';
            try {{
              await migrateLegacyMemoryDirsForTest(memory, [], async (source, target) => {{
                if (String(source) === sources[1]) throw new Error('injected second quarantine failure');
                await rename(source, target);
              }});
            }} catch (cause) {{ error = String(cause); }}
            console.log(JSON.stringify({{
              error,
              firstSourceFiles: readdirSync(sources[0]).sort(),
              secondSourceFiles: readdirSync(sources[1]).sort(),
              firstSourceBytes: readFileSync(sources[0] + '/first.md', 'utf8'),
              secondSourceBytes: readFileSync(sources[1] + '/second.md', 'utf8'),
              destinationFiles: readdirSync(memory.harnessDir).sort(),
              destinationIndex: readFileSync(memory.harnessDir + '/MEMORY.md', 'utf8'),
              destinationExisting: readFileSync(memory.harnessDir + '/existing.md', 'utf8'),
              destinationFirstExists: existsSync(memory.harnessDir + '/first.md'),
              destinationSecondExists: existsSync(memory.harnessDir + '/second.md'),
              memoryRootEntries: readdirSync(memory.agentDir + '/memory').sort(),
              expectedMemoryRootEntries: [...sources.map((source) => source.split('/').at(-1)), memory.harnessDir.split('/').at(-1)].sort(),
            }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert "injected second quarantine failure" in result["error"]
        assert result["firstSourceFiles"] == ["first.md"]
        assert result["secondSourceFiles"] == ["second.md"]
        assert result["firstSourceBytes"] == "first\n"
        assert result["secondSourceBytes"] == "second\n"
        assert result["destinationFiles"] == ["MEMORY.md", "existing.md"]
        assert result["destinationIndex"] == "# predecessor\n"
        assert result["destinationExisting"] == "existing\n"
        assert result["destinationFirstExists"] is False
        assert result["destinationSecondExists"] is False
        assert result["memoryRootEntries"] == result["expectedMemoryRootEntries"]
