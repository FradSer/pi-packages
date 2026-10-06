"""Offline output-builder contracts: features/agent-output.feature.

These probes use invented records, not a live provider/session reproduction.
The module is imported directly; the parent owns child-execution.ts integration.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "packages/subagents/src/agent-output.ts"


def isolated_env(home: str) -> dict[str, str]:
    """No ambient Pi bindings, credentials, user configuration or network."""
    return {
        "PATH": os.environ.get("PATH", ""),
        "HOME": home,
        "PI_CODING_AGENT_DIR": str(Path(home) / "agent"),
        "XDG_CONFIG_HOME": str(Path(home) / "config"),
        "XDG_CACHE_HOME": str(Path(home) / "cache"),
        "PI_OFFLINE": "1",
        "NO_COLOR": "1",
    }


def run_node(script: str) -> None:
    preamble = f"""
      import assert from "node:assert/strict";
      import net from "node:net";
      import tls from "node:tls";
      import http from "node:http";
      import https from "node:https";
      import {{ Buffer }} from "node:buffer";
      const noNetwork = () => {{ throw new Error("Network forbidden in agent-output tests"); }};
      globalThis.fetch = noNetwork;
      net.connect = net.createConnection = tls.connect = noNetwork;
      http.request = http.get = https.request = https.get = noNetwork;
      const output = await import({json.dumps(MODULE.as_uri())});
      const {{ default: Schema }} = await import("typebox/schema");
      const {{ Value }} = await import("typebox/value");
      const {{ validateToolArguments }} = await import("@earendil-works/pi-ai");
      const {{ defineTool }} = await import("@earendil-works/pi-coding-agent");
      const schema = output.AGENT_TOOL_OUTPUT_SCHEMA;
      const validator = Schema.Compile(schema);
      const bytes = value => Buffer.byteLength(value, "utf8");
      const lines = text => text ? text.split(/\\r\\n|\\r|\\n/).length : 0;
      const checked = result => {{
        const text = result.content.map(part => part.text).join("\\n");
        assert.ok(bytes(text) <= 16 * 1024, `text budget: ${{bytes(text)}}`);
        assert.ok(lines(text) <= 200, `line budget: ${{lines(text)}}`);
        assert.ok(bytes(JSON.stringify(result.structuredContent)) <= 32 * 1024, "structured budget");
        assert.ok(bytes(JSON.stringify(result.details)) <= 32 * 1024, "details budget");
        assert.deepEqual(result.details, result.structuredContent);
        assert.ok(validator.Check(result.structuredContent), JSON.stringify(validator.Errors(result.structuredContent)));
        assert.ok(Value.Check(schema, result.structuredContent), "dynamic schema agreement");
        const validated = validateToolArguments({{ name: "agent-output", parameters: schema }},
          {{ name: "agent-output", arguments: result.structuredContent }});
        assert.deepEqual(validated, result.structuredContent, "native Pi raw JSON validation");
        assert.equal(result.isError === true, result.details.ok === false);
        assert.equal(text.isWellFormed(), true, "no split Unicode code points");
        return result.details;
      }};
      const session = index => ({{ name: `worker-${{index}}`, session: `session:worker-${{index}}:id-${{index}}`,
        status: "stopped", sequenceEnded: true, role: `worker-${{index}}`, tools: ["read"],
        scope: "session", resultKind: "result" }});
      const definition = index => ({{ name: `saved-${{index}}`, status: "offline", scope: "project",
        source: `/project/.pi/agents/saved-${{index}}/agent.md`, description: "Review code", tools: ["read"] }});
    """
    with tempfile.TemporaryDirectory(prefix="agent-output-home-") as home:
        result = subprocess.run(
            ["node", "--input-type=module", "--eval", preamble + script],
            cwd=REPO, env=isolated_env(home), capture_output=True, text=True, timeout=45,
        )
    assert result.returncode == 0, result.stderr + result.stdout


def test_flat_output_schema_and_all_successful_outcomes() -> None:
    run_node("""
      assert.equal(schema.type, "object");
      assert.deepEqual(schema.required, ["operation", "ok", "outcome", "state", "nextActor"]);
      assert.equal(schema.additionalProperties, false);
      assert.ok(schema.oneOf.length>=6,"output schema validates discriminated branches");
      const base = {nextActor:"caller",name:"worker",session:"session:worker:id",grant:["read"],model:"provider/model",
        scope:"project",source:"/project/.pi/agents/worker/agent.md",cwd:"/project"};
      const examples = [
        {operation:"start",ok:true,outcome:"started",state:"accepted",prompted:true,prompt:"Review",...base},
        {operation:"start",ok:true,outcome:"started",state:"idle",prompted:false,...base},
        {operation:"input",delivery:"next",ok:true,outcome:"prompted",state:"working",prompted:true,prompt:"Check",...base},
        {operation:"input",delivery:"steer",ok:true,outcome:"interrupted",state:"working",steering:true,prompt:"Steer",...base},
        {operation:"stop",ok:true,outcome:"stopped",state:"stopped",evidence:"Process only",...base},
        {operation:"list",ok:true,outcome:"listed",state:"read-only",nextActor:"caller",agents:[],sessions:[],definitions:[],count:0,total:0,
          page:{offset:0,limit:20,returned:0,omitted:0,remaining:0,before:0,totalSessions:0,totalDefinitions:0}},
      ];
      for(const data of examples) {
        const before=JSON.stringify(data);
        const result=output.createAgentResult("receipt",data);
        assert.deepEqual(checked(result),data);
        assert.equal(JSON.stringify(data),before);
      }
      const tool=defineTool({name:"output-probe",label:"Output",description:"Offline schema seam",
        parameters:{type:"object",properties:{},required:[]},outputSchema:schema,
        async execute(){return output.createAgentResult("receipt",examples[0]);}});
      checked(await tool.execute("offline",{},undefined,undefined,{}));
      for(const invalid of [{ok:true,outcome:"started",state:"idle"},
        {operation:"start",ok:true,outcome:"made-up",state:"idle"},
        {operation:"start",ok:true,outcome:"started",state:"acknowledged"},
        {...examples[0],extra:"undeclared"},
        {operation:"list",ok:true,outcome:"stopped",state:"unknown",nextActor:"caller"},
        {operation:"stop",ok:false,outcome:"error",state:"unknown",nextActor:"caller"},
        {...examples[0],session:undefined},
        {...examples[2],session:undefined},
        {...examples[0],nextActor:undefined}]) assert.equal(validator.Check(JSON.parse(JSON.stringify(invalid))),false,JSON.stringify(invalid));
    """)


@pytest.mark.parametrize("text", ["界𠮷e\u0301" * 7000, "line\n" * 1000, "界𠮷\r\n" * 1000], ids=["multibyte", "many-lines", "crlf"])
def test_unicode_safe_text_and_line_bounds_include_marker(text: str) -> None:
    run_node(f"""
      const raw={json.dumps(text)};
      const result=output.boundedToolText(raw);
      assert.ok(bytes(result.text)<=16384);assert.ok(lines(result.text)<=200);
      assert.ok(result.truncation);assert.equal(result.truncation.truncated,true);
      assert.equal(result.truncation.originalBytes,bytes(raw));
      assert.equal(result.truncation.originalLines,lines(raw));
      assert.equal(result.truncation.outputBytes,bytes(result.text));
      assert.equal(result.truncation.outputLines,lines(result.text));
      assert.ok(result.text.includes(result.truncation.marker));assert.ok(result.text.isWellFormed());
      const prefix=result.text.slice(0,result.text.indexOf(result.truncation.marker)).trimEnd();
      assert.ok(raw.startsWith(prefix));
    """)


def test_text_exact_boundaries_and_one_line_preview() -> None:
    run_node("""
      for(const raw of ["", "short", "x".repeat(16384), Array(200).fill("line").join("\\n"), "𠮷".repeat(4096)]) {
        const bounded=output.boundedToolText(raw);
        assert.equal(bounded.text,raw);assert.equal(bounded.truncation,undefined);
      }
      const bounded=output.boundedToolText("𠮷".repeat(2000)+"\\nTAIL",{maxBytes:180,maxLines:1});
      assert.ok(bytes(bounded.text)<=180);assert.equal(lines(bounded.text),1);
      assert.ok(bounded.text.includes(bounded.truncation.marker));assert.ok(bounded.text.isWellFormed());
      assert.throws(()=>output.boundedToolText("long",{maxBytes:1}),RangeError);
    """)


@pytest.mark.parametrize("operation", ["start", "input", "list", "stop"])
def test_returned_failure_data_and_sanitized_bounded_diagnostics(operation: str) -> None:
    run_node(f"""
      const raw="\\u001b[31mPROVIDER_FAILURE\\u001b[0m\\u0007"+"界𠮷\\n".repeat(8000)+"TAIL";
      const context={{name:"worker",session:"session:worker:id",state:"working",status:"working",
        controlOutcome:"uncertain",pendingIntent:"stop",nextActor:"runtime",grant:["read"],scope:"session"}};
      const result=output.createAgentFailure({json.dumps(operation)},"operation-failed",raw,context);
      const data=checked(result);
      assert.equal(data.operation,{json.dumps(operation)});assert.equal(data.outcome,"error");
      assert.equal(data.code,"operation-failed");assert.equal(data.message,data.error);
      for(const [key,value] of Object.entries(context)) assert.deepEqual(data[key],value);
      assert.ok(!JSON.stringify(data).includes("TAIL"));
      assert.ok(!JSON.stringify(data).includes("\\\\u001b")&&!JSON.stringify(data).includes("\\\\u0007"));
      assert.ok(data.truncation.fields.some(field=>field.field==="error"));
    """)


def test_failure_action_is_bounded_without_guessing_a_start_or_ack_state() -> None:
    run_node("""
      const data=checked(output.createAgentFailure("bad\\u001b[31m"+"界".repeat(20000),"invalid-action","Bad action"));
      assert.equal(data.operation,"invalid");assert.equal(data.state,"unknown");
      assert.ok(bytes(data.requestedOperation)<1024);assert.ok(data.requestedOperation.includes("truncated"));
      assert.equal(data.controlOutcome,undefined);assert.equal(data.pendingIntent,undefined);
      assert.equal(data.nextActor,"caller");
      const atCut="x".repeat(999)+"𠮷"+"z".repeat(2000);
      const diagnostic=checked(output.createAgentFailure("start","spawn-failed",atCut));
      assert.ok(diagnostic.message.isWellFormed());
      assert.ok(diagnostic.message.includes("diagnostic truncated"));
    """)


def test_roster_previews_bound_nested_metadata_and_keep_exact_authority() -> None:
    run_node("""
      const record={...session(0),grant:["read","grep"],tools:["read","grep"],scope:"project",
        source:"/project/.pi/agents/worker-0/agent.md",currentTaskId:"task:exact",
        assignment:{id:"assignment:exact",kind:"task",resources:["file:exact"],closed:false},
        liveText:("界𠮷"+String.fromCharCode(34,92,10)).repeat(30000)+"FINAL_RESULT_TAIL",activeTool:"read "+"界".repeat(40000),
        error:"\\u001b[31mERROR_HEAD\\u001b[0m\\u0007"+"x".repeat(100000),
        finalDiagnostic:"PROVIDER_DIAGNOSTIC "+"𠮷".repeat(10000),
        metadata:{nested:{huge:Array(200).fill({text:"界".repeat(16000)})}}};
      const before=JSON.stringify(record);
      const data=checked(output.createAgentListPage([record],[]));
      assert.equal(data.ok,true);assert.equal(data.state,"read-only");assert.equal(data.nextActor,"caller");
      assert.equal(data.outcome,"listed");assert.equal(data.sessions.length,1);
      const view=data.sessions[0];
      for(const key of ["name","session","status","grant","tools","scope","source","currentTaskId","assignment"])
        assert.deepEqual(view[key],record[key]);
      // The roster is a status summary, so the child's output is omitted rather
      // than bounded, and the omission is stated rather than silent.
      assert.equal(view.liveText,undefined);
      assert.ok(view.truncation.omittedFields.includes("liveText"));
      assert.ok(view.truncation.fields.some(field=>field.field==="liveText"&&field.reason==="summary"));
      assert.ok(view.error.includes("diagnostic truncated"));assert.ok(view.finalDiagnostic.isWellFormed());
      assert.ok(view.activeTool.includes("truncated"));
      assert.equal(view.metadata,undefined);assert.ok(view.truncation.omittedFields.includes("metadata"));
      assert.ok(view.previewNotice.includes("metadata"));
      assert.ok(!JSON.stringify(data).includes("FINAL_RESULT_TAIL"));
      assert.equal(JSON.stringify(record),before,"raw state and final-result evidence stay intact");
      view.tools.push("mutated-return");view.assignment.resources.push("mutated-return");
      assert.equal(JSON.stringify(record),before,"returned nested metadata is detached");
    """)


def test_small_roster_record_keeps_exact_fields_and_unanswered_classification() -> None:
    run_node("""
      const record={...session(0),error:"short diagnostic",activeTool:"read",
        resultKind:"unanswered",unansweredReason:"length",stopReason:"length",finalDiagnostic:"short provider detail"};
      const result=output.createAgentListPage([record],[]);
      const data=checked(result);
      for(const [key,value] of Object.entries(record)) assert.deepEqual(data.sessions[0][key],value);
      const text=result.content[0].text;
      assert.ok(text.includes("unanswered · No usable final answer"));
      assert.ok(text.includes("error · short diagnostic"));
      assert.equal(data.sessions[0].truncation,undefined);
    """)


def test_unrepresentable_exact_grant_is_an_explicit_limit_error() -> None:
    run_node("""
      const record={...session(0),tools:["exact-tool:"+"x".repeat(40000)],grant:["read"],scope:"project",
        source:"/project/.pi/agents/worker-0/agent.md"};
      const before=JSON.stringify(record);
      const data=checked(output.createAgentListPage([record],[]));
      assert.equal(data.ok,false);assert.equal(data.code,"output-limit");assert.equal(data.operation,"list");
      assert.equal(data.session,record.session);assert.equal(data.name,record.name);assert.equal(data.status,"stopped");
      assert.deepEqual(data.grant,["read"]);assert.equal(data.scope,"project");
      assert.equal(data.tools,undefined);assert.ok(data.limit.omittedFields.includes("tools"));
      assert.ok(data.message.includes("exact"));assert.ok(data.message.includes("limit"));
      assert.equal(JSON.stringify(record),before);
    """)


def test_huge_exact_identity_is_never_presented_as_a_shortened_handle() -> None:
    run_node("""
      const record={...session(0),session:"session:worker-0:"+"x".repeat(100000)};
      const data=checked(output.createAgentListPage([record],[]));
      assert.equal(data.ok,false);assert.equal(data.code,"output-limit");assert.equal(data.session,undefined);
      assert.equal(data.name,record.name);assert.ok(data.limit.omittedFields.includes("session"));
      assert.ok(!JSON.stringify(data).includes("session:worker-0:xxx"));
    """)


def test_list_twenty_long_results_is_a_summary_not_twenty_full_readbacks() -> None:
    run_node("""
      const records=Array.from({length:20},(_,index)=>({...session(index),liveText:"界".repeat(16000)+`TAIL-${index}`}));
      const before=JSON.stringify(records);
      const result=output.createAgentListPage(records,[]);
      const data=checked(result);
      assert.equal(data.ok,true);assert.equal(data.count,20);assert.equal(data.total,20);
      assert.equal(data.page.limit,20);assert.equal(data.page.returned,20);assert.equal(data.page.omitted,0);
      assert.equal(data.page.nextOffset,undefined);
      assert.deepEqual(data.agents,data.sessions);
      assert.ok(data.previewNotice.includes("Session Result"));assert.ok(result.content[0].text.includes("summary"));
      for(const view of data.sessions) {
        assert.equal(view.liveText,undefined);assert.ok(view.truncation.omittedFields.includes("liveText"));
        assert.ok(view.truncation.fields.some(field=>field.field==="liveText"&&field.reason==="summary"));
      }
      assert.ok(!JSON.stringify(data).includes("TAIL-"));
      assert.equal(JSON.stringify(records),before);
    """)


def test_default_maximum_and_offset_pages_across_sessions_and_definitions() -> None:
    run_node("""
      const records=Array.from({length:31},(_,index)=>session(index));
      const definitions=Array.from({length:31},(_,index)=>definition(index));
      const expected=[...records,...definitions].map(record=>record.name);
      let offset=0;const seen=[];
      for(let attempt=0;attempt<10;attempt++) {
        const data=checked(output.createAgentListPage(records,definitions,{offset}));
        assert.equal(data.ok,true);assert.equal(data.total,62);assert.equal(data.page.limit,20);
        assert.equal(data.page.before,offset);assert.equal(data.count,31);
        assert.equal(data.page.totalSessions,31);assert.equal(data.page.totalDefinitions,31);
        assert.equal(data.page.returned,data.sessions.length+data.definitions.length);
        assert.equal(data.page.omitted,62-data.page.returned);
        assert.equal(data.page.remaining,62-offset-data.page.returned);
        seen.push(...data.sessions.map(record=>record.name),...data.definitions.map(record=>record.name));
        if(data.page.nextOffset===undefined) break;
        assert.equal(data.page.nextOffset,offset+data.page.returned);offset=data.page.nextOffset;
      }
      assert.deepEqual(seen,expected);assert.equal(new Set(seen).size,62);
      const max=checked(output.createAgentListPage(records,definitions,{limit:500}));
      assert.equal(max.page.limit,50);assert.ok(max.page.returned<=50);
      const past=checked(output.createAgentListPage(records,definitions,{offset:100}));
      assert.equal(past.page.returned,0);assert.equal(past.page.before,62);assert.equal(past.page.nextOffset,undefined);
    """)


def test_aggregate_json_budget_reduces_page_without_skipping_records() -> None:
    run_node("""
      const records=Array.from({length:50},(_,index)=>({...session(index),
        tools:["exact:"+"\\\"\\\\".repeat(1600)],liveText:"界".repeat(16000)}));
      const before=JSON.stringify(records);let offset=0;const seen=[];let pages=0;
      do {
        const result=output.createAgentListPage(records,[],{offset,limit:50});
        const data=checked(result);assert.equal(data.ok,true);
        assert.ok(data.page.returned>0&&data.page.returned<50,"aggregate budget reduces page size");
        for(const record of data.sessions) assert.deepEqual(record.tools,records[Number(record.name.split("-")[1])].tools);
        seen.push(...data.sessions.map(record=>record.session));
        assert.ok(result.content[0].text.includes("omitted"));
        pages++;assert.ok(pages<=50);
        if(data.page.nextOffset===undefined) break;
        assert.equal(data.page.nextOffset,offset+data.page.returned);offset=data.page.nextOffset;
      } while(true);
      assert.deepEqual(seen,records.map(record=>record.session));assert.equal(JSON.stringify(records),before);
    """)


def test_aggregate_text_budget_and_optional_previews_are_explicit() -> None:
    run_node("""
      const records=Array.from({length:50},(_,index)=>({...session(index),error:"failure "+"𠮷".repeat(5000),
        activeTool:"tool "+"界".repeat(5000)}));
      const definitions=Array.from({length:50},(_,index)=>({...definition(index),description:"界𠮷".repeat(10000)}));
      const all=[...records,...definitions];const seen=[];let offset=0;
      for(let attempt=0;attempt<100;attempt++) {
        const data=checked(output.createAgentListPage(records,definitions,{offset,limit:50}));
        assert.equal(data.ok,true);assert.ok(data.page.returned>0);
        for(const view of data.sessions) {
          assert.ok(view.error.includes("truncated"));assert.ok(view.activeTool.includes("truncated"));
          assert.ok(view.truncation.fields.length>=2);
        }
        for(const view of data.definitions) {
          assert.ok(view.description.includes("truncated"));
          assert.ok(view.truncation.fields.some(field=>field.field==="description"));
        }
        seen.push(...data.sessions.map(view=>view.name),...data.definitions.map(view=>view.name));
        if(data.page.nextOffset===undefined) break;
        offset=data.page.nextOffset;
      }
      assert.deepEqual(seen,all.map(view=>view.name));
    """)


def test_a_blocked_record_is_not_silently_skipped_at_page_boundary() -> None:
    run_node("""
      const records=[session(0),{...session(1),tools:["x".repeat(50000)]},session(2)];
      const first=checked(output.createAgentListPage(records,[],{limit:50}));
      assert.equal(first.ok,true);assert.equal(first.page.returned,1);assert.equal(first.page.nextOffset,1);
      const blocked=checked(output.createAgentListPage(records,[],{offset:first.page.nextOffset}));
      assert.equal(blocked.ok,false);assert.equal(blocked.code,"output-limit");assert.equal(blocked.limit.offset,1);
      assert.equal(blocked.session,records[1].session);assert.ok(blocked.limit.omittedFields.includes("tools"));
      assert.ok(!JSON.stringify(first).includes(records[2].session));assert.equal(blocked.page,undefined);
    """)


@pytest.mark.parametrize("options", [{"offset": -1}, {"offset": 1.5}, {"limit": 0}, {"limit": 2.5}])
def test_invalid_page_options_return_structured_errors(options: dict[str, float]) -> None:
    run_node(f"""
      const data=checked(output.createAgentListPage([session(0)],[],{json.dumps(options)}));
      assert.equal(data.ok,false);assert.equal(data.code,"invalid-parameters");assert.equal(data.operation,"list");
    """)


def test_management_receipts_fit_json_escaping_without_losing_exact_metadata() -> None:
    run_node("""
      const data={operation:"start",ok:true,outcome:"started",state:"idle",name:"reader",session:"session:reader:id",
        nextActor:"caller",prompted:false,prompt:"\\\"\\\\界𠮷\\n".repeat(30000),role:"Review "+"x".repeat(30000),
        grant:["read"],model:"provider/model",scope:"project",source:"/project/.pi/agents/reader/agent.md",
        metadata:{nested:Array(200).fill("x".repeat(5000))}};
      const before=JSON.stringify(data);
      const result=output.createAgentResult("Receipt\\n".repeat(1000),data);
      const fitted=checked(result);assert.equal(fitted.ok,true);
      for(const key of ["name","session","grant","model","scope","source"]) assert.deepEqual(fitted[key],data[key]);
      assert.ok(fitted.prompt.includes("truncated"));assert.ok(fitted.truncation.fields.some(field=>field.field==="prompt"));
      assert.ok(fitted.truncation.text.truncated);assert.equal(fitted.metadata,undefined);
      assert.ok(fitted.truncation.omittedFields.includes("metadata"));assert.equal(JSON.stringify(data),before);
    """)


@pytest.mark.parametrize("raw", ["short diagnostic", "x" * 1000, "\x1b[31m" + "界" * 1001 + "\x1b[0m\x07"],
    ids=["short", "at-limit", "sanitized-over-limit"])
def test_diagnostic_compatibility_is_identical_in_text_and_details(raw: str) -> None:
    run_node(f"""
      const raw={json.dumps(raw)};
      const safe=raw.includes("\\u001b")?"界".repeat(1001):raw;
      const expected=safe.length>1000?safe.slice(0,1000)+"… [diagnostic truncated]":safe;
      const record={{...session(0),error:raw,finalDiagnostic:raw}};
      for(const result of [output.createAgentListPage([record],[])]) {{
        const data=checked(result),view=data.sessions[0];
        assert.equal(view.error,expected);assert.equal(view.finalDiagnostic,expected);
        assert.ok(result.content[0].text.includes("error · "+expected));
        assert.deepEqual(output.createAgentResult(result.content[0].text,result.details),result);
      }}
    """)


def test_normalization_is_idempotent_and_cancellation_facts_survive() -> None:
    run_node("""
      const raw="\\u001b[31mFAILURE\\u001b[0m\\u0007"+"𠮷".repeat(10000);
      const cancelled=output.createAgentFailure("input","cancelled",raw,{state:"starting",outcome:"cancelled",
        nextActor:"runtime",pendingIntent:"input",dispatched:true,controlOutcome:"uncertain",session:"session:worker:id"});
      const data=checked(cancelled);
      assert.equal(data.operation,"input");
      assert.equal(data.outcome,"cancelled");assert.equal(data.code,"cancelled");assert.equal(data.state,"starting");
      assert.equal(data.nextActor,"runtime");assert.equal(data.pendingIntent,"input");assert.equal(data.dispatched,true);
      assert.equal(data.controlOutcome,"uncertain");assert.equal(data.session,"session:worker:id");
      assert.deepEqual(output.createAgentResult(cancelled.content[0].text,cancelled.details),cancelled);
      const listed=output.createAgentListPage([{...session(0),error:raw,liveText:"界𠮷".repeat(10000)}],[]);
      checked(listed);
      // The roster bounds a diagnostic once and states the omission instead of
      // carrying the child's output.
      assert.equal(listed.details.sessions[0].error.split("diagnostic truncated").length-1,1);
      assert.equal(listed.details.sessions[0].liveText,undefined);
      assert.ok(listed.details.sessions[0].truncation.omittedFields.includes("liveText"));
      const prompt=output.createAgentResult("receipt",{operation:"input",delivery:"next",ok:true,outcome:"prompted",state:"accepted",
        nextActor:"runtime",name:"worker",session:"session:worker:id",prompted:true,prompt:"界".repeat(30000)});
      const promptData=checked(prompt);
      assert.ok(promptData.prompt.includes("management preview truncated"));
      assert.ok(!promptData.prompt.includes("Session Result is complete"));
    """)


def test_native_types_accept_schema_and_discriminated_output_without_any() -> None:
    # The generated fixture is temporary and is removed by TemporaryDirectory.
    # Keeping it below tests lets tsc resolve the repo's installed native types.
    source = f"""
      import {{ defineTool, type AgentToolResult, type ToolDefinition }} from "@earendil-works/pi-coding-agent";
      import {{ Type }} from "typebox";
      import {{ AGENT_TOOL_OUTPUT_SCHEMA, createAgentResult, createAgentFailure,
        createAgentListPage, type AgentToolData, type AgentSessionView, type AgentDefinitionView,
        type AgentResult }} from {json.dumps(str(MODULE))};
      const view: AgentSessionView = {{name:"worker",session:"session:worker:id",status:"idle",sequenceEnded:true,
        role:"worker",tools:["read"],assignment:{{id:"attempt",kind:"task",resources:["file"]}}}};
      const definition: AgentDefinitionView = {{name:"saved",status:"offline",scope:"project",description:"Review",tools:["read"]}};
      const schema: NonNullable<ToolDefinition["outputSchema"]> = AGENT_TOOL_OUTPUT_SCHEMA;
      const result: AgentResult = createAgentResult("Started",{{operation:"start",ok:true,outcome:"started",state:"idle",
        nextActor:"caller",name:view.name,session:view.session!,grant:view.tools!,prompted:false}});
      const native: AgentToolResult<AgentToolData> = result;
      const tool = defineTool({{name:"offline",label:"Offline",description:"Compile-only",
        parameters:Type.Object({{}}),outputSchema:schema,async execute(){{return native;}}}});
      const failures: AgentToolResult<AgentToolData>[] = [createAgentFailure("stop","stop-unconfirmed","Not confirmed",{{
        session:view.session,state:"working",controlOutcome:"unconfirmed"}}),
        createAgentListPage([view],[definition],{{offset:0,limit:20}})];
      function narrow(data: AgentToolData): string {{
        if(!data.ok) return data.code + data.error;
        if(data.operation==="list") return String(data.count + data.total + data.page.returned);
        if(data.operation==="start") return data.session;
        return data.outcome;
      }}
      // @ts-expect-error a send receipt cannot claim a stopped outcome
      const badOutcome: AgentToolData = {{operation:"input",delivery:"next",ok:true,outcome:"stopped",state:"stopped",nextActor:"caller",name:"a",session:"session:a:id",prompt:"p",prompted:true}};
      // @ts-expect-error success data does not carry failure codes
      const badSuccess: AgentToolData = {{operation:"stop",ok:true,outcome:"stopped",state:"stopped",nextActor:"caller",name:"a",session:"session:a:id",code:"operation-failed"}};
      // @ts-expect-error acknowledgement is not a process state
      const badState: AgentToolData = {{operation:"stop",ok:true,outcome:"stopped",state:"acknowledged",nextActor:"caller",name:"a",session:"session:a:id"}};
      void [tool, failures, narrow, badOutcome, badSuccess, badState];
    """
    with tempfile.TemporaryDirectory(prefix="agent-output-types-", dir=REPO / "tests") as scratch:
        fixture = Path(scratch) / "fixture.ts"
        fixture.write_text(source, encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="agent-output-type-home-") as home:
            result = subprocess.run(
                ["pnpm", "exec", "tsc", "--noEmit", "--strict", "--skipLibCheck", "--target", "ES2022",
                 "--module", "ESNext", "--moduleResolution", "bundler", "--allowImportingTsExtensions", str(fixture)],
                cwd=REPO, env=isolated_env(home), capture_output=True, text=True, timeout=60,
            )
    assert result.returncode == 0, result.stdout + result.stderr
