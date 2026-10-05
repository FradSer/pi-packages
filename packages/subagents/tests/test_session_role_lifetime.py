"""Temporary role cleanup follows confirmed parent shutdown, not result settlement."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from subagents_helpers import PACKAGE, SRC, run_node


def test_confirmed_shutdown_retires_roster_and_drops_session_roles(tmp_path: Path) -> None:
    script=f"""
      import {{mock}} from "node:test";
      import * as spawner from {json.dumps((SRC/"spawner.ts").as_uri())};
      mock.module({json.dumps((SRC/"spawner.ts").as_uri())},{{namedExports:{{...spawner,
        terminateAllAgents:async()=>[{{name:"ephemeral",confirmedClosed:true}}]}}}});
      const {{default:extension,registerSessionAgent,resolveAgent,registerAgent,getAgent}}=await import({json.dumps((PACKAGE/"index.ts").as_uri())});
      registerSessionAgent({{name:"ephemeral",description:"temporary",prompt:"Keep this role",tools:[]}});
      registerAgent({{name:"ephemeral",role:"ephemeral",spawnId:"current",pid:7,status:"idle",scope:"session",standalone:true,createdAt:1,updatedAt:1}});
      const hooks=new Map();
      extension({{registerTool(){{}},registerMessageRenderer(){{}},on:(name,f)=>hooks.set(name,f),events:{{emit(){{}}}}}});
      await hooks.get("session_shutdown")({{}},{{mode:"print",cwd:process.cwd()}});
      console.log(JSON.stringify({{status:getAgent("ephemeral")?.status,role:resolveAgent("ephemeral")?.scope??null}}));
    """
    result=run_node(script,module_mocks=True,env_overrides={"HOME":str(tmp_path),"PI_CODING_AGENT_DIR":str(tmp_path/"agent")})
    assert result == {"status":"stopped","role":None}


def test_unconfirmed_shutdown_does_not_claim_closed_execution(tmp_path: Path) -> None:
    script=f"""
      import {{mock}} from "node:test";
      import * as spawner from {json.dumps((SRC/"spawner.ts").as_uri())};
      mock.module({json.dumps((SRC/"spawner.ts").as_uri())},{{namedExports:{{...spawner,
        terminateAllAgents:async()=>[{{name:"uncertain",confirmedClosed:false}}]}}}});
      const {{default:extension,registerAgent,getAgent}}=await import({json.dumps((PACKAGE/"index.ts").as_uri())});
      registerAgent({{name:"uncertain",role:"uncertain",spawnId:"current",pid:7,status:"working",scope:"session",standalone:true,createdAt:1,updatedAt:1}});
      const hooks=new Map();
      extension({{registerTool(){{}},registerMessageRenderer(){{}},on:(name,f)=>hooks.set(name,f),events:{{emit(){{}}}}}});
      await hooks.get("session_shutdown")({{}},{{mode:"print",cwd:process.cwd()}});
      console.log(JSON.stringify({{status:getAgent("uncertain")?.status,intent:getAgent("uncertain")?.leaderRequestedEnd}}));
    """
    result=run_node(script,module_mocks=True,env_overrides={"HOME":str(tmp_path),"PI_CODING_AGENT_DIR":str(tmp_path/"agent")})
    assert result == {"status":"working","intent":True}


@pytest.mark.parametrize("mode", ["confirmed", "unconfirmed", "replacement", "already-stopped"])
def test_extension_shutdown_retires_only_confirmed_exact_controls(tmp_path: Path, mode: str) -> None:
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    env.update(HOME=str(tmp_path), PI_CODING_AGENT_DIR=str(tmp_path / "agent"))
    result = subprocess.run(["node", "--experimental-test-module-mocks",
        str(PACKAGE / "tests" / "shutdown-controls-fixture.ts"), mode],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(result.stdout) == {"ok": True, "mode": mode}
