"""Parent-scoped durable history through native tool registrants and the library."""
from __future__ import annotations

import json
from pathlib import Path

from subagents_helpers import SRC, run_node


def test_tool_uses_native_parent_session_id_for_durable_history(tmp_path: Path) -> None:
    definition = tmp_path / "project" / ".pi" / "agents" / "reviewer" / "agent.md"
    definition.parent.mkdir(parents=True)
    definition.write_text("---\nname: reviewer\ndescription: Parent history regression\ntools: read\n---\nReview.\n")
    result = run_node(f"""
      import fs from "node:fs";import path from "node:path";
      import {{registerIntentTools}} from {json.dumps((SRC / 'intent-tools.ts').as_uri())};
      import {{ensureAgentWorkspace}} from {json.dumps((SRC / 'workspace.ts').as_uri())};
      const tools=new Map(),spawns=[],workspaces=[];
      const pi={{registerTool:tool=>tools.set(tool.name,tool)}};
      const options={{spawn:input=>{{spawns.push(input);return {{pid:42,readiness:Promise.resolve(true)}};}},
        terminate:async()=>({{outcome:"closed"}}),workspace:input=>{{workspaces.push(input);return ensureAgentWorkspace(input);}}}};
      registerIntentTools(pi,options);
      const ctx=id=>({{cwd:process.env.PI_TEST_CWD,sessionManager:{{getSessionId:()=>id}}}});
      const start=async id=>tools.get("agent_start").execute("start-"+id,
        {{identity:"reviewer",prompt:"Check"}},undefined,undefined,ctx(id));
      const stop=async (id,result)=>tools.get("agent_stop").execute("stop-"+id,
        {{session:result.details.session}},undefined,undefined,ctx(id));
      const a=await start("parent-A");await stop("parent-A",a);
      fs.writeFileSync(path.join(spawns[0].sessionDir,"history.jsonl"),JSON.stringify({{type:"session",version:3,id:"A",cwd:process.env.PI_TEST_CWD}})+"\\n");
      const b=await start("parent-B");await stop("parent-B",b);
      const resumed=await start("parent-A");await stop("parent-A",resumed);
      console.log(JSON.stringify({{ok:[a,b,resumed].map(value=>value.details.ok),parents:workspaces.map(input=>input.parentSessionId),
        paths:spawns.map(input=>input.sessionDir),modes:spawns.map(input=>input.session),cwd:spawns.map(input=>input.cwd),
        scratch:workspaces.map(input=>ensureAgentWorkspace(input).workspacePath)}}));
    """, env_overrides={"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
                       "PI_TEST_CWD": str(tmp_path / "project")})
    assert result["ok"] == [True, True, True]
    parents = result["parents"]
    assert parents == ["parent-A", "parent-B", "parent-A"]
    paths = result["paths"]
    assert paths[0] == paths[2] and paths[0] != paths[1]
    assert result["modes"] == ["persist", "persist", "resume"]
    assert result["cwd"] == [str(tmp_path / "project")] * 3
    assert len(set(result["scratch"])) == 1


def test_headless_parent_id_is_explicit_or_process_local(tmp_path: Path) -> None:
    definition = tmp_path / "project" / ".pi" / "agents" / "reviewer" / "agent.md"
    definition.parent.mkdir(parents=True)
    definition.write_text("---\nname: reviewer\ndescription: Parent history regression\ntools: read\n---\nReview.\n")
    result = run_node(f"""
      import {{executeChildIntent}} from {json.dumps((SRC / 'child-execution.ts').as_uri())};
      import {{ensureAgentWorkspace}} from {json.dumps((SRC / 'workspace.ts').as_uri())};
      const inputs=[];
      const options={{cwd:process.env.PI_TEST_CWD,spawn:()=>({{pid:42,readiness:Promise.resolve(true)}}),
        terminate:async()=>({{outcome:"closed"}}),workspace:input=>{{inputs.push(input);return ensureAgentWorkspace(input);}}}};
      for(const parentSessionId of ["embedded-parent",undefined,undefined]){{
        const started=await executeChildIntent({{name:"reviewer",prompt:"Check"}},{{...options,...(parentSessionId?{{parentSessionId}}:{{}})}});
        if(!started.details.ok)throw new Error(started.details.error);
        await executeChildIntent({{operation:"stop",session:started.details.session}},options);
      }}
      console.log(JSON.stringify({{parents:inputs.map(input=>input.parentSessionId)}}));
    """, env_overrides={"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
                       "PI_TEST_CWD": str(tmp_path / "project")})
    parents = result["parents"]
    assert parents[0] == "embedded-parent"
    assert isinstance(parents[1], str) and parents[1] and parents[1] == parents[2]
    assert parents[1] != "embedded-parent"
