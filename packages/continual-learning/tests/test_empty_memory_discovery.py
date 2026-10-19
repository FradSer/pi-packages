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
      const options={{promptGuidelines:[],sections:{{project_memory_discovery:'STALE_DISCOVERY',project_memory_auto_learning:'STALE_AUTO',other:'KEEP'}}}};
      const missing=await hooks.get('before_agent_start')({{systemPrompt:'TRUSTED',systemPromptOptions:options}},ctx);
      await fs.writeFile(paths.harnessDir+'/MEMORY.md','# Memory Index\\n\\n');
      const emptyIndex=await hooks.get('before_agent_start')({{systemPrompt:'TRUSTED',systemPromptOptions:options}},ctx);
      console.log(JSON.stringify({{missing:{{...missing,guidance:Object.values(options.sections),sections:options.sections}},emptyIndex:{{...emptyIndex,guidance:Object.values(options.sections),sections:options.sections}}}}));
    ''',env={'PI_CODING_AGENT_DIR':str(tmp_path / 'agent')})
    for state in ('missing','emptyIndex'):
        assert result[state] is not None, 'Empty Memory discovery was omitted'
        assert 'message' not in result[state], 'Empty discovery must not append a placeholder reference'
        assert result[state]['sections']['other'] == 'KEEP'
        assert set(result[state]['sections']) == {'other', 'project_memory_protocol'}
        assert 'If no established entries are available' in ' '.join(result[state]['guidance'])
        assert 'use the read tool to inspect relevant indexed Memory entries' in result[state]['sections']['project_memory_protocol']
        assert 'do not search guessed or alternative Memory locations' in ' '.join(result[state]['guidance'])
        protocol = result[state]['sections']['project_memory_protocol']
        assert "Respect the task's read and write scope" in protocol
        assert 'these are Pi input commands, not shell tools' in protocol
        assert 'The parent performs automatic maintenance when enabled' in protocol
        assert 'Memory retrieval alone does not authorize configuration discovery or launching another agent' in protocol
        assert 'those need separate task authorization' in protocol
        assert 'Maintain knowledge through /memory or /consolidate.' not in protocol
    assert result['missing'] == result['emptyIndex']


def test_automatic_learning_owns_durable_writes_and_remember_does_not_expand_task_scope(tmp_path):
    result = run_bun(f'''
      import fs from 'node:fs/promises';
      import register from './packages/continual-learning/extensions/inject-memory.ts';
      import {{resolveMemoryPaths}} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd={json.dumps(str(tmp_path / 'project'))};await fs.mkdir(cwd);
      const paths=resolveMemoryPaths(cwd);await fs.mkdir(paths.harnessDir,{{recursive:true}});
      await fs.writeFile(paths.settingsFile,JSON.stringify({{autoMemory:true}}));
      const hooks=new Map();register({{on:(n,f)=>hooks.set(n,f),registerCommand(){{}},sendMessage(){{}},appendEntry(){{}},getCommands:()=>[]}});
      const options={{sections:{{}}}};await hooks.get('before_agent_start')({{systemPromptOptions:options}},{{cwd,ui:{{notify(){{}}}}}});
      console.log(JSON.stringify(options.sections));
    ''',env={'PI_CODING_AGENT_DIR':str(tmp_path / 'agent')})
    guidance = result['project_memory_auto_learning']
    assert 'The parent validates and writes them' in guidance
    assert '"remember" does not authorize writing Memory, Harness, AGENTS.md' in guidance
    assert 'PI.md or agent configuration, or probing enforcement' in guidance
    assert 'explicit authoring requests take precedence' in guidance
    assert "Respect the task's read and write scope" in result['project_memory_protocol']
    assert 'these are Pi input commands, not shell tools' in result['project_memory_protocol']
