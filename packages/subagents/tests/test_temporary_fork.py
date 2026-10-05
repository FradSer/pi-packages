"""Temporary forks cross the real Pi control/context seams without history files."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
from http.server import BaseHTTPRequestHandler

from native_support import LoopbackServer
from pathlib import Path

import pytest

from subagents_helpers import REPO, SRC, run_node

FIXTURE = Path(__file__).with_name("native-temporary-fork-fixture.ts")


def fixture_env(tmp_path: Path) -> dict[str, str]:
    """No personal HOME, auth, ambient extensions or external model endpoint."""
    home = tmp_path / "home"
    agent = home / ".pi" / "agent"
    temporary = tmp_path / "tmp"
    agent.mkdir(parents=True)
    temporary.mkdir()
    (agent / "settings.json").write_text(json.dumps({
        "quietStartup": True, "compaction": {"enabled": False},
        "retry": {"enabled": False}, "enableInstallTelemetry": False,
    }), encoding="utf-8")
    return {
        "PATH": os.environ["PATH"], "HOME": str(home), "TMPDIR": str(temporary),
        "PI_CODING_AGENT_DIR": str(agent), "PI_OFFLINE": "1", "PI_TELEMETRY": "0",
        "PI_FORK_FIXTURE_ROOT": str(tmp_path), "PI_FORK_MARKER": secrets.token_hex(16),
        "PI_FORK_FIXTURE_AUTH": secrets.token_hex(16),
    }


@pytest.mark.parametrize("probe", ["spawn-prompted", "spawn-idle", "setup-rejected", "setup-close", "setup-timeout"])
def test_temporary_spawner_never_materializes_history_and_seeds_before_input(
    tmp_path: Path, probe: str,
) -> None:
    result = subprocess.run(
        ["node", "--experimental-test-module-mocks", str(FIXTURE), probe],
        cwd=REPO, env=fixture_env(tmp_path), capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(result.stdout) == {"ok": True, "probe": probe}


@pytest.mark.parametrize("probe", ["native", "spawner-native-prompted", "spawner-native-idle"])
def test_native_rpc_fork_keeps_structured_seed_and_two_inputs_only_in_memory(tmp_path: Path, probe: str) -> None:
    env = fixture_env(tmp_path)
    requests: list[dict[str, object]] = []

    class LocalModel(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            # This is deterministic loopback HTTP, not a real model invocation.
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(payload)
            # The native child can obtain this answer only if structured history
            # actually reaches the provider, not from a fixture-side cached seed.
            messages = payload.get("messages", [])
            marker_visible = any(message.get("role") == "user" and env["PI_FORK_MARKER"] in str(message.get("content"))
                                 for message in messages)
            answer = f"FORK_ANSWER_{len(requests)}" if marker_visible else "FORK_HISTORY_MISSING"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for delta, finish in (({"role": "assistant", "content": answer}, None), ({}, "stop")):
                chunk = {"id": "memory-fork", "object": "chat.completion.chunk", "created": 1,
                         "model": "history", "choices": [{"index": 0, "delta": delta,
                                                           "finish_reason": finish}]}
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    server = LoopbackServer(LocalModel)
    agent = Path(env["PI_CODING_AGENT_DIR"])
    (agent / "models.json").write_text(json.dumps({"providers": {
        "fork-loopback": {"baseUrl": f"http://127.0.0.1:{server.server_port}/v1",
                          "api": "openai-completions", "apiKey": env["PI_FORK_FIXTURE_AUTH"],
                          "models": [{"id": "history", "reasoning": False, "input": ["text"],
                                      "contextWindow": 200000, "maxTokens": 4096,
                                      "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}
    }}), encoding="utf-8")
    try:
        result = subprocess.run(["node", str(FIXTURE), probe], cwd=REPO, env=env,
                                capture_output=True, text=True, timeout=45)
        assert result.returncode == 0, result.stderr + result.stdout
        assert json.loads(result.stdout) == {"ok": True, "probe": probe, "requests": 2}
        assert len(requests) == 2
        for number, request in enumerate(requests, 1):
            messages = request["messages"]
            assert isinstance(messages, list)
            transcript = json.dumps(messages, ensure_ascii=False)
            assert transcript.count(env["PI_FORK_MARKER"]) == 1
            assert transcript.count("FORK_INPUT_ONE") == 1
            assert "subagents-context" not in transcript
            assert "parent_admin" not in transcript and "parent-private-metadata" not in transcript
            assert env["PI_FORK_FIXTURE_AUTH"] not in transcript
            assert not request.get("tools"), request
            assert any(message["role"] == "assistant" and message.get("tool_calls") for message in messages)
            assert any(message["role"] == "tool" and message.get("tool_call_id") == "historical-read" for message in messages)
            assert "The conversation history before this point was compacted" in transcript
            assert "summary of a branch" in transcript
            if number == 2:
                assert transcript.count("FORK_ANSWER_1") == 1
                assert transcript.count("FORK_INPUT_TWO") == 1
        assert not list(tmp_path.rglob("*.jsonl"))
        for path in tmp_path.rglob("*"):
            if path.is_file():
                assert env["PI_FORK_MARKER"].encode() not in path.read_bytes(), path
        assert not (agent / "agents").exists()
        assert not (agent / "sessions").exists()
    finally:
        server.close()


def test_fork_control_schema_filters_authority_and_correlates_only_setup_ack(tmp_path: Path) -> None:
    result = run_node(f"""
      import assert from "node:assert/strict";
      import {{createForkContextCommand,decodeForkContext,parseForkContextAck,FORK_CONTEXT_ACK_STATUS}}
        from {json.dumps((SRC / "work-context.ts").as_uri())};
      const source=[{{role:"system",content:"credential",toolsAdded:[{{name:"parent_admin"}}],timestamp:1}},
        {{role:"user",content:"Marker 中文\u2028line",timestamp:2,credentials:"credential"}}];
      const before=JSON.stringify(source),command=createForkContextCommand("setup-1",source);
      assert.equal(command.id,"setup-1");assert.equal(command.type,"prompt");
      const [name,id,encoded]=command.message.split(" ");
      assert.equal(name,"/subagents-context");assert.equal(id,"setup-1");
      assert.deepEqual(decodeForkContext(encoded),[{{role:"user",content:"Marker 中文\u2028line",timestamp:2}}]);
      assert.equal(before,JSON.stringify(source));
      const ack={{version:1,requestId:"setup-1",success:true,messageCount:1}};
      const record={{type:"extension_ui_request",method:"setStatus",statusKey:FORK_CONTEXT_ACK_STATUS,statusText:JSON.stringify(ack)}};
      assert.deepEqual(parseForkContextAck(record,"setup-1"),ack);
      assert.equal(parseForkContextAck(record,"wrong-id"),undefined);
      assert.equal(parseForkContextAck({{...record,statusKey:"other"}},"setup-1"),undefined);
      assert.equal(parseForkContextAck({{type:"response",id:"setup-1",command:"prompt",success:true,data:{{disposition:"handled"}}}},"setup-1"),undefined);
      assert.equal(parseForkContextAck({{...record,statusText:"malformed"}},"setup-1"),undefined);
      assert.throws(()=>decodeForkContext("%%%"),/payload/i);
      assert.throws(()=>decodeForkContext("A".repeat(8*1024*1024+4)),/limit/i);
      assert.throws(()=>decodeForkContext(Buffer.concat([Buffer.from('{{"version":1,"messages":[{{"role":"user","content":"'),
        Buffer.from([0xff]),Buffer.from('","timestamp":1}}]}}')]).toString("base64")),/payload/i);
      const encode=x=>Buffer.from(JSON.stringify(x)).toString("base64");
      const substantial=[{{role:"user",content:"x".repeat(512*1024),timestamp:1}}];
      assert.deepEqual(decodeForkContext(createForkContextCommand("substantial",substantial).message.split(" ")[2]),substantial);
      assert.throws(()=>decodeForkContext(encode({{version:1,messages:[{{role:"user",content:[{{type:"text",text:"x",textSignature:{{credentials:"hidden"}}}}],timestamp:1}}]}})),/payload/i);
      assert.throws(()=>decodeForkContext(encode({{version:2,messages:[]}})),/version|payload/i);
      assert.throws(()=>decodeForkContext(encode({{version:1,messages:[{{role:"unknown"}}]}})),/message|role/i);
      assert.throws(()=>decodeForkContext(encode({{version:1,messages:[],credentials:"credential"}})),/payload/i);
      assert.throws(()=>createForkContextCommand("bad id",[]),/request/i);
      assert.throws(()=>createForkContextCommand("large",[{{role:"user",content:"x".repeat(8*1024*1024),timestamp:1}}]),/limit|bytes/i);
      console.log(JSON.stringify({{ok:true}}));
    """, env_overrides=fixture_env(tmp_path))
    assert result == {"ok": True}


def test_extension_seed_is_request_local_once_and_invalid_setup_cannot_replace_it(tmp_path: Path) -> None:
    result = run_node(f"""
      import assert from "node:assert/strict";
      import extension from {json.dumps((SRC / "fork-extension.ts").as_uri())};
      import {{createForkContextCommand,parseForkContextAck,FORK_CONTEXT_ACK_STATUS}}
        from {json.dumps((SRC / "work-context.ts").as_uri())};
      const commands=new Map(),handlers=new Map(),records=[];
      extension({{registerCommand:(name,command)=>commands.set(name,command),on:(name,handler)=>handlers.set(name,handler)}});
      const seed=[{{role:"compactionSummary",summary:"Marker",tokensBefore:1,timestamp:1}},
        {{role:"user",content:"Historical input",timestamp:2}}];
      const ctx={{mode:"rpc",isIdle:()=>true,hasPendingMessages:()=>false,
        sessionManager:{{getSessionFile:()=>undefined,getEntries:()=>[]}},
        ui:{{setStatus:(statusKey,statusText)=>records.push({{type:"extension_ui_request",method:"setStatus",statusKey,statusText}})}}}};
      const setup=async(id,history=seed,context=ctx)=>{{
        const command=createForkContextCommand(id,history);
        await commands.get("subagents-context").handler(command.message.slice("/subagents-context ".length),context);
        return parseForkContextAck(records.at(-1),id);
      }};
      assert.equal((await setup("valid")).success,true);
      const native=[{{role:"user",content:"Assignment",timestamp:3}}];
      const first=await handlers.get("context")({{messages:native}},ctx);
      assert.deepEqual(first.messages,[...seed,...native]);assert.deepEqual(native,[{{role:"user",content:"Assignment",timestamp:3}}]);
      first.messages[0].summary="mutated request";
      assert.deepEqual((await handlers.get("context")({{messages:native}},ctx)).messages,[...seed,...native]);
      assert.equal((await setup("repeated",[])).success,false);
      assert.equal((await setup("persisted",[],{{...ctx,sessionManager:{{...ctx.sessionManager,getSessionFile:()=>"private.jsonl"}}}})).success,false);
      assert.equal((await setup("busy",[],{{...ctx,isIdle:()=>false}})).success,false);
      await commands.get("subagents-context").handler("malformed %%%",ctx);
      assert.equal(parseForkContextAck(records.at(-1),"malformed").success,false);
      assert.deepEqual((await handlers.get("context")({{messages:native}},ctx)).messages,[...seed,...native]);
      await handlers.get("session_shutdown")({{reason:"quit"}},ctx);
      assert.equal(await handlers.get("context")({{messages:native}},ctx),undefined);
      const freshCommands=new Map(),freshHandlers=new Map();
      extension({{registerCommand:(name,command)=>freshCommands.set(name,command),on:(name,handler)=>freshHandlers.set(name,handler)}});
      await freshHandlers.get("input")({{text:"Already accepted",source:"rpc"}},ctx);
      await freshCommands.get("subagents-context").handler(createForkContextCommand("late",seed).message.slice("/subagents-context ".length),ctx);
      assert.equal(parseForkContextAck(records.at(-1),"late").success,false);
      assert.equal(await freshHandlers.get("context")({{messages:native}},ctx),undefined);
      for(const [id,override] of [
        ["persisted",{{sessionManager:{{...ctx.sessionManager,getSessionFile:()=>"private.jsonl"}}}}],
        ["busy",{{isIdle:()=>false}}], ["queued",{{hasPendingMessages:()=>true}}],
        ["used",{{sessionManager:{{...ctx.sessionManager,getEntries:()=>[{{type:"message",message:{{role:"user"}}}}]}}}}],
        ["print",{{mode:"print"}}],
      ]){{
        const cmd=new Map(),hooks=new Map();
        extension({{registerCommand:(name,command)=>cmd.set(name,command),on:(name,handler)=>hooks.set(name,handler)}});
        await cmd.get("subagents-context").handler(createForkContextCommand(id,seed).message.slice("/subagents-context ".length),{{...ctx,...override}});
        assert.equal(parseForkContextAck(records.at(-1),id).success,false);
        assert.equal(await hooks.get("context")({{messages:native}},ctx),undefined);
      }}
      console.log(JSON.stringify({{ok:true}}));
    """, env_overrides=fixture_env(tmp_path))
    assert result == {"ok": True}
