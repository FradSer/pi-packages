from test_monitor_package import run_harness, run_typescript


def test_repeated_matcher_captures_have_compact_reconstructable_content() -> None:
    run_harness(r'''
        try {
          const names = Array.from({ length: 30 }, (_, i) => `field${i}`);
          const pattern = "^" + names.map(name => `(?<${name}>`).join("") + "a{4096}" + ")".repeat(names.length) + "$";
          const result = await start.execute("compact-captures", { command: "node -e \"console.log('a'.repeat(4096))\"",
            result_pattern: pattern }, undefined, undefined, ctx({ mode: "print", hasUI: false }));
          const content = result.content[0].text;
          assert.ok(Buffer.byteLength(content) < 9000, `Repeated captures expanded content to ${Buffer.byteLength(content)} bytes`);
          const fields = Object.create(null);
          for (const line of content.split("\n")) {
            const ordinary = /^capture\.([^=]+)=(.*)$/.exec(line);
            const alias = /^capture_alias\.([^=]+)=(.*)$/.exec(line);
            if (ordinary) fields[ordinary[1]] = ordinary[2];
            if (alias) { assert.ok(Object.hasOwn(fields, alias[2]), "alias must point backwards"); fields[alias[1]] = fields[alias[2]]; }
          }
          assert.deepEqual({ ...fields }, result.details.result.captures);
          assert.deepEqual(result.structuredContent.result.captures, result.details.result.captures);
          assert.match(content, /captures_truncated=true/);
        } finally { await shutdown(); }
    ''')


def test_report_aliases_json_only_when_exactly_equal_and_retains_scalars() -> None:
    run_typescript(r'''
        import assert from "node:assert/strict";
        import { formatTerminalContent } from "./packages/monitor/src/report.ts";
        for (const value of [false, null, 0, { value: "中文\\quoted\nline" }]) {
          const json = JSON.stringify(value);
          const result = { status: "success", elapsedMs: 1.3, result: value,
            captures: { json, first: json, second: json, unequal: json + "x" } };
          const before = structuredClone(result);
          const text = formatTerminalContent("test", result, "monitor_a");
          assert.ok(text.includes(`result=${json}`), text);
          assert.match(text, /^capture_alias.first=json$/m);
          assert.match(text, /^capture_alias.second=json$/m);
          assert.ok(text.includes(`capture.unequal=${json}x`));
          assert.deepEqual(result, before, "formatting cannot mutate structured/UI data");
        }
    ''')


def test_report_preserves_unequal_unicode_and_sanitizes_untrusted_fields() -> None:
    run_typescript(r'''
        import assert from "node:assert/strict";
        import { formatTerminalContent } from "./packages/monitor/src/report.ts";
        const result = { status: "failure", elapsedMs: 1200, captures: {
          名称: "中文\\path\nline", 副本: "中文\\path\nline", distinct: "中文\\path\nline extra",
          clean: "secret", control: "\u001b[31msecret", newline: "x\ny", literal: "x\\ny",
        }, resultParseError: "invalid\u001b[0m json", capturesTruncated: true,
          output: ["diagnostic 1", "diagnostic 2"], outputTruncated: true, expected: "DONE", exitCode: 7,
          signal: "SIGTERM", reason: "command_failed", timeoutMs: 5000 };
        const text = formatTerminalContent("label\u001b[31m", result, "monitor_a");
        assert.match(text, /^capture_alias.副本=名称$/m);
        for (const name of ["distinct", "clean", "control", "newline", "literal"])
          assert.ok(text.includes(`capture.${name}=`), `distinct raw value ${name} must remain explicit`);
        assert.ok(!text.includes("\u001b"));
        for (const field of ["result_parse_error=", "captures_truncated=true", "output=", "output_truncated=true",
          "expected=DONE", "exit_code=7", "signal=SIGTERM", "reason=command_failed", "timeout_ms=5000"])
          assert.ok(text.includes(field), field);
        assert.equal(result.captures.control, "\u001b[31msecret", "full details retain raw data");
        const invalidJson = formatTerminalContent("bad", { status: "success", elapsedMs: 1,
          captures: { json: "{bad", ordinary: "{bad", duplicate: "{bad" }, resultParseError: "invalid JSON" });
        assert.match(invalidJson, /^capture.ordinary=\{bad$/m);
        assert.match(invalidJson, /^capture_alias.duplicate=ordinary$/m);
        assert.ok(!invalidJson.includes("=json\n"));
    ''')
