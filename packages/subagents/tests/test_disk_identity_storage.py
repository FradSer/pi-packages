"""Disk identity and explicit copy-only migration contracts.

Contracts: features/disk-identity.feature and features/agent-migration.feature.
Only source modules are imported; all processes use isolated HOME/config.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from identity_support import AGENTS, LEGACY, run





def test_canonical_precedence_and_supported_definition_fields(tmp_path: Path) -> None:
    result = run('''
      sa.registerSessionAgent({name:"reviewer",description:"Session",tools:[],prompt:"SESSION"});
      const user=path.join(agentDir,"agents","reviewer","agent.md");
      const project=path.join(cwd,".pi","agents","reviewer","agent.md");
      const local=path.join(cwd,".pi","agents","reviewer.local","agent.md");
      put(user,raw("reviewer","USER","memory: false\\nworktree: true\\nisolation: isolated\\n"));
      put(project,raw("reviewer","PROJECT"));put(local,raw("reviewer","LOCAL"));
      const localRole=sa.resolveAgent("reviewer",cwd);fs.unlinkSync(local);
      const projectRole=sa.resolveAgent("reviewer",cwd);fs.unlinkSync(project);
      const userRole=sa.resolveAgent("reviewer",cwd);fs.unlinkSync(user);
      const sessionRole=sa.resolveAgent("reviewer",cwd);
      console.log(JSON.stringify({localRole,projectRole,userRole,sessionRole}));
    ''', tmp_path)
    for key, scope, body, managed in (
        ("localRole", "project-local", "LOCAL", False),
        ("projectRole", "project", "PROJECT", True),
        ("userRole", "user", "USER", False),
        ("sessionRole", "session", "SESSION", False),
    ):
        definition = result[key]
        assert definition["scope"] == scope and definition["prompt"] == body
        assert definition["gitManaged"] is managed
        assert not ({"memory", "worktree", "isolation", "persistent"} & definition.keys())
        if scope != "session":
            assert definition["source"].endswith("/agent.md")


def test_discovery_ignores_legacy_flat_files_and_derived_homes(tmp_path: Path) -> None:
    result = run('''
      const legacy=path.join(agentDir,"agents","legacy.md");put(legacy,raw("legacy"));
      put(path.join(agentDir,"agents","derived","memory","MEMORY.md"),"index");
      put(path.join(agentDir,"agents","derived","state.json"),"{}");
      put(path.join(cwd,".pi","agents","project-flat.md"),raw("project-flat"));
      const before=fs.readFileSync(legacy);
      const definitions=[...sa.discoverAgents(cwd).keys()];
      const absent=path.join(cwd,"absent");fs.mkdirSync(absent);
      sa.discoverAgents(absent);
      console.log(JSON.stringify({definitions,legacyKept:fs.readFileSync(legacy).equals(before),
        canonicalCreated:fs.existsSync(path.join(agentDir,"agents","legacy","agent.md")),
        projectCreated:fs.existsSync(path.join(absent,".pi"))}));
    ''', tmp_path)
    assert result == {"definitions": [], "legacyKept": True, "canonicalCreated": False, "projectCreated": False}


def test_discovery_does_not_provision_missing_storage(tmp_path: Path) -> None:
    result = run('''
      console.log(JSON.stringify({names:[...sa.discoverAgents(cwd).keys()],
        agentCreated:fs.existsSync(agentDir),projectCreated:fs.existsSync(path.join(cwd,".pi"))}));
    ''', tmp_path)
    assert result == {"names": [], "agentCreated": False, "projectCreated": False}


def test_only_valid_matching_canonical_declarations_are_discovered(tmp_path: Path) -> None:
    result = run('''
      const base=path.join(agentDir,"agents");
      put(path.join(base,"missing-name","agent.md"),"---\\ndescription: d\\ntools: read\\n---\\nBODY");
      put(path.join(base,"missing-description","agent.md"),"---\\nname: missing-description\\ntools: read\\n---\\nBODY");
      put(path.join(base,"missing-tools","agent.md"),"---\\nname: missing-tools\\ndescription: d\\n---\\nBODY");
      put(path.join(base,"mismatch","agent.md"),raw("other"));
      put(path.join(base,"traversal","agent.md"),raw("../escape"));
      put(path.join(base,"reserved.local","agent.md"),raw("reserved.local"));
      put(path.join(base,"valid","agent.md"),raw("valid","","model: inherit\\nverify: Tests pass\\n"));
      console.log(JSON.stringify({names:[...sa.discoverAgents(cwd).keys()],role:sa.resolveAgent("valid",cwd)}));
    ''', tmp_path)
    assert result["names"] == ["valid"]
    assert result["role"]["prompt"] == ""  # Empty instructions are a legal role.
    assert result["role"]["model"] == "inherit" and result["role"]["verify"] == "Tests pass"


@pytest.mark.parametrize("level", ["root", "directory", "file"])
def test_symlinked_declarations_are_not_discovered(tmp_path: Path, level: str) -> None:
    result = run(f'''
      const outside=path.join(cwd,"outside");put(path.join(outside,"reviewer","agent.md"),raw("reviewer"));
      const base=path.join(agentDir,"agents");fs.mkdirSync(agentDir,{{recursive:true}});
      const level={json.dumps(level)};
      if(level==="root")fs.symlinkSync(outside,base);
      else {{fs.mkdirSync(base);if(level==="directory")fs.symlinkSync(path.join(outside,"reviewer"),path.join(base,"reviewer"));
        else {{fs.mkdirSync(path.join(base,"reviewer"));fs.symlinkSync(path.join(outside,"reviewer","agent.md"),path.join(base,"reviewer","agent.md"));}}}}
      console.log(JSON.stringify({{names:[...sa.discoverAgents(cwd).keys()]}}));
    ''', tmp_path)
    assert result["names"] == []


@pytest.mark.parametrize("scope,suffix", [("user", "reviewer"), ("project", "reviewer"), ("project-local", "reviewer.local")])
def test_explicit_persistence_writes_only_new_shape(tmp_path: Path, scope: str, suffix: str) -> None:
    result = run(f'''
      const input={{name:"reviewer",description:"Inspect",tools:["read","grep"],model:"inherit",verify:"Tests pass",prompt:"ROLE BODY",memory:true,worktree:true,isolation:"isolated"}};
      const definition=sa.persistAgentDefinition(input,{json.dumps(scope)},cwd);
      const text=fs.readFileSync(definition.source,"utf8");
      console.log(JSON.stringify({{definition,text,resolved:sa.resolveAgent("reviewer",cwd),
        flat:fs.existsSync(path.join(agentDir,"agents","reviewer.md")),
        user:fs.existsSync(path.join(agentDir,"agents","reviewer","agent.md"))}}));
    ''', tmp_path)
    base = tmp_path / "home" / "agent" / "agents" if scope == "user" else tmp_path / "project" / ".pi" / "agents"
    assert result["definition"]["source"] == str(base / suffix / "agent.md")
    assert result["definition"] == result["resolved"]
    assert result["definition"]["prompt"] == "ROLE BODY"
    assert not ({"memory", "worktree", "isolation", "persistent"} & result["definition"].keys())
    assert "memory:" not in result["text"] and "worktree:" not in result["text"] and "isolation:" not in result["text"]
    assert "model: inherit" in result["text"] and "verify: Tests pass" in result["text"]
    assert result["flat"] is False and result["user"] is (scope == "user")


def test_session_registration_discards_extra_properties_and_never_writes(tmp_path: Path) -> None:
    result = run('''
      const role=sa.registerSessionAgent({name:"temporary",description:"d",tools:[" read "],prompt:" p ",memory:true,worktree:true,isolation:"isolated",source:"/forged",scope:"user"});
      sa.clearSessionAgents();
      console.log(JSON.stringify({role,remaining:[...sa.discoverAgents(cwd).keys()],created:fs.existsSync(agentDir)}));
    ''', tmp_path)
    assert result["remaining"] == [] and result["created"] is False
    # Tool-boundary contract preserves authored session instructions, unlike
    # identifier normalization; discarded identity/storage flags remain absent.
    assert result["role"] == {"name": "temporary", "description": "d", "tools": ["read"], "prompt": " p ", "scope": "session", "gitManaged": False}


@pytest.mark.parametrize("field", ["model", "tools"])
def test_persistence_refuses_frontmatter_injection_before_creating_dirs(tmp_path: Path, field: str) -> None:
    result = run(f'''
      const input={{name:"reviewer",description:"d",tools:["read"],prompt:"p"}};
      input[{json.dumps(field)}]={json.dumps('inherit\ntools: bash') if field == 'model' else json.dumps(['read\nmodel: evil'])};
      let refused=false;try{{sa.persistAgentDefinition(input,"user",cwd);}}catch{{refused=true;}}
      console.log(JSON.stringify({{refused,created:fs.existsSync(agentDir)}}));
    ''', tmp_path)
    assert result == {"refused": True, "created": False}


def test_persistence_refuses_destination_symlink(tmp_path: Path) -> None:
    result = run('''
      const target=path.join(cwd,"outside");put(target,"unchanged");
      const canonical=path.join(agentDir,"agents","reviewer","agent.md");fs.mkdirSync(path.dirname(canonical),{recursive:true});fs.symlinkSync(target,canonical);
      let refused=false;try{sa.persistAgentDefinition({name:"reviewer",description:"d",tools:[],prompt:"p"},"user",cwd);}catch{refused=true;}
      console.log(JSON.stringify({refused,target:fs.readFileSync(target,"utf8")}));
    ''', tmp_path)
    assert result == {"refused": True, "target": "unchanged"}




def test_migration_plan_and_dry_run_are_read_only(tmp_path: Path) -> None:
    result = run(LEGACY + '''
      const plan=sa.planAgentMigration(options);
      const dry=sa.applyAgentMigration(plan,{dryRun:true});
      console.log(JSON.stringify({plan,dry,originalsKept:originalsKept(),
        canonical:fs.existsSync(path.join(legacyMemory,"agent.md")),
        newMemory:fs.existsSync(path.join(legacyMemory,"memory")),
        projects:fs.existsSync(path.join(legacyMemory,"projects"))}));
    ''', tmp_path, migration=True)
    assert result["plan"]["status"] == "ready"
    assert result["dry"]["status"] == "dry-run"
    assert len(result["plan"]["files"]) == 5
    assert result["originalsKept"] is True
    assert result["canonical"] is False and result["newMemory"] is False and result["projects"] is False
    for file in result["plan"]["files"]:
        assert len(file["sourceSha256"]) == 64 and len(file["targetSha256"]) == 64
        assert Path(file["source"]).is_file() and not Path(file["destination"]).exists()


def test_apply_copies_role_memory_and_sessions_without_modifying_originals(tmp_path: Path) -> None:
    result = run(LEGACY + '''
      const plan=sa.planAgentMigration(options);
      const applied=sa.applyAgentMigration(plan);
      const canonical=path.join(legacyMemory,"agent.md");
      const migrated=fs.readFileSync(canonical,"utf8");
      const {resolveAgent}=await import(''' + json.dumps(AGENTS) + ''');
      console.log(JSON.stringify({applied,originalsKept:originalsKept(),migrated,
        bodyKept:migrated.slice(migrated.indexOf("---\\r\\n",5)+5)===body,
        role:resolveAgent("reviewer",cwd),
        memory:fs.readFileSync(path.join(legacyMemory,"memory","lesson.md"),"utf8"),
        index:fs.readFileSync(path.join(legacyMemory,"memory","MEMORY.md"),"utf8"),
        proposal:fs.readFileSync(path.join(legacyMemory,"memory","proposals","candidate.md"),"utf8"),
        history:fs.readFileSync(path.join(legacyMemory,"projects","project-one","session","history.jsonl"),"utf8")}));
    ''', tmp_path, migration=True)
    assert result["applied"]["status"] == "applied" and len(result["applied"]["copied"]) == 5
    assert result["originalsKept"] is True and result["bodyKept"] is True
    assert not any(f"{field}:" in result["migrated"] for field in ("memory", "worktree", "isolation", "persistent"))
    assert result["role"]["tools"] == ["read", "grep"] and result["role"]["model"] == "test/pinned"
    assert result["role"]["verify"] == "Tests pass"
    assert result["index"] == "CUSTOM INDEX\r\n" and result["proposal"] == "CANDIDATE\n" and result["history"] == "{}\n"


# Nine rows cover every pair of formatting axes; the 27-case product adds no new parser branch.
@pytest.mark.parametrize("whitespace,tools,line_endings", [
    ("spaces", "comma", "lf"), ("spaces", "inline", "crlf"), ("spaces", "block", "mixed"),
    ("tabs", "comma", "crlf"), ("tabs", "inline", "mixed"), ("tabs", "block", "lf"),
    ("mixed", "comma", "mixed"), ("mixed", "inline", "lf"), ("mixed", "block", "crlf"),
])
def test_migration_preserves_field_semantics_and_authored_bytes(
    tmp_path: Path, whitespace: str, tools: str, line_endings: str,
) -> None:
    result = run(f'''
      const {{parseAgentDefinition}}=await import({json.dumps(AGENTS)});
      const whitespace={json.dumps(whitespace)},tools={json.dumps(tools)},endings={json.dumps(line_endings)};
      const field=(key,value)=>whitespace==="spaces"?` ${{key}} : ${{value}}`:
        whitespace==="tabs"?`\t${{key}}\t:\t${{value}}`:` \t${{key}} \t : \t${{value}}`;
      const toolsLines=tools==="block"?[field("tools",""),"  # grant list",'  - "read"',"\t- grep"]:
        [field("tools",tools==="inline"?'["read", "grep"]':"read, grep")];
      const lines=["---",field("name","reviewer"),field("description",'"Inspect: safely"'),...toolsLines,
        field("model","test/pinned"),field("verify","Tests pass"),field("memory",""),
        "  - deprecated-memory",field("worktree",""),"  - deprecated-worktree",field("isolation",""),
        "  - deprecated-isolation",field("persistent",""),"  - deprecated-persistence","---"];
      const segments=lines.map((line,index)=>line+(endings==="crlf"||endings==="mixed"&&index%2===0?"\\r\\n":"\\n"));
      const body="\\n# Role\\r\\n保留正文\\n  trailing spaces  \\r\\n\\n";
      const definition=segments.join("")+body;
      const source=path.join(agentDir,"agents","reviewer.md");put(source,definition);
      const before=parseAgentDefinition(definition,"reviewer","user");
      const plan=sa.planAgentMigration({{agentName:"reviewer",scope:"user",cwd}});
      let error="";try{{sa.applyAgentMigration(plan);}}catch(e){{error=e.message;}}
      const destination=path.join(agentDir,"agents","reviewer","agent.md");
      const migrated=fs.existsSync(destination)?fs.readFileSync(destination):Buffer.alloc(0);
      const supportedCount=5+toolsLines.length;
      const expected=segments.slice(0,supportedCount).join("")+segments.at(-1)+body;
      console.log(JSON.stringify({{plan,error,before,after:parseAgentDefinition(migrated.toString("utf8"),"reviewer","user"),
        sourceKept:fs.readFileSync(source).equals(Buffer.from(definition)),
        bytesKept:migrated.equals(Buffer.from(expected)),bodyKept:migrated.subarray(-Buffer.byteLength(body)).equals(Buffer.from(body))}}));
    ''', tmp_path, migration=True)
    assert result["before"] == {
        "name": "reviewer", "description": "Inspect: safely", "tools": ["read", "grep"],
        "model": "test/pinned", "verify": "Tests pass", "prompt": "# Role\r\n保留正文\n  trailing spaces",
        "scope": "user", "gitManaged": False,
    }
    assert result["plan"]["status"] == "ready", result["plan"]["blocked"]
    assert result["error"] == ""
    assert result["after"] == result["before"]
    assert result["sourceKept"] is True and result["bytesKept"] is True and result["bodyKept"] is True


@pytest.mark.parametrize("tools_line", ["tools : read, grep", "tools\t:\t[read, grep]", " tools :\n  - read\n  - grep"])
def test_migration_never_overwrites_a_whitespace_tools_field_with_empty_default(
    tmp_path: Path, tools_line: str,
) -> None:
    result = run(f'''
      const {{parseAgentDefinition}}=await import({json.dumps(AGENTS)});
      const definition="---\\nname: reviewer\\ndescription: Inspect\\n"+{json.dumps(tools_line)}+"\\n---\\nROLE\\n";
      const source=path.join(agentDir,"agents","reviewer.md");put(source,definition);
      const before=parseAgentDefinition(definition,"reviewer","user");
      const plan=sa.planAgentMigration({{agentName:"reviewer",scope:"user",cwd}});sa.applyAgentMigration(plan);
      const migrated=fs.readFileSync(path.join(agentDir,"agents","reviewer","agent.md"));
      console.log(JSON.stringify({{before,after:parseAgentDefinition(migrated.toString("utf8"),"reviewer","user"),
        sourceKept:fs.readFileSync(source).equals(Buffer.from(definition)),bytesKept:migrated.equals(Buffer.from(definition))}}));
    ''', tmp_path, migration=True)
    assert result["before"]["tools"] == ["read", "grep"]
    assert result["after"] == result["before"], result
    assert result["sourceKept"] is True and result["bytesKept"] is True


def test_migration_adds_only_missing_legacy_defaults(tmp_path: Path) -> None:
    result = run('''
      const source=path.join(agentDir,"agents","reviewer.md");
      const body="\\nROLE\\r\\n保留\\n";
      const definition="---\\r\\nname : reviewer\\r\\n---\\r\\n"+body;put(source,definition);
      const plan=sa.planAgentMigration({agentName:"reviewer",scope:"user",cwd});
      let error="";try{sa.applyAgentMigration(plan);}catch(e){error=e.message;}
      const destination=path.join(agentDir,"agents","reviewer","agent.md");
      const migrated=fs.existsSync(destination)?fs.readFileSync(destination):Buffer.alloc(0);
      const {parseAgentDefinition}=await import(''' + json.dumps(AGENTS) + ''');
      console.log(JSON.stringify({plan,error,role:parseAgentDefinition(migrated.toString("utf8"),"reviewer","user"),
        bytesKept:migrated.equals(Buffer.from("---\\r\\nname : reviewer\\r\\ndescription: \\r\\ntools: \\r\\n---\\r\\n"+body)),
        sourceKept:fs.readFileSync(source).equals(Buffer.from(definition))}));
    ''', tmp_path, migration=True)
    assert result["plan"]["status"] == "ready" and result["error"] == ""
    assert result["role"]["description"] == "" and result["role"]["tools"] == []
    assert result["bytesKept"] is True and result["sourceKept"] is True


@pytest.mark.parametrize("field", ["name", "description", "tools", "model", "verify", "memory"])
def test_migration_blocks_duplicate_frontmatter_before_writing(tmp_path: Path, field: str) -> None:
    result = run(f'''
      const field={json.dumps(field)};
      const values={{name:"reviewer",description:"Inspect",tools:"read",model:"test/pinned",verify:"Tests pass",memory:"true"}};
      const extra=(field==="model"||field==="verify"||field==="memory"?`${{field}}: ${{values[field]}}\\n`:"")+
        ` ${{field}} \t: ${{values[field]}}\\n`;
      const source=path.join(agentDir,"agents","reviewer.md");put(source,raw("reviewer","PRIVATE BODY",extra));
      const before=fs.readFileSync(source);
      const plan=sa.planAgentMigration({{agentName:"reviewer",scope:"user",cwd}});
      let refused=false;try{{sa.applyAgentMigration(plan);}}catch{{refused=true;}}
      console.log(JSON.stringify({{plan,refused,source,sourceKept:fs.readFileSync(source).equals(before),
        destinationCreated:fs.existsSync(path.join(agentDir,"agents","reviewer"))}}));
    ''', tmp_path, migration=True)
    assert result["plan"]["status"] == "blocked" and result["refused"] is True
    assert any(
        block["kind"] == "invalid" and "duplicate" in block["message"].lower()
        and field in block["message"] and result["source"] in block["message"]
        for block in result["plan"]["blocked"]
    ), result["plan"]["blocked"]
    assert "PRIVATE BODY" not in json.dumps(result["plan"])
    assert result["sourceKept"] is True and result["destinationCreated"] is False


@pytest.mark.parametrize("invalid_bytes", [[255], [192, 175], [226, 130]])
def test_migration_blocks_non_utf8_definition_without_normalizing(
    tmp_path: Path, invalid_bytes: list[int],
) -> None:
    result = run(f'''
      const source=path.join(agentDir,"agents","reviewer.md");
      const bytes=Buffer.concat([Buffer.from(raw("reviewer","PRIVATE BODY")),Buffer.from({json.dumps(invalid_bytes)})]);
      put(source,bytes);
      const plan=sa.planAgentMigration({{agentName:"reviewer",scope:"user",cwd}});
      let refused=false;try{{sa.applyAgentMigration(plan);}}catch{{refused=true;}}
      console.log(JSON.stringify({{plan,refused,source,sourceKept:fs.readFileSync(source).equals(bytes),
        destinationCreated:fs.existsSync(path.join(agentDir,"agents","reviewer"))}}));
    ''', tmp_path, migration=True)
    assert result["plan"]["status"] == "blocked" and result["refused"] is True
    assert any(
        block["kind"] == "invalid" and "UTF-8" in block["message"] and result["source"] in block["message"]
        for block in result["plan"]["blocked"]
    ), result["plan"]["blocked"]
    assert "PRIVATE BODY" not in json.dumps(result["plan"])
    assert result["sourceKept"] is True and result["destinationCreated"] is False


def test_migration_blocks_defaults_that_change_authored_crlf_field_semantics(tmp_path: Path) -> None:
    result = run('''
      const {parseAgentDefinition}=await import(''' + json.dumps(AGENTS) + ''');
      const body="PRIVATE BODY\\n";
      const fields="name: reviewer\\r\\ndescription: Inspect # evidence\\r\\n";
      const definition="---\\r\\n"+fields+"---\\r\\n"+body;
      const expected=parseAgentDefinition("---\\r\\ntools: \\r\\n"+fields+"---\\r\\n"+body,"reviewer","user");
      const source=path.join(agentDir,"agents","reviewer.md");put(source,definition);
      const plan=sa.planAgentMigration({agentName:"reviewer",scope:"user",cwd});
      let refused=false;try{sa.applyAgentMigration(plan);}catch{refused=true;}
      const destination=path.join(agentDir,"agents","reviewer","agent.md");
      const migrated=fs.existsSync(destination)?parseAgentDefinition(fs.readFileSync(destination,"utf8"),"reviewer","user"):null;
      console.log(JSON.stringify({plan,expected,migrated,refused,source,
        sourceKept:fs.readFileSync(source).equals(Buffer.from(definition)),destinationCreated:fs.existsSync(destination)}));
    ''', tmp_path, migration=True)
    assert result["expected"]["description"] == "Inspect"
    assert result["plan"]["status"] == "blocked" and result["refused"] is True, result
    assert any(
        block["kind"] == "invalid" and "semantics" in block["message"] and result["source"] in block["message"]
        for block in result["plan"]["blocked"]
    ), result["plan"]["blocked"]
    assert "PRIVATE BODY" not in json.dumps(result["plan"])
    assert result["sourceKept"] is True and result["destinationCreated"] is False


def test_migration_blocks_filtering_that_changes_runtime_parser_semantics(tmp_path: Path) -> None:
    result = run('''
      const {parseAgentDefinition}=await import(''' + json.dumps(AGENTS) + ''');
      const header="---\\r\\nname: reviewer\\r\\ndescription: Inspect\\r\\ntools: read\\r\\nverify : Tests pass # evidence\\r\\n";
      const body="PRIVATE BODY\\n";
      const definition=header+"memory : true\\r\\n---\\r\\n"+body;
      const naive=header+"---\\r\\n"+body;
      const source=path.join(agentDir,"agents","reviewer.md");put(source,definition);
      const before=parseAgentDefinition(definition,"reviewer","user");
      const filtered=parseAgentDefinition(naive,"reviewer","user");
      const plan=sa.planAgentMigration({agentName:"reviewer",scope:"user",cwd});
      let refused=false;try{sa.applyAgentMigration(plan);}catch{refused=true;}
      console.log(JSON.stringify({plan,before,filtered,refused,source,
        sourceKept:fs.readFileSync(source).equals(Buffer.from(definition)),
        destinationCreated:fs.existsSync(path.join(agentDir,"agents","reviewer"))}));
    ''', tmp_path, migration=True)
    assert result["before"]["verify"] != result["filtered"]["verify"]
    assert result["plan"]["status"] == "blocked" and result["refused"] is True
    assert any(
        block["kind"] == "invalid" and "semantics" in block["message"] and result["source"] in block["message"]
        for block in result["plan"]["blocked"]
    ), result["plan"]["blocked"]
    assert "PRIVATE BODY" not in json.dumps(result["plan"])
    assert result["sourceKept"] is True and result["destinationCreated"] is False


@pytest.mark.parametrize("operation", ["open", "write"])
@pytest.mark.parametrize("disappearance", ["before-rollback", "during-unlink"])
def test_migration_rollback_continues_after_enoent_and_keeps_original_failure(
    tmp_path: Path, operation: str, disappearance: str,
) -> None:
    result = run(LEGACY + f'''
      const {{syncBuiltinESMExports}}=await import("node:module");
      const plan=sa.planAgentMigration(options),destinations=plan.files.map(file=>file.destination);
      const operation={json.dumps(operation)},disappearance={json.dumps(disappearance)};
      const failure=Object.assign(new Error("injected migration "+operation+" failure"),{{code:"EIO"}});
      const real={{openSync:fs.openSync,writeFileSync:fs.writeFileSync,lstatSync:fs.lstatSync,unlinkSync:fs.unlinkSync}};
      const descriptors=new Map(),inspected=[],removed=[];
      const victim=destinations[2],last=destinations.at(-1);
      let failed=false,caught;
      const fail=()=>{{if(disappearance==="before-rollback")real.unlinkSync(victim);failed=true;throw failure;}};
      fs.openSync=(file,...args)=>{{
        if(file===last&&operation==="open")fail();
        const fd=real.openSync(file,...args);if(destinations.includes(file))descriptors.set(fd,file);return fd;
      }};
      fs.writeFileSync=(file,...args)=>{{
        if(descriptors.get(file)===last&&operation==="write"){{real.writeFileSync(file,"PARTIAL");fail();}}
        return real.writeFileSync(file,...args);
      }};
      fs.lstatSync=(file,...args)=>{{if(failed&&destinations.includes(file))inspected.push(file);return real.lstatSync(file,...args);}};
      fs.unlinkSync=(file,...args)=>{{
        if(failed&&destinations.includes(file))removed.push(file);
        if(failed&&file===victim&&disappearance==="during-unlink"){{real.unlinkSync(file);return real.unlinkSync(file,...args);}}
        return real.unlinkSync(file,...args);
      }};
      syncBuiltinESMExports();
      try{{sa.applyAgentMigration(plan);}}catch(e){{caught=e;}}
      finally{{Object.assign(fs,real);syncBuiltinESMExports();}}
      const created=operation==="open"?destinations.slice(0,-1):destinations;
      console.log(JSON.stringify({{originalFailure:caught===failure,message:caught?.message,created,inspected,removed,victim,
        remaining:destinations.filter(file=>fs.existsSync(file)),originalsKept:originalsKept()}}));
    ''', tmp_path, migration=True)
    assert result["originalFailure"] is True, result
    assert result["inspected"] == list(reversed(result["created"]))
    expected_removed = list(reversed(result["created"]))
    if disappearance == "before-rollback":
        expected_removed.remove(result["victim"])
    assert result["removed"] == expected_removed
    assert result["remaining"] == [] and result["originalsKept"] is True


@pytest.mark.parametrize("operation", ["open", "write"])
@pytest.mark.parametrize("cleanup_operation", ["lstat", "unlink"])
@pytest.mark.parametrize("replacement", ["file", "symlink"])
def test_migration_rollback_reports_remaining_paths_and_keeps_replacement_inode(
    tmp_path: Path, operation: str, cleanup_operation: str, replacement: str,
) -> None:
    result = run(LEGACY + f'''
      const {{syncBuiltinESMExports}}=await import("node:module");
      const plan=sa.planAgentMigration(options),destinations=plan.files.map(file=>file.destination);
      const operation={json.dumps(operation)},cleanupOperation={json.dumps(cleanup_operation)},replacement={json.dumps(replacement)};
      const failure=Object.assign(new Error("injected migration "+operation+" failure"),{{code:"EIO"}});
      const cleanupFailure=Object.assign(new Error("injected rollback "+cleanupOperation+" failure"),{{code:"EACCES"}});
      const real={{openSync:fs.openSync,writeFileSync:fs.writeFileSync,lstatSync:fs.lstatSync,unlinkSync:fs.unlinkSync}};
      const descriptors=new Map(),inspected=[],removed=[];
      const retained=destinations[1],missing=destinations[2],replaced=destinations[3],last=destinations.at(-1);
      const target=path.join(cwd,"replacement-target"),held=path.join(cwd,"held-created-inode");put(target,"REPLACEMENT");
      let failed=false,caught,differentInode=false;
      const fail=()=>{{
        real.unlinkSync(missing);
        const owned=real.lstatSync(replaced);fs.renameSync(replaced,held);
        if(replacement==="file")real.writeFileSync(replaced,"REPLACEMENT");else fs.symlinkSync(target,replaced);
        const current=real.lstatSync(replaced);differentInode=owned.dev!==current.dev||owned.ino!==current.ino;
        failed=true;throw failure;
      }};
      fs.openSync=(file,...args)=>{{
        if(file===last&&operation==="open")fail();
        const fd=real.openSync(file,...args);if(destinations.includes(file))descriptors.set(fd,file);return fd;
      }};
      fs.writeFileSync=(file,...args)=>{{
        if(descriptors.get(file)===last&&operation==="write"){{real.writeFileSync(file,"PARTIAL");fail();}}
        return real.writeFileSync(file,...args);
      }};
      fs.lstatSync=(file,...args)=>{{
        if(failed&&destinations.includes(file))inspected.push(file);
        if(failed&&file===retained&&cleanupOperation==="lstat")throw cleanupFailure;
        return real.lstatSync(file,...args);
      }};
      fs.unlinkSync=(file,...args)=>{{
        if(failed&&destinations.includes(file))removed.push(file);
        if(failed&&file===retained&&cleanupOperation==="unlink")throw cleanupFailure;
        return real.unlinkSync(file,...args);
      }};
      syncBuiltinESMExports();
      try{{sa.applyAgentMigration(plan);}}catch(e){{caught=e;}}
      finally{{Object.assign(fs,real);syncBuiltinESMExports();}}
      const created=operation==="open"?destinations.slice(0,-1):destinations;
      console.log(JSON.stringify({{isAggregate:caught instanceof AggregateError,originalCause:caught?.cause===failure,
        originalFirst:caught?.errors?.[0]===failure,cleanupCause:caught?.errors?.some(e=>e.cause===cleanupFailure),
        message:caught?.message,diagnostics:caught?.errors?.map(e=>e.message),created,inspected,removed,retained,replaced,
        remaining:destinations.filter(file=>fs.existsSync(file)),differentInode,
        replacementContent:fs.existsSync(replaced)?fs.readFileSync(replaced,"utf8"):null,
        replacementSymlink:fs.existsSync(replaced)&&fs.lstatSync(replaced).isSymbolicLink(),
        targetContent:fs.readFileSync(target,"utf8"),originalsKept:originalsKept()}}));
    ''', tmp_path, migration=True)
    assert result["isAggregate"] is True and result["originalCause"] is True and result["originalFirst"] is True, result
    assert result["cleanupCause"] is True
    assert result["inspected"] == list(reversed(result["created"]))
    assert result["remaining"] == [result["retained"], result["replaced"]]
    assert result["replaced"] not in result["removed"]
    assert result["differentInode"] is True and result["replacementContent"] == "REPLACEMENT"
    assert result["replacementSymlink"] is (replacement == "symlink") and result["targetContent"] == "REPLACEMENT"
    assert any("replacement" in message.lower() and result["replaced"] in message for message in result["diagnostics"])
    assert any(
        cleanup_operation in message and "EACCES" in message and result["retained"] in message
        for message in result["diagnostics"]
    )
    assert "incomplete" in result["message"].lower()
    assert result["retained"] in result["message"] and result["replaced"] in result["message"]
    assert result["originalsKept"] is True


@pytest.mark.parametrize("scope,legacy,canonical", [("project", "reviewer.md", "reviewer"), ("project-local", "reviewer.local.md", "reviewer.local")])
def test_project_migration_never_creates_a_user_identity(tmp_path: Path, scope: str, legacy: str, canonical: str) -> None:
    result = run(f'''
      const base=path.join(cwd,".pi","agents");const source=path.join(base,{json.dumps(legacy)});put(source,raw("reviewer"));
      const plan=sa.planAgentMigration({{agentName:"reviewer",scope:{json.dumps(scope)},cwd}});
      const applied=sa.applyAgentMigration(plan);
      console.log(JSON.stringify({{applied,original:fs.readFileSync(source,"utf8"),
        canonical:fs.existsSync(path.join(base,{json.dumps(canonical)},"agent.md")),
        user:fs.existsSync(path.join(agentDir,"agents","reviewer","agent.md"))}}));
    ''', tmp_path, migration=True)
    assert result["applied"]["status"] == "applied" and result["canonical"] is True and result["user"] is False
    assert "Standing instructions" in result["original"]


def test_ordinary_legacy_scratch_copy_is_explicitly_project_scoped(tmp_path: Path) -> None:
    result = run(LEGACY + '''
      const workspace=path.join(agentDir,"workspaces","reviewer");
      put(path.join(workspace,"one","output.bin"),Buffer.from([0,255,10]));put(path.join(workspace,"two","other"),"OTHER");
      const unselected=sa.planAgentMigration(options);
      const plan=sa.planAgentMigration({...options,workspaceProjects:["one"]});
      const applied=sa.applyAgentMigration(plan);
      console.log(JSON.stringify({unselected:unselected.files.filter(f=>f.kind==="workspace"),
        applied,selected:[...fs.readFileSync(path.join(legacyMemory,"workspace","one","output.bin"))],
        other:fs.existsSync(path.join(legacyMemory,"workspace","two")),
        source:fs.existsSync(path.join(workspace,"one","output.bin")),originalsKept:originalsKept()}));
    ''', tmp_path, migration=True)
    assert result["unselected"] == []
    assert result["applied"]["status"] == "applied"
    assert result["selected"] == [0, 255, 10] and result["source"] is True
    assert result["other"] is False and result["originalsKept"] is True


@pytest.mark.parametrize("git_kind", ["file", "directory"])
def test_legacy_git_workspaces_are_blocked_manual_and_preserved(tmp_path: Path, git_kind: str) -> None:
    result = run(LEGACY + f'''
      const workspace=path.join(agentDir,"workspaces","reviewer","one");fs.mkdirSync(workspace,{{recursive:true}});
      const git=path.join(workspace,".git");if({json.dumps(git_kind)}==="file")put(git,"gitdir: /original");else fs.mkdirSync(git);
      put(path.join(workspace,"output"),"ONLY COPY");
      const inventory=sa.planAgentMigration(options);
      const selected=sa.planAgentMigration({{...options,workspaceProjects:["one"]}});
      let refused=false;try{{sa.applyAgentMigration(selected);}}catch{{refused=true;}}
      console.log(JSON.stringify({{inventory,selected,refused,git:fs.existsSync(git),
        output:fs.readFileSync(path.join(workspace,"output"),"utf8"),originalsKept:originalsKept(),
        copied:fs.existsSync(path.join(legacyMemory,"workspace","one"))}}));
    ''', tmp_path, migration=True)
    assert any(block["kind"] == "manual" and ".git" in block["message"] for block in result["inventory"]["blocked"])
    assert result["selected"]["status"] == "blocked" and result["refused"] is True
    assert result["git"] is True and result["output"] == "ONLY COPY"
    assert result["originalsKept"] is True and result["copied"] is False


@pytest.mark.parametrize("conflict", ["definition", "memory", "duplicate-source"])
def test_conflicts_are_refused_before_any_write(tmp_path: Path, conflict: str) -> None:
    result = run(LEGACY + f'''
      const type={json.dumps(conflict)};
      if(type==="definition")put(path.join(legacyMemory,"agent.md"),"EXISTING");
      if(type==="memory")put(path.join(legacyMemory,"memory","lesson.md"),"EXISTING");
      if(type==="duplicate-source")put(path.join(agentDir,"agents","alternate.md"),raw("reviewer","SECOND SOURCE"));
      const plan=sa.planAgentMigration(options);let refused=false;
      try{{sa.applyAgentMigration(plan);}}catch{{refused=true;}}
      console.log(JSON.stringify({{status:plan.status,blocked:plan.blocked,refused,originalsKept:originalsKept(),
        copiedProposal:fs.existsSync(path.join(legacyMemory,"memory","proposals","candidate.md"))}}));
    ''', tmp_path, migration=True)
    assert result["status"] == "blocked" and result["blocked"]
    assert result["refused"] is True and result["originalsKept"] is True and result["copiedProposal"] is False


@pytest.mark.parametrize("unsafe", ["source", "memory", "proposal", "session", "target", "workspace"])
def test_migration_refuses_symlinks_at_source_or_destination(tmp_path: Path, unsafe: str) -> None:
    result = run(LEGACY + f'''
      const outside=path.join(cwd,"outside");put(outside,"UNCHANGED");const type={json.dumps(unsafe)};
      const location=type==="source"?legacyRole:type==="memory"?path.join(legacyMemory,"lesson.md"):
        type==="proposal"?path.join(legacyMemory,"proposals","link.md"):
        type==="session"?path.join(agentDir,"subagent-sessions","reviewer","project-one","link.jsonl"):
        type==="workspace"?path.join(agentDir,"workspaces","reviewer","one","link"):
        path.join(legacyMemory,"memory");
      if(fs.existsSync(location))fs.unlinkSync(location);fs.mkdirSync(path.dirname(location),{{recursive:true}});fs.symlinkSync(outside,location);
      const plan=sa.planAgentMigration({{...options,...(type==="workspace"?{{workspaceProjects:["one"]}}:{{}})}});
      let refused=false;try{{sa.applyAgentMigration(plan);}}catch{{refused=true;}}
      console.log(JSON.stringify({{status:plan.status,refused,outside:fs.readFileSync(outside,"utf8"),
        canonical:fs.existsSync(path.join(legacyMemory,"agent.md"))}}));
    ''', tmp_path, migration=True)
    assert result == {"status": "blocked", "refused": True, "outside": "UNCHANGED", "canonical": False}


@pytest.mark.parametrize("tamper", ["source", "new-destination", "new-source", "path", "hash", "scope"])
def test_stale_or_tampered_plan_is_refused_before_writing(tmp_path: Path, tamper: str) -> None:
    result = run(LEGACY + f'''
      const plan=sa.planAgentMigration(options);const type={json.dumps(tamper)};
      if(type==="source")fs.appendFileSync(legacyRole,"NEW");
      if(type==="new-destination")put(path.join(legacyMemory,"memory","lesson.md"),"EXISTING");
      if(type==="new-source")put(path.join(legacyMemory,"new-entry.md"),"NEW SOURCE");
      if(type==="path")plan.files[0].destination=path.join(cwd,"escape");
      if(type==="hash")plan.files[0].sourceSha256="0".repeat(64);
      if(type==="scope")plan.scope="project";
      let error="";try{{sa.applyAgentMigration(plan);}}catch(e){{error=e.message;}}
      console.log(JSON.stringify({{error,canonical:fs.existsSync(path.join(legacyMemory,"agent.md")),
        escape:fs.existsSync(path.join(cwd,"escape")),proposal:fs.existsSync(path.join(legacyMemory,"memory","proposals","candidate.md"))}}));
    ''', tmp_path, migration=True)
    assert result["error"] and result["canonical"] is False and result["escape"] is False and result["proposal"] is False


@pytest.mark.parametrize("name,projects", [("../escape", []), ("reviewer", ["../escape"]), ("reviewer", ["/absolute"]), ("reviewer", ["one", "one"])])
def test_migration_rejects_traversal_or_duplicate_scope_selection(tmp_path: Path, name: str, projects: list[str]) -> None:
    result = run(f'''
      let refused=false;try{{sa.planAgentMigration({{agentName:{json.dumps(name)},scope:"user",cwd,workspaceProjects:{json.dumps(projects)}}});}}catch{{refused=true;}}
      console.log(JSON.stringify({{refused,created:fs.existsSync(agentDir)}}));
    ''', tmp_path, migration=True)
    assert result == {"refused": True, "created": False}
