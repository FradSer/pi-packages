from support import isolated_run_bun


def test_complete_automatic_source_edits_refresh_before_learning_but_not_readonly_or_truncated_tasks():
    # Given a real task read an old declaration then successfully edited it,
    # When automatic Memory learning starts, Then collect current source first
    # without replacing any original observation or weakening semantic review.
    out = isolated_run_bun(r'''
      import {taskSourceEditPaths} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {memorySourceAuditRequest} from './packages/continual-learning/extensions/memory-maintenance-audit.ts';
      const call=(id,name,path)=>({message:{role:'assistant',content:[{type:'toolCall',id,name,arguments:{path}}]}});
      const result=(id,name,isError=false)=>({message:{role:'toolResult',toolCallId:id,toolName:name,isError}});
      const task={kind:'learning-task-slice',version:1,entries:[call('edit','edit','/work/p/index.d.ts'),result('edit','edit'),
        call('read','read','/work/p/old.ts'),result('read','read'),call('failed','write','/work/p/failed.ts'),result('failed','write',true),
        call('private','write','/work/p/.memory/private.md'),result('private','write'),call('outside','edit','/private/other.ts'),result('outside','edit')]};
      const paths=taskSourceEditPaths(task,'/work/p');
      const input={mode:'automatic',inputSource:{source:'current-session',entryCount:20},sourceEditPaths:paths};
      console.log(JSON.stringify({paths,refresh:memorySourceAuditRequest(input),
        readonly:memorySourceAuditRequest({...input,sourceEditPaths:[]}),
        truncated:memorySourceAuditRequest({...input,inputSource:{...input.inputSource,omittedEntries:1}}),
        replay:memorySourceAuditRequest({...input,inputSource:{source:'backlog-session'}})}));
    ''')
    assert out['paths'] == ['index.d.ts']
    assert out['refresh']['purpose'] == 'settled-task'
    assert out['readonly'] is None and out['truncated'] is None and out['replay'] is None


def test_source_mutation_hints_need_one_matching_successful_parent_tool_result():
    out = isolated_run_bun(r'''
      import {taskSourceEditPaths} from './packages/continual-learning/extensions/incremental-learning.ts';
      const call=(id,name,path)=>({message:{role:'assistant',content:[{type:'toolCall',id,name,arguments:{path}}]}});
      const result=(id,name)=>({message:{role:'toolResult',toolCallId:id,toolName:name,isError:false}});
      const entries=[call('dup','edit','index.js'),call('dup','edit','wrong.js'),result('dup','edit'),
        result('orphan','edit'),call('mismatch','write','a.ts'),result('mismatch','edit'),
        call('twice','write','b.ts'),result('twice','write'),result('twice','write'),
        call('memory','write','.pi/memory/data.md'),result('memory','write'),
        call('ok','write','new.ts'),result('ok','write')];
      console.log(JSON.stringify({paths:taskSourceEditPaths({kind:'learning-task-slice',version:1,entries},'/work/p')}));
    ''')
    assert out['paths'] == ['new.ts']


def test_automatic_source_collection_rejects_stored_memories_before_any_worker():
    out = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import path from 'node:path';import {mock} from 'bun:test';
      const root=await fs.realpath(process.env.PI_CODING_AGENT_DIR),cwd=path.join(root,'project');await fs.mkdir(cwd);
      await fs.writeFile(path.join(cwd,'runtime.ts'),'export const mode="new";');
      const privateFile=path.join(root,'private.md');await fs.writeFile(privateFile,'Untrusted old Memory body must not reach collection');
      const kit=await import('./packages/kit/src/index.ts');let calls=0;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{calls++;throw Error('Forbidden worker');}}));
      const {auditMemoryMaintenanceSources}=await import('./packages/continual-learning/extensions/memory-maintenance-audit.ts');
      const audit=await auditMemoryMaintenanceSources({cwd,purpose:'settled-task',request:'current source',replayPaths:['runtime.ts'],
        memoryFiles:[privateFile],memoryIndex:[{name:'private.md',description:'private old metadata',type:'project',classification:'private'}],outputDir:root});
      console.log(JSON.stringify({outcome:audit.outcome,entries:audit.entries,calls,usage:audit.usage}));
    ''')
    assert out['outcome']=='failed' and out['entries']==[] and out['calls']==0
    assert out['usage']['cost']==0


def test_native_automatic_source_refresh_applies_current_source_without_keyword_gate(tmp_path):
    from live_automatic_source_refresh import run
    assert run(tmp_path / 'applied')['receipt']['operations'] == 1


def test_native_held_memory_stops_later_model_workers(tmp_path):
    from live_automatic_source_refresh import run
    result = run(tmp_path / 'held', 'held-later')
    assert result['piVersion'] == '1.3.0'
    assert result['receipt']['operations'] == 0
    assert 'harness-noop' not in result['kinds']
    assert result['externalRequests'] == result['paidRequests'] == 0


def test_native_automatic_source_refresh_holds_source_race(tmp_path):
    from live_automatic_source_refresh import run
    result = run(tmp_path / 'changed', 'source-changed')
    assert result['receipt']['operations'] == 0


def test_native_automatic_source_refresh_holds_refused_memory_read(tmp_path):
    from live_automatic_source_refresh import run
    result = run(tmp_path / 'refused', 'collector-refused')
    assert result['receipt']['operations'] == 0


def test_native_automatic_source_refresh_reads_deep_original_edit_path(tmp_path):
    from live_automatic_source_refresh import run
    assert run(tmp_path / 'deep', 'deep')['receipt']['operations'] == 1


def test_native_automatic_source_refresh_precedes_legacy_phase_promotion(tmp_path):
    from live_automatic_source_refresh import run
    result = run(tmp_path / 'legacy', 'legacy')
    assert result['receipt']['operations'] == 1
    assert result['kinds'].index('source-read') < result['kinds'].index('selector')


def test_renamed_edit_hints_do_not_poison_other_verified_current_sources():
    out = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import path from 'node:path';import {mock} from 'bun:test';
      const root=await fs.realpath(process.env.PI_CODING_AGENT_DIR),cwd=path.join(root,'project');await fs.mkdir(cwd);
      await fs.writeFile(path.join(cwd,'test-onIdle.js'),'original');await fs.rename(path.join(cwd,'test-onIdle.js'),path.join(cwd,'test-on-idle.js'));
      await fs.writeFile(path.join(cwd,'index.js'),'export const mode="new";');
      await fs.symlink('missing-target',path.join(cwd,'linked.js'));
      const kit=await import('./packages/kit/src/index.ts');let calls=0,scope;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async options=>{
        calls++;scope=JSON.parse(options.prompt.split('\n').at(-1));
        const {readPlannerFileSnapshot}=await import('./packages/continual-learning/extensions/planner-read-scope.ts');
        const {recordMaintenanceRead}=await import('./packages/continual-learning/extensions/memory-maintenance-audit.ts');
        const read=await readPlannerFileSnapshot('index.js',scope.readScope);
        await recordMaintenanceRead(scope.observationsPath,{path:path.join(cwd,'index.js'),offset:1,limit:200,result:read.text,sha256:read.sha256});
        return {exitCode:0,stderr:'',text:'Observed current source.',usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:.01}};
      }}));
      const {auditMemoryMaintenanceSources}=await import('./packages/continual-learning/extensions/memory-maintenance-audit.ts');
      const input={cwd,purpose:'settled-task',request:'current source',memoryFiles:[],outputDir:root};
      const audit=await auditMemoryMaintenanceSources({...input,replayPaths:['index.js','test-onIdle.js','test-on-idle.js']});
      const captured=scope;await audit.assertSourcesUnchanged();
      const before=calls,negatives=[];
      for(const bad of ['test-onIdle.js','linked.js','.env/missing','../outside.ts','.memory/missing.md']){
        const r=await auditMemoryMaintenanceSources({...input,replayPaths:bad==='test-onIdle.js'?[bad]:['index.js',bad]});
        negatives.push({outcome:r.outcome,entries:r.entries});
      }
      await fs.writeFile(path.join(cwd,'index.js'),'changed');let stale=false;try{await audit.assertSourcesUnchanged()}catch{stale=true}
      console.log(JSON.stringify({outcome:audit.outcome,entries:audit.entries,scope:captured,negativeCalls:calls-before,negatives,stale,receipt:JSON.parse(await fs.readFile(path.join(audit.directory,'receipt.json'),'utf8'))}));
    ''')
    assert out['outcome'] == 'observed' and len(out['entries']) == 2
    assert out['scope']['sourceIndex']['unavailableEditPaths'] == ['test-onIdle.js']
    assert out['receipt']['unavailableEditPaths'] == ['test-onIdle.js']
    assert all(not p.endswith('test-onIdle.js') for p in out['scope']['readScope']['files'])
    assert 'test-onIdle.js' not in str(out['entries'])
    assert out['stale'] and out['negativeCalls'] == 0
    assert all(r['outcome'] == 'failed' and r['entries'] == [] for r in out['negatives'])


def test_native_automatic_source_refresh_retains_a_renamed_original_edit(tmp_path):
    from live_automatic_source_refresh import run
    result = run(tmp_path / 'renamed', 'renamed')
    assert result['receipt']['operations'] == 1
    assert result['kinds'].index('main-rename') < result['kinds'].index('source-read')


def test_native_observed_memory_read_triggers_correction_without_selection_judge_or_keywords(tmp_path):
    from live_automatic_source_refresh import run
    result = run(tmp_path / 'read-review', 'read-review')
    assert result['receipt']['operations'] == 1
    assert result['kinds'].index('main-memory-read') < result['kinds'].index('source-read')
    assert result['kinds'].index('source-read') < result['kinds'].index('selector')
    assert 'body' in result['kinds']
