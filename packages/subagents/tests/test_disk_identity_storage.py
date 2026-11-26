from __future__ import annotations

# --- Merged from test_disk_identity_storage.py ---
# --- Merged from test_disk_identity_storage.py ---
"""Disk identity and explicit copy-only migration contracts.

Contracts: features/disk-identity.feature and features/agent-migration.feature.
Only source modules are imported; all processes use isolated HOME/config.
"""


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


# --- Merged from test_storage_hardening.py ---
"""Regression contracts for private storage write boundaries.

Contract: features/storage-hardening.feature. Every case uses an isolated
agent directory and a real Node filesystem call; no user configuration is
read or written.
"""


import json
from pathlib import Path

from subagents_helpers import PACKAGE, run_node

MEMORY = (PACKAGE / "src" / "memory.ts").as_uri()
AGENTS = (PACKAGE / "src" / "agents.ts").as_uri()
MIGRATION = (PACKAGE / "src" / "migration.ts").as_uri()


def _m1_run(script: str, tmp_path: Path) -> dict[str, object]:
    project = tmp_path / "project"
    project.mkdir()
    return run_node(
        f'''import * as memory from {json.dumps(MEMORY)};
        import * as agents from {json.dumps(AGENTS)};
        import * as migration from {json.dumps(MIGRATION)};
        import fs from "node:fs";
        import path from "node:path";
        const root = path.join(process.env.PI_CODING_AGENT_DIR, "agents", "reviewer", "memory");
        const put = (file, body) => {{ fs.mkdirSync(path.dirname(file), {{ recursive: true }}); fs.writeFileSync(file, body); }};
        {script}''',
        env_overrides={
            "HOME": str(tmp_path / "home"),
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
            "PI_TEST_CWD": str(project),
            "PI_OFFLINE": "1",
            "PI_SKIP_VERSION_CHECK": "1",
        },
    )


def test_hard_linked_entry_is_refused_without_mutating_outside(tmp_path: Path) -> None:
    result = _m1_run('''
      const outside = path.join(process.env.PI_CODING_AGENT_DIR, "outside.md");
      put(outside, "OUTSIDE"); fs.mkdirSync(root, { recursive: true });
      fs.linkSync(outside, path.join(root, "lesson.md"));
      const append = memory.appendMemoryEntry(root, { name: "lesson", description: "d", body: "NEW" }, { writable: true });
      console.log(JSON.stringify({ append, outside: fs.readFileSync(outside, "utf8"), links: fs.statSync(outside).nlink }));
    ''', tmp_path)
    assert result["append"]["ok"] is False
    assert result["outside"] == "OUTSIDE"
    assert result["links"] == 2


def test_hard_linked_index_is_refused_without_mutating_outside(tmp_path: Path) -> None:
    result = _m1_run('''
      const outside = path.join(process.env.PI_CODING_AGENT_DIR, "outside-index.md");
      put(outside, "INDEX OUTSIDE"); fs.mkdirSync(root, { recursive: true });
      fs.linkSync(outside, path.join(root, "MEMORY.md"));
      const error = (() => { try { memory.writeMemoryIndexFile(root); return ""; } catch (e) { return e.message; } })();
      console.log(JSON.stringify({ error, outside: fs.readFileSync(outside, "utf8"), links: fs.statSync(outside).nlink }));
    ''', tmp_path)
    assert result["error"]
    assert result["outside"] == "INDEX OUTSIDE"
    assert result["links"] == 2


def test_append_preflights_a_hard_linked_index_before_creating_entry(tmp_path: Path) -> None:
    result = _m1_run('''
      const outside = path.join(process.env.PI_CODING_AGENT_DIR, "outside-index.md");
      put(outside, "INDEX OUTSIDE"); fs.mkdirSync(root, { recursive: true });
      fs.linkSync(outside, path.join(root, "MEMORY.md"));
      const append = memory.appendMemoryEntry(root, { name: "lesson", description: "d", body: "NEW" }, { writable: true });
      console.log(JSON.stringify({ append, entry: fs.existsSync(path.join(root, "lesson.md")), outside: fs.readFileSync(outside, "utf8") }));
    ''', tmp_path)
    assert result["append"]["ok"] is False
    assert result["entry"] is False
    assert result["outside"] == "INDEX OUTSIDE"


def test_same_title_proposals_survive_same_millisecond(tmp_path: Path) -> None:
    result = _m1_run('''
      const clock = Date.now; Date.now = () => 1700000000000;
      let first, second;
      try {
        first = memory.writeMemoryProposal(root, { title: "Same title", capability: "ONE", applicability: "a", limits: "l" });
        second = memory.writeMemoryProposal(root, { title: "Same title", capability: "TWO", applicability: "a", limits: "l" });
      } finally { Date.now = clock; }
      const files = fs.readdirSync(path.join(root, "proposals")).sort();
      console.log(JSON.stringify({ first, second, files, contents: files.map(name => fs.readFileSync(path.join(root, "proposals", name), "utf8")) }));
    ''', tmp_path)
    assert result["first"]["ok"] is True and result["second"]["ok"] is True
    assert len(result["files"]) == 2
    assert any("ONE" in body for body in result["contents"])
    assert any("TWO" in body for body in result["contents"])


def test_hard_linked_definition_is_refused_without_mutating_outside(tmp_path: Path) -> None:
    result = _m1_run('''
      const outside = path.join(process.env.PI_CODING_AGENT_DIR, "outside-agent.md");
      put(outside, "OUTSIDE DEFINITION");
      const destination = path.join(process.env.PI_CODING_AGENT_DIR, "agents", "reviewer", "agent.md");
      fs.mkdirSync(path.dirname(destination), { recursive: true }); fs.linkSync(outside, destination);
      const error = (() => { try { agents.persistAgentDefinition({ name: "reviewer", description: "d", tools: [], prompt: "p" }, "user"); return ""; } catch (e) { return e.message; } })();
      console.log(JSON.stringify({ error, outside: fs.readFileSync(outside, "utf8"), links: fs.statSync(outside).nlink }));
    ''', tmp_path)
    assert result["error"]
    assert result["outside"] == "OUTSIDE DEFINITION"
    assert result["links"] == 2


def test_migration_refuses_hard_linked_legacy_source(tmp_path: Path) -> None:
    result = _m1_run('''
      const outside = path.join(process.env.PI_CODING_AGENT_DIR, "outside-memory.md");
      put(outside, "OUTSIDE MEMORY");
      const sourceRoot = path.join(process.env.PI_CODING_AGENT_DIR, "agents", "reviewer");
      put(path.join(process.env.PI_CODING_AGENT_DIR, "agents", "reviewer.md"), "---\\nname: reviewer\\ndescription: d\\ntools: read\\n---\\nROLE\\n");
      fs.mkdirSync(sourceRoot, { recursive: true }); fs.linkSync(outside, path.join(sourceRoot, "lesson.md"));
      const plan = migration.planAgentMigration({ agentName: "reviewer", scope: "user", cwd: process.env.PI_TEST_CWD });
      console.log(JSON.stringify({ status: plan.status, blocked: plan.blocked, outside: fs.readFileSync(outside, "utf8"), canonical: fs.existsSync(path.join(sourceRoot, "memory", "lesson.md")) }));
    ''', tmp_path)
    assert result["status"] == "blocked"
    assert result["outside"] == "OUTSIDE MEMORY"
    assert result["canonical"] is False
    assert any("linked" in block["message"].lower() for block in result["blocked"])


def test_oversized_proposal_is_refused_before_any_write(tmp_path: Path) -> None:
    result = _m1_run('''
      const proposal = memory.writeMemoryProposal(root, {
        title: "Too large", capability: "x".repeat(memory.MEMORY_ENTRY_MAX_BYTES),
        applicability: "a", limits: "l", evidence: "e",
      });
      console.log(JSON.stringify({ proposal, root: fs.existsSync(root), proposals: fs.existsSync(path.join(root, "proposals")) }));
    ''', tmp_path)
    assert result["proposal"]["ok"] is False
    assert "cap" in result["proposal"]["error"].lower()
    assert result["root"] is False and result["proposals"] is False


def test_exact_utf8_proposal_budget_preserves_complete_bytes(tmp_path: Path) -> None:
    result = _m1_run('''
      const RealDate = Date; const fixed = RealDate.parse("2026-01-01T00:00:00.000Z");
      class FixedDate extends RealDate { constructor(...args) { super(args.length ? args[0] : fixed); } static now() { return fixed; } }
      globalThis.Date = FixedDate;
      const title = "Boundary", applicability = "when", limits = "limits";
      const build = capability => ["---", `title: ${title}`, "status: proposed", `created: ${new Date().toISOString()}`, "---", "", "## Capability", "", capability, "", "## Applicability", "", applicability, "", "## Limits", "", limits, ""].join("\\n");
      const budget = memory.MEMORY_ENTRY_MAX_BYTES; const emptyBytes = Buffer.byteLength(build(""), "utf8");
      const remaining = budget - emptyBytes; const multibyte = "界".repeat(Math.floor(remaining / 3)) + "x".repeat(remaining % 3);
      const expected = build(multibyte); const proposal = memory.writeMemoryProposal(root, { title, capability: multibyte, applicability, limits });
      const file = proposal.ok ? fs.readFileSync(proposal.file, "utf8") : "";
      console.log(JSON.stringify({ proposal, bytes: Buffer.byteLength(file, "utf8"), exact: file === expected, tail: file.slice(-12) }));
    ''', tmp_path)
    assert result["proposal"]["ok"] is True
    assert result["bytes"] == 16 * 1024
    assert result["exact"] is True
    assert result["tail"].endswith("limits\n")


# --- Merged from test_session_role_lifetime.py ---
"""Temporary role cleanup follows confirmed parent shutdown, not result settlement."""

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


# --- Merged from test_temporary_and_persistent.py ---
"""Disk identity and resident lifetime: temporary-and-persistent.feature.

Canonical definitions are authored by fixtures, never by the model-facing tool.
All runtime paths, HOME and config stay under the test's temporary directory.
"""

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


def _m3_run(script: str, tmp_path: Path) -> dict[str, object]:
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
    result = _m3_run("""
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
    result = _m3_run("""
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
    result = _m3_run("""
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
    result = _m3_run("""
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
    result = _m3_run("""
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
    result = _m3_run("""
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
    result = _m3_run("""
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
    result = _m3_run("""
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
    result = _m3_run("""
      const listed=await call({operation:"list"});
      console.log(JSON.stringify({definitions:listed.details.definitions,agents:listed.details.agents,role:!!resolveAgent("derived-only",cwd)}));
    """, tmp_path)
    assert result == {"definitions": [], "agents": [], "role": False}
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before


def test_old_readiness_cleanup_cannot_stop_replacement(tmp_path: Path) -> None:
    result = _m3_run("""
      let successor;
      const failed=await executeChildIntent({name:"same"},{...options,spawn:o=>(spawns.push(o),{pid:7,readiness:Promise.resolve(false)}),terminate:async()=>{
        spawns[0].onExit({pid:7,exitCode:0,signal:null,stdout:"",stderr:""});
        successor=await call({name:"same",prompt:"Next"});return {outcome:"closed"};
      }});
      console.log(JSON.stringify({failed:failed.details.ok,successor:successor.details.ok,status:getAgent("same").status,error:getAgent("same").error??null}));
    """, tmp_path)
    assert result == {"failed": False, "successor": True, "status": "starting", "error": None}


def test_inline_replacement_cannot_widen_existing_grant(tmp_path: Path) -> None:
    result = _m3_run("""
      const first=await call({name:"bounded",role_prompt:"Read",tools:["read"]});
      await call({operation:"stop",session:first.details.session});
      const second=await call({name:"bounded",role_prompt:"Run",tools:["bash"],prompt:"Next"});
      console.log(JSON.stringify({ok:second.details.ok,spawns:spawns.length}));
    """, tmp_path)
    assert result == {"ok": False, "spawns": 1}


def test_unconfirmed_input_retains_uncertain_authority(tmp_path: Path) -> None:
    result = _m3_run("""
      const start=await executeChildIntent({name:"uncertain"},{...options,prompt:async()=>{throw new Error("acknowledgement timed out");}});
      const first=await call({operation:"input",delivery:"next",session:start.details.session,prompt:"Run"});
      const second=await call({operation:"input",delivery:"next",session:start.details.session,prompt:"Retry"});
      console.log(JSON.stringify({first:first.details.ok,second:second.details.ok,status:getAgent("uncertain").status}));
    """, tmp_path)
    assert result == {"first": False, "second": False, "status": "starting"}


def test_transient_result_delivery_retries_without_closing_child(tmp_path: Path) -> None:
    result = _m3_run("""
      let tries=0;
      await executeChildIntent({name:"retry-result",prompt:"Reply"},{...options,deliverSessionResult:n=>{
        if(n.kind==="result" && ++tries===1)throw new Error("sender unavailable");notices.push(n);
      }});
      spawns[0].onUpdate({text:"complete answer",turns:1,finalResponse:true});await flush();
      console.log(JSON.stringify({tries,results:notices.filter(n=>n.kind==="result").length,stops:stops.length,status:getAgent("retry-result").status}));
    """, tmp_path)
    assert result == {"tries": 2, "results": 1, "stops": 0, "status": "idle"}


def test_coalesced_send_accepts_third_input_and_delivers_each_answer(tmp_path: Path) -> None:
    result = _m3_run("""
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
    result = _m3_run("""
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
    result = _m3_run("""
      const opts={...options,terminate:async()=>({outcome:"unconfirmed"})};
      await executeChildIntent({name:"error-live",prompt:"Run"},opts);
      spawns[0].onError(new Error("control stream error"));await flush();
      const replacement=await executeChildIntent({name:"error-live",prompt:"Replacement"},opts);
      console.log(JSON.stringify({replacement:replacement.details.ok,status:getAgent("error-live").status}));
    """, tmp_path)
    assert result["replacement"] is False and result["status"] != "stopped"


def test_negative_ack_progress_restores_idle_and_allows_retry(tmp_path: Path) -> None:
    result = _m3_run("""
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
    result = _m3_run("""
      await call({name:"crash-after-answer",prompt:"Reply"});
      spawns[0].onUpdate({text:"done",turns:1,finalResponse:true});
      spawns[0].onExit({pid:7,exitCode:null,signal:"SIGKILL",stdout:"",stderr:""});
      console.log(JSON.stringify({error:getAgent("crash-after-answer").error??null,status:getAgent("crash-after-answer").status}));
    """, tmp_path)
    assert result["status"] == "stopped" and "SIGKILL" in result["error"]


def test_role_reference_is_bundled_without_coordination_dependency(tmp_path: Path) -> None:
    result = _m3_run("""
      const {AGENT_REFERENCE_PATH}=await import("file://"+process.cwd()+"/src/agents.ts");
      const manifest=JSON.parse(fs.readFileSync(path.join(process.cwd(),"package.json"),"utf8"));
      console.log(JSON.stringify({exists:fs.existsSync(AGENT_REFERENCE_PATH),bundled:manifest.files.includes("references"),content:fs.readFileSync(AGENT_REFERENCE_PATH,"utf8")}));
    """, tmp_path)
    assert result["exists"] is result["bundled"] is True
    assert "minimal" in result["content"].lower() and "agent-teams" not in result["content"]


# --- Merged from test_temporary_fork.py ---
"""Temporary forks cross the real Pi control/context seams without history files."""

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


# --- Merged from test_fork_history_compat.py ---
"""Persisted old messages do not turn parent tool activation into child authority."""

import json

from pathlib import Path

from subagents_helpers import SRC, run_node


def test_fork_filters_legacy_metadata_and_current_results_without_mutating_parent(tmp_path: Path) -> None:
    script = f"""
      import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
      import {{ snapshotWorkContext }} from {json.dumps((SRC / "work-context.ts").as_uri())};
      const usage={{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}}};
      const outputs=[];
      for (const legacy of [false,true]) {{
        const parent=SessionManager.inMemory(process.cwd());
        parent.appendMessage({{role:"user",content:"Read it",timestamp:1}});
        parent.appendMessage({{role:"assistant",content:[{{type:"toolCall",id:"read-1",name:"read",arguments:{{path:"file.ts"}}}}],
          api:"openai-completions",provider:"fixture",model:"fixture",stopReason:"toolUse",timestamp:2,usage}});
        parent.appendMessage({{role:"toolResult",toolCallId:"read-1",toolName:"read",
          content:[{{type:"text",text:"Original result"}}],isError:false,timestamp:3,
          details:{{parentOnly:true}},...(legacy?{{addedToolNames:["agent"]}}:{{}})}});
        const before=JSON.stringify(parent.getEntries());
        const snapshot=snapshotWorkContext(parent);
        const result=snapshot.find(m=>m.role==="toolResult");
        outputs.push({{text:result.content[0].text,details:"details" in result,
          activation:"addedToolNames" in result,unchanged:before===JSON.stringify(parent.getEntries())}});
      }}
      console.log(JSON.stringify(outputs));
    """
    assert run_node(script, env_overrides={"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"), "PI_OFFLINE": "1"}) == [
        {"text":"Original result", "details":False, "activation":False, "unchanged":True},
        {"text":"Original result", "details":False, "activation":False, "unchanged":True},
    ]


def test_fork_excludes_system_credentials_and_runtime_authority_preserving_native_history(tmp_path: Path) -> None:
    # The execution contract allows conversation evidence, never the parent's
    # prompt/tool checkpoint, credentials or a deferred provider operation.
    result = run_node(f"""
      import assert from "node:assert/strict";
      import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
      import {{ snapshotWorkContext }} from {json.dumps((SRC / "work-context.ts").as_uri())};
      const usage={{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}}};
      const assistant=(content,stopReason="stop")=>({{role:"assistant",content,api:"openai-completions",
        provider:"fixture",model:"fixture",timestamp:2,usage,stopReason}});
      const tool=(id,name="read")=>({{role:"toolResult",toolCallId:id,toolName:name,
        content:[{{type:"text",text:"Completed evidence"}}],isError:false,timestamp:3,
        details:{{credentials:"runtime-secret"}},addedToolNames:["agent"],
        nestedCalls:{{calls:[{{arguments:{{token:"runtime-secret"}}}}]}},runtimeAuthority:"parent-only"}});
      const parent=SessionManager.inMemory(process.cwd());
      parent.appendMessage({{role:"system",content:"parent-secret",timestamp:1,
        sections:{{credentials:"parent-secret"}},toolsAdded:[{{name:"parent_admin"}}]}});
      const origin=parent.appendMessage({{role:"user",content:[{{type:"text",text:"Request"}},
        {{type:"image",data:"aW1hZ2U=",mimeType:"image/png"}}],timestamp:1}});
      parent.appendMessage(assistant([{{type:"text",text:"Abandoned branch"}}]));
      parent.branchWithSummary(origin,"Native branch summary",{{credentials:"runtime-secret"}});
      const kept=parent.getLeafId();
      parent.appendMessage(assistant([
        {{type:"thinking",thinking:"Historical reasoning",thinkingSignature:"opaque-signature"}},
        {{type:"text",text:"Historical answer",textSignature:"text-signature"}},
        {{type:"toolCall",id:"done",name:"read",arguments:{{path:"file.ts"}}}},
        {{type:"toolCall",id:"pending",name:"read",arguments:{{path:"pending.ts"}}}}
      ],"toolUse"));
      parent.appendCustomMessageEntry("evidence","Custom evidence",true,{{credentials:"runtime-secret"}});
      parent.appendMessage(tool("done"));
      parent.appendMessage(tool("pending","wrong-name"));
      parent.appendCompaction("Native compaction summary",kept,100,{{credentials:"runtime-secret"}});
      parent.appendCustomEntry("authority",{{credentials:"runtime-secret",tools:["parent_admin"]}});
      parent.appendMessage(assistant([{{type:"text",text:"Deferred answer evidence"}}],"deferred"));
      parent.getLeafEntry().message.deferred={{provider:"fixture",api:"fixture",modelId:"fixture",
        id:"parent-operation",data:{{credentials:"runtime-secret"}}}};
      const before=JSON.stringify(parent.getEntries()),leaf=parent.getLeafId();
      const snapshot=snapshotWorkContext(parent),serialized=JSON.stringify(snapshot);
      assert.equal(before,JSON.stringify(parent.getEntries()));assert.equal(leaf,parent.getLeafId());
      assert.ok(!serialized.includes("parent-secret"));assert.ok(!serialized.includes("runtime-secret"));
      assert.ok(!serialized.includes("parent_admin"));assert.ok(!serialized.includes("parent-only"));
      assert.ok(!serialized.includes("pending"));assert.ok(!serialized.includes("Abandoned branch"));
      assert.equal(snapshot.filter(m=>m.role==="toolResult").length,1);
      assert.ok(snapshot.some(m=>m.role==="branchSummary"&&m.summary==="Native branch summary"));
      assert.ok(snapshot.some(m=>m.role==="compactionSummary"&&m.tokensBefore===100));
      assert.ok(serialized.includes("opaque-signature"));assert.ok(serialized.includes("text-signature"));
      assert.ok(serialized.includes("Deferred answer evidence"));
      snapshot.find(m=>m.role==="assistant").content[0].thinking="child mutation";
      assert.equal(before,JSON.stringify(parent.getEntries()));
      console.log(JSON.stringify({{ok:true}}));
    """, env_overrides={"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"), "PI_OFFLINE": "1"})
    assert result == {"ok": True}


def test_completed_exchanges_keep_only_matching_results_across_custom_history(tmp_path: Path) -> None:
    result = run_node(f"""
      import assert from "node:assert/strict";
      import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
      import {{ snapshotWorkContext }} from {json.dumps((SRC / "work-context.ts").as_uri())};
      const usage={{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}}};
      const parent=SessionManager.inMemory(process.cwd());
      const call=(id)=>({{role:"assistant",content:[{{type:"toolCall",id,name:"read",arguments:{{}}}}],
        api:"openai-completions",provider:"fixture",model:"fixture",stopReason:"toolUse",timestamp:2,usage}});
      const result=(toolCallId,toolName="read")=>({{role:"toolResult",toolCallId,toolName,
        content:[{{type:"text",text:toolCallId}}],isError:false,timestamp:3}});
      parent.appendMessage({{role:"user",content:"Request",timestamp:1}});
      parent.appendMessage(call("matched"));
      parent.appendCustomMessageEntry("evidence","Interleaved history",true);
      parent.appendMessage(result("matched"));parent.appendMessage(result("matched"));
      parent.appendMessage(call("unmatched"));parent.appendMessage(result("unmatched","wrong"));
      parent.appendMessage({{role:"user",content:"New boundary",timestamp:4}});
      parent.appendMessage(result("unmatched"));parent.appendMessage(call("unfinished"));
      const snapshot=snapshotWorkContext(parent);
      assert.deepEqual(snapshot.map(m=>m.role),["user","assistant","custom","toolResult","user"]);
      assert.equal(snapshot[1].content[0].id,"matched");
      console.log(JSON.stringify({{ok:true}}));
    """, env_overrides={"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"), "PI_OFFLINE": "1"})
    assert result == {"ok": True}


def test_durable_writer_preserves_summary_roles_in_private_history(tmp_path: Path) -> None:
    result = run_node(f"""
      import assert from "node:assert/strict";
      import {{ readFileSync,statSync }} from "node:fs";
      import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
      import {{ writeWorkContext }} from {json.dumps((SRC / "work-context.ts").as_uri())};
      const history=[{{role:"compactionSummary",summary:"Compacted marker",tokensBefore:12,timestamp:1}},
        {{role:"branchSummary",summary:"Branch marker",fromId:"historic-entry",timestamp:2}},
        {{role:"user",content:"Historical input",timestamp:3}}];
      const file=writeWorkContext(process.cwd(),{json.dumps(str(tmp_path))},history);
      const child=SessionManager.open(file);
      assert.deepEqual(child.buildSessionContext().messages,history);
      assert.equal(child.getHeader().parentSession,undefined);
      assert.equal(statSync(file).mode&0o777,0o600);
      assert.ok(readFileSync(file,"utf8").includes("Compacted marker"));
      console.log(JSON.stringify({{ok:true}}));
    """, env_overrides={"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"), "PI_OFFLINE": "1"})
    assert result == {"ok": True}


# --- Merged from test_migration_fd_failures.py ---
"""Descriptor fault chains preserve first failure and disclose unverified files."""

import json
from pathlib import Path

import pytest

from identity_support import LEGACY, run


@pytest.mark.parametrize("operation", ["write", "fsync", "close-only"])
def test_migration_fd_close_failure_preserves_original_cause_and_cleanup(tmp_path: Path, operation: str) -> None:
    result = run(LEGACY + f'''
      const {{syncBuiltinESMExports}}=await import("node:module");
      const plan=sa.planAgentMigration(options),destinations=plan.files.map(file=>file.destination);
      const primary=Object.assign(new Error("primary migration failure"),{{code:"EIO"}});
      const closing=Object.assign(new Error("descriptor close failure"),{{code:"EBADF"}});
      const real={{openSync:fs.openSync,writeFileSync:fs.writeFileSync,fsyncSync:fs.fsyncSync,closeSync:fs.closeSync}};
      const descriptors=new Map(),closed=[];const selected=destinations.at(-1);
      const operation={json.dumps(operation)};let caught;
      fs.openSync=(file,...args)=>{{const fd=real.openSync(file,...args);if(destinations.includes(file))descriptors.set(fd,file);return fd;}};
      fs.writeFileSync=(fd,...args)=>{{
        if(descriptors.get(fd)===selected&&operation==="write"){{real.writeFileSync(fd,"PARTIAL");throw primary;}}
        return real.writeFileSync(fd,...args);
      }};
      fs.fsyncSync=fd=>{{if(descriptors.get(fd)===selected&&operation==="fsync")throw primary;return real.fsyncSync(fd);}};
      fs.closeSync=fd=>{{
        const file=descriptors.get(fd);if(file)closed.push(file);
        real.closeSync(fd);
        if(file===selected)throw closing;
      }};
      syncBuiltinESMExports();
      try{{sa.applyAgentMigration(plan);}}catch(error){{caught=error;}}
      finally{{Object.assign(fs,real);syncBuiltinESMExports();}}
      const expected=operation==="close-only"?closing:primary;
      console.log(JSON.stringify({{aggregate:caught instanceof AggregateError,
        originalCause:caught?.cause===expected,first:caught?.errors?.[0]===expected,
        closeCause:caught?.errors?.some(error=>error.cause===closing),message:caught?.message,
        selected,closed,remaining:destinations.filter(file=>fs.existsSync(file)),originalsKept:originalsKept()}}));
    ''', tmp_path, migration=True)
    assert result["aggregate"] is True, result
    assert result["originalCause"] is True and result["first"] is True, result
    assert result["closeCause"] is True
    assert result["selected"] in result["message"]
    assert "close" in result["message"].lower() and "descriptor" in result["message"].lower()
    assert result["closed"].count(result["selected"]) == 1
    assert result["remaining"] == [] and result["originalsKept"] is True


@pytest.mark.parametrize("target_index", [0, -1])
@pytest.mark.parametrize("replacement", ["none", "file", "symlink"])
@pytest.mark.parametrize("close_fails", [False, True])
def test_migration_fstat_failure_discloses_unknown_ownership_without_blind_unlink(
    tmp_path: Path, replacement: str, close_fails: bool, target_index: int,
) -> None:
    result = run(LEGACY + f'''
      const {{syncBuiltinESMExports}}=await import("node:module");
      const plan=sa.planAgentMigration(options),destinations=plan.files.map(file=>file.destination);
      const primary=Object.assign(new Error("descriptor ownership inspection failed"),{{code:"EIO"}});
      const closing=Object.assign(new Error("descriptor close also failed"),{{code:"EBADF"}});
      const real={{openSync:fs.openSync,fstatSync:fs.fstatSync,closeSync:fs.closeSync,unlinkSync:fs.unlinkSync}};
      const descriptors=new Map(),closed=[],removed=[];const selected=destinations.at({target_index});
      const replacement={json.dumps(replacement)},closeFails={json.dumps(close_fails)};
      const outside=path.join(cwd,"unrelated-target"),held=path.join(cwd,"held-created-inode");
      put(outside,"UNRELATED");let caught;
      fs.openSync=(file,...args)=>{{const fd=real.openSync(file,...args);if(destinations.includes(file))descriptors.set(fd,file);return fd;}};
      fs.fstatSync=(fd,...args)=>{{
        if(descriptors.get(fd)===selected){{
          if(replacement!=="none"){{fs.renameSync(selected,held);if(replacement==="file")put(selected,"REPLACEMENT");else fs.symlinkSync(outside,selected);}}
          throw primary;
        }}
        return real.fstatSync(fd,...args);
      }};
      fs.closeSync=fd=>{{const file=descriptors.get(fd);if(file)closed.push(file);real.closeSync(fd);if(file===selected&&closeFails)throw closing;}};
      fs.unlinkSync=(file,...args)=>{{if(destinations.includes(file))removed.push(file);return real.unlinkSync(file,...args);}};
      syncBuiltinESMExports();
      try{{sa.applyAgentMigration(plan);}}catch(error){{caught=error;}}
      finally{{Object.assign(fs,real);syncBuiltinESMExports();}}
      console.log(JSON.stringify({{aggregate:caught instanceof AggregateError,originalCause:caught?.cause===primary,
        first:caught?.errors?.[0]===primary,closeCause:caught?.errors?.some(error=>error.cause===closing),
        message:caught?.message,selected,closed,removed,
        remaining:destinations.filter(file=>fs.existsSync(file)),originalsKept:originalsKept(),
        selectedText:fs.readFileSync(selected,"utf8"),symlink:fs.lstatSync(selected).isSymbolicLink(),
        outside:fs.readFileSync(outside,"utf8")}}));
    ''', tmp_path, migration=True)
    assert result["aggregate"] is True and result["originalCause"] is True and result["first"] is True, result
    assert result["closeCause"] is close_fails
    assert result["selected"] in result["message"]
    assert "ownership" in result["message"].lower() and "incomplete" in result["message"].lower()
    assert result["remaining"] == [result["selected"]]
    assert result["selected"] not in result["removed"]
    assert result["closed"].count(result["selected"]) == 1
    assert result["selectedText"] == ("" if replacement == "none" else "REPLACEMENT" if replacement == "file" else "UNRELATED")
    assert result["symlink"] is (replacement == "symlink")
    assert result["outside"] == "UNRELATED" and result["originalsKept"] is True
