from __future__ import annotations

import subprocess
import textwrap

from test_monitor_package import REPO


def run_probe(script: str) -> None:
    result = subprocess.run(
        ["node", "--import", "tsx", "--input-type=module"],
        cwd=REPO, input=textwrap.dedent(HARNESS + script), text=True,
        capture_output=True, timeout=25, check=False,
    )
    assert result.returncode == 0, f"{result.stderr}\n{result.stdout}"


HARNESS = r'''
import assert from "node:assert/strict";
import { MonitorManager, MAX_LINE_BUFFER, MAX_RESULT_TEXT } from "./packages/monitor/src/monitor.ts";
const CAPTURE_BUDGET = 32 * 1024;
const quote = (text) => "'" + text.replaceAll("'", "'\\''") + "'";
const probe = async (body, pattern, verify) => {
  const manager = new MonitorManager({ onTerminal() {} });
  try {
    const started = manager.start({
      command: "node -e " + quote(body), description: "integrity fixture",
      resultPattern: pattern, timeoutMs: 4000,
    });
    let response;
    // Inspect the actual IPC response to ensure limits apply before transfer,
    // rather than only to the final main-thread projection.
    const worker = manager.active.get(started.id).matcher;
    worker.on("message", (value) => { if (value) response = value; });
    const terminal = await manager.waitForTerminal(started.id);
    verify(terminal.result, response);
  } finally { await manager.stopAllOnShutdown(); }
};
const nested = (count, leaf) => Array.from({length:count}, (_,i)=>`(?<field${i}>`).join("") + leaf + ")".repeat(count);
'''


def test_oversized_physical_line_never_matches_fragment_anchors() -> None:
    run_probe(r'''
      for (const newline of [false, true]) {
        const body = `process.stdout.write('x'.repeat(${MAX_LINE_BUFFER})+'READY'${newline ? "+'\\n'" : ""}); setTimeout(()=>process.exit(0),500)`;
        await probe(body, "^READY$", (result) => {
          assert.equal(result.status, "failure", JSON.stringify(result));
          assert.equal(result.reason, "matcher_line_limit");
          assert.equal(result.outputTruncated, true);
          assert.ok(result.output?.length, "oversized line retains bounded diagnostics");
          assert.ok(Buffer.byteLength(JSON.stringify(result.output)) < 33 * 1024);
        });
      }
    ''')


def test_capture_budget_applies_inside_worker_and_discloses_loss() -> None:
    run_probe(r'''
      await probe("process.stdout.write('a'.repeat(4096)+'\\n')", nested(100, "a{4096}"), (result, response) => {
        assert.equal(result.status, "success");
        assert.equal(result.capturesTruncated, true);
        assert.ok(Buffer.byteLength(JSON.stringify(result.captures)) <= CAPTURE_BUDGET);
        assert.ok(Object.values(result.captures).every((value) => Buffer.byteLength(value) <= MAX_RESULT_TEXT));
        assert.ok(!Object.hasOwn(response, "values"), "unused positional captures must not cross IPC");
        assert.ok(Buffer.byteLength(JSON.stringify(response)) <= CAPTURE_BUDGET + MAX_RESULT_TEXT + 1024);
      });
      await probe("process.stdout.write(('\\\\'+String.fromCharCode(34)).repeat(2048)+'\\n')", nested(30, ".{4096}"), (result) => {
        assert.equal(result.status, "success");
        assert.equal(result.capturesTruncated, true);
        assert.ok(Buffer.byteLength(JSON.stringify(result.captures)) <= CAPTURE_BUDGET, "JSON escape bytes count toward the budget");
      });
    ''')


def test_exact_line_budget_accepts_split_crlf_record_delimiter() -> None:
    run_probe(r'''
      await probe(`process.stdout.write('x'.repeat(${MAX_LINE_BUFFER})+'\\r'); setTimeout(()=>process.stdout.write('\\n'),75); setTimeout(()=>process.exit(0),150)`,
        `^x{${MAX_LINE_BUFFER}}$`, (result) => {
          assert.equal(result.status, "success", "CRLF delimiters do not count as record payload");
          assert.equal(result.reason, undefined);
        });
    ''')


def test_json_has_priority_and_truncated_json_is_not_parsed() -> None:
    run_probe(r'''
      const payload = JSON.stringify({ value: "a".repeat(3000) });
      await probe(`process.stdout.write(${JSON.stringify(payload)}+'\\n')`, nested(20, "(?<json>.*)"), (result) => {
        assert.equal(result.status, "success");
        assert.equal(result.capturesTruncated, true);
        assert.deepEqual(result.result, { value: "a".repeat(3000) });
        assert.equal(result.captures.json, payload);
        assert.ok(Buffer.byteLength(JSON.stringify(result.captures)) <= CAPTURE_BUDGET);
      });
      const escaped = JSON.stringify("\\".repeat(10000));
      assert.ok(Buffer.byteLength(escaped) < CAPTURE_BUDGET);
      await probe(`process.stdout.write(${JSON.stringify(escaped)}+'\\n')`, "(?<json>.*)", (result) => {
        assert.equal(result.status, "success");
        assert.equal(result.capturesTruncated, true);
        assert.equal(result.result, undefined);
        assert.match(result.resultParseError, /capture.*(?:budget|limit|exceed)/i);
        assert.ok(Buffer.byteLength(JSON.stringify(result.captures ?? {})) <= CAPTURE_BUDGET);
      });
    ''')


def test_empty_json_reports_parse_error_and_valid_primitives_still_parse() -> None:
    run_probe(r'''
      for (const value of ["", "0", "false", "null"]) {
        await probe(`process.stdout.write('DONE'+${JSON.stringify(value)}+'\\n')`, "^DONE(?<json>.*)$", (result) => {
          assert.equal(result.status, "success");
          if (value === "") {
            assert.ok(result.resultParseError, "empty JSON is an error rather than absent JSON");
            assert.equal(result.result, undefined);
          } else {
            assert.deepEqual(result.result, JSON.parse(value));
            assert.equal(result.resultParseError, undefined);
          }
        });
      }
    ''')
