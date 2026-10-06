"""Regressions for blank review envelopes through the real standalone entry."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from subagents_helpers import SRC, PACKAGE, run_node

SPAWNER = (SRC / "spawner.ts").as_uri()
ENTRY = (PACKAGE / "index.ts").as_uri()
PREAMBLE = f"""
import assert from "node:assert/strict";
import {{mock}} from "node:test";
import * as transport from {json.dumps(SPAWNER)};
let callbacks;const sent=[],spawns=[],prompts=[];
mock.module({json.dumps(SPAWNER)},{{namedExports:{{...transport,
  spawnResident:options=>(callbacks=options,spawns.push(options),{{pid:7,accepted:Promise.resolve(true),readiness:Promise.resolve(true)}}),
  deliverResidentPrompt:async(name,input)=>(prompts.push({{name,input}}),true),
  terminateAgent:async()=>({{outcome:"closed"}}),
}}}});
const {{default:extension,getAgent,resetRoster}}=await import({json.dumps(ENTRY)});
resetRoster();const registered=[],renderers=new Map();
extension({{registerTool:tool=>registered.push(tool),registerMessageRenderer:(type,render)=>renderers.set(type,render),
  on(){{}},events:{{emit(){{}}}},sendMessage:(message,options)=>sent.push({{...message,options}})}});
const intentTools=new Map(registered.filter(t=>t.name.startsWith("agent_")).map(t=>[t.name,t]));
const call=(request)=>{{
  const {{operation,name,session,prompt,tools,...rest}}=request;
  const tool=operation==="input"||operation==="steer"?"agent_input":operation==="inspect"?"agent_list"
    :operation==="stop"?"agent_stop":operation==="list"?"agent_list":"agent_start";
  const params=tool==="agent_start"
    ?{{prompt:prompt??"Start the assigned work.",...(name===undefined?{{}}:{{label:name}}),...(tools===undefined?{{}}:{{tools}}),...rest}}
    :tool==="agent_input"?{{session,prompt,delivery:operation==="steer"?"steer":"next"}}:session===undefined?{{...rest}}:{{session,...rest}};
  return intentTools.get(tool).execute("repro",params,undefined,undefined,{{cwd:process.env.PI_TEST_CWD}});
}};
const begin=()=>callbacks.onUpdate({{text:"",turns:0,finalResponse:false}});
const theme={{fg:(_key,text)=>text,bg:(_key,text)=>text,bold:text=>text}};
const paint=message=>renderers.get(message.customType)(message,{{expanded:true}},theme).render(100).join("\\n");
"""


def run(script: str, tmp_path: Path) -> dict[str, object]:
    return run_node(PREAMBLE + script, module_mocks=True, env_overrides={
        "HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "PI_TEST_CWD": str(tmp_path), "PI_OFFLINE": "1",
    })


CASES = [
    ({"text": "", "stopReason": "stop"}, "empty"),
    ({"text": "  \n\t", "stopReason": "stop"}, "empty"),
    ({"text": "", "stopReason": "stop", "liveThinking": "Review reasoning"}, "empty"),
    ({"text": "", "stopReason": "error", "errorMessage": "provider temporarily unavailable"}, "error"),
    ({"text": "partial", "stopReason": "error", "errorMessage": "provider temporarily unavailable"}, "error"),
    ({"text": "partial", "stopReason": "aborted", "errorMessage": "user cancelled"}, "aborted"),
    ({"text": "partial", "stopReason": "length"}, "length"),
    ({"text": "", "stopReason": "toolUse", "hasToolCalls": True}, "incomplete"),
    ({"text": "partial", "stopReason": "stop", "hasToolCalls": True}, "incomplete"),
]


@pytest.mark.parametrize("terminal,reason", CASES)
def test_authoritative_unusable_answer_is_explicit_and_deduplicated(
    tmp_path: Path, terminal: dict[str, object], reason: str,
) -> None:
    result = run(f"""
      const start=await call({{name:"reviewer",prompt:"Review the fork",tools:[]}});begin();
      const terminal={{...{json.dumps(terminal)},turns:1,finalResponse:true,answerComplete:true}};
      callbacks.onUpdate(terminal);callbacks.onUpdate(terminal);
      const list=await call({{operation:"list"}});
      const outcome=sent[0];
      console.log(JSON.stringify({{count:sent.length,kind:outcome?.details?.kind,reason:outcome?.details?.reason,
        text:outcome?.details?.text,stopReason:outcome?.details?.stopReason,content:outcome?.content,
        options:outcome?.options,status:getAgent(start.details.name).status,list:list.content[0].text,
        row:outcome?paint(outcome):""}}));
    """, tmp_path)
    assert result["count"] == 1
    assert result["kind"] == "unanswered", result
    assert result["reason"] == reason
    assert result["text"] == terminal["text"]
    assert result["stopReason"] == terminal["stopReason"]
    assert "<agent-result-unanswered" in result["content"]
    assert "No usable final answer" in result["content"]
    assert result["options"] == {"deliverAs": "followUp", "triggerTurn": True}
    assert result["status"] == "idle"
    assert "unanswered ·" in result["list"] and "result ·" not in result["list"]
    assert "unanswered" in result["row"]


def test_empty_answer_can_receive_a_later_valid_input_in_the_same_resident(tmp_path: Path) -> None:
    result = run("""
      const first=await call({name:"reviewer",prompt:"Review",tools:[]});begin();
      callbacks.onUpdate({text:"",turns:1,finalResponse:true,answerComplete:true,stopReason:"stop"});
      const next=await call({operation:"input",delivery:"next",session:first.details.session,prompt:"Return a short final verdict"});
      begin();callbacks.onUpdate({text:"No blocking findings. Static review only.",turns:1,finalResponse:true,answerComplete:true,stopReason:"stop"});
      const same=sent.every(message=>message.details.session===first.details.session);
      const stopped=await call({operation:"stop",session:first.details.session});
      callbacks.onExit({pid:7,exitCode:0,signal:null,stdout:"",stderr:""});
      console.log(JSON.stringify({kinds:sent.map(message=>message.details.kind),turns:sent.map(message=>message.details.turn),same,
        spawns:spawns.length,accepted:next.details.ok,stopped:stopped.details.ok,count:sent.length}));
    """, tmp_path)
    assert result == {"kinds": ["unanswered", "result"], "turns": [1, 2], "same": True,
                      "spawns": 1, "accepted": True, "stopped": True, "count": 2}


def test_readiness_and_unconfirmed_empty_frame_do_not_consume_the_answer(tmp_path: Path) -> None:
    result = run("""
      const start=await call({name:"reviewer",tools:[]});
      callbacks.onUpdate({text:"",turns:0,finalResponse:true,ready:true});
      const accepted=await call({operation:"input",delivery:"next",session:start.details.session,prompt:"Review"});begin();
      callbacks.onUpdate({text:"",turns:1,finalResponse:true});
      const before=sent.length;
      callbacks.onUpdate({text:"  Complete final text\\n",turns:1,finalResponse:true,answerComplete:true,stopReason:"stop"});
      console.log(JSON.stringify({before,count:sent.length,kind:sent[0].details.kind,text:sent[0].details.text}));
    """, tmp_path)
    assert result == {"before": 0, "count": 1, "kind": "result", "text": "  Complete final text\n"}


def test_unanswered_delivery_retry_does_not_duplicate_or_reanswer_a_later_sequence(tmp_path: Path) -> None:
    result = run("""
      const {executeChildIntent}=await import("file://"+process.cwd()+"/src/child-execution.ts");
      const notices=[];let attempts=0;
      const start=await executeChildIntent({name:"retry-review",prompt:"Review",tools:[]},{cwd:process.env.PI_TEST_CWD,
        spawn:options=>(callbacks=options,{pid:7,accepted:Promise.resolve(true)}),
        deliverSessionResult:notice=>{
          if(notice.kind==="unanswered"&&++attempts===1)throw new Error("temporary sender failure");
          notices.push(notice);
        }});
      begin();callbacks.onUpdate({text:"",turns:1,finalResponse:true,answerComplete:true,stopReason:"stop"});
      callbacks.onUpdate({text:"",turns:1,finalResponse:true,answerComplete:true,stopReason:"stop"});
      await new Promise(resolve=>setImmediate(resolve));
      console.log(JSON.stringify({attempts,count:notices.length,kind:notices[0].kind,turn:notices[0].turn,
        status:getAgent(start.details.name).status}));
    """, tmp_path)
    assert result == {"attempts":2, "count":1, "kind":"unanswered", "turn":1, "status":"idle"}


def test_unanswered_details_round_trip_and_remain_distinct_from_ended(tmp_path: Path) -> None:
    result = run("""
      const {readSessionNotice,formatSessionNotice,sessionNoticeSpec}=await import("file://"+process.cwd()+"/src/session-result.ts");
      const old={kind:"result",name:"old",session:"session:old:handle",turn:1,text:"legacy answer",deliveredAt:0};
      const invalid={kind:"unanswered",name:"bad",session:"session:bad:handle",reason:"unknown",text:"",turn:1};
      const notice={kind:"unanswered",name:"review",session:"session:review:handle",reason:"length",
        text:"  partial\\n",turn:3,stopReason:"length",errorMessage:"  local diagnosis ",deliveredAt:0};
      const parsed=readSessionNotice(notice);const spec=sessionNoticeSpec(parsed);
      console.log(JSON.stringify({oldKind:readSessionNotice(old).kind,invalid:readSessionNotice(invalid)??null,
        kind:parsed.kind,text:parsed.text,turn:parsed.turn,bg:spec.bgToken,label:spec.label,content:formatSessionNotice(parsed)}));
    """, tmp_path)
    assert result["oldKind"] == "result" and result["invalid"] is None
    assert result["kind"] == "unanswered" and result["text"] == "  partial\n"
    assert result["turn"] == 3 and result["bg"] == "toolErrorBg" and result["label"] == "unanswered"
    assert "No usable final answer" in result["content"]


def test_malformed_notice_metadata_is_rejected_instead_of_fabricated(tmp_path: Path) -> None:
    result = run("""
      const {readSessionNotice,boundedFinalDiagnostic}=await import("file://"+process.cwd()+"/src/session-result.ts");
      const base={kind:"result",name:"review",session:"session:review:incarnation",text:"answer"};
      const malformed=[
        {...base,turn:0}, {...base,turn:NaN}, {...base,turn:"1"},
        {...base,deliveredAt:Infinity}, {...base,deliveredAt:1e20}, {...base,deliveredAt:"now"},
      ];
      const diagnostic="x".repeat(999)+"𐐀"+"tail";
      const bounded=boundedFinalDiagnostic(diagnostic);
      console.log(JSON.stringify({rejected:malformed.map(value=>readSessionNotice(value)===undefined),bounded,wellFormed:bounded?.includes("𐐀")===false && !/\\ud800|\\udc00/.test(JSON.stringify(bounded))}));
    """, tmp_path)
    assert result == {
        "rejected": [True, True, True, True, True, True],
        "bounded": "x" * 999 + "… [diagnostic truncated]",
        "wellFormed": True,
    }


def test_started_settle_without_completed_message_is_an_explicit_outcome(tmp_path: Path) -> None:
    result = run("""
      await call({name:"reviewer",prompt:"Review",tools:[]});begin();
      callbacks.onUpdate({text:"draft",turns:0,finalResponse:true,missingFinal:true});
      console.log(JSON.stringify({kind:sent[0].details.kind,reason:sent[0].details.reason,text:sent[0].details.text}));
    """, tmp_path)
    assert result == {"kind":"unanswered", "reason":"missing-final", "text":"draft"}


def test_unknown_stop_reason_is_bounded_for_delivery_restore_and_render(tmp_path: Path) -> None:
    result = run("""
      await call({name:"reviewer",prompt:"Review",tools:[]});begin();
      const raw="\\u001b[31m"+"z".repeat(20000);
      callbacks.onUpdate({text:"partial original",turns:1,finalResponse:true,answerComplete:true,stopReason:raw});
      const {readSessionNotice,formatSessionNotice,sessionNoticeSpec}=await import("file://"+process.cwd()+"/src/session-result.ts");
      const restored=readSessionNotice({...sent[0].details,stopReason:raw});
      const content=formatSessionNotice({...sent[0].details,stopReason:raw});
      const spec=sessionNoticeSpec({...sent[0].details,stopReason:raw});
      const listed=await call({operation:"list"});
      console.log(JSON.stringify({reason:sent[0].details.reason,stop:sent[0].details.stopReason,
        restored:restored.stopReason,text:sent[0].details.text,summary:spec.summary.join(" "),
        length:content.length,content,listLength:listed.content[0].text.length}));
    """, tmp_path)
    assert result["reason"] == "incomplete"
    assert result["stop"] == result["restored"] == "unknown", result
    assert result["length"] < 2000 and result["listLength"] < 2000
    assert len(result["summary"]) < 400
    assert "zzzz" not in result["content"] and "stop-reason=\"unknown\"" in result["content"]
    assert result["text"] == "partial original"


@pytest.mark.parametrize("probe", ["message-start", "text-start", "delta-only", "thinking-start", "tool-start", "unknown-stop"])
def test_native_parser_delivery_resets_evidence_per_message(tmp_path: Path, probe: str) -> None:
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    env.update(HOME=str(tmp_path), PI_CODING_AGENT_DIR=str(tmp_path / "agent"), PI_TEST_CWD=str(tmp_path), PI_OFFLINE="1")
    result = subprocess.run(["node", "--experimental-test-module-mocks",
        str(PACKAGE / "tests" / "parsed-final-evidence-fixture.ts"), probe],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(result.stdout) == {"ok": True, "probe": probe}


def test_error_diagnostic_is_bounded_and_original_partial_answer_remains(tmp_path: Path) -> None:
    result = run("""
      await call({name:"reviewer",prompt:"Review",tools:[]});begin();
      callbacks.onUpdate({text:"Original partial bytes",turns:1,finalResponse:true,answerComplete:true,stopReason:"error",
        errorMessage:"\\u001b[31m"+"x".repeat(5000)});
      console.log(JSON.stringify({kind:sent[0].details.kind,text:sent[0].details.text,error:sent[0].details.errorMessage,content:sent[0].content}));
    """, tmp_path)
    assert result["kind"] == "unanswered"
    assert result["text"] == "Original partial bytes"
    assert len(result["error"]) < 1200
    assert "truncated" in result["error"] and "\x1b" not in result["error"]
