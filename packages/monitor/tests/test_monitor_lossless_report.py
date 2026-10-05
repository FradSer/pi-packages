from test_monitor_package import run_harness, run_typescript


def test_opt_in_lossless_encoding_reconstructs_json_captures_and_keeps_errors_visible() -> None:
    run_typescript(r'''
      import assert from "node:assert/strict";
      import { formatTerminalContent } from "./packages/monitor/src/report.ts";
      for (const repeated of ["a", "中", "🧪", "\\", "\n", "$&", "\r", "\u001b", "\ud800", "\u2028", "\u2029"]) {
        const result = { status:"failure", elapsedMs:1, result:{value:repeated.repeat(12000)},
          captures:{first:repeated.repeat(4000),same:repeated.repeat(4000)},
          resultParseError:"example error", capturesTruncated:true, outputTruncated:true };
        const original = formatTerminalContent("case", result, "monitor_a");
        const compact = formatTerminalContent("case", result, "monitor_a", true);
        assert.ok(Buffer.byteLength(compact) < Buffer.byteLength(original)/2);
        const match = /^payload_rle=(.*)$/m.exec(compact);
        assert.ok(match, "explicit reversible payload required");
        const decoded = JSON.parse(match[1]).map(part => typeof part === "string" ? part : part[0].repeat(part[1])).join("");
        const restored = compact.replace(/^payload_encoding=.*\npayload_rle=.*$/m, () => decoded);
        assert.equal(restored, original);
        for(const diagnostic of ["status=failure", "result_parse_error=example error", "captures_truncated=true", "output_truncated=true"])
          assert.ok(compact.split("\n").includes(diagnostic), diagnostic);
        assert.equal(result.result.value, repeated.repeat(12000));
      }
      const varied = { status:"success", elapsedMs:1, result:{x:"small",ok:true}, captures:{one:"value"} };
      assert.equal(formatTerminalContent("case",varied,"id",true), formatTerminalContent("case",varied,"id"));
    ''')


def test_compact_option_reaches_registered_headless_and_custom_reports() -> None:
    run_harness(r'''
      const {Value}=await import("typebox/value");
      const {MonitorStartParams}=await import("./packages/monitor/src/types.ts");
      const args={command:"node -e \"console.log('DONE '+JSON.stringify({value:'a'.repeat(24576)}))\"",
        result_pattern:"^DONE (?<json>.*)$",compact:true,completion:"exit"};
      assert.equal(Value.Check(MonitorStartParams,args),true);
      assert.equal(Value.Check(MonitorStartParams,{...args,compact:"yes"}),false);
      try {
        const direct=await start.execute("compact",args,undefined,undefined,ctx({mode:"print",hasUI:false}));
        assert.match(direct.content[0].text,/^payload_rle=/m);
        assert.equal(direct.structuredContent.result.result.value,"a".repeat(24576));
        assert.equal(direct.details.result.result.value,"a".repeat(24576));
        const background=await start.execute("background",args,undefined,undefined,ctx());
        assert.equal(background.terminate,true);
        const deadline=Date.now()+6000;
        while(!sent.length && Date.now()<deadline) await new Promise(resolve=>setTimeout(resolve,10));
        assert.equal(sent.length,1);
        assert.match(sent[0].message.content,/^payload_rle=/m);
        assert.equal(sent[0].message.details.result.result.value,"a".repeat(24576));
      } finally { await shutdown(); }
    ''')
