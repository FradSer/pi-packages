import pytest
from support import isolated_run_bun


@pytest.mark.parametrize('case',['manual-initialization','manual-initialization-repair'])
def test_native_command_initialization_creates_memory_then_genuinely_owned_harness(tmp_path,case):
    # Given no entry bodies and automatic learning off, When a real Memory
    # command learns source knowledge, Then a separate automatic policy task
    # may create its own rule without changing the unrelated manual rule.
    from live_automatic_source_refresh import run
    value=run(tmp_path/'initialization',case)
    assert value['manualMaintenance']['initialKnowledgeEntries']==0
    assert value['receipt']['mode']=='manual' and value['receipt']['operations']==1
    proof=value['commandSourceReview']
    assert proof['ready'] and proof['origin']=='explicit-memory-command'
    assert proof['mutationAuthority'] is False and proof['initializationApproved'] is False
    assert all(not control['ready'] for control in value['commandSourceReviewNegatives'].values())
    initialization=value['automaticHarnessInitialization']
    closure=value['sourceBacklogClosure']
    assert closure['before']['pending']==1 and closure['after']['pending']==0
    assert closure['countedAsNewLearning'] is False
    assert value['sourceClosureIntegrity']['ready']
    assert value['sourceClosureIntegrity']['countedAsLearning'] is False
    assert closure['receipt']['operations']==0
    assert value['commandHistoryIntegrity']['passed']
    assert value['commandCorpusProof']['ready']
    assert all(not result['ready'] for result in value['commandCorpusProofNegatives'].values())
    assert initialization['receipt']['mode']=='automatic'
    assert initialization['receipt']['operations']==1
    assert initialization['origin']=='consolidation' and initialization['revisionVerified']
    assert initialization['nativePolicyProof']['ready']
    assert initialization['nativePolicyProof']['mutationAuthority'] is False
    assert initialization['nativePolicyProof']['learningBenefitEstablished'] is False
    assert initialization['historyIntegrity']['passed']
    assert initialization['historyIntegrity']['changedPaths']==['project/.pi/harness.json']
    assert all(not proof['ready'] for proof in initialization['nativePolicyNegatives'].values())
    assert initialization['manualRulePreserved']
    assert initialization['nativeExecution']['pnpmVersion']=='11.21.0'
    assert initialization['decisions']=={'npm --version':'block','npm test':'block','pnpm test':'execute','printf npm test':'execute'}
    assert value['externalRequests']==value['paidRequests']==0
    assert value['semanticOrLearningBenefitEstablished'] is False


def test_installed_workspace_pnpm_runs_offline_with_isolated_home(tmp_path,monkeypatch):
    # Given the real installed pinned CLI and a Corepack cache override, when
    # --version runs with a fresh HOME, no registry or Corepack execution follows.
    import json
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from pathlib import Path
    import shutil
    import subprocess
    import threading
    import live_acceptance_support as support
    from support import REPO
    actual=support.workspace_pnpm(REPO)
    package=Path(actual).parent.parent
    expected=json.loads((REPO/'package.json').read_text())['packageManager'].split('@',1)[1].split('+',1)[0]
    cache=tmp_path/'corepack';(cache/'v1/pnpm').mkdir(parents=True)
    (cache/'v1/pnpm'/expected).symlink_to(package,target_is_directory=True)
    monkeypatch.setenv('COREPACK_HOME',str(cache))
    real_which=shutil.which
    monkeypatch.setattr(support.shutil,'which',lambda name:None if name=='pnpm' else real_which(name))
    assert support.workspace_pnpm(REPO)==actual
    calls=[]
    class Registry(BaseHTTPRequestHandler):
        def log_message(self,*_args):pass
        def do_GET(self):calls.append(self.path);self.send_error(500)
        do_POST=do_GET
        do_HEAD=do_GET
    server=ThreadingHTTPServer(('127.0.0.1',0),Registry)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    home=tmp_path/'home';home.mkdir();project=tmp_path/'project';project.mkdir()
    env=support.isolated_environment(home,tmp_path/'agent')
    env.update(COREPACK_ENABLE_NETWORK='0',NODE_DISABLE_COMPILE_CACHE='1',npm_config_registry=f'http://127.0.0.1:{server.server_port}')
    try:
        result=subprocess.run([real_which('node'),actual,'--version'],cwd=project,env=env,capture_output=True,text=True,timeout=10)
        assert result.returncode==0,result.stderr
        assert result.stdout.strip()==expected and not calls
        assert env['HOME']==str(home) and env['PI_CODING_AGENT_DIR']==str(tmp_path/'agent')
    finally:server.shutdown();server.server_close();thread.join(timeout=5)


def test_missing_installed_workspace_pnpm_refuses_without_corepack(tmp_path,monkeypatch):
    import json
    import live_acceptance_support as support
    (tmp_path/'package.json').write_text(json.dumps({'packageManager':'pnpm@11.21.0'}))
    monkeypatch.setenv('COREPACK_HOME',str(tmp_path/'empty-cache'))
    monkeypatch.setattr(support.shutil,'which',lambda _name:None)
    with pytest.raises(AssertionError,match='no download attempted'):
        support.workspace_pnpm(tmp_path)


def test_native_held_command_initialization_does_not_start_owned_harness(tmp_path):
    from live_automatic_source_refresh import run
    value=run(tmp_path/'held','manual-initialization-held')
    assert value['receipt']['operations']==0
    assert value['manualMaintenance']['initialKnowledgeEntries']==0
    assert value['manualMaintenance']['dependentHarnessStarted'] is False
    assert not value.get('automaticHarnessInitialization')
    assert value['commandSourceReview']['ready'] is False
    assert 'harness-noop' not in value['kinds'] and 'harness-create' not in value['kinds']


def test_command_corpus_requires_native_source_and_complete_owned_state():
    result=isolated_run_bun('''
      import {commandMemoryCorpusProof} from './packages/continual-learning/tests/continuous-command-proof.ts';
      console.log(JSON.stringify(commandMemoryCorpusProof({}, {}, {})));
    ''')
    assert result['ready'] is False
    assert result['mutationAuthority'] is False and result['learningBenefitEstablished'] is False


def test_native_explicit_maintenance_corrects_when_automatic_learning_is_off(tmp_path):
    # Given an ordinary edit with automatic learning off, When the user invokes
    # /memory 整理记忆, Then fresh source and full review precede one mirrored rewrite.
    from live_automatic_source_refresh import run
    result = run(tmp_path / 'manual', 'manual-maintenance')
    maintenance = result['manualMaintenance']
    assert maintenance['command'] == '/memory 整理记忆'
    assert maintenance['automaticLearningEnabled'] is False
    assert maintenance['ordinaryTaskLearningReceipts'] == 0
    assert maintenance['bothRootsMatch'] and maintenance['harnessUnchanged']
    assert result['receipt']['mode'] == 'manual'
    assert result['receipt']['operations'] == 1
    assert result['externalRequests'] == result['paidRequests'] == 0
    assert result['semanticOrLearningBenefitEstablished'] is False


def test_native_explicit_maintenance_keeps_low_confidence_correction_unwritten(tmp_path):
    # Given the same explicit request, When coverage confidence is below 0.8,
    # Then retain the attempt and costs without changing Memory or Harness.
    from live_automatic_source_refresh import run
    result = run(tmp_path / 'manual-held', 'manual-maintenance-held')
    assert result['receipt']['mode'] == 'manual'
    assert result['receipt']['operations'] == 0
    assert result['manualMaintenance']['originalMemoryPreserved']
    assert result['manualMaintenance']['harnessUnchanged']
    assert result['manualMaintenance']['ordinaryTaskLearningReceipts'] == 0
    assert result['externalRequests'] == result['paidRequests'] == 0


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


def test_native_failed_coverage_reaches_backfill_and_requires_fresh_reviews(tmp_path):
    # Given an actual zero-write rejected Pi task, When explicit backfill runs,
    # Then its planner receives the exact omission and fresh source before a
    # separately reviewed correction reaches both Memory roots.
    from live_automatic_source_refresh import run
    result = run(tmp_path / 'coverage-replay', 'coverage-replay')
    replay = result['failedLearningReplay']
    assert result['piVersion'] == '1.3.0'
    assert replay['initialOperations'] == 0
    assert replay['replayReceipt']['operations'] == 1
    assert replay['actualQuestionsDelivered'] and replay['freshSourceCollected']
    assert replay['independentFreshReview'] and replay['bothRootsMatch']
    assert replay['learningBenefitEstablished'] is False
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


def test_native_coverage_only_hold_corrects_the_body_with_full_fresh_review(tmp_path):
    # Controlled loopback judgments through actual Pi, children, parent and SDK.
    # This establishes correction mechanics, not semantic quality or task benefit.
    from live_automatic_source_refresh import run
    result = run(tmp_path / 'coverage-correction', 'coverage-correction')
    assert result['piVersion'] == '1.3.0'
    assert result['coverageCorrection']['repairedBody']
    assert result['coverageCorrection']['initialHoldRetained']
    assert result['receipt']['operations'] == 1
    assert result['externalRequests'] == result['paidRequests'] == 0


def test_native_coverage_and_counter_holds_cannot_resample_unchanged_knowledge(tmp_path):
    # Given simultaneous holds in the actual native pipeline, When only citations
    # change, Then retain both holds and stop before a second coverage draw.
    from live_automatic_source_refresh import run
    result = run(tmp_path / 'coverage-citation-only', 'coverage-citation-only')
    assert result['piVersion'] == '1.3.0'
    assert result['unchangedCoverageHold']['initialHoldRetained']
    assert result['unchangedCoverageHold']['independentCounterHoldRetained']
    assert result['unchangedCoverageHold']['citationOnlyRepairRetained']
    assert not result['unchangedCoverageHold']['secondCoverageDraw']
    assert result['receipt']['operations'] == 0
    assert result['externalRequests'] == result['paidRequests'] == 0


def test_native_rejected_coverage_continues_only_independent_source_correction(tmp_path):
    # Given actual native worker output is contradictory, When independent source
    # review holds the body, Then one correction and fresh gates precede writing.
    from live_automatic_source_refresh import run
    result = run(tmp_path / 'coverage-invalid-correction', 'coverage-invalid-correction')
    assert result['piVersion'] == '1.3.0'
    assert result['coverageCorrection']['proofs'] == 1
    assert result['coverageCorrection']['initialHoldRetained']
    assert result['coverageCorrection']['repairedBody']
    assert result['receipt']['operations'] == 1
    assert result['externalRequests'] == result['paidRequests'] == 0
