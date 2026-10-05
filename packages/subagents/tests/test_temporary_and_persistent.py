"""Disk identity and resident lifetime: temporary-and-persistent.feature.

Canonical definitions are authored by fixtures, never by the model-facing tool.
All runtime paths, HOME and config stay under the test's temporary directory.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from subagents_helpers import SRC, run_node

PREAMBLE = f"""
import fs from "node:fs";
import path from "node:path";
import {{ executeChildIntent, setAgentHost }} from {json.dumps((SRC / "child-execution.ts").as_uri())};
import {{ resetRoster, getAgent }} from {json.dumps((SRC / "roster.ts").as_uri())};
import {{ resolveAgent, clearSessionAgents }} from {json.dumps((SRC / "agents.ts").as_uri())};
resetRoster();clearSessionAgents();setAgentHost(undefined);
const spawns=[],notices=[],stops=[],prompts=[];
const cwd=process.env.PI_TEST_CWD;
const options={{cwd,spawn:o=>(spawns.push(o),{{pid:7}}),
  prompt:async(name,message)=>(prompts.push({{name,message}}),true),
  terminate:async name=>(stops.push(name),{{outcome:"closed"}}),deliverSessionResult:n=>notices.push(n)}};
const call=params=>executeChildIntent(params,options);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
"""


def run(script: str, tmp_path: Path) -> dict[str, object]:
    return run_node(PREAMBLE + script, env_overrides={
        "PI_TEST_CWD": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
    })


def disk_role(tmp_path: Path, name: str, fields: str = "", scope: str = "user") -> Path:
    base = tmp_path / "agent" / "agents" if scope == "user" else tmp_path / ".pi" / "agents"
    directory = base / (f"{name}.local" if scope == "project-local" else name)
    directory.mkdir(parents=True, exist_ok=True)
    definition = directory / "agent.md"
    tools = "" if "tools:" in fields else "tools: \n"
    definition.write_text(
        f"---\nname: {name}\ndescription: inspect one file\n{tools}{fields}---\nSAVED ROLE BODY\n",
        encoding="utf-8",
    )
    return definition


def test_prompt_only_invocation_is_session_scoped_with_no_private_data(tmp_path: Path) -> None:
    result = run("""
      const start=await call({prompt:"Inspect one file",tools:["read"]});
      console.log(JSON.stringify({ok:start.details.ok,name:start.details.name,scope:start.details.scope,
        sessionPolicy:spawns[0]?.session,tools:spawns[0]?.tools,extensions:spawns[0]?.extensions,
        flag:"persistent" in start.details,privateData:fs.existsSync(process.env.PI_CODING_AGENT_DIR)}));
    """, tmp_path)
    assert result["ok"] is True
    assert result["name"].startswith("subagent-")
    assert result["scope"] == "session"
    assert result["sessionPolicy"] == "none"
    assert result["tools"] == ["read"]
    # Transport classification is explicit and creates no capability or private data.
    assert [Path(value).name for value in result["extensions"]] == ["stream-recovery.ts"]
    assert result["flag"] is False
    assert result["privateData"] is False


@pytest.mark.parametrize("durable", [False, True])
def test_each_settlement_leaves_same_incarnation_idle_and_sendable(tmp_path: Path, durable: bool) -> None:
    if durable:
        disk_role(tmp_path, "resident", "tools: read\n")
    result = run("""
      const start=await call({name:"resident",prompt:"First",tools:[]});
      spawns[0].onUpdate({text:"  完整答案\\n",turns:1,finalResponse:true,answerComplete:true});
      spawns[0].onUpdate({text:"  完整答案\\n",turns:1,finalResponse:true,answerComplete:true});
      await flush();
      const idle=getAgent("resident").status,planned=!!getAgent("resident").leaderRequestedEnd;
      const second=await call({operation:"input",delivery:"next",session:start.details.session,prompt:"Second"});
      spawns[0].onUpdate({text:"second answer",turns:1,finalResponse:true,answerComplete:true});
      await flush();
      const beforeStop=stops.length;
      const stop=await call({operation:"stop",session:start.details.session});
      console.log(JSON.stringify({ok:start.details.ok,idle,planned,second:second.details.ok,
        beforeStop,spawns:spawns.length,stop:stop.details.ok,stops,status:getAgent("resident").status,
        results:notices.filter(n=>n.kind==="result").map(n=>({text:n.text,turn:n.turn,session:n.session})),
        ended:notices.filter(n=>n.kind==="ended").length}));
    """, tmp_path)
    assert result["ok"] is True
    assert result["idle"] == "idle"
    assert result["planned"] is False
    assert result["second"] is True
    assert result["beforeStop"] == 0
    assert result["spawns"] == 1
    assert result["stop"] is True
    assert result["stops"] == ["resident"]
    assert result["status"] == "stopped"
    assert [notice["text"] for notice in result["results"]] == ["  完整答案\n", "second answer"]
    assert [notice["turn"] for notice in result["results"]] == [1, 2]
    assert len({notice["session"] for notice in result["results"]}) == 1
    assert result["ended"] == 0


@pytest.mark.parametrize("scope", ["user", "project", "project-local"])
def test_disk_scope_always_gets_memory_private_history_and_original_project(tmp_path: Path, scope: str) -> None:
    definition = disk_role(tmp_path, "saved", "tools: read\n", scope)
    before = (definition.read_bytes(), definition.stat().st_mtime_ns)
    result = run("""
      const start=await call({name:"saved",prompt:"First"});
      const child=spawns[0],entry=getAgent("saved");
      console.log(JSON.stringify({ok:start.details.ok,scope:start.details.scope,source:start.details.source,
        cwd:child?.cwd,session:child?.session,sessionDir:child?.sessionDir,extensions:child?.extensions,
        capabilities:child?.capabilityTools,env:child?.env,workspace:entry?.workspacePath,
        project:entry?.projectCwd,role:resolveAgent("saved",cwd)?.scope,kickoff:child?.description,
        flag:"persistent" in start.details,userCopy:fs.existsSync(path.join(process.env.PI_CODING_AGENT_DIR,"agents","saved","agent.md"))}));
    """, tmp_path)
    assert result["ok"] is True
    assert result["scope"] == scope
    assert result["role"] == scope
    assert result["source"] == str(definition)
    assert result["cwd"] == result["project"] == str(tmp_path)
    assert result["session"] == "persist"
    assert Path(result["sessionDir"]).is_relative_to(tmp_path / "agent" / "agents" / "saved" / "projects")
    assert Path(result["sessionDir"]).name == "session"
    assert result["workspace"] == str(tmp_path / "agent" / "agents" / "saved" / "workspace")
    assert result["capabilities"] == ["agent_memory"]
    assert [Path(value).name for value in result["extensions"]] == ["stream-recovery.ts", "agent-extension.ts"]
    assert result["env"]["PI_SUBAGENT_ROLE"] == "saved"
    assert result["env"]["PI_SUBAGENT_SCOPE"] == scope
    assert result["env"]["PI_SUBAGENT_DEFINITION"] == str(definition)
    assert "PI_SUBAGENT_MEMORY" not in result["env"]
    assert result["env"]["PI_SUBAGENT_PROJECT_CWD"] == str(tmp_path)
    assert result["env"]["PI_SUBAGENT_WORKSPACE_PATH"] == result["workspace"]
    assert str(tmp_path) in result["kickoff"] and result["workspace"] in result["kickoff"]
    assert result["flag"] is False
    assert result["userCopy"] is (scope == "user")
    assert (definition.read_bytes(), definition.stat().st_mtime_ns) == before


def test_durable_agent_reopens_only_its_private_project_history(tmp_path: Path) -> None:
    disk_role(tmp_path, "saved", "tools: read\n")
    result = run("""
      const first=await call({name:"saved",prompt:"First"});
      fs.mkdirSync(spawns[0].sessionDir,{recursive:true});
      fs.writeFileSync(path.join(spawns[0].sessionDir,"previous.jsonl"),"{}\\n");
      await call({operation:"stop",session:first.details.session});clearSessionAgents();
      const second=await call({name:"saved",prompt:"Next"});
      console.log(JSON.stringify({first:first.details.ok,second:second.details.ok,session:spawns[1]?.session,
        sameDir:spawns[0]?.sessionDir===spawns[1]?.sessionDir,tools:spawns[1]?.tools,
        differentIncarnation:first.details.session!==second.details.session}));
    """, tmp_path)
    assert result == {"first": True, "second": True, "session": "resume", "sameDir": True,
                      "tools": ["read"], "differentIncarnation": True}


def test_saved_identity_cannot_become_inline_or_hosted_temporary(tmp_path: Path) -> None:
    definition = disk_role(tmp_path, "saved", "tools: read\n")
    before = definition.read_bytes()
    result = run("""
      let hosted=0;
      setAgentHost({start:()=>{hosted++;return {ok:true,session:"session:saved:host"};},stop:async()=>({ok:true})});
      const start=await call({name:"saved",description:"Inline",role_prompt:"INLINE BODY",prompt:"Review"});
      spawns[0]?.onUpdate({text:"review result",turns:1,finalResponse:true});
      const oldOptOut=await call({name:"saved",persistent:false,prompt:"Amnesia"});
      console.log(JSON.stringify({ok:start.details.ok,hosted,session:spawns[0]?.session,
        role:spawns[0]?.description,memoryRole:spawns[0]?.env?.PI_SUBAGENT_ROLE,
        standalone:getAgent("saved")?.standalone,results:notices.filter(n=>n.kind==="result").length,
        oldOptOut:oldOptOut.details.ok}));
    """, tmp_path)
    assert result["ok"] is True
    assert result["hosted"] == 0
    assert result["session"] == "persist"
    assert "SAVED ROLE BODY" in result["role"] and "INLINE BODY" not in result["role"]
    assert result["memoryRole"] == "saved"
    assert result["standalone"] is True
    assert result["results"] == 1
    assert result["oldOptOut"] is False
    assert definition.read_bytes() == before


def test_new_definition_does_not_promote_old_temporary_conversation(tmp_path: Path) -> None:
    result = run("""
      const first=await call({name:"new-durable",role_prompt:"TEMP BODY",prompt:"First"});
      spawns[0].onUpdate({text:"TEMP CONTEXT",turns:1,finalResponse:true});
      await call({operation:"stop",session:first.details.session});
      const dir=path.join(process.env.PI_CODING_AGENT_DIR,"agents","new-durable");fs.mkdirSync(dir,{recursive:true});
      fs.writeFileSync(path.join(dir,"agent.md"),"---\\nname: new-durable\\ndescription: New disk identity\\ntools: read\\n---\\nDISK BODY\\n");
      const second=await call({name:"new-durable",prompt:"Second"});
      console.log(JSON.stringify({first:spawns[0].session,second:spawns[1]?.session,
        context:spawns[1]?.context??null,body:spawns[1]?.description,ok:second.details.ok}));
    """, tmp_path)
    assert result["ok"] is True
    assert result["first"] == "none" and result["second"] == "persist"
    assert result["context"] is None
    assert "DISK BODY" in result["body"] and "TEMP BODY" not in result["body"]


def test_offline_list_does_not_provision_private_data(tmp_path: Path) -> None:
    definition = disk_role(tmp_path, "offline", "tools: read\nmodel: test/offline\n", "project")
    before = (definition.read_bytes(), definition.stat().st_mtime_ns)
    result = run("""
      const temporary=await call({name:"stopped",prompt:"Run"});
      await call({operation:"stop",session:temporary.details.session});
      const listed=await call({operation:"list"});
      console.log(JSON.stringify({ok:listed.details.ok,definitions:listed.details.definitions,
        agents:listed.details.agents,text:listed.content[0].text,data:fs.existsSync(process.env.PI_CODING_AGENT_DIR),spawns:spawns.length}));
    """, tmp_path)
    assert result["ok"] is True
    offline, = result["definitions"]
    assert offline["name"] == "offline" and offline["status"] == "offline"
    assert offline["scope"] == "project" and offline["source"] == str(definition)
    assert offline["model"] == "test/offline" and offline["tools"] == ["read"]
    assert "session" not in offline
    assert len(result["agents"]) == 1 and result["agents"][0]["status"] == "stopped"
    assert "offline" in result["text"] and "definitions" in result["text"] and "sessions" in result["text"]
    assert result["data"] is False and result["spawns"] == 1
    assert (definition.read_bytes(), definition.stat().st_mtime_ns) == before


def test_live_definition_is_not_duplicated_as_offline(tmp_path: Path) -> None:
    disk_role(tmp_path, "saved")
    result = run("""
      const start=await call({name:"saved"});
      const live=await call({operation:"list"});
      await call({operation:"stop",session:start.details.session});
      const stopped=await call({operation:"list"});
      console.log(JSON.stringify({live:live.details.definitions,stopped:stopped.details.definitions,
        status:stopped.details.sessions[0].status}));
    """, tmp_path)
    assert result["live"] == []
    assert [entry["name"] for entry in result["stopped"]] == ["saved"]
    assert result["status"] == "stopped"


def test_derived_directories_are_not_identity_and_list_stays_read_only(tmp_path: Path) -> None:
    derived = tmp_path / "agent" / "agents" / "derived-only"
    (derived / "memory").mkdir(parents=True)
    (derived / "state.json").write_text('{}\n', encoding="utf-8")
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    result = run("""
      const listed=await call({operation:"list"});
      console.log(JSON.stringify({definitions:listed.details.definitions,agents:listed.details.agents,role:!!resolveAgent("derived-only",cwd)}));
    """, tmp_path)
    assert result == {"definitions": [], "agents": [], "role": False}
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before


def test_old_readiness_cleanup_cannot_stop_replacement(tmp_path: Path) -> None:
    result = run("""
      let successor;
      const failed=await executeChildIntent({name:"same"},{...options,spawn:o=>(spawns.push(o),{pid:7,readiness:Promise.resolve(false)}),terminate:async()=>{
        spawns[0].onExit({pid:7,exitCode:0,signal:null,stdout:"",stderr:""});
        successor=await call({name:"same",prompt:"Next"});return {outcome:"closed"};
      }});
      console.log(JSON.stringify({failed:failed.details.ok,successor:successor.details.ok,status:getAgent("same").status,error:getAgent("same").error??null}));
    """, tmp_path)
    assert result == {"failed": False, "successor": True, "status": "starting", "error": None}


def test_inline_replacement_cannot_widen_existing_grant(tmp_path: Path) -> None:
    result = run("""
      const first=await call({name:"bounded",role_prompt:"Read",tools:["read"]});
      await call({operation:"stop",session:first.details.session});
      const second=await call({name:"bounded",role_prompt:"Run",tools:["bash"],prompt:"Next"});
      console.log(JSON.stringify({ok:second.details.ok,spawns:spawns.length}));
    """, tmp_path)
    assert result == {"ok": False, "spawns": 1}


def test_unconfirmed_input_retains_uncertain_authority(tmp_path: Path) -> None:
    result = run("""
      const start=await executeChildIntent({name:"uncertain"},{...options,prompt:async()=>{throw new Error("acknowledgement timed out");}});
      const first=await call({operation:"input",delivery:"next",session:start.details.session,prompt:"Run"});
      const second=await call({operation:"input",delivery:"next",session:start.details.session,prompt:"Retry"});
      console.log(JSON.stringify({first:first.details.ok,second:second.details.ok,status:getAgent("uncertain").status}));
    """, tmp_path)
    assert result == {"first": False, "second": False, "status": "starting"}


def test_transient_result_delivery_retries_without_closing_child(tmp_path: Path) -> None:
    result = run("""
      let tries=0;
      await executeChildIntent({name:"retry-result",prompt:"Reply"},{...options,deliverSessionResult:n=>{
        if(n.kind==="result" && ++tries===1)throw new Error("sender unavailable");notices.push(n);
      }});
      spawns[0].onUpdate({text:"complete answer",turns:1,finalResponse:true});await flush();
      console.log(JSON.stringify({tries,results:notices.filter(n=>n.kind==="result").length,stops:stops.length,status:getAgent("retry-result").status}));
    """, tmp_path)
    assert result == {"tries": 2, "results": 1, "stops": 0, "status": "idle"}


def test_coalesced_send_accepts_third_input_and_delivers_each_answer(tmp_path: Path) -> None:
    result = run("""
      let next=2;
      const opts={...options,prompt:async()=>{spawns[0].onUpdate({text:`answer ${next++}`,turns:1,finalResponse:true});return true;}};
      const start=await executeChildIntent({name:"coalesced",prompt:"First"},opts);
      spawns[0].onUpdate({text:"answer 1",turns:1,finalResponse:true});
      const second=await executeChildIntent({operation:"input",delivery:"next",session:start.details.session,prompt:"Second"},opts);
      const third=await executeChildIntent({operation:"input",delivery:"next",session:start.details.session,prompt:"Third"},opts);
      console.log(JSON.stringify({second:second.details.ok,third:third.details.ok,status:getAgent("coalesced").status,
        texts:notices.filter(n=>n.kind==="result").map(n=>n.text),stops:stops.length}));
    """, tmp_path)
    assert result == {"second": True, "third": True, "status": "idle", "texts": ["answer 1", "answer 2", "answer 3"], "stops": 0}


def test_prior_delivery_retry_cannot_mark_next_input_answered(tmp_path: Path) -> None:
    result = run("""
      let tries=0,nextInput;
      const opts={...options,prompt:async()=>true,deliverSessionResult:n=>{
        if(n.kind==="result" && ++tries===1){
          nextInput=executeChildIntent({operation:"input",delivery:"next",session:n.session,prompt:"Second input"},opts);
          throw new Error("first delivery unavailable");
        }
        notices.push(n);
      }};
      await executeChildIntent({name:"retry-next",prompt:"First"},opts);
      spawns[0].onUpdate({text:"first answer",turns:1,finalResponse:true});
      await nextInput;await flush();
      spawns[0].onExit({pid:7,exitCode:null,signal:"SIGKILL",stdout:"",stderr:""});
      console.log(JSON.stringify({tries,results:notices.filter(n=>n.kind==="result").map(n=>n.text),ended:notices.filter(n=>n.kind==="ended").length}));
    """, tmp_path)
    assert result == {"tries": 2, "results": ["first answer"], "ended": 1}


def test_process_error_does_not_release_unconfirmed_live_name(tmp_path: Path) -> None:
    result = run("""
      const opts={...options,terminate:async()=>({outcome:"unconfirmed"})};
      await executeChildIntent({name:"error-live",prompt:"Run"},opts);
      spawns[0].onError(new Error("control stream error"));await flush();
      const replacement=await executeChildIntent({name:"error-live",prompt:"Replacement"},opts);
      console.log(JSON.stringify({replacement:replacement.details.ok,status:getAgent("error-live").status}));
    """, tmp_path)
    assert result["replacement"] is False and result["status"] != "stopped"


def test_negative_ack_progress_restores_idle_and_allows_retry(tmp_path: Path) -> None:
    result = run("""
      let refuse=true;
      const opts={...options,prompt:async()=>{if(refuse)spawns[0].onUpdate({text:"",turns:0,finalResponse:false,controlError:"prompt rejected"});return !refuse;}};
      const start=await executeChildIntent({name:"reject-idle"},opts);
      const rejected=await executeChildIntent({operation:"input",delivery:"next",session:start.details.session,prompt:"Reject"},opts);
      const after=getAgent("reject-idle").status;refuse=false;
      const retry=await executeChildIntent({operation:"input",delivery:"next",session:start.details.session,prompt:"Accept"},opts);
      console.log(JSON.stringify({rejected:rejected.details.ok,after,retry:retry.details.ok}));
    """, tmp_path)
    assert result == {"rejected": False, "after": "idle", "retry": True}


def test_answered_process_crash_keeps_exit_diagnostic(tmp_path: Path) -> None:
    result = run("""
      await call({name:"crash-after-answer",prompt:"Reply"});
      spawns[0].onUpdate({text:"done",turns:1,finalResponse:true});
      spawns[0].onExit({pid:7,exitCode:null,signal:"SIGKILL",stdout:"",stderr:""});
      console.log(JSON.stringify({error:getAgent("crash-after-answer").error??null,status:getAgent("crash-after-answer").status}));
    """, tmp_path)
    assert result["status"] == "stopped" and "SIGKILL" in result["error"]


def test_role_reference_is_bundled_without_coordination_dependency(tmp_path: Path) -> None:
    result = run("""
      const {AGENT_REFERENCE_PATH}=await import("file://"+process.cwd()+"/src/agents.ts");
      const manifest=JSON.parse(fs.readFileSync(path.join(process.cwd(),"package.json"),"utf8"));
      console.log(JSON.stringify({exists:fs.existsSync(AGENT_REFERENCE_PATH),bundled:manifest.files.includes("references"),content:fs.readFileSync(AGENT_REFERENCE_PATH,"utf8")}));
    """, tmp_path)
    assert result["exists"] is result["bundled"] is True
    assert "minimal" in result["content"].lower() and "agent-teams" not in result["content"]
