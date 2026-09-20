from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]


def run_bun(source: str, agent: Path | None = None) -> dict[str, object]:
    result = subprocess.run(
        ["bun", "-e", source],
        cwd=REPO,
        env={**os.environ, **({"PI_CODING_AGENT_DIR": str(agent)} if agent else {})},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def memory_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    memory = repo / ".memory"
    memory.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo, memory, tmp_path / "agent"


def memory_text(description: str) -> str:
    return f"---\nname: example\ndescription: {description}\ntype: project\n---\nBody must stay out of the prompt.\n"


def load_and_format(repo: Path, agent: Path, options: str = "{}", budget: str = "undefined") -> dict[str, object]:
    return run_bun(
        f"""
        import {{ loadAndDeduplicateMemories, formatMemoriesBlock }} from './packages/continual-learning/extensions/memory-files.ts';
        const loaded = await loadAndDeduplicateMemories({json.dumps(str(repo))}, {options});
        console.log(JSON.stringify({{ loaded, block: formatMemoriesBlock(loaded, {budget}) }}));
        """,
        agent,
    )


def test_long_description_keeps_late_trigger_when_it_fits(tmp_path: Path) -> None:
    # Given legacy metadata with its only routing cue beyond the old 120-char cut.
    repo, memory, agent = memory_repo(tmp_path)
    description = "Historical supporting detail. " * 8 + "Read when debugging release rollback."
    (memory / "legacy.md").write_text(memory_text(description), encoding="utf-8")
    result = load_and_format(repo, agent)
    assert description in result["block"]
    assert "Body must stay out" not in result["block"]
    assert "untrusted" in result["block"].lower()


def test_oversized_description_is_marked_and_root_is_verbatim(tmp_path: Path) -> None:
    repo, memory, agent = memory_repo(tmp_path)
    (memory / "huge.md").write_text(memory_text("routing cue " * 1500), encoding="utf-8")
    result = load_and_format(repo, agent, budget="1500")
    assert len(result["block"]) <= 1500
    # A shortened cue is marked once per row; repeating the full notice on every
    # row costs more characters than the descriptions it announces.
    assert "…" in result["block"]
    assert "read the complete index or the entry file" in result["block"]
    # The exact body path is the declared root plus the row's own filename.
    assert str(memory.resolve()) in result["block"]
    assert "- huge.md (public)" in result["block"]
    assert "routing cue" in result["block"]
    assert "Body must stay out" not in result["block"]


def test_final_budget_counts_all_entries_and_discloses_complete_discovery(tmp_path: Path) -> None:
    repo, memory, agent = memory_repo(tmp_path)
    # The overhead before the first row carries the absolute memory root, so a
    # short temporary path fits more rows than a long one. Size the fixture well
    # past the 1200-character budget so rows are omitted on every host.
    entries = 24
    for index in range(entries):
        (memory / f"item_{index:02d}.md").write_text(memory_text(f"Route task {index}"), encoding="utf-8")
    run_bun(
        f"""
        import {{ rebuildMemoryIndex }} from './packages/continual-learning/extensions/memory-files.ts';
        await rebuildMemoryIndex({json.dumps(str(memory))});
        console.log(JSON.stringify({{ ok: true }}));
        """,
        agent,
    )
    result = load_and_format(repo, agent, options="{ maxTotalChars: 1200 }")
    loaded = result["loaded"]
    assert loaded["totalEntries"] == entries
    assert len(loaded["entries"]) == entries  # No alphabetic filtering before final format.
    shown = len(re.findall(r"^- item_", result["block"], re.MULTILINE))
    assert 0 < shown < entries
    assert f"{shown} shown, {entries - shown} omitted of {entries} total" in result["block"]
    assert f"budget: {entries - shown}" in result["block"]
    assert str(memory.resolve() / "MEMORY.md") in result["block"]
    assert "offset: 1" in result["block"] and "limit: 100" in result["block"]
    assert "stale" in result["block"] and "authoritative" in result["block"]
    assert len(result["block"]) <= 1200


def test_max_files_is_global_after_private_precedence_and_reports_unread_files(tmp_path: Path) -> None:
    repo, memory, agent = memory_repo(tmp_path)
    (memory / "a.md").write_text(memory_text("public stale"), encoding="utf-8")
    (memory / "z.md").write_text(memory_text("public tail"), encoding="utf-8")
    result = run_bun(
        f"""
        import fs from 'node:fs/promises';
        import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
        import {{ loadAndDeduplicateMemories, formatMemoriesBlock }} from './packages/continual-learning/extensions/memory-files.ts';
        const paths = resolveMemoryPaths({json.dumps(str(repo))});
        await fs.mkdir(paths.harnessDir, {{ recursive: true }});
        await fs.writeFile(paths.harnessDir + '/a.md', {json.dumps(memory_text('private current'))});
        await fs.writeFile(paths.harnessDir + '/b.md', {json.dumps(memory_text('private second'))});
        const open = fs.open.bind(fs);
        const bodies = [];
        fs.open = async (file, ...args) => {{
          if (['a.md', 'b.md', 'z.md'].includes(String(file).split('/').at(-1))) bodies.push(String(file));
          return open(file, ...args);
        }};
        const loaded = await loadAndDeduplicateMemories({json.dumps(str(repo))}, {{ maxFiles: 1 }});
        console.log(JSON.stringify({{ loaded, bodies, block: formatMemoriesBlock(loaded) }}));
        """,
        agent,
    )
    assert result["loaded"]["totalEntries"] == 3
    assert result["loaded"]["omittedEntries"] == result["loaded"]["limitedEntries"] == 2
    assert len(result["bodies"]) == 1
    entries = result["loaded"]["entries"]
    assert [(entry["filename"], entry["source"]) for entry in entries] == [("a.md", "harness")]
    assert entries[0]["description"] == "private current"
    assert "1 shown, 2 omitted of 3 total" in result["block"]
    assert "maxFiles: 2" in result["block"]
    assert "prefer harness" in result["block"]
    assert "public stale" not in result["block"]


def test_zero_file_limit_still_discloses_total_and_read_only_fallback(tmp_path: Path) -> None:
    repo, memory, agent = memory_repo(tmp_path)
    (memory / "a.md").write_text(memory_text("when routing a task"), encoding="utf-8")
    before = {file.name: file.read_bytes() for file in memory.iterdir()}
    result = load_and_format(repo, agent, options="{ maxFiles: 0 }")
    assert result["loaded"]["entries"] == []
    assert result["loaded"]["totalEntries"] == result["loaded"]["limitedEntries"] == 1
    assert "0 shown, 1 omitted of 1 total" in result["block"]
    assert "unavailable" in result["block"].lower()
    assert str(memory.resolve()) in result["block"]
    assert "bounded" in result["block"] and "symlink" in result["block"]
    assert {file.name: file.read_bytes() for file in memory.iterdir()} == before
    assert not agent.exists()


def test_budget_too_small_for_discovery_rejects_explicitly(tmp_path: Path) -> None:
    repo, memory, agent = memory_repo(tmp_path)
    (memory / "a.md").write_text(memory_text("route"), encoding="utf-8")
    result = run_bun(
        f"""
        import {{ loadAndDeduplicateMemories, formatMemoriesBlock }} from './packages/continual-learning/extensions/memory-files.ts';
        const loaded = await loadAndDeduplicateMemories({json.dumps(str(repo))});
        let error = '';
        try {{ formatMemoriesBlock(loaded, 1); }} catch (cause) {{ error = cause.message; }}
        console.log(JSON.stringify({{ error }}));
        """,
        agent,
    )
    assert "budget" in result["error"].lower() and "discovery" in result["error"].lower()


def test_rebuilt_index_routes_every_entry_beyond_the_default_file_limit(tmp_path: Path) -> None:
    repo, memory, agent = memory_repo(tmp_path)
    for index in range(140):
        (memory / f"item_{index:03d}.md").write_text(memory_text(f"Relevance cue for task {index}"), encoding="utf-8")
    (memory / "legacy.md").write_text(memory_text("support " * 30 + "late legacy trigger"), encoding="utf-8")
    result = run_bun(
        f"""
        import {{ rebuildMemoryIndex, loadAndDeduplicateMemories, formatMemoriesBlock }} from './packages/continual-learning/extensions/memory-files.ts';
        import {{ readFile }} from 'node:fs/promises';
        await rebuildMemoryIndex({json.dumps(str(memory))});
        const index = await readFile({json.dumps(str(memory / 'MEMORY.md'))}, 'utf8');
        const loaded = await loadAndDeduplicateMemories({json.dumps(str(repo))});
        console.log(JSON.stringify({{ index, loaded, block: formatMemoriesBlock(loaded) }}));
        """,
        agent,
    )
    assert "Relevance cue for task 139" in result["index"]
    assert "late legacy trigger" in result["index"]
    assert len(re.findall(r"^- \[", result["index"], re.MULTILINE)) == 141
    assert "limit: 100" in result["index"]
    assert result["loaded"]["totalEntries"] == 141
    assert result["loaded"]["limitedEntries"] == 13
    assert "maxFiles: 13" in result["block"]
    assert "Body must stay out" not in result["index"]


def test_complete_index_is_byte_bounded_with_visible_per_entry_truncation(tmp_path: Path) -> None:
    _, memory, agent = memory_repo(tmp_path)
    for index in range(50):
        (memory / f"item_{index:02d}.md").write_text(memory_text("触发线索" * 1500), encoding="utf-8")
    result = run_bun(
        f"""
        import {{ rebuildMemoryIndex }} from './packages/continual-learning/extensions/memory-files.ts';
        import {{ readFile }} from 'node:fs/promises';
        await rebuildMemoryIndex({json.dumps(str(memory))});
        console.log(JSON.stringify({{ index: await readFile({json.dumps(str(memory / 'MEMORY.md'))}, 'utf8') }}));
        """,
        agent,
    )
    assert len(result["index"].encode("utf-8")) <= 64_000
    rows = [line for line in result["index"].splitlines() if line.startswith("- [")]
    assert len(rows) == 50
    assert all(len(line.encode("utf-8")) <= 4096 for line in rows)
    assert all("description truncated" in line and "触发线索" in line for line in rows)
    assert "�" not in result["index"]


def test_complete_index_retains_a_long_description_when_short_siblings_leave_space(tmp_path: Path) -> None:
    _, memory, agent = memory_repo(tmp_path)
    for index in range(200):
        (memory / f"short_{index:03d}.md").write_text(memory_text("short cue"), encoding="utf-8")
    description = "legacy context " * 100 + "tail relevance trigger"
    (memory / "legacy.md").write_text(memory_text(description), encoding="utf-8")
    result = run_bun(
        f"""
        import {{ rebuildMemoryIndex }} from './packages/continual-learning/extensions/memory-files.ts';
        import {{ readFile }} from 'node:fs/promises';
        await rebuildMemoryIndex({json.dumps(str(memory))});
        console.log(JSON.stringify({{ index: await readFile({json.dumps(str(memory / 'MEMORY.md'))}, 'utf8') }}));
        """,
        agent,
    )
    assert description in result["index"]
    assert len(result["index"].encode("utf-8")) < 64_000


def test_complete_index_does_not_reserve_nonexistent_metadata_at_large_corpus_size(tmp_path: Path) -> None:
    _, memory, agent = memory_repo(tmp_path)
    for index in range(1200):
        (memory / f"item_{index:04d}.md").write_text("body without frontmatter", encoding="utf-8")
    result = run_bun(
        f"""
        import {{ rebuildMemoryIndex }} from './packages/continual-learning/extensions/memory-files.ts';
        import {{ readFile }} from 'node:fs/promises';
        let error = '';
        try {{ await rebuildMemoryIndex({json.dumps(str(memory))}); }} catch (cause) {{ error = cause.message; }}
        console.log(JSON.stringify({{ error, index: error ? '' : await readFile({json.dumps(str(memory / 'MEMORY.md'))}, 'utf8') }}));
        """,
        agent,
    )
    assert result["error"] == ""
    assert result["index"].count("- [item_") == 1200
    assert len(result["index"].encode("utf-8")) <= 64_000


def test_read_pointers_preserve_repeated_whitespace_in_the_actual_path(tmp_path: Path) -> None:
    repo, memory, agent = memory_repo(tmp_path / "two  spaces")
    (memory / "a.md").write_text(memory_text("routing cue"), encoding="utf-8")
    result = load_and_format(repo, agent)
    # Declared roots and index pointers keep the exact path, including repeated
    # whitespace, and the entry row carries the filename to append to the root.
    assert str(memory.resolve()) in result["block"]
    assert str(memory.resolve() / "MEMORY.md") in result["block"]
    assert "- a.md (public)" in result["block"]


def test_symlinked_complete_index_is_not_advertised_as_a_read_target(tmp_path: Path) -> None:
    repo, memory, agent = memory_repo(tmp_path)
    (memory / "a.md").write_text(memory_text("routing cue"), encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("Never read outside metadata", encoding="utf-8")
    (memory / "MEMORY.md").symlink_to(outside)
    result = load_and_format(repo, agent)
    assert result["loaded"]["indexes"][0]["available"] is False
    assert "unavailable" in result["block"]
    assert not any("[read:" in line and "MEMORY.md" in line for line in result["block"].splitlines())
    assert str(memory.resolve()) in result["block"]
    assert "outside metadata" not in result["block"]


def test_index_replaced_by_symlink_during_body_read_is_not_advertised(tmp_path: Path) -> None:
    repo, memory, agent = memory_repo(tmp_path)
    (memory / "a.md").write_text(memory_text("routing cue"), encoding="utf-8")
    (memory / "MEMORY.md").write_text("# Memory Index\n", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("outside metadata", encoding="utf-8")
    result = run_bun(
        f"""
        import fs from 'node:fs/promises';
        import {{ loadAndDeduplicateMemories, formatMemoriesBlock }} from './packages/continual-learning/extensions/memory-files.ts';
        const open = fs.open.bind(fs);
        fs.open = async (file, ...args) => {{
          if (String(file).endsWith('/a.md')) {{
            await fs.unlink({json.dumps(str(memory / 'MEMORY.md'))});
            await fs.symlink({json.dumps(str(outside))}, {json.dumps(str(memory / 'MEMORY.md'))});
          }}
          return open(file, ...args);
        }};
        const loaded = await loadAndDeduplicateMemories({json.dumps(str(repo))});
        console.log(JSON.stringify({{ loaded, block: formatMemoriesBlock(loaded) }}));
        """,
        agent,
    )
    assert result["loaded"]["indexes"][0]["available"] is False
    assert not any("[read:" in line and "MEMORY.md" in line for line in result["block"].splitlines())


def test_bounded_metadata_read_reports_incomplete_description_without_body_leak(tmp_path: Path) -> None:
    repo, memory, agent = memory_repo(tmp_path)
    (memory / "a.md").write_text(memory_text("routing clue " * 50), encoding="utf-8")
    result = load_and_format(repo, agent, options="{ maxFileChars: 60 }")
    assert result["loaded"]["entries"][0]["descriptionTruncated"] is True
    assert "description truncated" in result["block"]
    assert "routing clue" in result["block"]
    assert "Body must stay out" not in result["block"]


def test_crlf_frontmatter_keeps_description_and_never_parses_body_description(tmp_path: Path) -> None:
    repo, memory, agent = memory_repo(tmp_path)
    (memory / "a.md").write_bytes(b'---\r\ndescription: "CRLF route cue"\r\n---\r\nbody\r\ndescription: body not metadata\r\n')
    result = load_and_format(repo, agent)
    assert result["loaded"]["entries"][0]["description"] == "CRLF route cue"
    assert "body not metadata" not in result["block"]


def test_failed_private_read_reports_unavailable_without_falling_back_to_public(tmp_path: Path) -> None:
    repo, memory, agent = memory_repo(tmp_path)
    (memory / "a.md").write_text(memory_text("stale public"), encoding="utf-8")
    result = run_bun(
        f"""
        import fs from 'node:fs/promises';
        import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
        import {{ loadAndDeduplicateMemories, formatMemoriesBlock }} from './packages/continual-learning/extensions/memory-files.ts';
        const paths = resolveMemoryPaths({json.dumps(str(repo))});
        await fs.mkdir(paths.harnessDir, {{ recursive: true }});
        await fs.writeFile(paths.harnessDir + '/a.md', {json.dumps(memory_text('private'))});
        const open = fs.open.bind(fs);
        fs.open = async (file, ...args) => {{
          if (file === paths.harnessDir + '/a.md') throw new Error('test denied');
          return open(file, ...args);
        }};
        const loaded = await loadAndDeduplicateMemories({json.dumps(str(repo))});
        console.log(JSON.stringify({{ loaded, block: formatMemoriesBlock(loaded) }}));
        """,
        agent,
    )
    assert result["loaded"]["entries"] == []
    assert result["loaded"]["unavailableEntries"] == result["loaded"]["totalEntries"] == 1
    assert "unavailable: 1" in result["block"]
    assert "stale public" not in result["block"]


def test_real_consolidation_persists_descriptions_without_forging_private_markers(tmp_path: Path) -> None:
    root = tmp_path / "transaction"
    safe_content = memory_text("Read when discussing (harness only), not a classification.")
    private_content = memory_text("Use for personal formatting preferences.")
    result = run_bun(
        f"""
        import {{ applyConsolidationPlan, hashMemoryRoot }} from './packages/continual-learning/extensions/consolidation-run.ts';
        import {{ readFile }} from 'node:fs/promises';
        const harness = {json.dumps(str(root / 'harness'))};
        const publicDir = {json.dumps(str(root / 'public'))};
        const manifest = {{ runId: 'run_index', scopeDigest: 'b'.repeat(64), snapshotDigest: 'a'.repeat(64), harnessDir: harness, publicDir, sourceHashes: {{ harness: {{}}, public: {{}} }} }};
        const plan = {{ runId: 'run_index', scopeDigest: 'b'.repeat(64), artifactHash: 'a'.repeat(64), selected: ['safe.md', 'private.md'], inventory: [{{ name: 'safe.md', classification: 'safe' }}, {{ name: 'private.md', classification: 'private' }}], operations: [
          {{ name: 'safe.md', kind: 'create', classification: 'safe', content: {json.dumps(safe_content)} }},
          {{ name: 'private.md', kind: 'create', classification: 'private', content: {json.dumps(private_content)} }},
        ] }};
        await applyConsolidationPlan({{ manifest, paths: {{}}, released: false }}, plan);
        // Read classification on the next apply too; descriptor text must not forge it.
        manifest.sourceHashes = {{ harness: await hashMemoryRoot(harness), public: await hashMemoryRoot(publicDir) }};
        await applyConsolidationPlan({{ manifest, paths: {{}}, released: false }}, {{ ...plan, operations: [] }});
        console.log(JSON.stringify({{
          harness: await readFile(harness + '/MEMORY.md', 'utf8'),
          public: await readFile(publicDir + '/MEMORY.md', 'utf8'),
        }}));
        """,
    )
    assert "personal formatting preferences" in result["harness"]
    assert "Read when discussing" in result["harness"]
    assert "Read when discussing" in result["public"]
    assert "(harness only)" not in result["public"]
    assert "private.md" not in result["public"]
    assert result["harness"].count("(harness only)") == 1


@pytest.mark.parametrize("prompt", ["memory-consolidator", "incremental-memory-consolidator"])
def test_planner_prompts_require_concise_front_loaded_relevance_descriptions(prompt: str) -> None:
    content = (PACKAGE / "prompts" / f"{prompt}.md").read_text(encoding="utf-8")
    assert "120 characters" in content
    assert "front-load" in content.lower()
    assert "description" in content and "single-line" in content
    assert "preservedIn" in content and "private" in content
    assert "read-only" in content
    assert '"schemaVersion": 1' in content and "{{SCOPE_DIGEST}}" in content
    assert "user" in content and "tool-result" in content


def test_selector_protocol_is_compact_metadata_only_and_preserves_schema() -> None:
    content = (PACKAGE / "prompts" / "memory-selector.md").read_text(encoding="utf-8")
    assert len(content) < 1800
    assert "metadata-only" in content and "Do not use tools" in content
    assert '"kind": "incremental-memory-selection"' in content
    assert '"contextDigest"' in content and "{{TASK}}" in content
    assert "case-sensitive" in content and "minimum sufficient" in content


def test_default_budget_lists_every_entry_with_a_relevance_cue(tmp_path: Path) -> None:
    # Declaring each root once instead of repeating an absolute read path per row
    # lets the bounded prompt block reach a corpus that previously spent its
    # budget on path text and truncated descriptions to nothing.
    repo, memory, agent = memory_repo(tmp_path)
    for index in range(60):
        (memory / f"item_{index:02d}.md").write_text(memory_text(f"Route task {index} when it matches"), encoding="utf-8")
    block = load_and_format(repo, agent)["block"]
    rows = [line for line in block.splitlines() if line.startswith("- item_")]
    assert len(rows) == 60
    assert "0 omitted of 60 total" in block
    assert all(" — Route task" in line for line in rows)
    assert len(block) <= 6000


def test_cues_give_way_before_entries_under_budget_pressure(tmp_path: Path) -> None:
    # Coverage first: filenames are never dropped while bare rows fit, so budget
    # pressure costs relevance metadata, not discoverability of later entries.
    repo, memory, agent = memory_repo(tmp_path)
    for index in range(40):
        (memory / f"item_{index:02d}.md").write_text(memory_text(f"Route task {index} when it matches " * 4), encoding="utf-8")
    lines = load_and_format(repo, agent)["block"].splitlines()
    header = "\n".join(lines[: next(i for i, line in enumerate(lines) if line.startswith("- item_"))]) + "\n"
    bare_rows = [re.sub(r" — .*$", "", line) for line in lines if line.startswith("- item_")]
    summary = f"{lines[-1]}\n"
    budget = len(header) + sum(len(row) + 1 for row in bare_rows) + len(summary) + 8
    block = load_and_format(repo, agent, budget=str(budget))["block"]
    emitted = [line for line in block.splitlines() if line.startswith("- item_")]
    assert len(emitted) == 40
    assert "0 omitted of 40 total" in block
    assert not any(" — " in line for line in emitted)
    assert len(block) <= budget


def load_twice(repo: Path, agent: Path, script_tail: str = "", options: str = "{}") -> dict[str, object]:
    return run_bun(
        f"""
        import fs from 'node:fs/promises';
        import {{ loadAndDeduplicateMemories }} from './packages/continual-learning/extensions/memory-files.ts';
        let opens = 0;
        const originalOpen = fs.open.bind(fs);
        fs.open = async (target, ...args) => {{
          const name = String(target);
          if (name.endsWith('.md') && !name.endsWith('MEMORY.md')) opens += 1;
          return originalOpen(target, ...args);
        }};
        const root = {json.dumps(str(repo))};
        const first = await loadAndDeduplicateMemories(root, {options});
        const firstOpens = opens;
        opens = 0;
        {script_tail}
        const second = await loadAndDeduplicateMemories(root, {options});
        const summary = (loaded) => loaded.entries.map((entry) => [entry.filename, entry.description ?? null, entry.content]);
        console.log(JSON.stringify({{
          firstOpens, secondOpens: opens,
          firstEntries: summary(first), secondEntries: summary(second),
          firstTotal: first.totalEntries, secondTotal: second.totalEntries,
        }}));
        """,
        agent,
    )


def test_unchanged_entry_metadata_is_reused_within_a_process(tmp_path: Path) -> None:
    repo, memory, agent = memory_repo(tmp_path)
    for index in range(3):
        (memory / f"item_{index}.md").write_text(memory_text(f"Route cue {index}"), encoding="utf-8")
    result = load_twice(repo, agent)
    # Every turn used to open and re-parse every entry only for its description.
    assert result["firstOpens"] == 3
    assert result["secondOpens"] == 0
    assert result["firstEntries"] == result["secondEntries"]
    assert result["secondTotal"] == 3


def test_rewritten_and_replaced_entries_are_re_read(tmp_path: Path) -> None:
    repo, memory, agent = memory_repo(tmp_path)
    (memory / "kept.md").write_text(memory_text("Original cue"), encoding="utf-8")
    (memory / "atomic.md").write_text(memory_text("Atomic original"), encoding="utf-8")
    result = load_twice(
        repo,
        agent,
        script_tail=f"""
        const target = {json.dumps(str(memory / "kept.md"))};
        const replacement = {json.dumps(str(memory / "atomic.md"))};
        await fs.writeFile(target, {json.dumps(memory_text("Rewritten cue"))});
        await fs.writeFile(replacement + '.tmp', {json.dumps(memory_text("Atomic replaced"))});
        await fs.rename(replacement + '.tmp', replacement);
        """,
    )
    descriptions = dict((name, description) for name, description, _ in result["secondEntries"])
    assert descriptions["kept.md"] == "Rewritten cue"
    assert descriptions["atomic.md"] == "Atomic replaced"
    assert result["secondOpens"] == 2
    assert result["secondTotal"] == 2


def test_entry_replaced_by_a_symlink_is_not_reused_or_read(tmp_path: Path) -> None:
    repo, memory, agent = memory_repo(tmp_path)
    (memory / "a.md").write_text(memory_text("safe cue"), encoding="utf-8")
    secret = tmp_path / "secret.md"
    secret.write_text(memory_text("secret cue"), encoding="utf-8")
    result = load_twice(
        repo,
        agent,
        script_tail=f"""
        await fs.unlink({json.dumps(str(memory / "a.md"))});
        await fs.symlink({json.dumps(str(secret))}, {json.dumps(str(memory / "a.md"))});
        """,
    )
    assert result["firstTotal"] == 1
    assert result["secondTotal"] == 0
    assert result["secondEntries"] == []
    assert "secret cue" not in json.dumps(result["secondEntries"])


def test_metadata_reuse_respects_the_read_bound(tmp_path: Path) -> None:
    repo, memory, agent = memory_repo(tmp_path)
    (memory / "long.md").write_text(memory_text("cue " * 80), encoding="utf-8")
    result = run_bun(
        f"""
        import {{ loadAndDeduplicateMemories }} from './packages/continual-learning/extensions/memory-files.ts';
        const root = {json.dumps(str(repo))};
        const bounded = await loadAndDeduplicateMemories(root, {{ maxFileChars: 60 }});
        const full = await loadAndDeduplicateMemories(root);
        const flags = (loaded) => loaded.entries.map((entry) => [entry.descriptionTruncated ?? false, entry.content.length]);
        console.log(JSON.stringify({{ bounded: flags(bounded), full: flags(full) }}));
        """,
        agent,
    )
    # The byte bound is part of the reuse key: a shorter bounded read must not be
    # served to a later load that allowed a longer one.
    assert result["bounded"][0][0] is True
    assert result["full"][0][0] is False
    assert result["full"][0][1] > result["bounded"][0][1]


def test_rows_are_listed_without_cues_while_entries_must_be_dropped(tmp_path: Path) -> None:
    repo, memory, agent = memory_repo(tmp_path)
    for index in range(12):
        (memory / f"item_{index:02d}.md").write_text(memory_text(f"Route task {index} " + "detail " * 40), encoding="utf-8")
    lines = load_and_format(repo, agent)["block"].splitlines()
    header = "\n".join(lines[: next(i for i, line in enumerate(lines) if line.startswith("- item_"))]) + "\n"
    bare = [re.sub(r" — .*$", "", line) for line in lines if line.startswith("- item_")]
    summary = f"{lines[-1]}\n"
    budget = len(header) + sum(len(row) + 1 for row in bare[:3]) + len(summary) + 8
    block = load_and_format(repo, agent, budget=str(budget))["block"]
    emitted = [line for line in block.splitlines() if line.startswith("- item_")]
    # Coverage first: an unaffordable cue is dropped, never the filename row.
    assert emitted == bare[:3]
    assert "3 shown, 9 omitted of 12 total" in block
    assert len(block) <= budget


def test_block_stays_within_every_budget_it_accepts(tmp_path: Path) -> None:
    repo, memory, agent = memory_repo(tmp_path)
    for index in range(20):
        (memory / f"item_{index:02d}.md").write_text(memory_text("cue " * (index + 1)), encoding="utf-8")
    result = run_bun(
        f"""
        import {{ loadAndDeduplicateMemories, formatMemoriesBlock }} from './packages/continual-learning/extensions/memory-files.ts';
        const loaded = await loadAndDeduplicateMemories({json.dumps(str(repo))});
        const swept = [];
        for (let budget = 700; budget <= 9000; budget += 137) {{
          try {{
            const block = formatMemoriesBlock(loaded, budget);
            swept.push([budget, block.length, block.length <= budget]);
          }} catch (cause) {{
            swept.push([budget, -1, String(cause.message).includes('too small')]);
          }}
        }}
        const roomy = formatMemoriesBlock(loaded, 9000);
        console.log(JSON.stringify({{ swept, roomyRows: (roomy.match(/^- item_/gm) ?? []).length, roomyOmitted: roomy.includes('0 omitted') }}));
        """,
        agent,
    )
    for budget, size, ok in result["swept"]:
        assert ok, f"budget {budget} produced {size}"
    assert any(size == -1 for _, size, _ in result["swept"]), "a too-small budget is reported, not silently truncated"
    assert result["roomyRows"] == 20
    assert result["roomyOmitted"] is True
