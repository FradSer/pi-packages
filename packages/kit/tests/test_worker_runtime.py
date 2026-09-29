"""Shared worker-runtime primitives in pi-kit.

Contract: packages/kit/features/worker-runtime.feature

These are the file and environment mechanics that agent-teams uses today and
that the subagents/task/teams split needs in more than one package, so they live
in pi-kit rather than being reimplemented per consumer. Behaviour is asserted
against the real filesystem, and the single-writer race is asserted against real
concurrent processes rather than two sequential in-process calls.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
SRC = PACKAGE / "src"
KIT = (SRC / "index.ts").as_uri()


def run_typescript(script: str, timeout: int = 30) -> dict[str, object]:
    result = subprocess.run(
        ["node", "--import", "tsx", "--input-type=module"],
        cwd=REPO,
        input=textwrap.dedent(script),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    assert result.returncode == 0, f"TypeScript runtime check failed:\n{result.stderr}\n{result.stdout}"
    return json.loads(result.stdout.strip().splitlines()[-1])


# ── Rule: an incremental JSONL read never loses or replays a record ──


def test_jsonl_batch_reads_once_and_advances() -> None:
    result = run_typescript(
        f'''
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        import {{ readJsonlBatch }} from "{KIT}";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "kit-jsonl-"));
        const file = path.join(dir, "events.jsonl");
        fs.writeFileSync(file, '{{"id":1}}\\n{{"id":2}}\\n{{"id":3}}\\n');
        const first = readJsonlBatch(file, 0);
        const second = readJsonlBatch(file, first.nextOffset);
        console.log(JSON.stringify({{
          records: first.records,
          nextOffset: first.nextOffset,
          fileSize: fs.statSync(file).size,
          diagnostics: first.diagnostics,
          secondRecords: second.records,
          secondOffset: second.nextOffset,
        }}));
        fs.rmSync(dir, {{ recursive: true, force: true }});
        '''
    )
    assert [record["id"] for record in result["records"]] == [1, 2, 3]
    assert result["nextOffset"] == result["fileSize"], "the offset must land exactly at EOF"
    assert result["diagnostics"] == []
    assert result["secondRecords"] == [], "a drained file must not replay"
    assert result["secondOffset"] == result["fileSize"]


def test_jsonl_batch_leaves_an_unterminated_record_for_the_next_read() -> None:
    result = run_typescript(
        f'''
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        import {{ readJsonlBatch }} from "{KIT}";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "kit-jsonl-"));
        const file = path.join(dir, "events.jsonl");
        fs.writeFileSync(file, '{{"id":1}}\\n{{"id":2');
        const partial = readJsonlBatch(file, 0);
        fs.appendFileSync(file, '}}\\n');
        const rest = readJsonlBatch(file, partial.nextOffset);
        console.log(JSON.stringify({{
          partialIds: partial.records.map((record) => record.id),
          partialOffset: partial.nextOffset,
          partialDiagnostics: partial.diagnostics,
          restIds: rest.records.map((record) => record.id),
        }}));
        fs.rmSync(dir, {{ recursive: true, force: true }});
        '''
    )
    assert result["partialIds"] == [1], "only the complete record may be consumed"
    assert result["partialOffset"] == 9, "the offset must stop before the unterminated record"
    assert result["partialDiagnostics"] == []
    assert result["restIds"] == [2], "the finished record must arrive on the next read"


def test_jsonl_batch_restarts_when_the_offset_exceeds_the_file() -> None:
    result = run_typescript(
        f'''
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        import {{ readJsonlBatch }} from "{KIT}";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "kit-jsonl-"));
        const file = path.join(dir, "events.jsonl");
        fs.writeFileSync(file, '{{"id":9}}\\n');
        const restarted = readJsonlBatch(file, 4096);
        const missing = readJsonlBatch(path.join(dir, "absent.jsonl"), 128);
        console.log(JSON.stringify({{
          restartedIds: restarted.records.map((record) => record.id),
          missingRecords: missing.records,
          missingOffset: missing.nextOffset,
          missingDiagnostics: missing.diagnostics,
        }}));
        fs.rmSync(dir, {{ recursive: true, force: true }});
        '''
    )
    assert result["restartedIds"] == [9], "a recreated file must restart from zero"
    assert result["missingRecords"] == []
    assert result["missingOffset"] == 0
    assert result["missingDiagnostics"] == [], "a missing file is empty, not an error"


def test_jsonl_batch_skips_an_oversized_record_and_reports_it() -> None:
    result = run_typescript(
        f'''
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        import {{ readJsonlBatch }} from "{KIT}";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "kit-jsonl-"));
        const file = path.join(dir, "events.jsonl");
        fs.writeFileSync(file, JSON.stringify({{ id: "x".repeat(200) }}));
        const batch = readJsonlBatch(file, 0, Number.POSITIVE_INFINITY, 64);
        const mixed = (() => {{
          const other = path.join(dir, "mixed.jsonl");
          fs.writeFileSync(other, '{{"id":1}}\\nnot-json\\n{{"id":2}}\\n');
          return readJsonlBatch(other, 0);
        }})();
        console.log(JSON.stringify({{
          records: batch.records,
          advanced: batch.nextOffset > 0,
          diagnostics: batch.diagnostics,
          mixedIds: mixed.records.map((record) => record.id),
          mixedDiagnostics: mixed.diagnostics,
        }}));
        fs.rmSync(dir, {{ recursive: true, force: true }});
        '''
    )
    assert result["records"] == []
    assert result["advanced"] is True, "one oversized sender must not block the drain"
    assert result["diagnostics"] == ["malformed or unterminated record was consumed"]
    assert result["mixedIds"] == [1, 2], "valid records around a bad line still arrive"
    assert result["mixedDiagnostics"] == ["malformed JSON record was consumed"]


# ── Rule: appends and replacements are capped, private, and atomic ──


def test_append_creates_private_file_and_refuses_oversize_with_the_callers_label() -> None:
    result = run_typescript(
        f'''
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        import {{ appendJsonlLine, writeJsonAtomic }} from "{KIT}";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "kit-append-"));
        const file = path.join(dir, "nested", "inbox.jsonl");
        appendJsonlLine(file, {{ id: "a" }});
        appendJsonlLine(file, {{ id: "b" }});
        const lines = fs.readFileSync(file, "utf8").trim().split("\\n");
        let error = "";
        try {{
          appendJsonlLine(file, {{ blob: "y".repeat(200) }}, {{ maxBytes: 64, label: "Worker event" }});
        }} catch (caught) {{ error = caught.message; }}
        const target = path.join(dir, "state.json");
        writeJsonAtomic(target, {{ v: 1 }});
        writeJsonAtomic(target, {{ v: 2 }});
        const leftovers = fs.readdirSync(dir).filter((name) => name.endsWith(".tmp"));
        console.log(JSON.stringify({{
          lines,
          dirMode: (fs.statSync(path.dirname(file)).mode & 0o777).toString(8),
          fileMode: (fs.statSync(file).mode & 0o777).toString(8),
          error,
          linesAfterRefusal: fs.readFileSync(file, "utf8").trim().split("\\n").length,
          finalValue: JSON.parse(fs.readFileSync(target, "utf8")),
          tmpLeftovers: leftovers,
        }}));
        fs.rmSync(dir, {{ recursive: true, force: true }});
        '''
    )
    assert [json.loads(line)["id"] for line in result["lines"]] == ["a", "b"]
    assert result["dirMode"] == "700", "the directory must be private"
    assert result["fileMode"] == "600", "the record file must be owner-only"
    assert result["error"] == "Worker event exceeds 64 bytes.", "the caller's label must reach the error"
    assert result["linesAfterRefusal"] == 2, "a refused record must not be partially written"
    assert result["finalValue"] == {"v": 2}
    assert result["tmpLeftovers"] == [], "an atomic replacement leaves no temporary file"


# ── Rule: exactly one racer publishes a given intent ──


def test_exactly_one_concurrent_racer_wins_the_intent() -> None:
    """Real concurrent processes, not two sequential in-process calls."""
    directory = tempfile.mkdtemp(prefix="kit-intent-race-")
    racers = 8
    script = textwrap.dedent(
        f'''
        import {{ createExclusiveJsonFile }} from "{KIT}";
        const won = createExclusiveJsonFile({json.dumps(directory)}, "contested", {{ racer: process.argv[1] }});
        process.stdout.write(won ? "true" : "false");
        '''
    )

    def race(index: int) -> str:
        completed = subprocess.run(
            ["node", "--import", "tsx", "--input-type=module", "--eval", script, str(index)],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        return completed.stdout.strip()

    try:
        with ThreadPoolExecutor(max_workers=racers) as pool:
            outcomes = list(pool.map(race, range(racers)))
        assert outcomes.count("true") == 1, f"exactly one racer may win, got {outcomes}"
        assert outcomes.count("false") == racers - 1, "losers report failure rather than throwing"
        published = [name for name in os.listdir(directory) if name.endswith(".json")]
        assert published == ["contested.json"], published
        assert not [name for name in os.listdir(directory) if name.endswith(".tmp")], "no temporary file may remain"
        # The published payload belongs to the one racer that reported success.
        winner = json.loads(Path(directory, "contested.json").read_text(encoding="utf-8"))
        assert str(winner["racer"]) == str(outcomes.index("true")), (
            f"the surviving intent must be the winner's, got racer={winner['racer']!r}"
        )
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_exclusive_create_confines_a_traversal_name_and_refuses_oversize() -> None:
    result = run_typescript(
        f'''
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        import {{ createExclusiveJsonFile, safeFileName }} from "{KIT}";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "kit-intent-"));
        const traversal = "../../../escape";
        const won = createExclusiveJsonFile(dir, traversal, {{ ok: true }});
        const escaped = fs.existsSync(path.resolve(dir, traversal + ".json"));
        const outside = fs.existsSync(path.join(os.tmpdir(), "escape.json"));
        let error = "";
        try {{
          createExclusiveJsonFile(dir, "big", {{ blob: "z".repeat(200) }}, {{ maxBytes: 64, label: "Task intent" }});
        }} catch (caught) {{ error = caught.message; }}
        console.log(JSON.stringify({{
          won,
          escaped,
          outside,
          safeFileName: safeFileName(traversal),
          written: fs.readdirSync(dir),
          error,
        }}));
        fs.rmSync(dir, {{ recursive: true, force: true }});
        '''
    )
    assert result["won"] is True
    assert result["escaped"] is False, "a traversal name must not escape the intent directory"
    assert result["outside"] is False
    assert "/" not in str(result["safeFileName"]), "the separator must be encoded"
    assert result["written"] == ["..%2F..%2F..%2Fescape.json"], result["written"]
    assert result["error"] == "Task intent exceeds 64 bytes."


# ── Rule: draining an intent never destroys an in-flight publish ──


def test_take_intent_drains_in_order_and_reports_the_consumers_reason() -> None:
    result = run_typescript(
        f'''
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        import {{ createExclusiveJsonFile, takeJsonIntent }} from "{KIT}";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "kit-take-"));
        const validate = (parsed) => {{
          const value = parsed;
          if (typeof value?.taskId !== "string" || value.taskId === "") {{
            return {{ ok: false, reason: "requires non-empty taskId" }};
          }}
          return {{ ok: true, value }};
        }};
        createExclusiveJsonFile(dir, "b-task", {{ taskId: "b" }});
        createExclusiveJsonFile(dir, "a-task", {{ taskId: "a" }});
        const first = takeJsonIntent(dir, validate, {{ label: "task intent" }});
        const second = takeJsonIntent(dir, validate, {{ label: "task intent" }});
        const third = takeJsonIntent(dir, validate, {{ label: "task intent" }});
        createExclusiveJsonFile(dir, "bad", {{ nope: true }});
        const bad = takeJsonIntent(dir, validate, {{ label: "task intent" }});
        const missing = takeJsonIntent(path.join(dir, "absent"), validate);
        console.log(JSON.stringify({{
          first: first.intent, firstDiagnostic: first.diagnostic,
          second: second.intent,
          thirdIntent: third.intent ?? null, thirdDiagnostic: third.diagnostic ?? null,
          badIntent: bad.intent ?? null, badDiagnostic: bad.diagnostic ?? null,
          remaining: fs.readdirSync(dir).filter((name) => name.endsWith(".json")),
          missingIntent: missing.intent ?? null, missingDiagnostic: missing.diagnostic ?? null,
        }}));
        fs.rmSync(dir, {{ recursive: true, force: true }});
        '''
    )
    assert result["first"]["taskId"] == "a", "the lowest name drains first"
    assert result["second"]["taskId"] == "b"
    assert result["thirdIntent"] is None
    assert result["badIntent"] is None
    assert result["badDiagnostic"] == 'malformed task intent "bad.json" was consumed (requires non-empty taskId)', (
        "the label parameter must reproduce the consumer's existing wording exactly"
    )
    assert result["remaining"] == [], "a consumed intent must be removed so it cannot block the queue"
    assert result["missingIntent"] is None
    assert result["missingDiagnostic"] is None, "a missing directory is empty, not an error"


def test_take_intent_retries_a_young_partial_and_consumes_an_old_one() -> None:
    result = run_typescript(
        f'''
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        import {{ takeJsonIntent }} from "{KIT}";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "kit-grace-"));
        const validate = (parsed) => ({{ ok: true, value: parsed }});
        const young = path.join(dir, "young.json");
        fs.writeFileSync(young, '{{"half":');
        const youngTake = takeJsonIntent(dir, validate, {{ label: "task intent" }});
        const youngSurvived = fs.existsSync(young);
        const old = path.join(dir, "old.json");
        fs.writeFileSync(old, '{{"half":');
        const past = Date.now() / 1000 - 3600;
        fs.utimesSync(old, past, past);
        fs.rmSync(young, {{ force: true }});
        const oldTake = takeJsonIntent(dir, validate, {{ label: "task intent" }});
        console.log(JSON.stringify({{
          youngIntent: youngTake.intent ?? null,
          youngDiagnostic: youngTake.diagnostic ?? null,
          youngSurvived,
          oldIntent: oldTake.intent ?? null,
          oldDiagnostic: oldTake.diagnostic ?? null,
          oldRemoved: !fs.existsSync(old),
        }}));
        fs.rmSync(dir, {{ recursive: true, force: true }});
        '''
    )
    assert result["youngIntent"] is None
    assert result["youngDiagnostic"] is None, "a half-written intent inside the grace is not an error yet"
    assert result["youngSurvived"] is True, "destroying an in-flight intent would strand its author"
    assert result["oldIntent"] is None
    assert result["oldDiagnostic"] == 'unreadable task intent "old.json" was consumed'
    assert result["oldRemoved"] is True


# ── Rule: a required environment binding is all-or-nothing ──


def test_required_env_binding_is_all_or_nothing() -> None:
    result = run_typescript(
        f'''
        import {{ readRequiredEnvBinding }} from "{KIT}";
        const names = ["WORKER_NAME", "SPAWN_ID", "OUTBOX"];
        const complete = readRequiredEnvBinding(names, {{ WORKER_NAME: "rev", SPAWN_ID: "s1", OUTBOX: "/tmp/o" }});
        const missing = readRequiredEnvBinding(names, {{ WORKER_NAME: "rev", SPAWN_ID: "s1" }});
        const empty = readRequiredEnvBinding(names, {{ WORKER_NAME: "rev", SPAWN_ID: "", OUTBOX: "/tmp/o" }});
        const extra = readRequiredEnvBinding(["ONLY"], {{ ONLY: "v", UNRELATED: "x" }});
        console.log(JSON.stringify({{ complete, missing: missing ?? null, empty: empty ?? null, extra }}));
        '''
    )
    assert result["complete"] == {"WORKER_NAME": "rev", "SPAWN_ID": "s1", "OUTBOX": "/tmp/o"}
    assert result["missing"] is None, "a missing name must yield no binding at all"
    assert result["empty"] is None, "an empty value counts as missing"
    assert result["extra"] == {"ONLY": "v"}, "the binding holds exactly the requested names"


# ── Packaging and layout invariants ──


def test_session_key_scopes_per_session_and_falls_back_to_cwd() -> None:
    """Two packages keep per-session state and must agree on the directory."""
    result = run_typescript(
        f'''
        import {{ sessionKey }} from "{(SRC / "index.ts").as_uri()}";
        console.log(JSON.stringify({{
          a: sessionKey("/sessions/a.jsonl", "/proj"),
          aAgain: sessionKey("/sessions/a.jsonl", "/elsewhere"),
          b: sessionKey("/sessions/b.jsonl", "/proj"),
          cwd: sessionKey(undefined, "/proj"),
          cwdAgain: sessionKey(undefined, "/proj"),
          length: sessionKey("/sessions/a.jsonl", "/proj").length,
        }}));
        '''
    )
    assert result["a"] == result["aAgain"], "the session file, not the cwd, is the scope when present"
    assert result["a"] != result["b"], "two sessions in one project must not share state"
    assert result["cwd"] == result["cwdAgain"], "the fallback is deterministic"
    assert result["cwd"] != result["a"], "a session file and a bare cwd are different scopes"
    assert result["length"] == 16


def test_worker_runtime_stays_inside_the_single_file_module() -> None:
    """pi-kit's single-file layout is a deliberate loader-compatibility
    invariant, not an accident: src/index.ts documents that a zero-internal-import
    module resolves identically under Node type stripping, tsx, pi's extension
    loader, and tsc with any moduleResolution. Adding a sibling module and
    re-exporting it would reintroduce the relative-specifier edge case that
    invariant exists to avoid."""
    source = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "Worker runtime primitives" in source, "the primitives must live in src/index.ts"
    siblings = [path.name for path in SRC.glob("*.ts") if path.name != "index.ts"]
    assert siblings == [], f"src/ must stay a single module; found {siblings}"
    assert 'from "./' not in source, "src/index.ts must have no internal relative import"
    for name in (
        "readJsonlBatch", "appendJsonlLine", "writeJsonAtomic",
        "createExclusiveJsonFile", "takeJsonIntent", "readRequiredEnvBinding", "safeFileName",
    ):
        assert f"export function {name}" in source, name


def test_worker_runtime_imports_no_pi_core_or_consumer_package() -> None:
    """The primitives are node builtins only, so pi-kit's dependency-free
    manifest stays honest."""
    source = (SRC / "index.ts").read_text(encoding="utf-8")
    section = source[source.index("Worker runtime primitives"):]
    assert "@earendil-works/" not in section, "the worker-runtime section must not import pi core"
    assert "@fradser/" not in section
    assert "import " not in section, "the section must reuse the module's existing node imports"
