"""Native Pi must not load or append outside history through private-session links."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import uuid
from pathlib import Path

import pytest

from subagents_helpers import SRC, PACKAGE, run_node


@pytest.mark.parametrize("link", ["symlink", "hard-link"])
def test_native_resume_refuses_linked_history_without_touching_target(tmp_path: Path, link: str) -> None:
    (tmp_path / "project").mkdir()
    script=f"""
      import fs from "node:fs";import path from "node:path";
      import {{SessionManager}} from "@earendil-works/pi-coding-agent";
      import {{agentSessionPath}} from {json.dumps((SRC/"workspace.ts").as_uri())};
      const cwd=process.env.PI_TEST_CWD;
      const outside=path.join(process.env.HOME,"outside-history");fs.mkdirSync(outside);
      const session=SessionManager.create(cwd,outside);
      session.appendMessage({{role:"user",content:"OUTSIDE_PRIVATE_SENTINEL",timestamp:1}});
      const file=session.getSessionFile();
      const dir=agentSessionPath("unsafe-reader",cwd,process.env.PI_HISTORY_SAFETY_PARENT_ID);fs.mkdirSync(dir,{{recursive:true}});
      if({json.dumps(link)}==="symlink")fs.symlinkSync(file,path.join(dir,"linked.jsonl"));else fs.linkSync(file,path.join(dir,"linked.jsonl"));
      console.log(JSON.stringify({{file,dir}}));
    """
    env={"PATH":os.environ["PATH"],"HOME":str(tmp_path),"PI_CODING_AGENT_DIR":str(tmp_path/"agent"),
        "PI_TEST_CWD":str(tmp_path/"project"),"PI_OFFLINE":"1","PI_HISTORY_SAFETY_ROOT":str(tmp_path),
        "PI_HISTORY_SAFETY_AUTH":secrets.token_hex(16),"PI_HISTORY_SAFETY_PARENT_ID":str(uuid.uuid4())}
    setup=run_node(script,env_overrides=env)
    outside=Path(setup["file"]);before=(hashlib.sha256(outside.read_bytes()).hexdigest(),outside.stat().st_mtime_ns)
    definition=tmp_path/"agent"/"agents"/"unsafe-reader"/"agent.md"
    definition.write_text("---\nname: unsafe-reader\ndescription: Linked history fixture\ntools: \n---\nRead-only role.\n")
    cli=PACKAGE.parents[1]/"node_modules"/"@earendil-works"/"pi-coding-agent"/"dist"/"cli.js"
    fixture=PACKAGE.parents[1]/"tests"/"live-history-safety-fixture.ts"
    result=subprocess.run(["node",str(cli),"--print","--no-session","--session-id",env["PI_HISTORY_SAFETY_PARENT_ID"],"--no-extensions",
        "--no-skills","--no-prompt-templates","--no-themes","--no-context-files","--no-approve",
        "--no-builtin-tools","--extension",str(fixture),"--provider","history-safety-fixture",
        "--model","scripted","--thinking","off","Attempt the unsafe private resume"],
        cwd=tmp_path/"project",env=env,input="",text=True,capture_output=True,timeout=20)
    assert result.returncode==0, result.stdout+result.stderr
    assert "HISTORY_SAFETY_REFUSED" in result.stdout, result.stdout+result.stderr
    assert before==(hashlib.sha256(outside.read_bytes()).hexdigest(),outside.stat().st_mtime_ns)
    report=json.loads((tmp_path/"safety-evidence.json").read_text())
    assert report=={"spawns":0,"refused":True,"outsideInContext":False,"code":"workspace-failed"}, report
