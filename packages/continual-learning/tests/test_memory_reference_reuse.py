from __future__ import annotations
import json
from support import run_bun


def test_unchanged_discovery_is_structured_and_bodies_are_never_injected(tmp_path) -> None:
    result = run_bun(f'''
      import fs from 'node:fs/promises';
      import {{execFileSync}} from 'node:child_process';
      import register from './packages/continual-learning/extensions/inject-memory.ts';
      import {{resolveMemoryPaths}} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd={json.dumps(str(tmp_path / 'project'))};await fs.mkdir(cwd);execFileSync('git',['init','-q',cwd]);
      const p=resolveMemoryPaths(cwd);await fs.mkdir(p.harnessDir,{{recursive:true}});
      await fs.writeFile(p.harnessDir+'/test.md','---\\nname: test\\ndescription: Unique routing description\\ntype: project\\n---\\nSECRET_BODY_MARKER');
      await fs.writeFile(p.settingsFile,JSON.stringify({{autoMemory:false}}));
      const hooks={{}};register({{on:(n,f)=>hooks[n]=f,registerCommand(){{}},sendMessage(){{}},appendEntry(){{}},getCommands:()=>[]}});
      const ctx={{cwd,ui:{{notify(){{}}}}}};
      await fs.mkdir(cwd+'/.memory');await fs.writeFile(cwd+'/.memory/TEST.md','---\\nname: test\\ndescription: STALE_PUBLIC_DESCRIPTION\\n---\\nPUBLIC_BODY');
      const start=async()=>{{const options={{sections:{{}}}};const returned=await hooks.before_agent_start({{systemPromptOptions:options,prompt:'task'}},ctx);return {{options,returned:returned??null}};}};
      const first=await start(),second=await start();
      const old={{role:'custom',customType:'continual-learning-memory-reference',content:'old',details:{{retrieved:[{{filename:'test.md'}}]}}}};
      const filtered=await hooks.context({{messages:[old,{{role:'user',content:'next'}}]}});
      await fs.writeFile(p.harnessDir+'/test.md','---\\nname: test\\ndescription: Corrected description\\ntype: project\\n---\\nNEW_BODY');
      const changed=await start();await fs.unlink(p.harnessDir+'/test.md');await fs.unlink(cwd+'/.memory/TEST.md');
      const deleted=await start();
      console.log(JSON.stringify({{first,second,filtered,changed,deleted}}));
    ''', env={'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    block = result['first']['options']['sections']['project_memory_discovery']
    assert 'SECRET_BODY_MARKER' not in block and 'STALE_PUBLIC_DESCRIPTION' not in block
    assert block.count('- test.md') == 1
    assert result['first'] == result['second']
    assert result['first']['returned'] is None
    assert result['filtered']['messages'] == [{'role': 'user', 'content': 'next'}]
    assert 'Corrected description' in result['changed']['options']['sections']['project_memory_discovery']
    assert 'project_memory_discovery' not in result['deleted']['options']['sections']
