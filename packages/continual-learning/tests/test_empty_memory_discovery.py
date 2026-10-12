"""An empty Memory must expose its absence instead of inviting guessed reads."""
import json
from support import run_bun


def test_empty_memory_discovery_is_explicit_with_or_without_an_empty_index(tmp_path):
    result = run_bun(f'''
      import fs from 'node:fs/promises';
      import register from './packages/continual-learning/extensions/inject-memory.ts';
      import {{resolveMemoryPaths}} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd={json.dumps(str(tmp_path / 'project'))}; await fs.mkdir(cwd);
      const paths=resolveMemoryPaths(cwd); await fs.mkdir(paths.harnessDir,{{recursive:true}});
      await fs.writeFile(paths.settingsFile,JSON.stringify({{autoMemory:false}}));
      const hooks=new Map(); register({{on:(n,f)=>hooks.set(n,f),registerCommand:()=>{{}},sendMessage:()=>{{}},appendEntry:()=>{{}},getCommands:()=>[],exec:async()=>({{stdout:'',stderr:'',code:0}})}});
      const ctx={{cwd,ui:{{notify:()=>{{}}}}}};
      const missing=await hooks.get('before_agent_start')({{systemPrompt:'TRUSTED'}},ctx);
      await fs.writeFile(paths.harnessDir+'/MEMORY.md','# Memory Index\\n\\n');
      const emptyIndex=await hooks.get('before_agent_start')({{systemPrompt:'TRUSTED'}},ctx);
      console.log(JSON.stringify({{missing:missing??null,emptyIndex:emptyIndex??null}}));
    ''',env={'PI_CODING_AGENT_DIR':str(tmp_path / 'agent')})
    for state in ('missing','emptyIndex'):
        assert result[state] is not None, 'Empty Memory discovery was omitted'
        assert 'message' not in result[state], 'Empty discovery must not append a placeholder reference'
        assert 'If no established entries are available' in result[state]['systemPrompt']
        assert 'do not search guessed or alternative Memory locations' in result[state]['systemPrompt']
    assert result['missing'] == result['emptyIndex']
