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


def test_scope_key_does_not_collide_for_path_punctuation() -> None:
    result = run_bun(
        """
        import { resolveMemoryPaths } from './packages/memory/extensions/memory-paths.ts';
        console.log(JSON.stringify({
          left: resolveMemoryPaths('/tmp/a-b/c').scopeKey,
          right: resolveMemoryPaths('/tmp/a/b-c').scopeKey,
        }));
        """
    )
    assert result["left"] != result["right"]


def test_real_and_symlinked_project_paths_share_scope_lock() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        physical = root / "physical"
        alias = root / "alias"
        physical.mkdir()
        alias.symlink_to(physical, target_is_directory=True)
        result = run_bun(
            f"""
            import {{ resolveMemoryPaths }} from './packages/memory/extensions/memory-paths.ts';
            const physical = resolveMemoryPaths({json.dumps(str(physical))});
            const alias = resolveMemoryPaths({json.dumps(str(alias))});
            console.log(JSON.stringify({{ physical, alias }}));
            """
        )
        assert result["physical"]["cwd"] == result["alias"]["cwd"]
        assert result["physical"]["scopeKey"] == result["alias"]["scopeKey"]
        assert result["physical"]["lockFile"] == result["alias"]["lockFile"]


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
            }} from './packages/memory/extensions/consolidation-run.ts';
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
        (root / "secret.md").write_text("private", encoding="utf-8")
        (repo / ".memory" / "z.md").write_text("z", encoding="utf-8")
        (repo / ".memory" / "a.md").write_text("a", encoding="utf-8")
        (repo / ".memory" / "leak.md").symlink_to(root / "secret.md")
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            const {{ loadAndDeduplicateMemories }} = await import('./packages/memory/extensions/memory-files.ts');
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
        (repo / ".memory" / "valid_name.md").write_text("valid", encoding="utf-8")
        (repo / ".memory" / "prompt!.md").write_text("punctuation", encoding="utf-8")
        (repo / ".memory" / "upper.MD").write_text("upper", encoding="utf-8")
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            const {{ loadAndDeduplicateMemories }} = await import('./packages/memory/extensions/memory-files.ts');
            console.log(JSON.stringify(await loadAndDeduplicateMemories({json.dumps(str(repo))})));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert [entry["filename"] for entry in result] == ["valid_name.md"]
        truncated = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            const {{ loadAndDeduplicateMemories }} = await import('./packages/memory/extensions/memory-files.ts');
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
            const {{ readMemoryConfigState }} = await import('./packages/memory/extensions/config.ts');
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
        import { resolveMemoryPaths } from './packages/memory/extensions/memory-paths.ts';
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
            const {{ loadAndDeduplicateMemories }} = await import('./packages/memory/extensions/memory-files.ts');
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
            const {{ loadAndDeduplicateMemories }} = await import('./packages/memory/extensions/memory-files.ts');
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
            const {{ loadAndDeduplicateMemories }} = await import('./packages/memory/extensions/memory-files.ts');
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
            const {{ writeMemoryConfig }} = await import('./packages/memory/extensions/config.ts');
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
            const {{ writeMemoryConfig }} = await import('./packages/memory/extensions/config.ts');
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
            const {{ writeMemoryConfig }} = await import('./packages/memory/extensions/config.ts');
            writeMemoryConfig({{ provider: 'openai', model: 'gpt-5' }});
            console.log(JSON.stringify({{ raw: await Bun.file({json.dumps(str(agent / 'memory.json'))}).text(), files: await (await import('node:fs/promises')).readdir({json.dumps(str(agent))}) }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert json.loads(result["raw"]) == {"provider": "openai", "model": "gpt-5"}
        assert result["files"] == ["memory.json"]
