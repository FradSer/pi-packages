"""Merged tests from: test_tui_design_refinements.py, test_tui_review_repairs.py, test_meaningful_renderer_details.py."""

from __future__ import annotations

from support import run_bun
from pathlib import Path
import pytest
from support import run_bun_script

# --- Merged from test_tui_design_refinements.py ---

def test_reader_preserves_logical_position_and_end_after_reflow() -> None:
    result = run_bun(r'''
      import {showDetailPages} from './packages/continual-learning/extensions/detail-pages.ts';
      let result;
      await showDetailPages({notify(){},select(){},custom:async(factory)=>{
        const tui={terminal:{rows:24},requestRender(){}};
        const c=factory(tui,{bold:t=>t,fg:(_c,t)=>t},{matches:(d,k)=>d==='down'&&k==='tui.select.down'},()=>{});
        c.render(48);for(let i=0;i<75;i++)c.handleInput('down');
        const before=c.render(48);const after=c.render(80);
        for(let i=0;i<200;i++)c.handleInput('down');const end=c.render(48);const endWide=c.render(80);
        tui.terminal.rows=12;const shortEnd=c.render(80);result={before,after,end,endWide,shortEnd};
      }},'Reader',Array.from({length:100},(_,i)=>`line-${i} Preserve evidence and verify the actual result.`).join('\n'));
      console.log(JSON.stringify(result));
    ''')
    assert result['before'][2] == 'result.'
    assert 'line-37' in '\n'.join(result['after'])
    assert 'line-99' in '\n'.join(result['endWide'])
    assert 'line-99' in '\n'.join(result['shortEnd'])


def test_history_target_policy_help_and_nested_returns() -> None:
    result = run_bun('''
      import {openMemoryMenu} from './packages/continual-learning/extensions/memory-menu.ts';
      const menus=[];const choices=['Recent learning',undefined,'Learning settings','Advanced phase policies','Agents policy',undefined,undefined,undefined,'Close'];
      await openMemoryMenu({cwd:'/fixture',hasUI:true,ui:{notify(){},select:async(title,options)=>{menus.push({title,options});return choices.shift()}}},{
        status:async()=>({autoSettledLearning:false,autoContinualLearning:false,model:'fixture/model',entries:0}),loadMemories:async()=>({entries:[]}),
        listHistory:async()=>[{id:'opaque',createdAt:'2026-10-09T20:30:00Z',phase:'memory',status:'applied',changes:[{target:{name:'build-command.md'}}]}],
        manage:async()=>{throw Error('no writes')},selectModel:async()=>{},toggleAutoMemory:async()=>{},isBusy:()=>false,
        policies:async()=>({policies:{memory:'apply',harness:'propose',agents:'off'},agentsDisabled:true})});
      console.log(JSON.stringify(menus));
    ''')
    assert result[1]['options'][0].startswith('#1 build-command.md')
    titles = [row['title'] for row in result]
    agents = next(i for i, title in enumerate(titles) if title.startswith('Agents policy'))
    assert 'Advanced phase policies' in titles[agents + 1]
    assert 'Learning settings' in titles[agents + 2]
    assert 'AGENTS.md disabled' in titles[agents]
    assert titles[agents].split('\n')[0] == 'Agents policy'


def test_model_hints_are_complete_at_48_columns_and_12_rows() -> None:
    result = run_bun('''
      import {initTheme} from '@earendil-works/pi-coding-agent';initTheme('dark');
      import {searchModelFromPicker} from './packages/kit/src/index.ts';
      let lines;
      await searchModelFromPicker({notify(){},custom:async(factory)=>{
        const c=factory({terminal:{rows:12},requestRender(){}},{bold:t=>t,fg:(_c,t)=>t},{matches:()=>false},()=>{});
        lines=c.render(48);
      }},[{provider:'fixture',id:'model'}]);console.log(JSON.stringify(lines));
    ''')
    assert len(result) <= 12
    assert any('Enter: select' in line and 'Esc: cancel' in line for line in result)


def test_harness_reader_defaults_to_close() -> None:
    result = run_bun('''
      import {runHarnessMenu} from './packages/continual-learning/extensions/harness-menu.ts';
      const menus=[];const choices=['rule · text:release','Close',undefined];
      await runHarnessMenu({notify(){},input(){},select:async(title,options)=>{menus.push({title,options});return choices.shift()}},
      {rules:[{id:'rule',text:'release',instructions:'Check evidence',source:'project'}],errors:[],notices:[],invalidRules:[],legacy:{policies:[],invalidPolicies:[],skillPrompts:{},disabled:[],unavailable:false},bashEvaluationComplete:true,configReadIncomplete:false},{project:'.pi/harness.json'},()=>{});
      console.log(JSON.stringify(menus));
    ''')
    assert result[1]['options'][0] == 'Close'


def test_end_intent_survives_a_resize_where_the_whole_body_fits() -> None:
    result = run_bun(r'''
      import {showDetailPages} from './packages/continual-learning/extensions/detail-pages.ts';
      let lines;
      await showDetailPages({notify(){},select(){},custom:async(factory)=>{
        const c=factory({terminal:{rows:24},requestRender(){}},{bold:t=>t,fg:(_c,t)=>t},{matches:(d,k)=>d==='down'&&k==='tui.select.down'},()=>{});
        c.render(48);for(let i=0;i<30;i++)c.handleInput('down');c.render(48);c.render(120);lines=c.render(48);
      }},'Reader',Array.from({length:12},(_,i)=>`line-${i} Preserve evidence and verify the actual result.`).join('\n'));
      console.log(JSON.stringify(lines));
    ''')
    assert 'line-11' in '\n'.join(result)


def test_history_mirror_names_do_not_hide_status_at_48_columns() -> None:
    result = run_bun('''
      import {openMemoryMenu} from './packages/continual-learning/extensions/memory-menu.ts';
      const menus=[];const choices=['Recent learning',undefined,'Close'];
      await openMemoryMenu({cwd:'/fixture',hasUI:true,ui:{notify(){},select:async(title,options)=>{menus.push({title,options});return choices.shift()}}},{
        status:async()=>({autoSettledLearning:false,autoContinualLearning:false,model:'fixture/model',entries:0}),loadMemories:async()=>({entries:[]}),
        listHistory:async()=>['applied','undone'].map(status=>({id:status,createdAt:'2026-10-09T20:30:00Z',phase:'memory',status,changes:
          ['MEMORY.md','cl_real_isolated_fact.md','MEMORY.md','cl_real_isolated_fact.md'].map(name=>({target:{name}}))})),
        manage:async()=>{},selectModel:async()=>{},toggleAutoMemory:async()=>{},isBusy:()=>false});
      console.log(JSON.stringify(menus[1].options));
    ''')
    for row, status in zip(result[:2], ['applied', 'undone']):
        assert row.count('cl_real_isolated_fact.md') == 1
        assert status in row[:48]
        assert row.index('cl_real_isolated_fact.md') < row.index(status)

# --- Merged from test_tui_review_repairs.py ---

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
    assert result == {'subject': '1 memory applied', 'tone': 'success', 'noop': 'no changes written'}


def test_terminal_pipeline_error_after_recovered_retry_is_reported() -> None:
    result = run_bun('''
      import fs from 'node:fs';
      import {buildLearningReceipt,learningSummarySubject,learningSummaryTone} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const source=fs.readFileSync('./packages/continual-learning/extensions/inject-memory.ts','utf8');
      const body=source.split('}).catch(async (error: unknown) => {')[1].split('}).finally(async () => {')[0];
      const state={cancelled:false,attempts:[{phase:'memory',outcome:'rejected',operations:0},{phase:'memory',outcome:'applied',operations:1},{phase:'agents',outcome:'noop',operations:0}]};
      let receipt;let reported=false;
      const opts={cwd:'/fixture',mode:'manual',reportReceipt:r=>receipt=r};
      const reportTerminal=r=>{if(!reported){reported=true;opts.reportReceipt(r);}};
      const handler=new Function('state','opts','pipelineScreen','learningInput','buildLearningReceipt','writeLearningReceipt','resolveMemoryPaths','notifyPi','ctx','pipelineBatchId','recordLearningDebug','reportTerminal',
        'return async error => {'+body+'}')(state,opts,{memory:true,harness:false,agents:true,reasons:[]},undefined,buildLearningReceipt,async()=>{},()=>({runsDir:'/fixture'}),()=>{},{ui:{}},undefined,()=>{},reportTerminal);
      await handler(new Error('proposal write failed'));
      console.log(JSON.stringify({subject:learningSummarySubject(receipt),tone:learningSummaryTone(receipt)}));
    ''')
    assert result == {'subject': '1 memory applied; agents failed', 'tone': 'error'}

# --- Merged from test_meaningful_renderer_details.py ---

HARNESS = Path(__file__).with_name("meaningful_details_harness.ts")


@pytest.fixture(scope="module")
def rendered() -> dict:
    return run_bun_script(HARNESS, temp_dirs=("PI_CODING_AGENT_DIR",))


@pytest.mark.parametrize(
    ("case", "label"),
    [("policy-blocked", "policy blocked"), ("policy-allowed", "policy allowed"), ("policy-observed", "policy observed")],
)
def test_policy_reason_is_only_in_title_and_explanation_survives(rendered: dict, case: str, label: str) -> None:
    row = rendered[case]
    data = row["data"]
    expanded = row["views"]["240"]["expanded"]
    assert expanded[0] == f"[harness] {label} · {data['reason']}"
    for field in ("policy", "action", "outcome", "tool", "source", "file"):
        assert f"{field} · {data[field]}" in expanded
    assert "\n".join(expanded).count(data["reason"]) == 1
    assert not any(line.startswith("reason ·") for line in expanded)
    collapsed = row["views"]["240"]["collapsed"]
    assert len(collapsed) == 1 and "to expand" in collapsed[0]


@pytest.mark.parametrize("status", ["checked", "observed", "violated", "unsupported", "repair-exhausted"])
def test_check_status_and_detail_stay_in_title_while_evidence_remains(rendered: dict, status: str) -> None:
    row = rendered[f"check-{status}"]
    data = row["data"]
    expanded = row["views"]["240"]["expanded"]
    assert expanded[0] == f"[harness] check {status} · {data['detail']}"
    for field in ("phase", "policy", "path"):
        assert f"{field} · {data[field]}" in expanded
    assert "\n".join(expanded).count(data["detail"]) == 1
    assert not any(line.startswith(("status ·", "detail ·")) for line in expanded)


def test_legacy_guidance_entry_type_still_renders_as_harness_guidance(rendered: dict) -> None:
    current = rendered["skill-rule"]
    legacy = rendered["guidance-legacy-entry"]
    assert legacy["data"] == current["data"]
    assert legacy["views"] == current["views"]
    assert legacy["views"]["240"]["expanded"][0] == "[harness] skill rule · review"


def test_output_check_keeps_phase_and_policy_without_inventing_a_path(rendered: dict) -> None:
    expanded = rendered["check-output"]["views"]["240"]["expanded"]
    assert "phase · output" in expanded and "policy · artifact-evidence" in expanded
    assert not any(line.startswith("path ·") for line in expanded)


@pytest.mark.parametrize(
    ("case", "label", "subject"),
    [
        ("skill-rule", "skill rule", "review"),
        ("skill-prompt", "skill rule", "review"),
        ("text-rule", "text guidance", "project-a-guidance"),
        ("text-incomplete", "text guidance incomplete", "guidance"),
    ],
)
def test_guidance_identity_is_only_in_title_but_prompt_and_provenance_survive(
    rendered: dict, case: str, label: str, subject: str,
) -> None:
    row = rendered[case]
    data = row["data"]
    expanded = row["views"]["240"]["expanded"]
    assert expanded[0] == f"[harness] {label} · {subject}"
    assert f"source · {data['source']}" in expanded
    assert f"file · {data['file']}" in expanded
    assert f"prompt · {data['prompt'].splitlines()[0]}" in expanded
    assert data["prompt"].splitlines()[1] in expanded
    assert not any(line.startswith(("skill ·", "rule ·")) for line in expanded)


@pytest.mark.parametrize(("case", "field"), [("policy-long", "reason"), ("check-long", "detail"), ("guidance-long", "skill")])
def test_narrow_expansion_recovers_subject_without_repeating_a_field(rendered: dict, case: str, field: str) -> None:
    row = rendered[case]
    view = row["views"]["48"]
    assert "to expand" in " ".join(view["collapsed"])
    assert not any(line.startswith(("reason ·", "detail ·", "skill ·")) for line in view["expanded"])
    # Wrapping may split words or preserve a hyphen, so compare non-whitespace text.
    subject = "".join(row["data"][field].split())
    expanded = "".join("".join(view["expanded"]).split())
    assert expanded.count(subject) == 1


@pytest.mark.parametrize("width", [240, 48])
def test_full_guidance_prompt_survives_character_and_detail_line_limits(rendered: dict, width: int) -> None:
    row = rendered["guidance-full-prompt"]
    prompt = row["data"]["prompt"]
    assert len(prompt) > 2000 and len(prompt.splitlines()) > 50
    expanded = "".join("".join(row["views"][str(width)]["expanded"]).split())
    assert "".join(prompt.split()) in expanded
    for field in ("source", "file"):
        assert "".join(f"{field} · {row['data'][field]}".split()) in expanded
