from __future__ import annotations
import json
from support import run_bun


def test_unchanged_index_is_reused_and_bodies_are_never_injected(tmp_path) -> None:
    result = run_bun(f'''
      import fs from 'node:fs/promises';
      import {{execFileSync}} from 'node:child_process';
      import register from './packages/continual-learning/extensions/inject-memory.ts';
      import {{resolveMemoryPaths}} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd={json.dumps(str(tmp_path / 'project'))};await fs.mkdir(cwd);execFileSync("git",["init","-q",cwd]);
      const p=resolveMemoryPaths(cwd);await fs.mkdir(p.harnessDir,{{recursive:true}});
      await fs.writeFile(p.harnessDir+'/test.md','---\\nname: test\\ndescription: Unique routing description\\ntype: project\\n---\\nSECRET_BODY_MARKER');
      await fs.writeFile(p.settingsFile,JSON.stringify({{autoMemory:false}}));
      const hooks={{}},branch=[];register({{on:(n,f)=>hooks[n]=f,registerCommand(){{}},sendMessage(){{}},appendEntry(){{}},getCommands:()=>[],exec:async()=>({{stdout:'',stderr:'',code:0}})}});
      const ctx={{cwd,ui:{{notify(){{}}}},sessionManager:{{getBranch:()=>branch}}}};
      await fs.mkdir(cwd+'/.memory');await fs.writeFile(cwd+'/.memory/TEST.md','---\\nname: test\\ndescription: STALE_PUBLIC_DESCRIPTION\\n---\\nPUBLIC_BODY');
      const first=await hooks.before_agent_start({{systemPrompt:'TRUSTED',prompt:'test.md Unique routing description'}},ctx);
      branch.push({{type:'custom_message',...first.message}});
      const second=await hooks.before_agent_start({{systemPrompt:'TRUSTED',prompt:'another task'}},ctx);
      const recovered=await hooks.context({{messages:[{{role:'user',content:'compacted'}}]}});
      const reused=await hooks.context({{messages:[{{role:'custom',...first.message}},{{role:'user',content:'next'}}]}});
      await fs.writeFile(p.harnessDir+'/test.md','---\\nname: test\\ndescription: Corrected description\\ntype: project\\n---\\nNEW_BODY');
      const changed=await hooks.before_agent_start({{systemPrompt:'TRUSTED',prompt:'changed'}},ctx);
      const refreshed=await hooks.context({{messages:[{{role:'custom',...first.message}},{{role:'custom',...changed.message}},{{role:'custom',...changed.message}}]}});
      await fs.unlink(p.harnessDir+'/test.md');await fs.unlink(cwd+'/.memory/TEST.md');
      const deleted=await hooks.before_agent_start({{systemPrompt:'TRUSTED',prompt:'deleted'}},ctx);
      const cleaned=await hooks.context({{messages:[{{role:'custom',...changed.message}}]}});
      console.log(JSON.stringify({{first,second,recovered,reused,changed,refreshed,deleted,cleaned}}));
    ''')
    assert 'SECRET_BODY_MARKER' not in result['first']['message']['content']
    assert '(harness)' not in result['first']['message']['content']
    assert 'message' not in result['second']
    assert sum(m.get('customType') == 'continual-learning-memory-reference' for m in result['recovered']['messages']) == 1
    assert sum(m.get('customType') == 'continual-learning-memory-reference' for m in result['reused']['messages']) == 1

    block = result['first']['message']['content']
    assert block.count('- test.md') == 1
    assert 'STALE_PUBLIC_DESCRIPTION' not in block
    assert 'test.md' not in result['first']['systemPrompt']
    assert result['reused']['messages'][0]['customType'] == 'continual-learning-memory-reference'
    assert 'Corrected description' in result['changed']['message']['content']
    assert len(result['refreshed']['messages']) == 1
    assert result['refreshed']['messages'][0]['content'] == result['changed']['message']['content']
    assert 'message' not in result['deleted']
    assert result['cleaned']['messages'] == []
