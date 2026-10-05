"""Ordinary durable homes; VISION.md replaces the former Git-worktree policy.

Contract: features/agent-workspace.feature. Every process uses isolated HOME/config.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from subagents_helpers import PACKAGE, run_node

WORKSPACE = (PACKAGE / "src" / "workspace.ts").as_uri()


def run(script: str, tmp_path: Path) -> dict[str, object]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    return run_node(
        f'''import * as sa from {json.dumps(WORKSPACE)};
        import fs from "node:fs";
        import path from "node:path";
        const cwd = process.env.PI_TEST_CWD;
        {script}''',
        env_overrides={
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / "config"),
            "PI_CODING_AGENT_DIR": str(home / "agent"),
            "PI_TEST_CWD": str(project),
        },
    )


def test_paths_are_read_only_private_and_scoped(tmp_path: Path) -> None:
    result = run('''
      const home = sa.agentHomePath("reviewer");
      const workspace = sa.agentWorkspacePath("reviewer");
      const session = sa.agentSessionPath("reviewer", cwd);
      console.log(JSON.stringify({home, workspace, session,
        stable: sa.agentSessionPath("reviewer", cwd) === session,
        otherAgent: sa.agentHomePath("builder") !== home,
        otherProject: sa.agentSessionPath("reviewer", path.dirname(cwd)) !== session,
        created: fs.existsSync(process.env.PI_CODING_AGENT_DIR)}));
    ''', tmp_path)
    home = tmp_path / "home" / "agent" / "agents" / "reviewer"
    assert result["home"] == str(home)
    assert result["workspace"] == str(home / "workspace")
    slug = run('console.log(JSON.stringify({slug:sa.projectSlug(cwd)}));', tmp_path)["slug"]
    assert result["session"] == str(home / "projects" / str(slug) / "session")
    assert result["stable"] is True
    assert result["otherAgent"] is True and result["otherProject"] is True
    assert result["created"] is False


def test_parent_session_paths_are_hashed_stable_and_isolated(tmp_path: Path) -> None:
    result = run('''
      const first = sa.agentSessionPath("reviewer",cwd,"parent-one");
      const same = sa.agentSessionPath("reviewer",cwd,"parent-one");
      const other = sa.agentSessionPath("reviewer",cwd,"parent-two");
      const legacy = sa.agentSessionPath("reviewer",cwd);
      console.log(JSON.stringify({first,same,other,legacy,created:fs.existsSync(process.env.PI_CODING_AGENT_DIR)}));
    ''', tmp_path)
    home = tmp_path / "home" / "agent" / "agents" / "reviewer"
    expected = f"parent-{hashlib.sha256(b'parent-one').hexdigest()}"
    other_expected = f"parent-{hashlib.sha256(b'parent-two').hexdigest()}"
    first = Path(str(result["first"]))
    other = Path(str(result["other"]))
    assert result["first"] == result["same"]
    assert result["first"] != result["other"]
    assert first == home / "projects" / first.parent.parent.parent.name / "parents" / expected / "session"
    assert other.parent.name == other_expected
    assert re.fullmatch(r"parent-[0-9a-f]{64}", first.parent.name)
    assert "parent-one" not in str(first) and "parent-two" not in str(other)
    assert result["legacy"] == str(home / "projects" / first.parent.parent.parent.name / "session")
    assert result["created"] is False


@pytest.mark.parametrize("parent_id", ["", "   ", "\t"])
def test_blank_parent_session_id_is_refused_before_writes(tmp_path: Path, parent_id: str) -> None:
    result = run(f'''
      const parentId = {json.dumps(parent_id)};
      const refused = [];
      for (const action of [
        () => sa.agentSessionPath("reviewer",cwd,parentId),
        () => sa.ensureAgentWorkspace({{agentName:"reviewer",cwd,parentSessionId:parentId}}),
      ]) {{
        try {{ action(); refused.push(false); }} catch {{ refused.push(true); }}
      }}
      console.log(JSON.stringify({{refused,created:fs.existsSync(process.env.PI_CODING_AGENT_DIR)}}));
    ''', tmp_path)
    assert result == {"refused": [True, True], "created": False}


def test_oversized_parent_session_id_is_refused_before_writes(tmp_path: Path) -> None:
    result = run('''
      const parentId = "x".repeat(4097);
      let refused = false;
      try { sa.ensureAgentWorkspace({agentName:"reviewer",cwd,parentSessionId:parentId}); } catch { refused = true; }
      console.log(JSON.stringify({refused,created:fs.existsSync(process.env.PI_CODING_AGENT_DIR)}));
    ''', tmp_path)
    assert result == {"refused": True, "created": False}


def test_new_parent_session_does_not_import_legacy_history(tmp_path: Path) -> None:
    result = run('''
      const legacy = sa.agentSessionPath("reviewer",cwd);
      fs.mkdirSync(legacy,{recursive:true});
      const oldFile = path.join(legacy,"history.jsonl");
      fs.writeFileSync(oldFile,"LEGACY_HISTORY\\n");
      const before = fs.readFileSync(oldFile);
      const provisioned = sa.ensureAgentWorkspace({agentName:"reviewer",cwd,parentSessionId:"new-parent"});
      console.log(JSON.stringify({
        legacy,session:provisioned.sessionDir,
        legacyExists:fs.existsSync(legacy),oldUnchanged:fs.readFileSync(oldFile).equals(before),
        newExists:fs.statSync(provisioned.sessionDir).isDirectory(),same:legacy===provisioned.sessionDir,
        oldEntries:fs.readdirSync(legacy),newEntries:fs.readdirSync(provisioned.sessionDir)
      }));
    ''', tmp_path)
    assert result["legacyExists"] is True and result["oldUnchanged"] is True
    assert result["same"] is False and result["newExists"] is True
    assert result["oldEntries"] == ["history.jsonl"]
    assert result["newEntries"] == []


@pytest.mark.parametrize("entry", ["symlink", "dangling", "directory", "hard-link"])
def test_provision_refuses_unsafe_jsonl_history_before_writes(tmp_path: Path, entry: str) -> None:
    result = run(f'''
      const session=sa.agentSessionPath("reviewer",cwd);fs.mkdirSync(session,{{recursive:true}});
      const outside=path.join(cwd,"outside-history.jsonl");fs.writeFileSync(outside,"private-history\\n");
      const before=fs.readFileSync(outside);const candidate=path.join(session,"unsafe.jsonl");
      const kind={json.dumps(entry)};
      if(kind==="symlink")fs.symlinkSync(outside,candidate);
      else if(kind==="dangling")fs.symlinkSync(path.join(cwd,"absent-history"),candidate);
      else if(kind==="hard-link")fs.linkSync(outside,candidate);
      else fs.mkdirSync(candidate);
      let error="";try{{sa.ensureAgentWorkspace({{agentName:"reviewer",cwd}});}}catch(e){{error=e.message;}}
      console.log(JSON.stringify({{error,unchanged:fs.readFileSync(outside).equals(before),
        state:fs.existsSync(path.join(sa.agentHomePath("reviewer"),"state.json")),
        memory:fs.existsSync(path.join(sa.agentHomePath("reviewer"),"memory"))}}));
    ''', tmp_path)
    assert result["error"]
    assert result["unchanged"] is True
    assert result["state"] is False and result["memory"] is False


def test_project_slug_preserves_the_existing_hash_algorithm(tmp_path: Path) -> None:
    result = run('console.log(JSON.stringify({slug:sa.projectSlug(cwd),cwd}));', tmp_path)
    resolved = str(Path(str(result["cwd"])).resolve())
    digest = hashlib.sha256(resolved.encode()).hexdigest()[:12]
    readable = resolved.lstrip("/").replace("/", "-")[-120:]
    assert result["slug"] == f"{readable}-{digest}"


def test_first_provision_creates_ordinary_dirs_and_second_reuses(tmp_path: Path) -> None:
    result = run('''
      const first = sa.ensureAgentWorkspace({agentName:"reviewer",cwd});
      const second = sa.ensureAgentWorkspace({agentName:"reviewer",cwd});
      const home = sa.agentHomePath("reviewer");
      console.log(JSON.stringify({first,second,
        index:fs.readFileSync(path.join(home,"memory","MEMORY.md"),"utf8"),
        proposals:fs.statSync(path.join(home,"memory","proposals")).isDirectory(),
        workspace:fs.statSync(first.workspacePath).isDirectory(),
        session:fs.statSync(first.sessionDir).isDirectory(),
        git:fs.existsSync(path.join(first.workspacePath,".git")),
        definition:fs.existsSync(path.join(home,"agent.md")),
        state:JSON.parse(fs.readFileSync(path.join(home,"state.json"),"utf8")),
        temp:fs.readdirSync(home).filter(n=>n.endsWith(".tmp"))}));
    ''', tmp_path)
    first, second = result["first"], result["second"]
    assert set(first) == {"cwd", "workspacePath", "sessionDir", "reused"}
    assert first["cwd"] == str(tmp_path / "project")
    assert first["cwd"] != first["workspacePath"]
    assert first["reused"] is False and second["reused"] is True
    assert first["workspacePath"] == second["workspacePath"]
    assert first["sessionDir"] == second["sessionDir"]
    assert "Agent Memory" in result["index"]
    assert result["proposals"] is True and result["workspace"] is True and result["session"] is True
    assert result["git"] is False and result["definition"] is False
    assert set(result["state"]) == {"createdAt", "lastProject", "memoryEntryCount"}
    assert result["state"]["lastProject"] == str(tmp_path / "project")
    assert result["state"]["memoryEntryCount"] == 0
    assert result["temp"] == []


def test_provision_preserves_index_output_and_creation_time(tmp_path: Path) -> None:
    result = run('''
      const first = sa.ensureAgentWorkspace({agentName:"reviewer",cwd});
      const home = sa.agentHomePath("reviewer");
      const statePath = path.join(home,"state.json");
      const originalState = JSON.parse(fs.readFileSync(statePath,"utf8"));
      const indexPath = path.join(home,"memory","MEMORY.md");
      const index = "CUSTOM INDEX\\r\\n保留内容\\n";
      fs.writeFileSync(indexPath,index);
      fs.writeFileSync(path.join(home,"memory","lesson.md"),"entry");
      fs.writeFileSync(path.join(home,"memory","proposals","candidate.md"),"proposal");
      fs.writeFileSync(path.join(first.workspacePath,"output.bin"),Buffer.from([0,255,10]));
      const otherProject = path.join(cwd,"other");fs.mkdirSync(otherProject);
      const second = sa.ensureAgentWorkspace({agentName:"reviewer",cwd:otherProject});
      const state = JSON.parse(fs.readFileSync(statePath,"utf8"));
      console.log(JSON.stringify({state,otherProject,
        creationKept:state.createdAt===originalState.createdAt,
        indexKept:fs.readFileSync(indexPath,"utf8")===index,
        output:[...fs.readFileSync(path.join(first.workspacePath,"output.bin"))],
        sameScratch:first.workspacePath===second.workspacePath,
        distinctSession:first.sessionDir!==second.sessionDir,
        reused:second.reused,definition:fs.existsSync(path.join(home,"agent.md"))}));
    ''', tmp_path)
    assert result["creationKept"] is True and result["indexKept"] is True
    assert result["output"] == [0, 255, 10]
    assert result["sameScratch"] is True and result["distinctSession"] is True
    assert result["reused"] is True and result["definition"] is False
    assert result["state"]["lastProject"] == result["otherProject"]
    assert result["state"]["memoryEntryCount"] == 1


@pytest.mark.parametrize("name", ["../escape", "a/b", "a\\b", "", "..", "reviewer.local"])
def test_path_helpers_reject_unsafe_or_reserved_names(tmp_path: Path, name: str) -> None:
    result = run(f'''
      const refused = [];
      for (const f of [()=>sa.agentHomePath({json.dumps(name)}),()=>sa.agentWorkspacePath({json.dumps(name)}),
        ()=>sa.agentSessionPath({json.dumps(name)},cwd),()=>sa.ensureAgentWorkspace({{agentName:{json.dumps(name)},cwd}})]) {{
        try {{ f();refused.push(false); }} catch {{refused.push(true);}}
      }}
      console.log(JSON.stringify({{refused,created:fs.existsSync(process.env.PI_CODING_AGENT_DIR)}}));
    ''', tmp_path)
    assert result == {"refused": [True, True, True, True], "created": False}


@pytest.mark.parametrize("unsafe", ["home", "memory", "MEMORY.md", "workspace", "projects", "state.json"])
def test_provision_refuses_symlinks_without_changing_their_target(tmp_path: Path, unsafe: str) -> None:
    result = run(f'''
      const home = sa.agentHomePath("reviewer");
      const outside = path.join(cwd,"outside");fs.mkdirSync(outside);
      const sentinel = path.join(outside,"sentinel");fs.writeFileSync(sentinel,"unchanged");
      fs.mkdirSync(home,{{recursive:true}});
      const label = {json.dumps(unsafe)};
      const target = label==="home"?home:label==="MEMORY.md"?path.join(home,"memory",label):path.join(home,label);
      if(label==="home")fs.rmdirSync(home);
      fs.mkdirSync(path.dirname(target),{{recursive:true}});
      fs.symlinkSync(["MEMORY.md","state.json"].includes(label)?sentinel:outside,target);
      let error="";try{{sa.ensureAgentWorkspace({{agentName:"reviewer",cwd}});}}catch(e){{error=e.message;}}
      console.log(JSON.stringify({{refused:!!error,error,sentinel:fs.readFileSync(sentinel,"utf8"),outside:fs.readdirSync(outside)}}));
    ''', tmp_path)
    assert result["refused"] is True
    assert "symlink" in result["error"].lower()
    assert result["sentinel"] == "unchanged" and result["outside"] == ["sentinel"]


@pytest.mark.parametrize("git_kind", ["file", "directory"])
def test_provision_never_disguises_a_git_workspace(tmp_path: Path, git_kind: str) -> None:
    result = run(f'''
      const workspace = sa.agentWorkspacePath("reviewer");fs.mkdirSync(workspace,{{recursive:true}});
      const git = path.join(workspace,".git");
      if({json.dumps(git_kind)}==="file")fs.writeFileSync(git,"gitdir: /legacy");else fs.mkdirSync(git);
      fs.writeFileSync(path.join(workspace,"output"),"only copy");
      let error="";try{{sa.ensureAgentWorkspace({{agentName:"reviewer",cwd}});}}catch(e){{error=e.message;}}
      console.log(JSON.stringify({{error,kept:fs.existsSync(git),output:fs.readFileSync(path.join(workspace,"output"),"utf8")}}));
    ''', tmp_path)
    assert result["error"] and result["kept"] is True and result["output"] == "only copy"


def test_provision_preserves_extra_state_and_respects_a_memory_writer_lock(tmp_path: Path) -> None:
    result = run('''
      sa.ensureAgentWorkspace({agentName:"reviewer",cwd});
      const home=sa.agentHomePath("reviewer");const file=path.join(home,"state.json");
      const state=JSON.parse(fs.readFileSync(file,"utf8"));state.retainedMetadata={label:"Do not discard"};
      fs.writeFileSync(file,JSON.stringify(state));
      sa.ensureAgentWorkspace({agentName:"reviewer",cwd});
      const metadataKept=JSON.parse(fs.readFileSync(file,"utf8")).retainedMetadata;
      const before=fs.readFileSync(file);const lock=file+".lock";fs.writeFileSync(lock,"other-process");
      let refused=false;try{sa.ensureAgentWorkspace({agentName:"reviewer",cwd:path.join(cwd,"another")});}catch{refused=true;}
      console.log(JSON.stringify({metadataKept,refused,unchanged:fs.readFileSync(file).equals(before),lock:fs.readFileSync(lock,"utf8")}));
    ''', tmp_path)
    assert result == {"metadataKept":{"label":"Do not discard"},"refused":True,"unchanged":True,"lock":"other-process"}


def test_malformed_state_is_not_overwritten(tmp_path: Path) -> None:
    result = run('''
      const home=sa.agentHomePath("reviewer");fs.mkdirSync(home,{recursive:true});
      const file=path.join(home,"state.json");fs.writeFileSync(file,"{invalid");
      let refused=false;try{sa.ensureAgentWorkspace({agentName:"reviewer",cwd});}catch{refused=true;}
      console.log(JSON.stringify({refused,content:fs.readFileSync(file,"utf8")}));
    ''', tmp_path)
    assert result == {"refused": True, "content": "{invalid"}


def test_parallel_provisioners_publish_complete_state_and_share_creation_time(tmp_path: Path) -> None:
    result = run(f'''
      const {{spawn}}=await import("node:child_process");
      const script=`import * as sa from {json.dumps(WORKSPACE)};import fs from "node:fs";
        sa.ensureAgentWorkspace({{agentName:"reviewer",cwd:process.env.PI_TEST_CWD}});
        console.log(fs.readFileSync(sa.agentHomePath("reviewer")+"/state.json","utf8"));`;
      const states=await Promise.all(Array.from({{length:6}},()=>new Promise((resolve,reject)=>{{
        const child=spawn(process.execPath,["--input-type=module","--eval",script],{{env:process.env}});
        let out="",err="";child.stdout.on("data",d=>out+=d);child.stderr.on("data",d=>err+=d);
        child.on("error",reject);child.on("close",code=>code?reject(new Error(err)):resolve(JSON.parse(out)));
      }})));
      const home=sa.agentHomePath("reviewer");
      console.log(JSON.stringify({{states,temp:fs.readdirSync(home).filter(n=>n.endsWith(".tmp")),
        final:JSON.parse(fs.readFileSync(path.join(home,"state.json"),"utf8"))}}));
    ''', tmp_path)
    assert len({state["createdAt"] for state in result["states"]}) == 1
    assert result["final"]["createdAt"] == result["states"][0]["createdAt"]
    assert result["temp"] == []


def test_git_preserve_and_release_apis_are_removed(tmp_path: Path) -> None:
    result = run('console.log(JSON.stringify({keys:Object.keys(sa)}));', tmp_path)
    assert "preserveAgentWorkspace" not in result["keys"]
    assert "releaseAgentWorkspace" not in result["keys"]
    assert "workspacesRoot" not in result["keys"]
    source = (PACKAGE / "src" / "workspace.ts").read_text(encoding="utf-8")
    assert "node:child_process" not in source
