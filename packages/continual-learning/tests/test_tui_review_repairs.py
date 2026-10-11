from support import run_bun


def test_partial_failure_survives_successful_phase() -> None:
    result = run_bun('''
      import {learningSummarySubject} from './packages/continual-learning/extensions/learning-efficiency.ts';
      console.log(JSON.stringify(learningSummarySubject({attempts:[
        {phase:'memory',outcome:'applied',operations:1},
        {phase:'harness',outcome:'failed',operations:0}
      ],screen:{reasons:[]}})));
    ''')
    assert '1 memory applied' in result
    assert 'harness failed' in result


def test_model_search_accepts_letters_and_fits_narrow_terminal() -> None:
    result = run_bun('''
      import {initTheme} from '@earendil-works/pi-coding-agent';
      import {visibleWidth} from '@earendil-works/pi-tui';
      import {searchModelFromPicker} from './packages/kit/src/index.ts';
      initTheme('dark'); let result;
      await searchModelFromPicker({notify(){},custom:async(factory)=>{
        const component=factory({requestRender(){},terminal:{rows:24}},
          {fg:(_c,t)=>t,bold:t=>t},{matches:()=>false},()=>{});
        component.handleInput('j');component.handleInput('k');
        const lines=component.render(48);
        result={query:lines[2],width:Math.max(...lines.map(visibleWidth))};
      }},[{provider:'fixture',id:'jk-'+'long-model-'.repeat(8)}],undefined);
      console.log(JSON.stringify(result));
    ''')
    assert 'jk' in result['query']
    assert result['width'] <= 48


def test_native_list_and_reader_keep_focus_and_body_reachable_without_notifications() -> None:
    result = run_bun(r'''
      import {selectMenu,showDetailPages} from './packages/continual-learning/extensions/detail-pages.ts';
      import {visibleWidth} from '@earendil-works/pi-tui';
      const keys={matches:(data,key)=>({up:'tui.select.up',down:'tui.select.down',enter:'tui.select.confirm',esc:'tui.select.cancel'}[data]===key)};
      const theme={fg:(_c,t)=>t,bold:t=>t}; let notices=0,selected,body=[];
      const ui={notify(){notices++},select(){throw Error('native custom required')},custom:async(factory)=>{
        const c=factory({terminal:{rows:24},requestRender(){}},theme,keys,value=>selected=value);
        if(c.title==='List'){
          c.render(48); for(let n=0;n<39;n++)c.handleInput('down');
          const lines=c.render(48); c.handleInput('enter');
          return {lines,selected};
        }
        for(let n=0;n<20;n++){body.push(...c.render(48));c.handleInput('\x1b[6~')}
        c.handleInput('enter');return selected;
      }};
      const list=await selectMenu(ui,'List',Array.from({length:40},(_,n)=>`record-${n} `+'Long description '.repeat(10)));
      await showDetailPages(ui,'Reader',Array.from({length:100},(_,n)=>`中文证据 line-${n}`).join('\n'));
      console.log(JSON.stringify({list,notices,body,width:Math.max(...body.map(visibleWidth))}));
    ''')
    assert result['list']['selected'].startswith('record-39')
    assert any('> record-39' in line for line in result['list']['lines'])
    assert any('Esc: back' in line for line in result['list']['lines'])
    assert len(result['list']['lines']) <= 24
    assert result['notices'] == 0
    assert any('line-0' in line for line in result['body'])
    assert any('line-99' in line for line in result['body'])
    assert result['width'] <= 48


def test_diagnostics_and_procedure_keep_complete_evidence_and_compact_delivery() -> None:
    result = run_bun(r'''
      import register from './packages/continual-learning/extensions/guardrails.ts';
      import {runHarnessMenu} from './packages/continual-learning/extensions/harness-menu.ts';
      const commands={},messages=[],renderers={},menus=[];
      register({on(){},registerCommand:(n,c)=>commands[n]=c,registerEntryRenderer(){},
        registerMessageRenderer:(n,r)=>renderers[n]=r,getCommands:()=>[],sendMessage:(m,o)=>messages.push({m,o})});
      await commands.harness.handler('Use a safe fixture rule',{cwd:process.env.PI_CODING_AGENT_DIR,ui:{notify(){}}});
      await runHarnessMenu({notify(){throw Error('no chat flood')},select:async(title,options)=>{
        menus.push(title); return menus.length===1?'View diagnostics':menus.length===2?'Close':undefined;
      }}, {rules:[],errors:Array.from({length:12},(_,n)=>`error-${n}`),notices:[],invalidRules:[],
        legacy:{policies:[],invalidPolicies:[],skillPrompts:{},disabled:[],unavailable:false},
        bashEvaluationComplete:true,configReadIncomplete:false},{},()=>{});
      console.log(JSON.stringify({menus,messages,registered:Object.keys(renderers)}));
    ''')
    assert 'error-11' in result['menus'][1]
    assert result['messages'][0]['m']['customType'] == 'harness-procedure'
    assert 'Required protocol' in result['messages'][0]['m']['content']
    assert result['messages'][0]['o'] == {'deliverAs': 'followUp', 'triggerTurn': True}
    assert 'harness-procedure' in result['registered']


def test_error_and_incomplete_events_use_semantic_colors() -> None:
    result = run_bun('''
      import {initTheme} from '@earendil-works/pi-coding-agent';
      import register from './packages/continual-learning/extensions/output-checks.ts';
      initTheme('dark');let renderer;const colors=[];
      register({on(){},registerEntryRenderer:(_n,r)=>renderer=r});
      const theme={fg:(c,t)=>{colors.push(c);return t},bg:(c,t)=>{colors.push(c);return t},bold:t=>t};
      renderer({data:{status:'violated',phase:'artifact',detail:'bad'}},{expanded:false},theme).render(80);
      console.log(JSON.stringify(colors));
    ''')
    assert 'toolErrorBg' in result
    assert 'error' in result
    assert 'toolSuccessBg' not in result


def test_rpc_adapter_preserves_dialogs_and_ss3_reader_actions() -> None:
    result = run_bun(r'''
      import {managementUI,selectMenu,showDetailPages} from './packages/continual-learning/extensions/detail-pages.ts';
      const calls=[];
      const rpc={custom:async()=>{throw Error('RPC custom must not run')},notify(){},select:async(t,o)=>{calls.push({t,o});return o[0]}};
      await selectMenu(managementUI(rpc,'rpc'),'RPC list',['first']);
      await showDetailPages(managementUI(rpc,'rpc'),'RPC reader','Complete body');
      let selected;
      await showDetailPages({notify(){},select(){},custom:async(factory)=>{
        const c=factory({terminal:{rows:24},requestRender(){}},{fg:(_c,t)=>t,bold:t=>t},
          {matches:(data,key)=>data==='enter'&&key==='tui.select.confirm'},value=>selected=value);
        c.render(48);c.handleInput('\x1bOC');c.handleInput('enter');
      }},'Reader','body',['Close','Undo this change']);
      console.log(JSON.stringify({calls,selected}));
    ''')
    assert len(result['calls']) == 2
    assert 'Complete body' in result['calls'][1]['t']
    assert result['selected'] == 'Undo this change'


def test_model_picker_resizes_the_same_component_and_reveals_full_identifier() -> None:
    result = run_bun(r'''
      import {initTheme} from '@earendil-works/pi-coding-agent';
      import {searchModelFromPicker} from './packages/kit/src/index.ts';initTheme('dark');
      let result;
      await searchModelFromPicker({notify(){},custom:async(factory)=>{
        const tui={terminal:{rows:24},requestRender(){}};
        const c=factory(tui,{fg:(_c,t)=>t,bold:t=>t},{matches:()=>false},()=>{});
        c.render(48);tui.terminal.rows=12;const lines=c.render(48);
        const previews=[];for(let n=0;n<12;n++){previews.push(...c.render(48));c.handleInput('\x1bOC')}
        result={height:lines.length,tail:previews.some(line=>line.includes('UNIQUE_TAIL'))};
      }},Array.from({length:20},(_,n)=>({provider:'fixture',id:'a'.repeat(120)+'UNIQUE_TAIL-'+n})),undefined);
      console.log(JSON.stringify(result));
    ''')
    assert result['height'] <= 12
    assert result['tail'] is True


def test_recovered_retry_is_not_reported_as_an_unresolved_failure() -> None:
    result = run_bun('''
      import {learningSummarySubject,learningSummaryTone} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const receipt={attempts:[{phase:'memory',outcome:'rejected',operations:0},{phase:'memory',outcome:'applied',operations:1}],screen:{reasons:[]}};
      console.log(JSON.stringify({subject:learningSummarySubject(receipt),tone:learningSummaryTone(receipt),noop:learningSummarySubject({...receipt,attempts:[{phase:'memory',outcome:'rejected',operations:0},{phase:'memory',outcome:'noop',operations:0}]})}));
    ''')
    assert result == {'subject': '1 memory applied', 'tone': 'success', 'noop': 'no durable changes'}


def test_terminal_pipeline_error_after_recovered_retry_is_reported() -> None:
    result = run_bun('''
      import fs from 'node:fs';
      import {buildLearningReceipt,learningSummarySubject,learningSummaryTone} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const source=fs.readFileSync('./packages/continual-learning/extensions/inject-memory.ts','utf8');
      const body=source.split('}).catch(async (error: unknown) => {')[1].split('}).finally(async () => {')[0];
      const state={cancelled:false,attempts:[{phase:'memory',outcome:'rejected',operations:0},{phase:'memory',outcome:'applied',operations:1},{phase:'agents',outcome:'noop',operations:0}]};
      let receipt;
      const opts={cwd:'/fixture',mode:'manual',reportResult:true,reportReceipt:r=>receipt=r};
      const handler=new Function('state','opts','pipelineScreen','learningInput','buildLearningReceipt','writeLearningReceipt','resolveMemoryPaths','shouldReportLearningReceipt','notifyPi','ctx','currentLearningBatch',
        'return async error => {'+body+'}')(state,opts,{memory:true,harness:false,agents:true,reasons:[]},undefined,buildLearningReceipt,async()=>{},()=>({runsDir:'/fixture'}),()=>true,()=>{},{ui:{}},()=>undefined);
      await handler(new Error('proposal write failed'));
      console.log(JSON.stringify({subject:learningSummarySubject(receipt),tone:learningSummaryTone(receipt)}));
    ''')
    assert result == {'subject': '1 memory applied; agents failed', 'tone': 'error'}
