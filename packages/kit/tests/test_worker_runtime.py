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


# ── Worker usage ledger and failed terminal output contracts ──


def test_worker_ledger_and_failed_output_parsing_contracts() -> None:
    result = run_typescript(
        fr'''
        import {{ parsePiWorkerUsageLedger, parsePiWorkerOutput }} from {json.dumps(KIT)};
        const reply = (stopReason, input, cost, text = "final", errorMessage) => ({{
          type: "message_end",
          message: {{
            role: "assistant",
            stopReason,
            ...(errorMessage ? {{ errorMessage }} : {{}}),
            content: [{{ type: "text", text }}],
            usage: {{ input, output: 2, cacheRead: 3, cacheWrite: 0, totalTokens: input + 5, cost: {{ total: cost }} }},
          }},
        }});
        const events = [reply("toolUse", 10, 0.01), reply("stop", 20, 0.02)];
        const output = events.map(JSON.stringify).join("\n");
        const good = parsePiWorkerUsageLedger(output);
        const failed = parsePiWorkerUsageLedger(output + "\n" + JSON.stringify({{ type: "message_end", message: {{ role: "assistant", stopReason: "error", usage: {{ input: 0, output: 0 }} }} }}));
        const partial = parsePiWorkerUsageLedger(output + '\n{{"type":"message_end"');
        const missingField = parsePiWorkerUsageLedger(JSON.stringify({{ type: "message_end", message: {{ role: "assistant", stopReason: "stop", usage: {{ input: 7, output: 2, cost: {{ total: 0.04 }} }} }} }}));
        const missing = parsePiWorkerUsageLedger(output + "\n" + JSON.stringify({{ type: "message_end", message: {{ role: "assistant", stopReason: "stop" }} }}));
        const terminalFailures = ["error", "aborted"].map((stopReason) =>
          parsePiWorkerOutput(JSON.stringify(reply(stopReason, 0, 0, "partial plan", "PRIVATE")))
        );
        const recoveryRows = [
          [reply("stop", 1, 0, "earlier"), reply("error", 0, 0, "partial")],
          [reply("error", 0, 0, "partial"), reply("stop", 10, 0.01, "recovered")],
          [reply("error", 0, 0, "partial"), {{ type: "auto_retry_end", success: true }}],
        ].map((seq) => parsePiWorkerOutput(seq.map(JSON.stringify).join("\n")));
        const retryCancelled = [true, false].map((success) =>
          parsePiWorkerOutput([reply("error", 0, 0, ""), reply("aborted", 0, 0, ""), {{ type: "auto_retry_end", success }}].map(JSON.stringify).join("\n"))
        );
        console.log(JSON.stringify({{
          good, failed, partial, missing, missingField,
          legacy: parsePiWorkerOutput(output),
          terminalFailures, recoveryRows, retryCancelled,
        }}));
        '''
    )
    assert result["good"]["complete"]
    assert result["good"]["knownUsage"] == {"input": 30, "output": 4, "cacheRead": 6, "cacheWrite": 0, "totalTokens": 40, "cost": 0.03}
    assert result["good"]["assistantMessages"] == 2
    for name in ("failed", "partial", "missing"):
        assert not result[name]["complete"]
        assert result[name]["knownUsage"] == result["good"]["knownUsage"]
    assert result["legacy"]["usage"]["input"] == 20
    assert not result["missingField"]["complete"]
    assert result["missingField"]["knownUsage"]["input"] == 7
    assert result["missingField"]["knownUsage"]["cost"] == 0.04
    assert result["terminalFailures"] == [{"text": "", "failure": "model-error"}, {"text": "", "failure": "cancelled"}]
    # Note: recovered reply after failed message omits total usage because failed request prevents complete total
    assert result["recoveryRows"] == [{"text": "", "failure": "model-error"}, {"text": "recovered"}, {"text": "", "failure": "model-error"}]
    assert result["retryCancelled"] == [{"text": "", "failure": "cancelled"}] * 2


def test_actual_worker_cumulative_usage_and_failed_exit_contracts() -> None:
    result = run_typescript(
        fr'''
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const root = fs.mkdtempSync(path.join(os.tmpdir(), "kit-worker-outcomes-"));
        const pkg = path.join(root, "package");
        fs.mkdirSync(pkg);
        fs.writeFileSync(path.join(pkg, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const cli = path.join(pkg, "cli.mjs");
        const prior = process.argv[1];
        process.argv[1] = cli;
        try {{
          const {{ runPiWorker }} = await import({json.dumps(KIT)});
          const sumEvents = [10, 20].map((input) => ({{
            type: "message_end",
            message: {{ role: "assistant", stopReason: "stop", content: [{{ type: "text", text: "done" }}], usage: {{ input, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: input + 1, cost: {{ total: 0.01 }} }} }},
          }}));
          fs.writeFileSync(cli, sumEvents.map((e) => "console.log(" + JSON.stringify(JSON.stringify(e)) + ");").join("\n"));
          const cumulative = await runPiWorker({{ prompt: "inspect", cwd: root, minimal: true, tools: [] }});

          const exitZeroFailures = [];
          for (const stopReason of ["error", "aborted"]) {{
            fs.writeFileSync(cli, "console.log(" + JSON.stringify(JSON.stringify({{
              type: "message_end",
              message: {{ role: "assistant", stopReason, errorMessage: "PRIVATE-DO-NOT-RELAY", content: [{{ type: "text", text: "partial plan" }}], usage: {{ input: 0, output: 0 }} }},
            }})) + ");");
            exitZeroFailures.push(await runPiWorker({{ prompt: "inspect", cwd: root, minimal: true, tools: [] }}));
          }}

          const recoveredEvents = ["error", "stop"].map((stopReason) => ({{
            type: "message_end",
            message: {{ role: "assistant", stopReason, errorMessage: "PRIVATE", content: [{{ type: "text", text: "recovered valid plan" }}], usage: {{ input: 1, output: 1, totalTokens: 2, cost: {{ total: 0 }} }} }},
          }}));
          fs.writeFileSync(cli, recoveredEvents.map((e) => "console.log(" + JSON.stringify(JSON.stringify(e)) + ");").join("\n") + "\nprocess.exitCode=7;");
          const nonZeroExit = await runPiWorker({{ prompt: "inspect", cwd: root, minimal: true, tools: [] }});

          console.log(JSON.stringify({{ cumulative, exitZeroFailures, nonZeroExit }}));
        }} finally {{
          process.argv[1] = prior;
          fs.rmSync(root, {{ recursive: true, force: true }});
        }}
        '''
    )
    assert result["cumulative"]["usage"]["input"] == 30
    assert result["cumulative"]["usage"]["totalTokens"] == 32
    assert result["cumulative"]["usage"]["cost"] == 0.02

    rows = result["exitZeroFailures"]
    assert all(row["exitCode"] != 0 and row["text"] == "" and "usage" not in row for row in rows)
    assert [row["cancelled"] for row in rows] == [False, True]
    assert all("PRIVATE" not in row["stderr"] for row in rows)
    assert [row["terminal"] for row in rows] == [
        {"kind": "model-error", "nativeExitCode": 0},
        {"kind": "cancelled", "nativeExitCode": 0},
    ]

    nz = result["nonZeroExit"]
    assert nz["text"] == "" and nz["exitCode"] == 7 and "usage" not in nz
    assert nz["usageLedger"]["complete"] is False
    assert nz["terminal"] == {"kind": "process-exit", "nativeExitCode": 7}
    assert "PRIVATE" not in json.dumps(nz["terminal"])


# ── Decision-model transport surface (counterpart to runPiWorker) ──

DECISION_FIXTURE = Path(__file__).with_name("decision-surface-fixture.ts")


def _run_decision(*scenarios: str) -> dict[str, dict[str, object]]:
    result = subprocess.run(
        ["bun", str(DECISION_FIXTURE), *scenarios],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    return {
        value["scenario"]: value
        for line in result.stdout.splitlines()
        if line.strip()
        for value in [json.loads(line)]
    }


def test_decision_surface_answers_validation_retries_cancellation_and_deadline() -> None:
    cases = _run_decision(
        "answers",
        "empty-questions",
        "missing-answer",
        "non-object-answer",
        "no-answers",
        "not-json",
        "oversize",
        "unauthorized",
        "throttled-once",
        "throttled",
        "unreachable",
        "pre-aborted",
        "cancelled",
        "timeout",
    )
    value = cases["answers"]
    assert value["ok"] is True and value["model"] == "jev-1.13.0", value
    assert value["answers"]["a"] == {"type": "noul", "noul": 0.9}
    assert value["answers"]["b"]["probabilities"] == {"yes": 0.9, "no": 0.1}
    assert value["answers"]["b"]["confidence"] == 0.8
    assert "confidence" not in value["answers"]["a"]
    assert value["usage"] == {"inputTokens": 12, "outputTokens": 5} and value["hits"] == 1

    rejected = cases["empty-questions"]
    assert rejected["failure"] == "rejected" and rejected["isDecisionError"] is True and rejected["hits"] == 0

    for scenario in ("missing-answer", "non-object-answer", "no-answers", "not-json", "oversize"):
        assert cases[scenario]["failure"] == "malformed" and cases[scenario]["hits"] == 1, (scenario, cases[scenario])
    assert "omits 1 of 2" in cases["missing-answer"]["message"]

    assert cases["unauthorized"]["failure"] == "unauthorized" and cases["unauthorized"]["hits"] == 1
    assert cases["throttled-once"]["ok"] is True and cases["throttled-once"]["hits"] == 2
    for scenario, failure in (("throttled", "throttled"), ("unreachable", "unreachable")):
        assert cases[scenario]["failure"] == failure and cases[scenario]["hits"] == 3

    assert cases["pre-aborted"]["failure"] == "cancelled" and cases["pre-aborted"]["hits"] == 0
    assert cases["cancelled"]["failure"] == "cancelled" and cases["cancelled"]["hits"] == 1
    assert cases["timeout"]["failure"] == "timeout"
