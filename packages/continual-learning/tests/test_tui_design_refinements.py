from support import run_bun


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
        status:async()=>({autoMemory:false,model:'fixture/model',entries:0}),loadMemories:async()=>({entries:[]}),
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
        status:async()=>({autoMemory:false,model:'fixture/model',entries:0}),loadMemories:async()=>({entries:[]}),
        listHistory:async()=>['applied','undone'].map(status=>({id:status,createdAt:'2026-10-09T20:30:00Z',phase:'memory',status,changes:
          ['MEMORY.md','cl_real_isolated_fact.md','MEMORY.md','cl_real_isolated_fact.md'].map(name=>({target:{name}}))})),
        manage:async()=>{},selectModel:async()=>{},toggleAutoMemory:async()=>{},isBusy:()=>false});
      console.log(JSON.stringify(menus[1].options));
    ''')
    for row, status in zip(result[:2], ['applied', 'undone']):
        assert row.count('cl_real_isolated_fact.md') == 1
        assert status in row[:48]
        assert row.index('cl_real_isolated_fact.md') < row.index(status)
