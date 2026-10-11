from support import run_bun


def test_exact_pipeline_batches_preserve_legacy_and_concurrent_identity():
    result = run_bun('''
      import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
      import {withLearningBatch,recordLearningMutation,listLearningHistory} from './packages/continual-learning/extensions/learning-history.ts';
      const root=await fs.mkdtemp(path.join(os.tmpdir(),'cl-batches-'));
      process.env.PI_CODING_AGENT_DIR=path.join(root,'agent');await fs.mkdir(process.env.PI_CODING_AGENT_DIR);
      const cwd=path.join(root,'project');await fs.mkdir(path.join(cwd,'.pi'),{recursive:true});
      const target=path.join(cwd,'.pi/harness.json');
      try {
        await recordLearningMutation(cwd,'harness',[target],async()=>{await fs.writeFile(target,'legacy')});
        await withLearningBatch(async()=>{
          await recordLearningMutation(cwd,'harness',[target],async()=>{await fs.writeFile(target,'one')});
          await Promise.resolve();
          await recordLearningMutation(cwd,'harness',[target],async()=>{await fs.writeFile(target,'two')});
        });
        const records=await listLearningHistory(cwd);
        const ids=await Promise.all([1,2].map(n=>withLearningBatch(async()=>{
          const {currentLearningBatch}=await import('./packages/continual-learning/extensions/learning-history.ts');
          await Promise.resolve();return currentLearningBatch();
        })));
        console.log(JSON.stringify({legacy:records.filter(r=>!r.batchId).length,batches:records.filter(r=>r.batchId).map(r=>r.batchId),ids}));
      } finally {await fs.rm(root,{recursive:true,force:true})}
    ''')
    assert result['legacy'] == 1
    assert len(result['batches']) == 2 and len(set(result['batches'])) == 1
    assert len(set(result['ids'])) == 2


def test_batch_menu_keeps_exact_change_confirmation_and_index_label():
    result = run_bun('''
      import {openMemoryMenu} from './packages/continual-learning/extensions/memory-menu.ts';
      const menus=[];const choices=['Recent learning',undefined,'Close'];let opened=false;
      const records=[{id:'a',batchId:'batch_0123456789abcdef0123456789abcdef',phase:'memory',status:'applied',createdAt:'2026-10-10T01:00:00Z',changes:[{target:{name:'fact.md'}}]},
        {id:'b',batchId:'batch_0123456789abcdef0123456789abcdef',phase:'memory',status:'applied',createdAt:'2026-10-10T01:00:00Z',changes:[{target:{name:'MEMORY.md'},before:null}]}];
      await openMemoryMenu({cwd:'/fixture',hasUI:true,ui:{notify(){},select:async(title,options)=>{menus.push({title,options});if(title.startsWith('Learning batches')){if(opened)return 'Back';opened=true;return options[0]}return choices.shift()}}},{
        status:async()=>({autoMemory:false,model:'fixture/model',entries:1}),loadMemories:async()=>({entries:[]}),listHistory:async()=>records,
        manage:async()=>{throw Error('No batch mutation')},selectModel:async()=>{},toggleAutoMemory:async()=>{},isBusy:()=>false});
      console.log(JSON.stringify(menus));
    ''')
    assert 'Learning batches' in result[1]['title']
    assert 'fact.md' in result[1]['options'][0] and '2 applied' in result[1]['options'][0][:48]
    assert any('Index setup' in option for menu in result for option in menu['options'])
    assert all('Undo batch' not in option for menu in result for option in menu['options'])
