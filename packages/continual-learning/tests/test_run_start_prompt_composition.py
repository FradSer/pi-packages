"""Run-start prompt contributions compose in both extension orders."""
import json
import os
from pathlib import Path
import pytest
from support import run_bun


def test_memory_and_goal_compose_with_pi_12_prompt_builder(tmp_path):
    configured = os.environ.get("PI_12_PACKAGE_DIR")
    if not configured:
        pytest.skip("Set PI_12_PACKAGE_DIR to a provisioned Pi 1.2 package directory")
    package = Path(configured).resolve()
    version = json.loads((package / "package.json").read_text())["version"]
    assert version.startswith("1.2."), f"Expected Pi 1.2, got {version}"
    builder = (package / "dist/core/system-prompt.js").as_uri()
    result = run_bun(f'''
      import fs from 'node:fs/promises';
      import registerMemory from './packages/continual-learning/extensions/inject-memory.ts';
      import {{registerGoalEvents}} from './packages/goal/src/events.ts';
      import {{normalizeGoalRecord}} from './packages/goal/src/record.ts';
      import {{normalizeBuildSystemPromptOptions,buildSystemPrompt}} from {json.dumps(builder)};
      const cwd={json.dumps(str(tmp_path / 'project'))};await fs.mkdir(cwd);
      const {{resolveMemoryPaths}}=await import('./packages/continual-learning/extensions/memory-paths.ts');
      const paths=resolveMemoryPaths(cwd);await fs.mkdir(paths.harnessDir,{{recursive:true}});
      await fs.writeFile(paths.harnessDir+'/fixture.md','---\\nname: fixture\\ndescription: DISCOVERY_MARKER\\ntype: project\\n---\\nBODY_NOT_INJECTED');
      const memoryHooks=new Map(); const goalHooks=new Map();
      const api=hooks=>({{on:(n,h)=>hooks.set(n,h),registerCommand(){{}},sendMessage(){{}},appendEntry(){{}},getCommands:()=>[],exec:async()=>({{stdout:'',stderr:'',code:0}})}});
      registerMemory(api(memoryHooks));
      let goal;
      registerGoalEvents({{pi:api(goalHooks),get goal(){{return goal}},acceptGoalSetting(){{}},settings:()=>({{}}),currentUnmet:()=>undefined}});
      const rows=[];
      for(const active of [false,true]) for(const reverse of [false,true]) for(const custom of [false,true]) {{
        goal=active?normalizeGoalRecord({{id:'fixture',objective:'ACTIVE_GOAL_MARKER',status:'active'}}):undefined;
        const options=normalizeBuildSystemPromptOptions({{cwd,contextFiles:[],skills:[],...(custom?{{customPrompt:'CUSTOM_OWNER'}}:{{}}),sections:{{fixture:'OTHER_SECTION'}}}});
        const event={{messageType:'custom',systemPromptOptions:options}};
        const handlers=[memoryHooks.get('before_agent_start'),goalHooks.get('before_agent_start')];
        if(reverse)handlers.reverse();
        const results=[];for(const handler of handlers)results.push(await handler(event,{{cwd,ui:{{notify(){{}}}}}}));
        const wire=buildSystemPrompt(options);
        rows.push({{active,reverse,custom,owner:wire.includes('CUSTOM_OWNER'),discovery:wire.includes('DISCOVERY_MARKER'),auto:wire.includes('After this user task settles'),body:wire.includes('BODY_NOT_INJECTED'),capability:wire.includes('[pi-goal capability]'),memory:wire.includes('Project Memory discovery'),state:wire.includes('ACTIVE_GOAL_MARKER'),forced:results.some(r=>r?.systemPrompt!==undefined),customInjection:results.some(r=>r?.message!==undefined),other:wire.includes('OTHER_SECTION'),forceOption:options.forceSystemPrompt!==undefined}});
      }}
      console.log(JSON.stringify(rows));
    ''', env={'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    assert len(result) == 8
    for row in result:
        assert row['capability'] and row['memory']
        assert row['state'] == row['active']
        assert not row['forced'] and not row['forceOption'] and not row['customInjection']
        assert row['other']
        assert row['owner'] == row['custom']
        assert row['discovery'] and row['auto'] and not row['body']
