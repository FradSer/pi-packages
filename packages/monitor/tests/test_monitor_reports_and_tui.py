from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import tempfile
from pathlib import Path

import pytest

from test_monitor_package import PACKAGE, REPO, EXTENSION_HARNESS, HARNESS, run_harness, run_typescript


# ── test_monitor_compact_report.py ──


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

# ── test_monitor_lossless_report.py ──


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

# ── test_monitor_tiny_report.py ──


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

# ── test_monitor_token_boundary.py ──
"""Real Pi/provider serialization checks; no tokenizer dependency or model network."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from live_monitor import stop

FIXTURE = Path(__file__).with_name("token-provider-fixture.ts")


def native_context(tool: str, code: str, **oracle: object) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix="monitor-token-boundary-") as raw:
        root = Path(raw)
        tasktmp = root / "tasktmp"
        tasktmp.mkdir()
        agent = root / "agent"
        agent.mkdir()
        trace = root / "trace.jsonl"
        loaded = tool in ("monitor_start", "codemode")
        spec = {"name": "boundary", "loaded": loaded, "tool": tool, "repeats": 1,
                "command": "node -e " + shlex.quote(code), "result_pattern": "^DONE (?<json>.*)$", **oracle}
        env = dict(os.environ, PI_CODING_AGENT_DIR=str(agent), PI_OFFLINE="1", PI_TELEMETRY="0",
                   TMPDIR=str(tasktmp), PI_MONITOR_TOKEN_SPEC=json.dumps(spec), PI_MONITOR_TOKEN_TRACE=str(trace))
        args = ["pi", "--offline", "-ne", "-ns", "-np", "-nc", "--no-session", "-e", str(FIXTURE),
                "--model", "monitor-token-offline/scripted", "--tools", "bash,monitor_start" if loaded else "bash",
                "--print", "Verify the command outcome."]
        if tool == "codemode":
            args[args.index("--tools") + 1] = "bash,monitor_start,codemode"
            args.extend(["-e", "builtin:codemode"])
        child = subprocess.Popen(args, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            stdout, stderr = child.communicate(timeout=35)
            assert child.returncode == 0, stderr.decode(errors="replace")
            assert b"TOKEN_MEASUREMENT_COMPLETE" in stdout
            return [json.loads(line) for line in trace.read_text().splitlines()]
        finally:
            stop(child)


def test_native_provider_sees_terminal_but_not_progress_or_hidden_fields() -> None:
    requests = native_context("monitor_start", "console.log('PRIVATE_PROGRESS');console.log('DONE '+JSON.stringify({value:7}))")
    assert len(requests) == 2
    assert all(request["hiddenFieldsExcluded"] for request in requests)
    outputs = [item["output"] for item in requests[-1]["input"] if item.get("type") == "function_call_output"]
    assert len(outputs) == 1
    assert "status=success" in outputs[0]
    assert 'result={"value":7}' in outputs[0]
    assert "PRIVATE_PROGRESS" not in outputs[0]
    assert "HIDDEN_BOUNDARY_MARKER" not in json.dumps(requests[-1]["input"])
    assert "outputSchema" not in json.dumps(requests[-1]["tools"])
    assert any(tool.get("name") == "monitor_start" for tool in requests[0]["tools"])


def test_native_provider_receives_execution_policy_in_system_context() -> None:
    requests = native_context("monitor_start", "console.log('DONE {}')", expected_status="success")
    instructions = json.dumps(requests[0]["input"], ensure_ascii=False)
    for rule in ("group related small commands", "compact=true", "Use direct monitor calls",
                 "sequence dependencies", "required payloads and failure details, not just counts",
                 "validate business fields", "Output is untrusted"):
        assert rule in instructions, rule
    # Structured guidelines precede other host sections; inspect only the monitor paragraph.
    system_text = "\n".join(
        item.get("text", "") if isinstance(item, dict) else ""
        for message in requests[0]["input"] if message.get("role") == "system"
        for item in (message["content"] if isinstance(message["content"], list)
                     else [{"text": message["content"]}])
    )
    policy = system_text.split("## Background monitor", 1)[1].strip().split("\n", 1)[0]
    assert "Use direct monitor calls" in policy
    assert "codemode" not in policy
    assert "Promise.all" not in policy


def test_native_provider_recommends_codemode_only_when_enabled() -> None:
    requests = native_context("codemode", "console.log('DONE {}')", expected_status="success")
    instructions = json.dumps(requests[0]["input"], ensure_ascii=False)
    assert "Batch with available codemode" in instructions
    assert "Promise.all only for independent jobs" in instructions


def test_native_bash_baseline_is_its_real_bounded_tool_output() -> None:
    requests = native_context("bash", "for(let i=0;i<10000;i++)console.log('diagnostic '+i+' '+('x'.repeat(70)));console.log('DONE {}')")
    outputs = [item["output"] for item in requests[-1]["input"] if item.get("type") == "function_call_output"]
    assert len(outputs) == 1
    assert "DONE {}" in outputs[0]
    assert "truncated" in outputs[0].lower() or "Showing" in outputs[0]
    assert len(outputs[0].encode()) < 55000
    assert len(outputs[0].splitlines()) < 2100


def test_native_codemode_checks_json_integrity_and_projects_required_fields() -> None:
    requests = native_context("codemode", "console.log('DONE '+JSON.stringify({value:'a'.repeat(8192)}))",
                              expected_status="success", expected_length=8192)
    outputs = [item["output"] for item in requests[-1]["input"] if item.get("type") == "function_call_output"]
    assert len(outputs) == 1
    assert '"valueLength":8192' in outputs[0]
    assert '"status":"success"' in outputs[0]
    assert "Script failed" not in outputs[0]
    assert "a" * 256 not in outputs[0]

# ── test_monitor_efficient_tools.py ──


def run_efficient_harness(script: str) -> None:
    # These content checks render structured guidance; composition checks test the hook directly.
    script = script.replace('await fire("before_agent_start",', 'await renderedGuidance(')
    run_harness(r'''
      const renderedGuidance = async (event, context) => {
        event.systemPromptOptions = {sections: {}};
        const reply = await fire("before_agent_start", event, context);
        assert.equal(reply, undefined);
        return {systemPrompt: event.systemPrompt + Object.values(event.systemPromptOptions.sections).join("\\n")};
      };
    ''' + script)


def test_completion_schema_and_registered_tool_follow_finite_contract() -> None:
    run_efficient_harness(r'''
      const { Value } = await import("typebox/value");
      const { MonitorStartParams } = await import("./packages/monitor/src/types.ts");
      assert.ok(Object.hasOwn(MonitorStartParams.properties, "completion"));
      const base = {command:"printf DONE", result_pattern:"^DONE$"};
      for (const completion of ["match", "exit"]) assert.equal(Value.Check(MonitorStartParams, {...base, completion}), true);
      assert.equal(Value.Check(MonitorStartParams, {...base, completion:"unknown"}), false);
      try {
        const value = await start.execute("finite", {command:"printf DONE; sleep 0.3; printf 'ISH\\n'", result_pattern:"^DONE$", completion:"exit"},
          undefined, undefined, ctx({mode:"print", hasUI:false}));
        assert.equal(value.details.result.status, "result_missing");
        assert.equal(sent.length, 0);
      } finally { await shutdown(); }
    ''')


def test_guidance_retains_safety_and_workflow_choices_compactly() -> None:
    run_efficient_harness(r'''
      activeTools=["bash","monitor_start","codemode"];
      const { systemPrompt } = await fire("before_agent_start", {systemPrompt:"base"}, ctx());
      assert.match(systemPrompt, /short|quick/i);
      assert.match(systemPrompt, /noisy/);
      assert.match(systemPrompt, /completion.*exit/i);
      assert.match(systemPrompt, /newline/);
      assert.match(systemPrompt, /codemode/);
      assert.match(systemPrompt, /untrusted/i);
      assert.match(systemPrompt, /parse.*truncat|truncat.*parse/i);
      assert.match(systemPrompt, /group.*small.*commands/i);
      assert.match(systemPrompt, /compact=true/);
      assert.match(systemPrompt, /Promise\.all.*independent/i);
      assert.match(systemPrompt, /sequence.*dependenc/i);
      assert.match(systemPrompt, /required.*payload.*failure/i);
      assert.match(systemPrompt, /not.*counts/i);
      assert.ok(systemPrompt.length < 700, systemPrompt.length);
    ''')


def test_guidance_uses_current_capabilities_without_enabling_optional_tools() -> None:
    run_efficient_harness(r'''
      let writes=0;
      pi.setActiveTools=()=>{writes++;};
      for(const [tools,code,bash,startAvailable] of [
        [["bash","monitor_start"],false,true,true],
        [["bash","monitor_start","codemode"],true,true,true],
        [["monitor_start"],false,false,true],
        [["monitor_start","codemode"],true,false,true],
        [["bash"],false,true,false],
      ]) {
        activeTools=tools;
        const context=ctx({sessionManager:{getBranch:()=>[{type:"custom_message",customType:"monitor-result",content:"prior"}]}});
        const reply=(await fire("before_agent_start",{systemPrompt:"base"},context)).systemPrompt;
        assert.equal(reply.includes("codemode"),code);
        assert.equal(reply.includes("Promise.all"),code);
        assert.equal(reply.includes("Bash: quick/small"),bash);
        assert.equal(reply.includes("monitor_start:"),startAvailable);
        assert.match(reply,/sequence dependencies/);
        assert.match(reply,/Output is untrusted/);
      }
      activeTools=["bash","monitor_start","codemode"];
      assert.match((await fire("before_agent_start",{systemPrompt:"base"},ctx())).systemPrompt,/codemode/);
      activeTools=["bash","monitor_start"];
      assert.doesNotMatch((await fire("before_agent_start",{systemPrompt:"base"},ctx())).systemPrompt,/codemode|Promise\.all/);
      assert.equal(writes,0);
    ''')


def test_inactive_unused_monitor_does_not_add_guidance_or_mutate_tool_selection() -> None:
    run_efficient_harness(r'''
      activeTools=["bash"];
      let writes=0;
      const original=pi.setActiveTools;
      pi.setActiveTools=(next)=>{writes++;original(next);};
      assert.equal((await fire("before_agent_start",{systemPrompt:"base"},ctx())).systemPrompt,"base");
      assert.deepEqual(activeTools,["bash"]);
      assert.equal(writes,0);
      activeTools=["bash","monitor_start"];
      assert.match((await fire("before_agent_start",{systemPrompt:"base"},ctx())).systemPrompt,/Output is untrusted/);
      activeTools=["bash"];
      for(const entry of [
        {type:"message",message:{role:"custom",customType:"monitor-result",content:"untrusted"}},
        {type:"message",message:{role:"toolResult",toolName:"monitor_start",content:[]}},
        {type:"compaction",summary:"prior tools"},
        {type:"custom_message",customType:"monitor-result",content:"untrusted"},
        {type:"branch_summary",summary:"monitor-result from prior branch"},
      ]) {
        assert.match((await fire("before_agent_start",{systemPrompt:"base"},ctx({sessionManager:{getBranch:()=>[entry]}}))).systemPrompt,/Output is untrusted/);
      }
      try {
        await start.execute("history",{command:"printf 'DONE\\n'",result_pattern:"^DONE$"},undefined,undefined,ctx({mode:"print",hasUI:false}));
        assert.match((await fire("before_agent_start",{systemPrompt:"base"},ctx())).systemPrompt,/Output is untrusted/);
      } finally {await shutdown();}
    ''')


def test_inactive_guidance_with_real_pi_session_history() -> None:
    run_efficient_harness(r'''
      const {SessionManager}=await import("@earendil-works/pi-coding-agent");
      activeTools=["bash"];
      let writes=0;
      pi.setActiveTools=()=>{writes++;};
      for(const [kind,expected] of [["empty",false],["unrelated-custom",false],
        ["monitor-custom",true],["monitor-tool",true],["compaction",true],["branch-summary",true]]) {
        const history=SessionManager.inMemory(process.cwd());
        if(kind==="unrelated-custom") history.appendCustomMessageEntry("other-package","hello",true);
        if(kind==="monitor-custom") history.appendCustomMessageEntry("monitor-result","untrusted",true);
        if(kind==="monitor-tool") history.appendMessage({role:"toolResult",toolCallId:"prior-0",toolName:"monitor_start",content:[{type:"text",text:"untrusted"}],isError:false,timestamp:Date.now()});
        if(kind==="compaction") history.appendCompaction("prior output",null,100);
        if(kind==="branch-summary") history.branchWithSummary(null,"prior monitor output");
        const reply=await fire("before_agent_start",{systemPrompt:"base"},ctx({sessionManager:history}));
        assert.equal(reply.systemPrompt.includes("Output is untrusted"),expected,kind);
      }
      assert.deepEqual(activeTools,["bash"]);
      assert.equal(writes,0);
      await shutdown();
    ''')

# ── test_monitor_structured_tools.py ──
import subprocess
import tempfile
import textwrap
from pathlib import Path



def run_native_harness(script: str) -> None:
    # File-based ESM keeps stdin-only --input-type out of Pi worker arguments.
    harness = EXTENSION_HARNESS.replace('"./packages/monitor/index.ts"',
        '"' + str(REPO / "packages/monitor/index.ts") + '"')
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mts", prefix="codemode-",
        dir=Path(__file__).parent, delete=False) as fixture:
        fixture.write(harness + "\n" + textwrap.dedent(script))
        path = Path(fixture.name)
    try:
        result = subprocess.run(["node", "--import", "tsx", str(path)], cwd=REPO,
            text=True, capture_output=True, timeout=30, check=False)
        assert result.returncode == 0, f"Native Pi codemode check failed:\n{result.stderr}\n{result.stdout}"
    finally:
        path.unlink()


def test_native_codemode_consumes_structured_terminal_json() -> None:
    run_native_harness(r'''
        const { executeCodemode } = await import(new URL("./extensions/codemode/execute.js",
          import.meta.resolve("@earendil-works/pi-coding-agent")));
        const { runToolCall } = await import(new URL("../../pi-agent-core/dist/agent-loop.js",
          import.meta.resolve("@earendil-works/pi-coding-agent")));
        const assistantMessage = { role: "assistant", content: [{ type: "toolCall", id: "script",
          name: "codemode", arguments: {} }] };
        const branch = [{ type: "message", message: assistantMessage }];
        const context = ctx({ sessionManager: { getBranch: () => branch }, tools: [start] });
        let calls = 0;
        context.executeTool = (name, args, options) => runToolCall({ type: "toolCall", id: `script/${++calls}`,
          name, arguments: args }, { assistantMessage, context: { messages: [assistantMessage], tools: [start] },
          tools: [{ ...start, execute: (id, params, signal, update) => start.execute(id, params, signal, update, context) }],
          signal: options.signal });
        try {
          const parameters = { command: "printf 'DONE {\"count\":7}\\n'", result_pattern: "DONE (?<json>.*)" };
          const primitives = [false, null, 0].map(value => ({ value,
            args: { command: `printf 'DONE ${JSON.stringify(value)}\\n'`, result_pattern: "DONE (?<json>.*)" } }));
          const result = await executeCodemode("script", { code: `
            const terminal = await tools.monitor_start(${JSON.stringify(parameters)});
            if (terminal.status !== 'success' || terminal.result.result.count !== 7)
              throw new Error('missing typed monitor outcome');
            text({ status: terminal.status, count: terminal.result.result.count, monitorId: terminal.monitorId });
            for (const fixture of ${JSON.stringify(primitives)}) {
              const value = await tools.monitor_start(fixture.args);
              if (value.result.result !== fixture.value) throw new Error('JSON primitive lost');
            }
          ` }, undefined, undefined, context);
          assert.equal(result.isError, undefined, JSON.stringify(result));
          const output = result.content.filter(block => block.type === "text").map(block => block.text).join("\n");
          assert.match(output, /"count":7/, output);
          assert.match(output, /"status":"success"/, output);
          assert.equal(calls, 4);
          assert.equal(sent.length, 0);
        } finally { await shutdown(); }
    ''')


def test_structured_pending_terminal_and_stop_follow_declared_schemas() -> None:
    run_harness(r'''
        const { Value } = await import("typebox/value");
        try {
          const pending = await start.execute("pending", { command: "sleep 5", result_pattern: "NEVER" },
            undefined, undefined, ctx());
          assert.equal(pending.structuredContent?.status, "running");
          assert.equal(pending.structuredContent.monitorId, pending.details.monitorId);
          assert.equal(Value.Check(start.outputSchema, pending.structuredContent), true);
          const stopped = await stop.execute("stop", { monitor_id: pending.details.monitorId });
          assert.deepEqual(stopped.structuredContent, { stopped: 1 });
          assert.equal(Value.Check(stop.outputSchema, stopped.structuredContent), true);
          const terminal = await start.execute("bad-json", { command: "printf 'DONE {bad}\\n'", result_pattern: "DONE (?<json>.*)" },
            undefined, undefined, ctx({ mode: "print", hasUI: false }));
          assert.equal(terminal.structuredContent.status, "success");
          assert.equal(terminal.structuredContent.result.captures.json, "{bad}");
          assert.ok(terminal.structuredContent.result.resultParseError);
          assert.equal(Value.Check(start.outputSchema, terminal.structuredContent), true);
          assert.match(terminal.content[0].text, /result_parse_error=/);
        } finally { await shutdown(); }
    ''')


def test_preaborted_tool_does_not_start_command() -> None:
    run_harness(r'''
        const { mkdtempSync, rmSync } = await import("node:fs");
        const { tmpdir } = await import("node:os");
        const { join } = await import("node:path");
        const directory = mkdtempSync(join(tmpdir(), "monitor-cancel-"));
        const marker = join(directory, "marker");
        const controller = new AbortController();
        controller.abort();
        try {
          await fire("session_start");
          await assert.rejects(() => start.execute("cancelled", { command: `touch '${marker}'`, result_pattern: "NEVER" },
            controller.signal, undefined, ctx()), { name: "AbortError" });
          await new Promise(resolve => setTimeout(resolve, 150));
          assert.equal(existsSync(marker), false);
          assert.equal(sent.length, 0);
          assert.equal(activeTools.includes("monitor_stop"), false);
        } finally { await shutdown(); rmSync(directory, { recursive: true, force: true }); }
    ''')


def test_nested_abort_stops_command_but_acknowledged_background_survives() -> None:
    run_harness(r'''
        const { mkdtempSync, rmSync } = await import("node:fs");
        const { tmpdir } = await import("node:os");
        const { join } = await import("node:path");
        const directory = mkdtempSync(join(tmpdir(), "monitor-nested-cancel-"));
        const marker = join(directory, "marker");
        const controller = new AbortController();
        const context = ctx({ sessionManager: { getBranch: () => [{ type: "message", message: { role: "assistant",
          content: [{ type: "toolCall", id: "parent", name: "codemode", arguments: {} }] } }] } });
        try {
          const waiting = start.execute("parent/1", { command: `sleep 0.5; touch '${marker}'; printf DONE`, result_pattern: "DONE" },
            controller.signal, undefined, context);
          setTimeout(() => controller.abort(), 50);
          await assert.rejects(waiting, { name: "AbortError" });
          await new Promise(resolve => setTimeout(resolve, 700));
          assert.equal(existsSync(marker), false);
          assert.equal(sent.length, 0);
          const backgroundController = new AbortController();
          const acknowledged = await start.execute("background", { command: "sleep 0.2; printf DONE", result_pattern: "DONE" },
            backgroundController.signal, undefined, ctx());
          assert.equal(acknowledged.terminate, true);
          backgroundController.abort();
          const deadline = Date.now() + 3000;
          while (sent.length === 0 && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 20));
          assert.equal(sent.length, 1);
          assert.equal(sent[0].message.details.result.status, "success");
        } finally { await shutdown(); rmSync(directory, { recursive: true, force: true }); }
    ''')


def test_failed_tool_renderers_preserve_errors() -> None:
    run_harness(r'''
        try {
          for (const tool of [start, stop]) {
            const error = { content: [{ type: "text", text: "EXPLICIT_TOOL_FAILURE" }], details: {} };
            const rendered = paint(tool.renderResult(error, { expanded: true, isPartial: false }, theme,
              { args: {}, toolCallId: "failed", isError: true })).join("\n");
            assert.match(rendered, /EXPLICIT_TOOL_FAILURE/, rendered);
            assert.match(rendered, /failed/, rendered);
            assert.ok(!rendered.includes("started"), rendered);
          }
        } finally { await shutdown(); }
    ''')


def test_matcher_startup_failure_returns_terminal_instead_of_pending() -> None:
    run_harness(r'''
        const threads = (await import("node:worker_threads")).default;
        const { syncBuiltinESMExports } = await import("node:module");
        const originalWorker = threads.Worker;
        threads.Worker = class { constructor() { throw new Error("WORKER_STARTUP_FAILURE"); } };
        syncBuiltinESMExports();
        const context = ctx({ sessionManager: { getBranch: () => [{ type: "message", message: { role: "assistant",
          content: [{ type: "toolCall", id: "standalone", name: "monitor_start", arguments: {} }] } }] } });
        try {
          const result = await start.execute("standalone", { command: "sleep 5", result_pattern: "DONE" },
            undefined, undefined, context);
          assert.equal(result.structuredContent.status, "failure");
          assert.equal(result.details.result.status, "failure");
          assert.match(result.details.result.reason, /WORKER_STARTUP_FAILURE/);
          assert.notEqual(result.terminate, true);
          assert.match(result.content[0].text, /status=failure/);
          assert.ok(!result.content[0].text.includes("terminal_result=pending"));
          assert.equal(sent.length, 0);
          const rendered = paint(start.renderResult(result, { expanded: true, isPartial: false }, theme,
            { args: {}, toolCallId: "standalone", isError: false })).join("\n");
          assert.match(rendered, /failure/);
          assert.match(rendered, /WORKER_STARTUP_FAILURE/);
        } finally {
          threads.Worker = originalWorker;
          syncBuiltinESMExports();
          await shutdown();
        }
    ''')

# ── test_monitor_start_presentation.py ──


def test_start_snapshot_is_pending_and_prioritizes_effective_configuration() -> None:
    run_harness(r'''
      try {
        const args={command:"sleep 30",description:"fixture",result_pattern:"DONE"};
        const result=await start.execute("start-config",args,undefined,undefined,ctx());
        assert.equal(result.details.startConfiguration.cwd,process.cwd());
        assert.equal(result.details.startConfiguration.timeoutMs,600000);
        assert.equal(result.details.startConfiguration.completion,"match");
        const colors=[];
        const tint={...theme,fg:(name,text)=>{colors.push(name);return text;},bg:(name,text)=>{colors.push(name);return text;}};
        const component=start.renderResult(result,{expanded:true},tint,{args,isError:false});
        const lines=paint(component,80).join("\n");
        for(const text of ["Command:","Success condition: DONE"]) assert.ok(lines.includes(text),text);
        for(const absent of ["pending at start","terminal ·","Completion:","Timeout:","cwd ·","id ·","command ·"]) assert.ok(!lines.includes(absent),absent);
        assert.ok(lines.indexOf("Command:")<lines.indexOf("Success condition:"));
        assert.ok(colors.includes("warning")); assert.ok(colors.includes("toolPendingBg"));
        assert.ok(!colors.includes("toolSuccessBg"));
        assert.deepEqual(Object.keys(result.structuredContent).sort(),["description","monitorId","status"]);
        assert.ok(!result.content[0].text.includes("cwd="));
        assert.ok(!result.content[0].text.includes("sleep 30"));
        const before=result.content[0].text;
        paint(start.renderResult(result,{expanded:false},theme,{args,isError:false}),40);
        assert.equal(result.content[0].text,before);
      } finally {await shutdown();}
    ''')


def test_restored_start_snapshot_keeps_exact_command_and_native_expansion() -> None:
    run_harness(r'''
      try {
        const args={command:"sleep 30\n#"+"configuration detail ".repeat(30),description:"fixture",result_pattern:"DONE",failure_pattern:"FATAL",completion:"exit",timeout_ms:1234};
        const result=await start.execute("snapshot",args,undefined,undefined,ctx());
        await stop.execute("stop",{});
        const colors=[];
        const tint={...theme,fg:(name,text)=>{colors.push(name);return text;},bg:(name,text)=>{colors.push(name);return text;}};
        const component=start.renderResult(JSON.parse(JSON.stringify(result)),{expanded:true},tint,{args:{},isError:false});
        const text=paint(component,80).join("\n");
        assert.ok(text.includes("Completion: exit (result match + exit 0)"));
        assert.ok(text.includes("Timeout: 1.234s"));
        assert.ok(text.includes("Failure condition: FATAL"));
        assert.ok(text.includes("configuration detail"));
        assert.equal(result.details.startConfiguration.command,args.command);
        assert.ok(!text.includes("terminal ·")&&!/running/i.test(text),"historical start snapshot must not claim current running state");
        const collapsed=paint(start.renderResult(result,{expanded:false},theme,{args,isError:false}),120).join("\n");
        assert.ok(collapsed.includes("[monitor] started · fixture"));
        assert.ok(collapsed.includes("to expand"));
        paint(component,20);
      } finally {await shutdown();}
    ''')


def test_start_configuration_preserves_meaningful_whitespace() -> None:
    run_harness(r'''
      const {mkdtempSync,rmSync}=await import("node:fs");
      const cwd=mkdtempSync("/tmp/monitor  cwd-");
      try {
        const args={command:"sleep 30; printf 'a  b'\n#  indented",description:"spaces",result_pattern:"a  b",failure_pattern:"FATAL  ERROR"};
        const result=await start.execute("spaces",args,undefined,undefined,ctx({cwd}));
        const restored=JSON.parse(JSON.stringify(result));
        const text=paint(start.renderResult(restored,{expanded:true},theme,{args:{},isError:false}),120).join("\n");
        for(const expected of ["printf 'a  b'","#  indented","Success condition: a  b","Failure condition: FATAL  ERROR"]) assert.ok(text.includes(expected),expected);
        assert.ok(!text.includes("cwd ·"),"cwd has no parameter and equals the session cwd");
        const controls={...restored,details:{...restored.details,startConfiguration:{...restored.details.startConfiguration,command:"printf 'a\tb'\r\n#safe"}}};
        const controlText=paint(start.renderResult(controls,{expanded:true},theme,{args:{},isError:false}),80).join("\n");
        assert.ok(controlText.includes("Command (escaped controls):"));
        assert.ok(controlText.includes("a\\tb"));
        assert.ok(!controlText.includes("\t") && !controlText.includes("\r"));
      } finally {await shutdown();rmSync(cwd,{recursive:true,force:true});}
    ''')


def test_start_command_carries_pi_syntax_color() -> None:
    run_harness(r'''
      try {
        const { initTheme } = await import("@earendil-works/pi-coding-agent");
        initTheme("dark");
        const args={command:"set -e\necho DONE",description:"fixture",result_pattern:"DONE"};
        const result=await start.execute("syntax",args,undefined,undefined,ctx());
        const styled=start.renderResult(result,{expanded:true},theme,{args,isError:false}).render(80);
        const command=styled.find((row)=>stripVTControlCharacters(row).trim()==="set -e");
        assert.ok(command!==undefined,"the command keeps its own row");
        assert.ok(command.includes("\u001b["),"the command row carries Pi theme color");
        assert.equal(stripVTControlCharacters(command).trim(),"set -e","the command text survives its color");
        const label=styled.find((row)=>stripVTControlCharacters(row).trim()==="Command:");
        assert.ok(label!==undefined,"the label keeps its own row");
        assert.ok(!label.includes("\u001b["),"the label keeps kit's plain text color");
      } finally {await shutdown();}
    ''')

# ── test_monitor_console_viewport.py ──



CONSOLE = r'''
let component;
const tui = { terminal: { rows: 24, columns: 80 }, requestRender() {} };
const ui = {
  custom(factory) {
    component = factory(tui, theme, {}, () => {});
    return Promise.resolve();
  },
  notify() {}, setWidget() {},
};
const open = () => commands.get("monitor").handler("", ctx({ ui }));
const frame = () => {
  const rows = paint(component, tui.terminal.columns);
  assert.ok(rows.length <= tui.terminal.rows, `${rows.length} lines exceed ${tui.terminal.rows} rows`);
  assert.ok(!component.render(tui.terminal.columns).join("").includes("\u009b"));
  return rows.join("\n");
};
'''


def test_console_diagnostics_disclosure_scroll_and_resize() -> None:
    run_harness(CONSOLE + r'''
      try {
        await start.execute("diagnostics", {
          command: `node -e "for(let i=0;i<80;i++) console.log('diagnostic-' + i); process.exit(1)"`,
          description: "diagnostic fixture",
          result_pattern: "NEVER_MATCHES",
        }, undefined, undefined, ctx({ mode: "print", hasUI: false }));
        await open();
        assert.ok(!frame().includes("diagnostic-79"), "terminal.output is hidden by default");
        component.handleInput("\r");
        component.handleInput("\u001b[F");
        assert.ok(frame().includes("diagnostic-79"), "End exposes the final output line");
        component.handleInput("\u001b[H");
        assert.ok(frame().includes("Status: failure"), "Home returns to the first detail row");
        for (const rows of [12, 7, 6, 5, 3, 1, 24]) {
          tui.terminal.rows = rows;
          tui.terminal.columns = rows === 1 ? 8 : 40;
          frame();
          component.handleInput("\u001b[F");
          frame();
        }
        tui.terminal.rows = 1; tui.terminal.columns = 80;
        component.handleInput("\u001b[F");
        assert.ok(frame().includes("diagnostic-79"), "one-row terminals can reach output");
        tui.terminal.rows = 24; tui.terminal.columns = 80;
        component.handleInput("\u001b[F");
        assert.ok(frame().includes("diagnostic-79"));
        component.handleInput("\r");
        assert.ok(!frame().includes("diagnostic-79"), "hiding output resets its scroll position");
      } finally { await shutdown(); }
    ''')


def test_console_selection_follows_monitor_id_after_completion() -> None:
    run_harness(CONSOLE + r'''
      try {
        const first = await start.execute("first", { command: "sleep 10", description: "first fixture", result_pattern: "NEVER" }, undefined, undefined, ctx());
        await start.execute("second", { command: "sleep 10", description: "second fixture", result_pattern: "NEVER" }, undefined, undefined, ctx());
        await open();
        assert.ok(frame().includes("(running) first fixture"));
        await stop.execute("finish-first", { monitor_id: first.details.monitorId });
        assert.ok(frame().includes("(stopped) first fixture"), "completion must not select another monitor at the same index");
        component.handleInput("x");
        assert.ok(frame().includes("(running) second fixture"), "x on finished selection must not stop a different monitor");
      } finally { await shutdown(); }
    ''')


def test_console_list_viewport_and_independent_detail_navigation() -> None:
    run_harness(CONSOLE + r'''
      try {
        for (let i = 0; i < 10; i++) {
          await start.execute(`task-${i}`, {
            command: "sleep 10", description: `fixture-${i}\u001b[31m\u009b32m`, result_pattern: "NEVER",
          }, undefined, undefined, ctx());
        }
        await open();
        tui.terminal.rows = 12;
        for (let i = 0; i < 9; i++) component.handleInput("\u001b[B");
        assert.ok(frame().includes("(running) fixture-9"));
        component.handleInput("\u001b[6~");
        frame();
        component.handleInput("\u001b[F");
        assert.ok(frame().includes("Logs: 0 retained"), "last detail is reachable");
        component.handleInput("\u001b[5~");
        frame();
        component.handleInput("\u001b[H");
        assert.ok(frame().includes("Status: running"), "Home returns to the first detail row");
      } finally { await shutdown(); }
    ''')


def test_fullscreen_host_routes_scroll_keys_to_console() -> None:
    run_harness(r'''
      import { TuiAltScreen, TUI_KEYBINDINGS } from "@earendil-works/pi-tui";
      setKeybindings(new KeybindingsManager(TUI_KEYBINDINGS));
      let input;
      let component;
      const terminal = new Proxy({
        rows: 24, columns: 80, kittyProtocolActive: false,
        start(onInput) { input = onInput; },
      }, { get(target, name) { return target[name] ?? (() => {}); } });
      const tui = new TuiAltScreen(terminal, false, undefined, { mouse: false });
      const received = [];
      const ui = {
        custom(factory, options) {
          let overlay;
          component = factory(tui, theme, {}, () => overlay?.hide());
          const handler = component.handleInput;
          component.handleInput = (data) => { received.push(data); handler(data); };
          if (options?.overlay) overlay = tui.showOverlay(component, options.overlayOptions);
          else { tui.addChild(component); tui.setFocus(component); }
          return Promise.resolve();
        }, notify() {}, setWidget() {},
      };
      try {
        await start.execute("fullscreen", {
          command: `node -e "for(let i=0;i<80;i++) console.log('diagnostic-' + i); process.exit(1)"`,
          description: "fullscreen fixture", result_pattern: "NEVER_MATCHES",
        }, undefined, undefined, ctx({ mode: "print", hasUI: false }));
        await commands.get("monitor").handler("", ctx({ ui }));
        tui.start();
        paint(component, 80);
        input("\r");
        for (const key of ["\u001b[6~", "\u001b[F", "\u001b[5~", "\u001b[H"]) input(key);
        assert.deepEqual(received, ["\r", "\u001b[6~", "\u001b[F", "\u001b[5~", "\u001b[H"],
          "fullscreen viewport must defer paging and Home/End to the console");
        input("\u001b[F");
        assert.ok(paint(component, 80).join("\n").includes("diagnostic-79"));
        input("q");
      } finally { tui.stop(); await shutdown(); }
    ''')


def test_console_long_names_keep_status_and_narrow_help_is_reachable() -> None:
    run_harness(CONSOLE + r'''
      try {
        await start.execute("long-name", {
          command: "sleep 10", description: "发布验证中文long-description-".repeat(12), result_pattern: "NEVER",
        }, undefined, undefined, ctx());
        await open();
        for (const columns of [80, 40, 20]) {
          tui.terminal.columns = columns;
          const rows = paint(component, columns);
          assert.ok(rows[2].includes("running"), `state must survive long descriptions: ${rows.join("\n")}`);
          assert.ok(rows.at(-2).includes("? help"), `help must remain discoverable: ${rows.join("\n")}`);
        }
        tui.terminal.rows = 6; tui.terminal.columns = 20;
        assert.ok(paint(component, 20).at(-1).includes("? help"));
        component.handleInput("?");
        component.handleInput("\u001b[F");
        assert.ok(frame().includes("stop all"), "all shortcuts are reachable even at 20x6");
        component.handleInput("?");
        assert.ok(frame().includes("running"), "help restores selection and details");
      } finally { await shutdown(); }
    ''')


def test_console_refresh_timer_is_scoped_and_cleared_on_close() -> None:
    run_harness(CONSOLE + r'''
      const originalSet = globalThis.setInterval;
      const originalClear = globalThis.clearInterval;
      let tick, cleared = false, renders = 0;
      const timer = { unref() {} };
      try {
        await start.execute("live", { command: "sleep 10", description: "live fixture", result_pattern: "NEVER" }, undefined, undefined, ctx());
        globalThis.setInterval = (callback, ms) => {
          assert.ok(ms >= 200, "refresh must be bounded"); tick = callback; return timer;
        };
        globalThis.clearInterval = (value) => { if (value === timer) cleared = true; else originalClear(value); };
        tui.requestRender = () => { renders++; };
        ui.custom = (factory) => new Promise((resolve) => { component = factory(tui, theme, {}, resolve); });
        const opening = open();
        assert.equal(typeof tick, "function", "open console must refresh live output");
        const before = renders;
        tick();
        assert.ok(renders > before);
        assert.equal(sent.length, 0, "refresh never emits model messages");
        component.handleInput("q");
        await opening;
        assert.ok(cleared, "closing console clears its refresh timer");
      } finally {
        globalThis.setInterval = originalSet; globalThis.clearInterval = originalClear;
        await shutdown();
      }
    ''')


def test_open_console_repaints_new_output_before_terminal_result() -> None:
    run_harness(CONSOLE + r'''
      let renders = 0;
      tui.requestRender = () => { renders++; };
      ui.custom = (factory) => new Promise((resolve) => { component = factory(tui, theme, {}, resolve); });
      try {
        await start.execute("progress", {
          command: `node -e "let i=0; setInterval(()=>console.log('live-'+(++i)),100)"`,
          description: "live output", result_pattern: "NEVER",
        }, undefined, undefined, ctx());
        const opening = open();
        component.handleInput("\r");
        const before = renders;
        await new Promise((resolve) => setTimeout(resolve, 600));
        assert.ok(renders >= before + 2, "live progress requests fresh frames while idle");
        component.handleInput("\u001b[F");
        assert.ok(frame().includes("live-"), "new output is visible before completion");
        assert.ok(frame().includes("running"));
        assert.equal(sent.length, 0);
        component.handleInput("q");
        await opening;
        const closedRenders = renders;
        await new Promise((resolve) => setTimeout(resolve, 300));
        assert.equal(renders, closedRenders, "closed console has no background repaints");
      } finally { await shutdown(); }
    ''')


def test_console_shortcuts_decode_kitty_and_ignore_releases_or_control_keys() -> None:
    run_harness(CONSOLE + r'''
      let closed = 0;
      ui.custom = (factory) => { component = factory(tui, theme, {}, () => { closed++; }); return Promise.resolve(); };
      try {
        await start.execute("kitty", { command: "sleep 10", description: "kitty fixture", result_pattern: "NEVER" }, undefined, undefined, ctx());
        await open();
        for (const key of ["\u001b[63u", "\u001b[47:63;2u", "\u001b[27;2;63~", "\u001b[27;1;63~"]) {
          component.handleInput(key);
          assert.ok(frame().includes("Monitor controls"), "encoded question mark opens help");
          component.handleInput("?");
        }
        component.handleInput("\u001b[120;1:3u");
        component.handleInput("\u001b[120;5u");
        component.handleInput("\u001b[27;5;120~");
        component.handleInput("\u001b[27;3;120~");
        component.handleInput("\u001b[27;5;113~");
        assert.equal(closed, 0);
        assert.ok(frame().includes("running"), "release and Ctrl+x must not stop work");
        component.handleInput("\u001b[120u");
        assert.ok(frame().includes("stopped"), "Kitty x stops selected work");
        component.handleInput("\u001b[27;1;113~");
        assert.equal(closed, 1, "modifyOtherKeys q closes console");
        await open();
        component.handleInput("\u001b[113u");
        assert.equal(closed, 2, "Kitty q closes console");
      } finally { await shutdown(); }
    ''')

# ── test_monitor_tui_outcomes.py ──


def test_terminal_rows_keep_status_and_use_outcome_colors() -> None:
    run_harness(r'''
      try {
        for (const status of ["success", "failure", "timeout", "result_missing", "stopped"]) {
          const colors = [];
          const tint = { ...theme, fg: (name, text) => { colors.push(name); return text; }, bg: (name, text) => { colors.push(name); return text; } };
          const result = { content: [{type:"text",text:"report"}], details: { description:"业务校验".repeat(30), monitorId:"fixture", result:{status,elapsedMs:1,reason:"fixture"} } };
          for (const custom of [false,true]) {
            colors.length = 0;
            const component = custom
              ? renderers.get("monitor-result")({customType:"monitor-result",...result},{expanded:false},tint)
              : start.renderResult(result,{expanded:false},tint,{args:{},isError:false});
            for (const width of [20,40,80]) assert.ok(paint(component,width).join("\n").includes(status), `${status} lost at ${width}`);
            if (["failure","timeout","result_missing"].includes(status)) {
              assert.ok(colors.includes("error")); assert.ok(colors.includes("toolErrorBg"));
              assert.ok(!colors.includes("toolSuccessBg"));
            } else if (status === "stopped") assert.ok(colors.includes("dim"));
          }
        }
      } finally { await shutdown(); }
    ''')


def test_large_values_preview_and_full_console_disclosure() -> None:
    run_harness(CONSOLE + r'''
      try {
        const value = "a".repeat(24000) + "PAYLOAD_END";
        const args = { command: `node -e 'console.log("DONE " + JSON.stringify({body:"a".repeat(24000)+String.fromCharCode(80,65,89,76,79,65,68,95,69,78,68),ok:true}))'`, description:"large", result_pattern:"DONE (?<json>.*)", completion:"exit" };
        const result = await start.execute("large",args,undefined,undefined,ctx({mode:"print",hasUI:false}));
        assert.equal(result.details.result.result.body,value);
        const rows = paint(start.renderResult(result,{expanded:true},theme,{args,isError:false}),80);
        assert.ok(rows.length < 30); assert.ok(rows.join("\n").includes("preview"));
        const unicode = {...result,details:{...result.details,result:{...result.details.result,result:{body:String.fromCodePoint(0x20000).repeat(100)}}}};
        assert.ok(!paint(start.renderResult(unicode,{expanded:true},theme,{args,isError:false}),80).join("\n").includes("preview"), "preview threshold counts Unicode code points");
        await open();
        component.handleInput("\u001b[F");
        assert.ok(!frame().includes("PAYLOAD_END"));
        component.handleInput("v"); component.handleInput("\u001b[F");
        assert.ok(frame().includes("PAYLOAD_END"));
        component.handleInput("v"); component.handleInput("\u001b[F");
        assert.ok(!frame().includes("PAYLOAD_END"));
      } finally {await shutdown();}
    ''')


def test_failure_details_precede_long_command() -> None:
    run_harness(CONSOLE + r'''
      try {
        await start.execute("failure", {command:"exit 2\n#"+"long command ".repeat(300), description:"fixture",result_pattern:"DONE",completion:"exit"},undefined,undefined,ctx({mode:"print",hasUI:false}));
        await open(); tui.terminal.rows=6; tui.terminal.columns=40;
        assert.ok(frame().includes("Exit code: 2"));
        assert.ok(frame().includes("Reason: process_exit"));
      } finally {await shutdown();}
    ''')


def test_parallel_widget_has_adaptive_budget() -> None:
    run_harness(r'''
      let widget;
      const tui={terminal:{rows:24},requestRender(){}};
      const ui={setWidget(_key,factory){widget=factory?.(tui,theme);},notify(){}};
      try {
        await fire("session_start",{},ctx({ui}));
        for(let i=0;i<12;i++) await start.execute(`job-${i}`,{command:"sleep 30",description:`job-${i}`,result_pattern:"DONE"},undefined,undefined,ctx({ui}));
        assert.ok(paint(widget,80).length<=3);
        assert.ok(paint(widget,80).join("\n").includes("10 more"));
        tui.terminal.rows=6;
        assert.equal(paint(widget,40).length,1);
        assert.ok(paint(widget,40).join("\n").includes("12 running"));
      } finally {await shutdown();}
    ''')


def test_restored_and_evicted_results_keep_full_transcript_values() -> None:
    run_harness(r'''
      try {
        const value = "a".repeat(500) + "RESTORED_PAYLOAD_END";
        const restored = {customType:"monitor-result",content:"report",details:{description:"restored",monitorId:"missing",result:{status:"success",elapsedMs:1,result:{body:value}}}};
        const restoredRows = paint(renderers.get("monitor-result")(restored,{expanded:true},theme),80).join("\n").replace(/\s/g, "");
        assert.ok(restoredRows.includes("RESTORED_PAYLOAD_END"));
        const args = {command:`node -e 'console.log("DONE " + JSON.stringify({body:"a".repeat(500)+String.fromCharCode(80,65,89,76,79,65,68,95,69,78,68)}))'`,description:"old",result_pattern:"DONE (?<json>.*)",completion:"exit"};
        const result = await start.execute("old",args,undefined,undefined,ctx({mode:"print",hasUI:false}));
        const tool = start.renderResult(result,{expanded:true},theme,{args,isError:false});
        const custom = renderers.get("monitor-result")({customType:"monitor-result",...result},{expanded:true},theme);
        assert.ok(paint(tool,80).join("\n").includes("preview"));
        for(let i=0;i<20;i++) await start.execute(`new-${i}`,{command:"printf DONE",result_pattern:"DONE"},undefined,undefined,ctx({mode:"print",hasUI:false}));
        for(const component of [tool,custom]) {
          const text = paint(component,80).join("\n").replace(/\s/g, "");
          assert.ok(text.includes("PAYLOAD_END"),"existing components must reveal values after history eviction");
        }
      } finally {await shutdown();}
    ''')


def test_stopped_rows_accept_native_theme_instances() -> None:
    run_harness(r'''
      const { getThemeByName } = await import("./node_modules/@earendil-works/pi-coding-agent/dist/modes/interactive/theme/theme.js");
      const nativeTheme = getThemeByName("dark");
      try {
        const result={content:[{type:"text",text:"report"}],details:{description:"stopped",monitorId:"fixture",result:{status:"stopped",elapsedMs:1}}};
        const component=start.renderResult(result,{expanded:true},nativeTheme,{args:{},isError:false});
        assert.ok(paint(component,80).join("\n").includes("stopped"));
      } finally {await shutdown();}
    ''')

# ── test_monitor_result_attribution.py ──
"""A terminal result must attribute what ended the run, for both audiences."""




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

# ── test_monitor_accuracy_matrix.py ──

import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def run_accuracy_matrix() -> dict:
    with tempfile.TemporaryDirectory(prefix="monitor-accuracy-") as directory:
        pid_file = Path(directory) / "pids"
        try:
            completed = subprocess.run(
                ["node", "--import", "tsx", "packages/monitor/tests/accuracy-matrix-fixture.mts"],
                cwd=REPO, env={**os.environ, "MONITOR_MATRIX_PID_FILE": str(pid_file)},
                capture_output=True, text=True, timeout=90,
            )
            assert completed.stdout.strip(), completed.stderr
            report = json.loads(completed.stdout.strip().splitlines()[-1])
            failures = [case for case in report["observed"] if not case["passed"]]
            assert completed.returncode == 0, json.dumps(failures, ensure_ascii=False, indent=2) + completed.stderr
            return report
        finally:
            if pid_file.exists():
                for entry in pid_file.read_text().splitlines():
                    try:
                        os.killpg(int(entry), signal.SIGKILL)
                    except ProcessLookupError:
                        pass


def test_real_process_accuracy_matrix() -> None:
    report = run_accuracy_matrix()
    assert report["cases"] >= 75
    assert report["uniqueMonitorIds"] == report["cases"]
    assert all(case["passed"] for case in report["observed"])


