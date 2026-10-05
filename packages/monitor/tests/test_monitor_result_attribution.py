"""A terminal result must attribute what ended the run, for both audiences."""

from __future__ import annotations

from test_monitor_console_viewport import CONSOLE
from test_monitor_package import run_harness


def test_a_match_stopped_run_never_reads_like_a_finished_command() -> None:
    run_harness(r'''
      try {
        const matched = await start.execute("match-mode", {
          command: "printf FIRST_DONE; sleep 30", description: "match mode", result_pattern: "FIRST_DONE",
        }, undefined, undefined, ctx({ mode: "print", hasUI: false }));
        const matchResult = matched.details.result;
        assert.equal(matchResult.status, "success");
        assert.equal(matchResult.completion, "match");
        assert.equal(matchResult.stoppedBy, "match", "the contract ended the run, not the process");
        const text = matched.content[0].text;
        assert.match(text, /^completion=match$/m);
        assert.match(text, /^stopped_by=match$/m);
        assert.match(text, /^matched=FIRST_DONE$/m);
        assert.doesNotMatch(text, /^next=/m, "a passing run carries evidence instead of advice");
        // A truncated success must not collapse into the minimal reply, because
        // that reply says only that the run passed.
        assert.notEqual(text.trim(), "status=success");
        const rows = paint(start.renderResult(matched, { expanded: true }, theme, { args: {}, isError: false }), 100);
        const band = rows.join("\n");
        assert.ok(band.includes("Stopped by: the success contract; later steps never ran"), band);
        assert.ok(band.includes("Completion: match"));
        assert.ok(!band.includes("Monitor id:"), "the console list keeps the id");

        const exited = await start.execute("exit-mode", {
          command: "printf SECOND_DONE", description: "exit mode", result_pattern: "^SECOND_DONE$", completion: "exit",
        }, undefined, undefined, ctx({ mode: "print", hasUI: false }));
        assert.equal(exited.details.result.stoppedBy, undefined, "the process finished on its own");
        assert.equal(exited.details.result.exitCode, 0);
        assert.doesNotMatch(exited.content[0].text, /^stopped_by=/m);
      } finally { await shutdown(); }
    ''')


def test_an_unpassed_run_names_the_next_actor_and_its_cause() -> None:
    run_harness(r'''
      import { formatTerminalContent } from "./packages/monitor/src/report.ts";
      const failed = await start.execute("failed", {
        command: "node -e \"process.exit(2)\"", description: "failing command", result_pattern: "NEVER",
      }, undefined, undefined, ctx({ mode: "print", hasUI: false }));
      assert.equal(failed.details.result.status, "failure");
      assert.match(failed.content[0].text, /^next=inspect output, then fix the command$/m);

      const timedOut = await start.execute("timed-out", {
        command: "sleep 30", description: "slow command", result_pattern: "NEVER", timeout_ms: 400,
      }, undefined, undefined, ctx({ mode: "print", hasUI: false }));
      assert.equal(timedOut.details.result.status, "timeout");
      assert.match(timedOut.content[0].text, /^next=rerun with a larger timeout_ms, or finish the work faster$/m);

      // Every unpassed cause names the actor's next move; a passed run stays advice-free.
      const next = (result) => (formatTerminalContent("fixture", result).match(/^next=(.*)$/m) ?? [])[1];
      const cases = [
        [{ status: "stopped", elapsedMs: 5, reason: "manual_stop" }, "the monitor was stopped; no further result arrives"],
        [{ status: "timeout", elapsedMs: 5000, reason: "timeout" }, "rerun with a larger timeout_ms, or finish the work faster"],
        [{ status: "result_missing", elapsedMs: 5000, exitCode: 0, expected: "DONE" },
          "inspect output and expected, then rerun or broaden result_pattern"],
        [{ status: "failure", elapsedMs: 10, reason: "matcher_queue_limit" }, "the matcher stopped; retry with simpler patterns"],
        [{ status: "failure", elapsedMs: 10, reason: "invalid_json_result" }, "fix the json group, or stop requesting parsed json"],
        [{ status: "failure", elapsedMs: 10, stoppedBy: "failure_match" },
          "inspect the captured failure output, then fix the cause"],
        [{ status: "failure", elapsedMs: 10, exitCode: 2, reason: "process_exit" }, "inspect output, then fix the command"],
        [{ status: "failure", elapsedMs: 10, reason: "process_exit" }, "inspect output and reason, then rerun or report the blocker"],
      ];
      for (const [result, expected] of cases) assert.equal(next(result), expected, JSON.stringify(result));
      assert.equal(next({ status: "success", elapsedMs: 10, exitCode: 0, completion: "exit" }), undefined);
    ''')


def test_the_console_uses_the_same_field_vocabulary_as_the_rows() -> None:
    run_harness(CONSOLE + r'''
      try {
        await start.execute("console-vocabulary", {
          command: "set -e\nprintf DONE", description: "console vocabulary", result_pattern: "DONE",
          failure_pattern: "FATAL", timeout_ms: 60000,
        }, undefined, undefined, ctx({ mode: "print", hasUI: false }));
        await open();
        const view = frame();
        for (const expected of [
          "Status: success",
          "Stopped by: the success contract; later steps never ran",
          "Command:",
          "set -e",
          "Success condition: DONE",
          "Failure condition: FATAL",
          "Completion: match",
          "Logs:",
        ]) assert.ok(view.includes(expected), `${expected} missing from:\n${view}`);
        for (const stale of ["command:", "success: DONE", "failure:", "logs:", "status:", "Monitor: "]) {
          assert.ok(!view.includes(stale), `${stale} still uses the old vocabulary:\n${view}`);
        }
      } finally { await shutdown(); }
    ''')
