from test_monitor_package import run_harness, run_typescript


def test_compact_direct_pure_success_uses_native_correlation_without_losing_metadata() -> None:
    run_harness(r'''
      try {
        const result=await start.execute("tiny",{command:"printf 'DONE\\n'",result_pattern:"^DONE$",compact:true,completion:"exit"},
          undefined,undefined,ctx({mode:"print",hasUI:false}));
        assert.equal(result.content[0].text,"status=success\nexit_code=0");
        assert.match(result.structuredContent.monitorId,/^monitor_/);
        assert.equal(result.details.monitorId,result.structuredContent.monitorId);
        assert.ok(result.details.description);
        assert.ok(result.structuredContent.result.elapsedMs>=0);
        assert.equal(result.details.result.exitCode,0);
        assert.equal(sent.length,0);
      } finally {await shutdown();}
    ''')


def test_compact_direct_success_payload_uses_native_envelope_without_loss() -> None:
    run_harness(r'''
      try {
        for(const value of [false,null,0,"",{value:"complete",nested:{ok:true}}]) {
          const json=JSON.stringify(value);
          const code=`console.log('DONE '+${JSON.stringify(json)})`;
          const encoded=Buffer.from(code).toString("base64");
          const command=`node -e 'eval(Buffer.from("${encoded}","base64").toString())'`;
          const result=await start.execute("payload",{command,result_pattern:"^DONE (?<json>.*)$",completion:"exit",compact:true},undefined,undefined,ctx({mode:"print",hasUI:false}));
          assert.ok(result.content[0].text.startsWith("status=success\n"));
          assert.ok(!/^(Monitor:|monitor_id=|elapsed=)/m.test(result.content[0].text));
          assert.deepEqual(JSON.parse(result.content[0].text.split("\n").find(line=>line.startsWith("result=")).slice(7)),value);
          assert.deepEqual(result.structuredContent.result.result,value);
          assert.equal(result.details.monitorId,result.structuredContent.monitorId);
          assert.ok(result.details.description);
        }
      } finally {await shutdown();}
    ''')


def test_compact_tiny_path_preserves_payload_diagnostics_and_custom_identity() -> None:
    run_typescript(r'''
      import assert from "node:assert/strict";
      import {formatTerminalContent} from "./packages/monitor/src/report.ts";
      const pure={status:"success",elapsedMs:2};
      assert.equal(formatTerminalContent("label",pure,"monitor_a",true,true),"status=success");
      assert.match(formatTerminalContent("label",pure,"monitor_a",true),/^monitor_id=monitor_a$/m);
      assert.equal(formatTerminalContent("label",pure,"monitor_a",false,true),formatTerminalContent("label",pure,"monitor_a"));
      for(const result of [
        {...pure,resultParseError:"invalid JSON"},{...pure,capturesTruncated:true},
        {...pure,outputTruncated:true},{...pure,output:["diagnostic"]},
        {...pure,status:"failure",exitCode:2},{...pure,status:"timeout",reason:"timeout"},
        {...pure,status:"result_missing",expected:"DONE"},{...pure,status:"stopped"},
        {...pure,reason:"unexpected"},{...pure,signal:"SIGTERM"},{...pure,exitCode:7},
      ]) {
        const original=structuredClone(result);
        const text=formatTerminalContent("label",result,"monitor_a",true,true);
        assert.match(text,/^monitor_id=monitor_a$/m);
        assert.deepEqual(result,original);
      }
    ''')


def test_compact_unicode_json_respects_regex_and_keeps_complete_payload() -> None:
    run_harness(r'''
      const value={value:"中文\u2028下一步\u2029尾部"};
      const code=`console.log('DONE '+${JSON.stringify(JSON.stringify(value))})`;
      const encoded=Buffer.from(code).toString("base64");
      const command=`node -e 'eval(Buffer.from("${encoded}","base64").toString())'`;
      try {
        const narrow=await start.execute("narrow",{command,result_pattern:"^DONE (?<json>.*)$",completion:"exit",compact:true},undefined,undefined,ctx({mode:"print",hasUI:false}));
        assert.equal(narrow.details.result.status,"result_missing");
        const broad=await start.execute("broad",{command,result_pattern:"^DONE (?<json>[\\s\\S]*)$",completion:"exit",compact:true},undefined,undefined,ctx({mode:"print",hasUI:false}));
        assert.equal(broad.details.result.status,"success");
        assert.deepEqual(broad.structuredContent.result.result,value);
        assert.ok(broad.content[0].text.startsWith("status=success\n"));
        const line=broad.content[0].text.split("\n").find(line=>line.startsWith("result="));
        assert.deepEqual(JSON.parse(line.slice(7)),value);
      } finally {await shutdown();}
    ''')


def test_json_report_preserves_c1_controls_without_terminal_control_bytes() -> None:
    run_typescript(r'''
      import assert from "node:assert/strict";
      import {formatTerminalContent} from "./packages/monitor/src/report.ts";
      const value={value:"start\u0085next\u009b31mend\u009dOSC\u009ctail\u2028line\u2029paragraph"};
      for(const compact of [false,true]) {
        const text=formatTerminalContent("label",{status:"success",elapsedMs:1,result:value},"monitor_a",compact,true);
        const line=text.split("\n").find(line=>line.startsWith("result="));
        assert.deepEqual(JSON.parse(line.slice(7)),value);
        assert.ok(!/[\u0080-\u009f]/.test(text));
      }
    ''')
