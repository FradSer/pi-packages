from __future__ import annotations

import json
from pathlib import Path

from test_guardrails_extension import run_bun


def test_registered_bash_gate_confirm_and_real_results_are_preserved(tmp_path: Path) -> None:
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      import fs from 'node:fs';import path from 'node:path';
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks={{}},commands={{}},entries=[];let timeout;
      register({{on:(n,f)=>hooks[n]=f,registerCommand:(n,c)=>commands[n]=c,registerEntryRenderer(){{}},appendEntry:(t,d)=>entries.push(d),getCommands:()=>[]}});
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(path.join(cwd,'.pi'));
      fs.writeFileSync(path.join(cwd,'.pi/harness.json'),JSON.stringify({{rules:[
        {{id:'approve',bash:'^fixture$',action:'confirm',message:'Confirm fixture scope.'}},
        {{id:'guide',bash:'^fixture$',message:'Report actual outcome.'}},
        {{id:'deny',bash:'^blocked$',action:'block',message:'Use safe fixture.'}}
      ]}}));
      const invoke=(id,command,choice,hasUI=true)=>hooks.tool_call({{toolName:'bash',toolCallId:id,input:{{command}}}},{{cwd,hasUI,ui:{{select:async(t,o,options)=>{{timeout=options.timeout;return choice}}}}}});
      const headless=await invoke('headless','fixture',undefined,false);
      const denied=await invoke('denied','fixture','Block');
      const expired=await invoke('expired','fixture',undefined);
      const allowed=await invoke('allowed','fixture','Allow once');
      const blocked=await invoke('blocked','blocked',undefined,false);
      const actual={{toolName:'bash',toolCallId:'allowed',content:[{{type:'text',text:'actual stderr'}}],details:{{exitCode:7,truncated:true}},isError:true}};
      const patched=await hooks.tool_result(actual);
      const replay=await hooks.tool_result(actual);
      const ordinary=await hooks.tool_call({{toolName:'write',input:{{path:'notes.txt',content:'fixture'}}}},{{cwd}});
      console.log(JSON.stringify({{headless,denied,expired,allowed:allowed??null,blocked,timeout,patched,actual,replay:replay??null,ordinary:ordinary??null,entries}}));
    ''')
    assert result['headless']['block'] and 'no UI' in result['headless']['reason']
    assert result['denied']['block'] and 'user choice' in result['denied']['reason']
    assert result['expired']['block'] and 'timed out' in result['expired']['reason']
    assert result['allowed'] is None and result['ordinary'] is None
    assert result['blocked']['block'] and 0 < result['timeout'] <= 60000
    assert result['patched']['content'][0] == result['actual']['content'][0]
    assert result['actual']['details'] == {'exitCode':7,'truncated':True}
    assert result['actual']['isError'] is True
    assert 'Report actual outcome' in result['patched']['content'][1]['text']
    assert 'Confirm fixture scope' in result['patched']['content'][1]['text']
    assert result['replay'] is None
    assert len([e for e in result['entries'] if e['outcome'] == 'allowed once']) == 1


def test_registered_hook_preserves_legacy_tool_scope_without_bash_lockout(tmp_path: Path) -> None:
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      import fs from 'node:fs';import path from 'node:path';
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks={{}},commands={{}},notices=[];
      register({{on:(n,f)=>hooks[n]=f,registerCommand:(n,c)=>commands[n]=c,registerEntryRenderer(){{}},appendEntry(){{}},getCommands:()=>[]}});
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(path.join(cwd,'.pi'));
      const target=path.join(cwd,'.pi/harness.json');const before=JSON.stringify({{policies:[{{name:'all-write',tools:['write'],pattern:'.*',reason:'old'}}],skillPrompts:{{old:{{prompt:'old',target:'system'}}}}}});
      fs.writeFileSync(target,before);
      const ordinary=await hooks.tool_call({{toolName:'write',input:{{path:'notes.txt',content:'text'}}}},{{cwd}});
      const bash=await hooks.tool_call({{toolName:'bash',input:{{command:'safe-fixture'}}}},{{cwd}});
      await commands.harness.handler('',{{cwd,ui:{{notify:m=>notices.push(m)}}}});
      console.log(JSON.stringify({{ordinary:ordinary??null,bash:bash??null,notices,unchanged:fs.readFileSync(target,'utf8')===before}}));
    ''')
    assert result['ordinary']['block'] and result['unchanged']
    assert result['bash'] is None
    assert any('legacy' in message for message in result['notices'])
