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


def test_private_directory_lock_and_runs_use_flat_readable_scope() -> None:
    result = run_bun(
        """
        import { escapedProjectPath, resolveMemoryPaths } from './packages/continual-learning/extensions/memory-paths.ts';
        const memory = resolveMemoryPaths('/tmp/a-b/c');
        console.log(JSON.stringify({ readable: escapedProjectPath('/tmp/a-b/c'), memory }));
        """
    )
    name = result["memory"]["harnessDir"].split("/")[-1]
    assert name == result["readable"] == result["memory"]["scopeKey"]
    assert Path(result["memory"]["lockFile"]) == Path(result["memory"]["agentDir"]) / "memory" / "locks" / (name + ".lock")
    assert Path(result["memory"]["runsDir"]).name == name
    assert name == "--tmp-a-b-c--"
    assert len(name.encode("utf8")) <= 240


def test_private_directories_and_locks_coexist_for_lock_suffix_projects() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_bun(
            f"""
            import {{ acquireConsolidationLock, resolveConsolidationRunPaths }} from './packages/continual-learning/extensions/consolidation-run.ts';
            import {{ mkdirSync, existsSync, statSync }} from 'node:fs';
            import {{ join, dirname }} from 'node:path';
            const root = {json.dumps(tmp)};
            const projects = ['foo', 'foo.lock'].map(name => {{
              const cwd = join(root, name);
              mkdirSync(cwd);
              const paths = resolveConsolidationRunPaths(cwd, 'run_namespace', join(root, 'agent'));
              mkdirSync(paths.memory.harnessDir, {{ recursive: true }});
              return paths;
            }});
            const locks = [];
            let error = '';
            let simultaneous = false;
            try {{
              for (const paths of projects) locks.push(await acquireConsolidationLock(paths));
              simultaneous = projects.every(paths => existsSync(paths.lockFile));
            }} catch (cause) {{ error = String(cause); }}
            finally {{ for (const lock of locks) await lock.release(); }}
            console.log(JSON.stringify({{
              error, simultaneous,
              isolated: projects.every(paths => dirname(paths.lockFile) === join(paths.memory.agentDir, 'memory', 'locks')),
              preserved: projects.every(paths => statSync(paths.memory.harnessDir).isDirectory()),
              released: projects.every(paths => !existsSync(paths.lockFile)),
            }}));
            """
        )
        assert result == {"error": "", "simultaneous": True, "isolated": True, "preserved": True, "released": True}


def test_symlinked_locks_directory_denies_actual_lock_acquisition() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_bun(
            f"""
            import {{ acquireConsolidationLock, resolveConsolidationRunPaths }} from './packages/continual-learning/extensions/consolidation-run.ts';
            import {{ mkdirSync, symlinkSync, readdirSync, existsSync }} from 'node:fs';
            import {{ join }} from 'node:path';
            const root = {json.dumps(tmp)};
            const agent = join(root, 'agent');
            const outside = join(root, 'outside');
            mkdirSync(join(agent, 'memory'), {{ recursive: true }});
            mkdirSync(outside);
            symlinkSync(outside, join(agent, 'memory', 'locks'));
            const paths = resolveConsolidationRunPaths(join(root, 'foo'), 'run_symlink', agent);
            let error = '';
            let lock;
            try {{ lock = await acquireConsolidationLock(paths); }} catch (cause) {{ error = String(cause); }}
            finally {{ await lock?.release(); }}
            console.log(JSON.stringify({{ error, outside: readdirSync(outside), lockExists: existsSync(paths.lockFile) }}));
            """
        )
        assert result["error"]
        assert result["outside"] == []
        assert result["lockExists"] is False


def test_colliding_readable_names_intentionally_share_private_scope() -> None:
    result = run_bun(
        """
        import { escapedProjectPath, resolveMemoryPaths } from './packages/continual-learning/extensions/memory-paths.ts';
        const first = resolveMemoryPaths('/tmp/a:b/c');
        const second = resolveMemoryPaths('/tmp/a/b/c');
        console.log(JSON.stringify({
          first,
          second,
          firstPrefix: escapedProjectPath('/tmp/a:b/c'),
          secondPrefix: escapedProjectPath('/tmp/a/b/c'),
        }));
        """
    )
    assert result["firstPrefix"] == result["secondPrefix"] == "--tmp-a-b-c--"
    for key in ("scopeKey", "harnessDir", "lockFile", "runsDir"):
        assert result["first"][key] == result["second"][key]


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
        raw = str(physical.resolve()).lstrip("/").replace("/", "-").replace(":", "-")
        expected_name = f"--{raw}--"
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
    assert result["prefix"] == "--Users-FradSer-Documents-Home Lab--"
    assert result["name"] == result["prefix"] == result["scopeKey"]


def test_overlong_flat_scope_is_rejected_without_truncation() -> None:
    result = run_bun(
        """
        import { resolveMemoryPaths } from './packages/continual-learning/extensions/memory-paths.ts';
        const accepted = resolveMemoryPaths('/' + 'a'.repeat(235));
        let error = '';
        try { resolveMemoryPaths('/' + 'a'.repeat(237)); }
        catch (cause) { error = cause.message; }
        console.log(JSON.stringify({ name: accepted.scopeKey, error }));
        """
    )
    assert len(result["name"].encode("utf8")) == 239
    assert "exceeds 240 bytes" in result["error"]


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
        assert [entry["filename"] for entry in result["entries"]] == ["a.md", "z.md"]
        assert result["totalEntries"] == 2
        assert all("private" not in entry["content"] for entry in result["entries"])


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
        assert [entry["filename"] for entry in result["entries"]] == ["valid_name.md"]
        truncated = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            const {{ loadAndDeduplicateMemories }} = await import('./packages/continual-learning/extensions/memory-files.ts');
            console.log(JSON.stringify(await loadAndDeduplicateMemories({json.dumps(str(repo))}, {{ maxFileChars: 3 }})));
            """
        )
        assert truncated["entries"][0]["content"] == "val\n… [truncated]"


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
        assert result["values"]["entries"][0]["content"] == "xxx\n… [truncated]"


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
        initialize_git_repo(repo)
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
        assert result["entries"] == []
        assert result["indexes"] == []


def test_loader_skips_a_child_replaced_by_a_symlink() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        memory = repo / ".memory"
        secret = root / "secret.md"
        memory.mkdir(parents=True)
        secret.write_text("secret", encoding="utf-8")
        (memory / "a.md").write_text("safe", encoding="utf-8")
        initialize_git_repo(repo)
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
        assert result["entries"] == []


def test_index_rebuild_rejects_root_swap_before_publishing_metadata(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    outside = tmp_path / "outside"
    memory.mkdir()
    outside.mkdir()
    (memory / "a.md").write_text("---\ndescription: safe cue\n---\n", encoding="utf-8")
    (outside / "a.md").write_text("---\ndescription: outside cue\n---\n", encoding="utf-8")
    result = run_bun(
        f"""
        import fs from 'node:fs/promises';
        import {{ rebuildMemoryIndex }} from './packages/continual-learning/extensions/memory-files.ts';
        const open = fs.open.bind(fs);
        let swapped = false;
        fs.open = async (target, ...args) => {{
          if (!swapped && String(target).endsWith('/a.md')) {{
            await fs.rename({json.dumps(str(memory))}, {json.dumps(str(tmp_path / 'saved'))});
            await fs.symlink({json.dumps(str(outside))}, {json.dumps(str(memory))}, 'dir');
            swapped = true;
          }}
          return open(target, ...args);
        }};
        let error = '';
        try {{ await rebuildMemoryIndex({json.dumps(str(memory))}); }} catch (cause) {{ error = cause.message; }}
        console.log(JSON.stringify({{ error, outside: await fs.readdir({json.dumps(str(outside))}) }}));
        """
    )
    assert "root changed" in result["error"]
    assert result["outside"] == ["a.md"]
    assert "outside cue" not in result["error"]


def test_index_rebuild_cleanup_does_not_remove_a_replacement_root_file(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    outside = tmp_path / "outside"
    memory.mkdir()
    outside.mkdir()
    (memory / "a.md").write_text("---\ndescription: safe cue\n---\n", encoding="utf-8")
    result = run_bun(
        f"""
        import fs from 'node:fs/promises';
        import {{ basename, join }} from 'node:path';
        import {{ rebuildMemoryIndex }} from './packages/continual-learning/extensions/memory-files.ts';
        const open = fs.open.bind(fs);
        let replacement = '';
        fs.open = async (target, ...args) => {{
          const handle = await open(target, ...args);
          if (String(target).endsWith('.tmp')) {{
            const write = handle.writeFile.bind(handle);
            handle.writeFile = async (...values) => {{
              await write(...values);
              await fs.rename({json.dumps(str(memory))}, {json.dumps(str(tmp_path / 'saved'))});
              await fs.symlink({json.dumps(str(outside))}, {json.dumps(str(memory))}, 'dir');
              replacement = join({json.dumps(str(outside))}, basename(target));
              await fs.writeFile(replacement, 'outside must remain');
            }};
          }}
          return handle;
        }};
        let error = '';
        try {{ await rebuildMemoryIndex({json.dumps(str(memory))}); }} catch (cause) {{ error = cause.message; }}
        let preserved = false;
        try {{ preserved = (await fs.readFile(replacement, 'utf8')) === 'outside must remain'; }} catch {{}}
        console.log(JSON.stringify({{ error, preserved }}));
        """
    )
    assert "root changed" in result["error"]
    assert result["preserved"] is True


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
            import {{ join, dirname }} from 'node:path';
            const paths = resolveConsolidationRunPaths({json.dumps(str(repo))}, 'run_stale', {json.dumps(str(agent))});
            mkdirSync(dirname(paths.lockFile), {{ recursive: true }});
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


def test_obsolete_private_roots_are_ignored_without_mutation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "Cafe\u0301!!-- Lab"
        agent = root / "agent"
        repo.mkdir()
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            import {{ escapedProjectPath, resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            import {{ loadAndDeduplicateMemories }} from './packages/continual-learning/extensions/memory-files.ts';
            import {{ existsSync, mkdirSync, readFileSync, writeFileSync }} from 'node:fs';
            const memory = resolveMemoryPaths({json.dumps(str(repo))});
            const obsolete = [
              memory.agentDir + '/memory/' + 'a'.repeat(64),
              memory.agentDir + '/memory/' + escapedProjectPath(memory.cwd) + '--' + 'a'.repeat(64),
              memory.agentDir + '/memory/' + memory.cwd.replace(/[\\/]+/g, '-'),
            ];
            for (const [index, dir] of obsolete.entries()) {{
              mkdirSync(dir, {{ recursive: true }});
              writeFileSync(dir + `/obsolete${{index}}.md`, `obsolete ${{index}}\\n`);
            }}
            mkdirSync(memory.harnessDir, {{ recursive: true }});
            writeFileSync(memory.harnessDir + '/canonical.md', 'canonical\\n');
            const before = obsolete.map((dir, index) => readFileSync(dir + `/obsolete${{index}}.md`, 'utf8'));
            const entries = await loadAndDeduplicateMemories({json.dumps(str(repo))});
            console.log(JSON.stringify({{
              entries: entries.entries.map((entry) => [entry.filename, entry.content]),
              obsoleteStillExist: obsolete.map((dir, index) => existsSync(dir + `/obsolete${{index}}.md`)),
              obsoleteUnchanged: obsolete.map((dir, index) => readFileSync(dir + `/obsolete${{index}}.md`, 'utf8') === before[index]),
            }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result["entries"] == [["canonical.md", "canonical\n"]]
        assert result["obsoleteStillExist"] == [True, True, True]
        assert result["obsoleteUnchanged"] == [True, True, True]


def test_colliding_readable_roots_load_the_same_private_memory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        agent = Path(tmp) / "agent"
        result = run_bun(
            f"""
            import {{ escapedProjectPath, resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
            import {{ loadAndDeduplicateMemories }} from './packages/continual-learning/extensions/memory-files.ts';
            import {{ existsSync, mkdirSync, readFileSync, writeFileSync }} from 'node:fs';
            const leftCwd = '/tmp/a:b/c';
            const rightCwd = '/tmp/a/b/c';
            const left = resolveMemoryPaths(leftCwd, {json.dumps(str(agent))});
            const right = resolveMemoryPaths(rightCwd, {json.dumps(str(agent))});
            const sharedRoot = left.agentDir + '/memory/' + escapedProjectPath(left.cwd);
            if (sharedRoot !== right.agentDir + '/memory/' + escapedProjectPath(right.cwd)) throw new Error('expected collision');
            mkdirSync(sharedRoot, {{ recursive: true }});
            writeFileSync(sharedRoot + '/ambiguous.md', 'ambiguous\\n');
            mkdirSync(left.harnessDir, {{ recursive: true }});
            mkdirSync(right.harnessDir, {{ recursive: true }});
            writeFileSync(left.harnessDir + '/left.md', 'left\\n');
            writeFileSync(right.harnessDir + '/right.md', 'right\\n');
            const leftEntries = await loadAndDeduplicateMemories(leftCwd);
            const rightEntries = await loadAndDeduplicateMemories(rightCwd);
            console.log(JSON.stringify({{
              sharedCanonicalRoot: left.harnessDir === right.harnessDir,
              left: leftEntries.entries.map((entry) => entry.filename),
              right: rightEntries.entries.map((entry) => entry.filename),
              sharedKept: existsSync(sharedRoot + '/ambiguous.md'),
              sharedBytes: readFileSync(sharedRoot + '/ambiguous.md', 'utf8'),
            }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result == {
            "sharedCanonicalRoot": True,
            "left": ["ambiguous.md", "left.md", "right.md"],
            "right": ["ambiguous.md", "left.md", "right.md"],
            "sharedKept": True,
            "sharedBytes": "ambiguous\n",
        }


def test_git_root_probe_is_memoized_within_a_process(tmp_path: Path) -> None:
    # Memory paths resolve on every user turn; the git probe must not run again
    # for the same project. Breaking PATH after the first resolve proves the
    # answer came from the memoized probe rather than a second subprocess.
    repo = tmp_path / "repo"
    repo.mkdir()
    initialize_git_repo(repo)
    result = run_bun(
        f"""
        import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
        const before = resolveMemoryPaths({json.dumps(str(repo))});
        process.env.PATH = '/nonexistent-path-for-probe-test';
        const after = resolveMemoryPaths({json.dumps(str(repo))});
        console.log(JSON.stringify({{ before: before.publicDir ?? null, after: after.publicDir ?? null }}));
        """
    )
    assert result["before"] == str(repo / ".memory")
    assert result["after"] == result["before"]


def test_unavailable_git_probe_disables_public_memory_without_failing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".memory").mkdir()
    result = run_bun(
        f"""
        process.env.PATH = '/nonexistent-path-for-probe-test';
        import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
        const resolved = resolveMemoryPaths({json.dumps(str(repo))});
        console.log(JSON.stringify({{ publicDir: resolved.publicDir ?? null, harnessDir: resolved.harnessDir }}));
        """
    )
    assert result["publicDir"] is None
    assert result["harnessDir"]
