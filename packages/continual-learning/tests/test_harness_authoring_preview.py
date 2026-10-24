from __future__ import annotations

import json
from pathlib import Path
from support import isolated_run_bun as run_bun


def test_preview_executes_plain_fixtures_and_requires_complete_coverage() -> None:
    result = run_bun('''
      import {previewHarnessCandidate} from './packages/continual-learning/extensions/harness-authoring-preview.ts';
      const candidate=JSON.stringify({rules:[{id:'traffic',text:'D0',instructions:'confirm volume first'}]});
      const cases=[{ruleId:'traffic',input:'接下来维护 D0',matches:true},{ruleId:'traffic',input:'本地配色',matches:false}];
      const run=(content,fixtures)=>previewHarnessCandidate(content,fixtures,new Set());
      console.log(JSON.stringify({good:run(candidate,cases),missing:run(candidate,cases.slice(0,1)),
        inert:run(JSON.stringify({rules:[{id:'traffic',text:String.fromCharCode(92).repeat(2)+'bD0'+String.fromCharCode(92).repeat(2)+'b',instructions:'confirm volume first'}]}),cases),falseNegative:run(candidate,[...cases.slice(0,1),{...cases[1],input:'D0'}]),
        disabled:run(JSON.stringify({rules:[{id:'existing-rule',enabled:false}]}),[]),empty:run(JSON.stringify({rules:[]}),[]),invalid:run('{',cases),foreign:run(candidate,cases.map(c=>({...c,ruleId:'other'})))}));
    ''')
    assert result['good']['passed'] and result['disabled']['passed']
    for name in ['missing', 'inert', 'falseNegative', 'empty', 'invalid', 'foreign']:
        assert not result[name]['passed'], name


def test_authoring_write_requires_exact_preview_and_tool_expires(tmp_path: Path) -> None:
    result = run_bun(f'''
      import fs from 'node:fs';
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / 'agent'))};
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks={{}},commands={{}},tools={{}}; let active=['read','write'];
      register({{on:(n,f)=>hooks[n]=f,registerEntryRenderer(){{}},registerMessageRenderer(){{}},registerCommand:(n,c)=>commands[n]=c,
        registerTool:t=>tools[t.name]=t,getActiveTools:()=>active,setActiveTools:t=>active=t,getCommands:()=>[],sendMessage(){{}}}});
      const ctx={{cwd:{json.dumps(str(tmp_path))},hasUI:false,ui:{{notify(){{}}}}}};
      const content=JSON.stringify({{rules:[{{id:'traffic',text:'D0',instructions:'confirm volume first'}}]}});
      const event={{toolName:'write',toolCallId:'write',input:{{path:'.pi/harness.json',content}}}};
      const before=await tools.harness_preview.execute('inactive',{{content,cases:[]}},undefined,undefined,ctx);
      await commands.harness.handler('避免后续 D0 的流量被打爆',ctx);
      const admitted=active.includes('harness_preview');
      const blocked=await hooks.tool_call(event,ctx);
      const preview=await tools.harness_preview.execute('preview',{{content,cases:[{{ruleId:'traffic',input:'维护 D0',matches:true}},{{ruleId:'traffic',input:'本地配色',matches:false}}]}},undefined,undefined,ctx);
      const normalDuring=await hooks.tool_call({{toolName:'write',toolCallId:'normal-during',input:{{path:'notes.txt',content:'Ordinary source work'}}}},ctx);
      const allowed=await hooks.tool_call(event,ctx);
      const repeated=await hooks.tool_call(event,ctx);
      const normalAfter=await hooks.tool_call({{toolName:'write',toolCallId:'normal-after',input:{{path:'notes.txt',content:'Ordinary source work'}}}},ctx);
      const changed=await hooks.tool_call({{...event,input:{{...event.input,content:content+' '}}}},ctx);
      await hooks.agent_end?.({{}},ctx);
      const across=await tools.harness_preview.execute('across',{{content,cases:[{{ruleId:'traffic',input:'维护 D0',matches:true}},{{ruleId:'traffic',input:'本地配色',matches:false}}]}},undefined,undefined,ctx);
      const acrossWrite=await hooks.tool_call(event,ctx);
      await hooks.session_tree({{}},ctx);
      const tree=await tools.harness_preview.execute('tree',{{content,cases:[]}},undefined,undefined,ctx);
      const treeInactive=!active.includes('harness_preview');
      await commands.harness.handler('继续维护 D0',ctx);
      await hooks.session_shutdown({{}},ctx);
      const after=await tools.harness_preview.execute('expired',{{content,cases:[]}},undefined,undefined,ctx);
      console.log(JSON.stringify({{before,admitted,blocked,preview,allowed:allowed??null,repeated,changed,normalDuring:normalDuring??null,normalAfter:normalAfter??null,across,acrossWrite:acrossWrite??null,tree,treeInactive,active,after,files:fs.existsSync({json.dumps(str(tmp_path / '.pi'))})}}));
    ''')
    assert result['before']['isError'] and result['after']['isError']
    assert result['admitted'] and result['blocked']['block']
    assert result['preview']['details']['passed'] and result['allowed'] is None
    assert result['repeated']['block'] and result['changed']['block']
    assert result['across']['details']['passed'] and result['acrossWrite'] is None
    assert result['normalDuring'] is None and result['normalAfter'] is None
    assert result['tree']['isError'] and result['treeInactive']
    assert 'harness_preview' not in result['active'] and not result['files']


def test_preview_consumption_is_atomic_after_last_await_and_legacy_confirmation(tmp_path: Path) -> None:
    result = run_bun(f'''
      import fs from 'node:fs'; import path from 'node:path'; import {{AsyncLocalStorage}} from 'node:async_hooks';
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / 'agent'))};
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks={{}},commands={{}},tools={{}};let active=['read','write'];
      register({{on:(n,f)=>hooks[n]=f,registerEntryRenderer(){{}},registerMessageRenderer(){{}},registerCommand:(n,c)=>commands[n]=c,
        registerTool:t=>tools[t.name]=t,getActiveTools:()=>active,setActiveTools:t=>active=t,getCommands:()=>[],sendMessage(){{}},appendEntry(){{}}}});
      const cwd={json.dumps(str(tmp_path))},target=path.join(cwd,'.pi/harness.json');
      fs.mkdirSync(path.dirname(target),{{recursive:true}});
      const content=JSON.stringify({{rules:[{{id:'traffic',text:'D0',instructions:'confirm volume first'}}]}});
      fs.writeFileSync(target,content);
      const ctx={{cwd,hasUI:true,ui:{{notify(){{}},select:async()=> 'Allow once'}}}};
      const event=i=>({{toolName:'write',toolCallId:'write-'+i,input:{{path:target,content}}}});
      const preview=()=>tools.harness_preview.execute('preview',{{content,cases:[]}},undefined,undefined,ctx);
      await commands.harness.handler('维护 D0',ctx);await preview();
      const original=fs.promises.lstat.bind(fs.promises);let arrivals=0,release,firstArrived;const barrier=new Promise(r=>release=r),firstAtFinal=new Promise(r=>firstArrived=r);
      const ownership=new AsyncLocalStorage();
      // Each admitted call reads its predecessor once, then rechecks on finalization.
      // Global ordinal reads assume an IO ordering and can strand the second call.
      fs.promises.lstat=async(...args)=>{{const value=await original(...args);const call=ownership.getStore();if(args[0]===target&&call&&++call.reads===2){{if(++arrivals===1)firstArrived();else release();await barrier;}}return value;}};
      const first=ownership.run({{reads:0}},()=>hooks.tool_call(event(1),ctx));
      await firstAtFinal; // Force the ordering that stranded the old global-read barrier.
      const second=ownership.run({{reads:0}},()=>hooks.tool_call(event(2),ctx));
      const parallel=await Promise.all([first,second]);
      fs.promises.lstat=original;
      fs.mkdirSync(process.env.PI_CODING_AGENT_DIR,{{recursive:true}});
      fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'harness.json'),JSON.stringify({{policies:[{{name:'confirm-write',tools:['write'],paths:['content'],pattern:'traffic',action:'confirm',reason:'confirm'}}],disabled:[],skillPrompts:{{}}}}));
      await preview();const confirmed=await hooks.tool_call(event(3),ctx);const reused=await hooks.tool_call(event(4),ctx);
      await preview();fs.writeFileSync(target,JSON.stringify({{rules:[]}}));const stale=await hooks.tool_call(event(5),ctx);
      console.log(JSON.stringify({{arrivals,parallel:parallel.map(x=>x??null),confirmed:confirmed??null,reused,stale,unchanged:fs.readFileSync(target,'utf8')}}));
    ''')
    assert result['arrivals'] == 2
    assert sum(item is None for item in result['parallel']) == 1
    assert sum(bool(item and item.get('block')) for item in result['parallel']) == 1
    assert result['confirmed'] is None and result['reused']['block']
    assert result['stale']['block'] and json.loads(result['unchanged']) == {'rules': []}


def test_preview_renderer_is_quiet_and_preserves_result_at_narrow_width() -> None:
    result = run_bun('''
      import {visibleWidth} from '@earendil-works/pi-tui';
      import register from './packages/continual-learning/extensions/guardrails.ts';
      const tools={};register({on(){},registerEntryRenderer(){},registerCommand(){},getCommands:()=>[],registerTool:t=>tools[t.name]=t});
      const tool=tools.harness_preview, theme={fg:(_c,t)=>t,bg:(_c,t)=>t,bold:t=>t};
      const component=tool.renderResult({content:[{type:'text',text:'complete candidate must stay out of UI'}],details:{passed:true,errors:[],cases:[{}]}},{expanded:false,isPartial:false},theme,{isError:false});
      const wide=component.render(120),narrow=component.render(48);
      const checking=tool.renderResult({content:[]},{isPartial:true},theme,{}).render(48);
      const rejected=tool.renderResult({content:[{type:'text',text:JSON.stringify({passed:false,raw:'must not dump JSON'})}],details:{passed:false,errors:['selector mismatch'],cases:[{}]}},{expanded:false,isPartial:false},theme,{isError:true}).render(48);
      console.log(JSON.stringify({shell:tool.renderShell,call:tool.renderCall().render(48),wide,narrow,widths:narrow.map(visibleWidth),checking,rejected}));
    ''')
    assert result['shell'] == 'self' and result['call'] == []
    assert 'verified' in '\n'.join(result['wide']) and 'verified' in '\n'.join(result['narrow'])
    assert all(width <= 48 for width in result['widths'])
    assert 'complete candidate' not in '\n'.join(result['wide'])
    assert 'rejected' not in '\n'.join(result['checking'])
    assert 'rejected' in '\n'.join(result['rejected'])
    assert 'must not dump JSON' not in '\n'.join(result['rejected'])
    assert '{' not in '\n'.join(result['rejected'])


def test_new_bash_rule_requires_parent_bound_command_evidence() -> None:
    result = run_bun('''
      import {previewHarnessCandidate} from './packages/continual-learning/extensions/harness-authoring-preview.ts';
      const content=JSON.stringify({rules:[{id:'gate',bash:'^git push$',message:'confirm',action:'confirm'}]});
      const cases=[{ruleId:'gate',input:'git push',matches:true},{ruleId:'gate',input:'git status',matches:false}];
      console.log(JSON.stringify({invented:previewHarnessCandidate(content,cases,new Set()),
        grounded:previewHarnessCandidate(content,cases,new Set(),undefined,new Set(['git push'])),
        wrong:previewHarnessCandidate(content,cases,new Set(),undefined,new Set(['git status'])),
        unchanged:previewHarnessCandidate(content,[],new Set(),JSON.parse(content))}));
    ''')
    assert not result['invented']['passed'] and not result['wrong']['passed']
    assert result['grounded']['passed'] and result['unchanged']['passed']


def test_parent_command_examples_exclude_failed_claimed_and_duplicate_calls() -> None:
    result = run_bun('''
      import {harnessCommandExamples} from './packages/continual-learning/extensions/guardrails.ts';
      const call=(id,command)=>({type:'message',message:{role:'assistant',content:[{type:'toolCall',name:'bash',id,arguments:{command}}]}});
      const done=(toolCallId,isError)=>({type:'message',message:{role:'toolResult',toolName:'bash',toolCallId,isError}});
      const branch=[call('ok','git push'),done('ok',false),call('bad','bad-command'),done('bad',true),
        call('dup','old-command'),done('dup',false),call('dup','new-command'),done('dup',false),
        {type:'message',message:{role:'assistant',content:[{type:'text',text:'I executed imaginary-command'}]}}];
      console.log(JSON.stringify([...harnessCommandExamples('guard `quoted command`',{sessionManager:{getBranch:()=>branch}})]));
    ''')
    assert sorted(result) == ['git push', 'quoted command']
