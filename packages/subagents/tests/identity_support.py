"""Shared disk identity and legacy migration setup."""
from __future__ import annotations

import json
from pathlib import Path

from subagents_helpers import PACKAGE, run_node

AGENTS = (PACKAGE / "src" / "agents.ts").as_uri()
MIGRATION = (PACKAGE / "src" / "migration.ts").as_uri()


def run(script: str, tmp_path: Path, *, migration: bool = False) -> dict[str, object]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    return run_node(
        f'''import * as sa from {json.dumps(MIGRATION if migration else AGENTS)};
        import fs from "node:fs";import path from "node:path";
        const cwd=process.env.PI_TEST_CWD;
        const agentDir=process.env.PI_CODING_AGENT_DIR;
        const put=(file,body)=>{{fs.mkdirSync(path.dirname(file),{{recursive:true}});fs.writeFileSync(file,body);}};
        const raw=(name,body="Standing instructions",extra="")=>`---\nname: ${{name}}\ndescription: Inspect\ntools: read, grep\n${{extra}}---\n${{body}}\n`;
        {script}''',
        env_overrides={
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / "config"),
            "PI_CODING_AGENT_DIR": str(home / "agent"),
            "PI_TEST_CWD": str(project),
        },
    )


LEGACY = '''
const legacyRole=path.join(agentDir,"agents","reviewer.md");
const legacyMemory=path.join(agentDir,"agents","reviewer");
const body="\\n# Role\\r\\n保留正文\\n\\n";
const definition="---\\r\\nname: reviewer\\r\\ndescription: Inspect\\r\\ntools:\\r\\n  - read\\r\\n  - grep\\r\\nmodel: test/pinned\\r\\nverify: Tests pass\\r\\nmemory: true\\r\\nworktree: true\\r\\nisolation: isolated\\r\\npersistent: true\\r\\n---\\r\\n"+body;
put(legacyRole,definition);
put(path.join(legacyMemory,"lesson.md"),"---\\nname: lesson\\ndescription: reusable\\n---\\nENTRY\\n");
put(path.join(legacyMemory,"MEMORY.md"),"CUSTOM INDEX\\r\\n");
put(path.join(legacyMemory,"proposals","candidate.md"),"CANDIDATE\\n");
put(path.join(agentDir,"subagent-sessions","reviewer","project-one","history.jsonl"),"{}\\n");
const options={agentName:"reviewer",scope:"user",cwd};
const snapshots=new Map([legacyRole,path.join(legacyMemory,"lesson.md"),path.join(legacyMemory,"MEMORY.md"),path.join(legacyMemory,"proposals","candidate.md"),path.join(agentDir,"subagent-sessions","reviewer","project-one","history.jsonl")].map(file=>[file,fs.readFileSync(file)]));
const originalsKept=()=>[...snapshots].every(([file,bytes])=>fs.readFileSync(file).equals(bytes));
'''
