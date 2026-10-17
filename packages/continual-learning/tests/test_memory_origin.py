from support import isolated_run_bun
from pathlib import Path
import pytest
from support import run_bun_script


@pytest.mark.parametrize('mode', ['same', 'mode644', 'body-change', 'rollback', 'late-chmod', 'late-symlink'])
def test_identical_consolidation_preserves_memory_revision_and_origin(mode):
    # Given bound Memory, When rewriting identical bytes, Then preserve its origin.
    # Actual changes count once; foreign changes fail without rollback over them.
    result = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import path from 'node:path';import {mock} from 'bun:test';
      const mode=MODE,original=fs.lstat;let target,armed=false,hits=0,outside;
      mock.module('node:fs/promises',()=>({...fs,default:fs,lstat:async function(file,opts){
        const st=await original.call(fs,file,opts);
        if(armed&&String(file)===target&&opts?.bigint&&++hits===2){
          if(mode==='late-chmod')await fs.chmod(target,0o644);
          else{await fs.unlink(target);await fs.symlink(outside,target)}
        }return st;
      }}));
      const {fixture}=await import('./packages/continual-learning/tests/memory-origin-harness.ts');
      const {createConsolidationRun,releaseConsolidationRun,applyConsolidationPlan}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const f=await fixture('identical-apply',1);target=f.target;
      if(mode==='mode644')await fs.chmod(f.target,0o644);
      const before=await fs.lstat(f.target,{bigint:true});
      const run=await createConsolidationRun({cwd:f.cwd,sessionManager:{getBranch:()=>[{role:'user',content:'Keep the observed contract current.'}]}},f.cwd,false);
      const content=await fs.readFile(f.target,'utf8');outside=path.join(f.cwd,'outside.md');await fs.writeFile(outside,content);
      let applied,error;armed=mode.startsWith('late-');
      try {
        const m=run.manifest;
        applied=await applyConsolidationPlan(run,{runId:m.runId,scopeDigest:m.scopeDigest,artifactHash:m.snapshotDigest,
          inventory:[{name:'contract.md',classification:'private'}],selected:['contract.md'],operations:[{name:'contract.md',kind:'rewrite',classification:'private',content:mode==='body-change'?content.replaceAll('V0','V1'):content}]},
          undefined,mode==='rollback'?async()=>{throw Error('Verifier rejects')}:undefined);
      }catch(e){error=e.message}finally{armed=false;await releaseConsolidationRun(run,{keepArtifacts:true})}
      const after=await fs.lstat(f.target,{bigint:true}),revision=s=>[s.dev,s.ino,s.size,s.mtimeNs,s.ctimeNs].map(String).join(':');
      const origin=await f.load();
      console.log(JSON.stringify({hits,sameRevision:revision(before)===revision(after),applied:applied??null,error:error??null,originStatus:origin.status,
        modeBits:Number(after.mode&0o777n),symlink:after.isSymbolicLink(),outsideUnchanged:(await fs.readFile(outside,'utf8'))===content}));
    '''.replace('MODE', repr(mode)), temp_dirs=('PROBE_DIR',))
    assert result['outsideUnchanged']
    if mode in ('same', 'rollback'):
        assert result['sameRevision'] and result['originStatus'] == 'available', result
        if mode == 'same':
            assert result['applied']['changed'] == [] and result['error'] is None
        else:
            assert result['applied'] is None and result['error'] == 'Verifier rejects'
    elif mode in ('mode644', 'body-change'):
        assert result['applied']['changed'] == ['contract.md'] and result['modeBits'] == 0o600
    else:
        assert result['hits'] >= 2 and result['applied'] is None and result['error']
        assert result['modeBits'] == 0o644 if mode == 'late-chmod' else result['symlink']


def test_parent_memory_history_retains_exact_origin_without_changing_mutation_outcome():
    # Given a parent-validated Memory mutation, When recording its result,
    # Then keep exact origin hashes and file revision, or mark origin unavailable.
    result = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import path from 'node:path';
      import {createConsolidationRun,releaseConsolidationRun,createPreApplyReceipt,createConsolidationReceipt,writeConsolidationReceipt,sha256Digest,hashMemoryRoot} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {recordLearningMutation,listLearningHistory} from './packages/continual-learning/extensions/learning-history.ts';
      const root=process.env.PROBE_DIR,rows=[];
      for(const mode of ['available','missing-post','wrong-created','changed-plan','changed-snapshot','wrong-parent','wrong-digest','symlink-plan','legacy','rejected']){
        const cwd=path.join(root,mode);await fs.mkdir(cwd);
        const ctx={cwd,sessionManager:{getBranch:()=>[{role:'user',content:'Remember the currently observed contract for future maintenance.'}]}};
        const run=await createConsolidationRun(ctx,cwd,false),m=run.manifest;
        const content='---\nname: contract.md\ndescription: Observed contract\ntype: project\n---\nObserved source contract.\n';
        const candidate={name:'contract.md',kind:'project',classification:'private',content,evidence:[{index:0,quote:'Remember the currently observed contract for future maintenance.'}]};
        const plan={kind:'memory-consolidation-plan',version:1,schemaVersion:1,runId:m.runId,scopeKey:m.scopeKey,scopeDigest:m.scopeDigest,artifactHash:m.snapshotDigest,snapshotDigest:m.snapshotDigest,selected:[],operations:[],newMemories:[candidate]};
        const text=JSON.stringify(plan,null,2)+'\n',planDigest=sha256Digest(text);await fs.writeFile(run.paths.planFile,text);
        await writeConsolidationReceipt(run,createPreApplyReceipt({runId:m.runId,scopeDigest:m.scopeDigest,artifactHash:m.snapshotDigest,selected:[],sourceHashes:m.sourceHashes,planDigest}),'pre');
        if(mode==='symlink-plan'){
          const outside=path.join(cwd,'outside.json');await fs.writeFile(outside,text);await fs.unlink(run.paths.planFile);await fs.symlink(outside,run.paths.planFile);
        }
        const target=path.join(m.harnessDir,'contract.md');await fs.mkdir(m.harnessDir,{recursive:true});
        try{
          const result=await recordLearningMutation(cwd,'memory',[target],async()=>{
            await fs.writeFile(target,content);
            if(mode==='changed-plan')await fs.appendFile(run.paths.planFile,' ');
            if(mode==='changed-snapshot')await fs.appendFile(run.paths.snapshotFile,' ');
            if(mode!=='missing-post')await writeConsolidationReceipt(run,createConsolidationReceipt(m,[],{harness:await hashMemoryRoot(m.harnessDir),public:{}},planDigest,['contract.md']));
            if(mode==='wrong-created'){
              const post=JSON.parse(await fs.readFile(run.paths.postReceiptFile,'utf8'));post.created=[];await fs.writeFile(run.paths.postReceiptFile,JSON.stringify(post));
            }
            return {outcome:mode==='rejected'?'rejected':'applied',value:17};
          },plan,mode==='legacy'?undefined:{run,planPath:mode==='wrong-parent'?path.join(cwd,'outside.json'):run.paths.planFile,planDigest:mode==='wrong-digest'?'0'.repeat(64):planDigest});
          const records=await listLearningHistory(cwd),record=records.find(r=>r.changes.some(c=>c.target.name==='contract.md'));
          const st=await fs.lstat(target,{bigint:true});
          rows.push({mode,result,status:record.status,origin:record.origin??null,after:record.changes[0].after.digest,afterRevision:record.changes[0].after.revision,
            actualRevision:[st.dev,st.ino,st.size,st.mtimeNs,st.ctimeNs].map(String).join(':'),
            actualHashes:Object.fromEntries(await Promise.all(['manifest.json','snapshot.json','context-manifest.json','plan.json','pre-receipt.json',...(mode==='missing-post'?[]:['post-receipt.json'])].map(async n=>[n,sha256Digest(await fs.readFile(path.join(run.paths.runDir,n)))])))});
        }finally{await releaseConsolidationRun(run,{keepArtifacts:true})}
      }
      console.log(JSON.stringify(rows));
    ''', temp_dirs=('PROBE_DIR',))
    for row in result:
        assert row['result']['value'] == 17
        assert row['afterRevision'] == row['actualRevision']
        if row['mode'] == 'rejected':
            assert row['status'] == 'pending' and row['origin'] is None
        elif row['mode'] == 'legacy':
            assert row['status'] == 'applied' and row['origin'] is None
        elif row['mode'] == 'available':
            assert row['status'] == 'applied'
            assert row['origin']['status'] == 'available'
            assert row['origin']['artifactHashes'] == row['actualHashes']
            assert row['origin']['targets'] == [{'root': 'private', 'name': 'contract.md', 'digest': row['after'], 'revision': row['actualRevision']}]
        else:
            assert row['status'] == 'applied' and row['result']['outcome'] == 'applied'
            assert row['origin']['status'] == 'unavailable' and 'artifactHashes' not in row['origin']


def test_origin_metadata_does_not_make_legacy_or_malformed_history_trustworthy():
    result = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import path from 'node:path';
      import {recordLearningMutation,listLearningHistory,readLearningHistory} from './packages/continual-learning/extensions/learning-history.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd=process.env.PROBE_DIR,p=resolveMemoryPaths(cwd),file=path.join(p.harnessDir,'a.md');await fs.mkdir(p.harnessDir,{recursive:true});
      await recordLearningMutation(cwd,'memory',[file],()=>fs.writeFile(file,'Original knowledge.'));
      const record=(await listLearningHistory(cwd))[0],history=path.join(p.agentDir,'memory/history',p.scopeKey,record.id+'.json');
      const origin={version:1,status:'available',runId:'run_fixture',artifactHashes:Object.fromEntries(['manifest.json','snapshot.json','context-manifest.json','plan.json','pre-receipt.json','post-receipt.json'].map(n=>[n,'a'.repeat(64)])),
        targets:[{root:'private',name:'a.md',digest:record.changes[0].after.digest,revision:'1:2:3:4:5'}]};
      const invalid=[];
      for(const change of [x=>delete x.origin.artifactHashes['snapshot.json'],x=>x.origin.targets.push(x.origin.targets[0]),x=>x.origin.targets[0].revision='milliseconds-only',
        x=>x.origin.runId='../escape',x=>x.origin.targets[0].name='../escape.md',x=>x.phase='harness',x=>x.origin.extra='authority',
        x=>x.origin={version:1,status:'unavailable',reason:'unverifiable',artifactHashes:{}}]){
        const next={...structuredClone(record),origin:structuredClone(origin)};change(next);await fs.writeFile(history,JSON.stringify(next));
        try{await readLearningHistory(cwd,record.id);invalid.push(false)}catch{invalid.push(true)}
      }
      await fs.writeFile(history,JSON.stringify(record));const legacy=await readLearningHistory(cwd,record.id);
      console.log(JSON.stringify({invalid,legacyUnchanged:JSON.stringify(legacy)===JSON.stringify(record)}));
    ''', temp_dirs=('PROBE_DIR',))
    assert all(result['invalid']) and result['legacyUnchanged']


def test_exact_history_revisions_expose_manual_aba_and_preserve_undo_semantics():
    # Given an observed revision, When a file is changed away and back before
    # another managed write, Then equal bytes do not erase the revision break.
    result = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import path from 'node:path';
      import {recordLearningMutation,listLearningHistory,previewLearningUndo,undoLearningChange,readLearningHistory} from './packages/continual-learning/extensions/learning-history.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      import {writeFileAtomic,sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const cwd=process.env.PROBE_DIR,p=resolveMemoryPaths(cwd),file=path.join(p.harnessDir,'a.md');await fs.mkdir(p.harnessDir,{recursive:true});
      await recordLearningMutation(cwd,'memory',[file],()=>fs.writeFile(file,'Original knowledge.'));
      const first=(await listLearningHistory(cwd))[0];
      await fs.writeFile(file,'Manual change.');await writeFileAtomic(file,'Original knowledge.',0o644);
      await recordLearningMutation(cwd,'memory',[file],()=>fs.writeFile(file,'Next knowledge.'));
      const second=(await listLearningHistory(cwd)).find(r=>r.changes[0].after.digest===sha256Digest('Next knowledge.'));
      const before=second.changes[0].before,previous=first.changes[0].after;
      const preview=await previewLearningUndo(cwd,second.id);await undoLearningChange(cwd,second.id,preview.digest);
      console.log(JSON.stringify({equalBytes:before.digest===previous.digest,revisionBreak:before.revision!==previous.revision,
        revisions:[before.revision,previous.revision],restored:await fs.readFile(file,'utf8'),status:(await readLearningHistory(cwd,second.id)).status}));
    ''', temp_dirs=('PROBE_DIR',))
    assert result['equalBytes'] and result['revisionBreak'] and all(result['revisions'])
    assert result['restored'] == 'Original knowledge.' and result['status'] == 'undone'


@pytest.mark.parametrize('mode', ['creation', 'chain', 'beyond-display', 'safe-git', 'safe-no-git', 'unrelated-undone', 'new-incarnation'])
def test_origin_loader_returns_complete_unbroken_current_incarnation(mode):
    value = run_bun_script(Path(__file__).with_name('memory-origin-harness.ts'), mode, temp_dirs=('PROBE_DIR',))
    result = value['result']
    assert result['status'] == 'available', result
    transactions = result['context']['transactions']
    assert len(transactions) == (1 if mode in ('creation', 'new-incarnation') else 3)
    assert transactions[0]['snapshot'] == value['expectedSnapshot']
    assert transactions[0]['kind'] == 'create' and all(t['kind'] == 'rewrite' for t in transactions[1:])
    assert value['currentUnchanged'] and value['paidRequests'] == 0


@pytest.mark.parametrize('mode', ['legacy', 'manual-current', 'manual-chain', 'undone', 'pending', 'duplicate', 'case-alias', 'artifact', 'foreign', 'wrong-created', 'bound-records', 'bound-entries', 'bound-bytes', 'bound-depth', 'bound-artifactBytes'])
def test_origin_loader_refuses_incomplete_ambiguous_or_changed_context(mode):
    value = run_bun_script(Path(__file__).with_name('memory-origin-harness.ts'), mode, temp_dirs=('PROBE_DIR',))
    assert value['result']['status'] == 'unavailable', value['result']
    assert 'context' not in value['result']
    assert value['currentUnchanged'] and value['paidRequests'] == 0


@pytest.mark.parametrize('mode', ['race-record', 'race-inventory', 'context-edit'])
def test_origin_loader_cannot_reuse_context_after_state_or_context_changes(mode):
    value = run_bun_script(Path(__file__).with_name('memory-origin-harness.ts'), mode, temp_dirs=('PROBE_DIR',))
    assert value['result']['status'] == 'available'
    assert value['contextEditRejected'] if mode == 'context-edit' else value['changedRejected']


@pytest.mark.parametrize('callback', [False, True])
def test_origin_loader_checks_cancellation_after_final_file_observation(callback):
    result = isolated_run_bun(r'''
      import fs from 'node:fs/promises';
      import {fixture} from './packages/continual-learning/tests/memory-origin-harness.ts';
      const f=await fixture('late-abort',1),controller=new AbortController();
      const original=fs.lstat;let hits=0;
      fs.lstat=async function(file,opts){
        const result=await original.call(this,file,opts);
        if(String(file)===f.target&&opts?.bigint&&++hits===LIMIT)controller.abort();
        return result;
      };
      const result=await f.load({signal:controller.signal});let rejected=false;
      if(CALLBACK&&result.status==='available')try{await result.assertUnchanged()}catch{rejected=true}
      console.log(JSON.stringify({status:result.status,reason:result.reason,hasContext:!!result.context,aborted:controller.signal.aborted,hits,rejected}));
    '''.replace('LIMIT', '6' if callback else '4').replace('CALLBACK', str(callback).lower()), temp_dirs=('PROBE_DIR',))
    assert result['aborted'], result
    if callback:
        assert result['status'] == 'available' and result['rejected']
    else:
        assert result['status'] == 'unavailable' and result['reason'] == 'cancelled' and not result['hasContext']


def test_origin_loader_rechecks_context_after_final_file_observation():
    result = isolated_run_bun(r'''
      import fs from 'node:fs/promises';
      import {fixture} from './packages/continual-learning/tests/memory-origin-harness.ts';
      const f=await fixture('late-context-change',1),loaded=await f.load();
      if(loaded.status!=='available')throw Error('Missing fixture origin');
      const original=fs.lstat;let hits=0,rejected=false;
      fs.lstat=async function(file,opts){
        const stat=await original.call(this,file,opts);
        if(String(file)===f.target&&opts?.bigint&&++hits===2)loaded.context.transactions[0].snapshot.extra='Concurrent edit';
        return stat;
      };
      try{await loaded.assertUnchanged()}catch{rejected=true}finally{fs.lstat=original}
      console.log(JSON.stringify({hits,rejected,changed:loaded.context.transactions[0].snapshot.extra==='Concurrent edit'}));
    ''', temp_dirs=('PROBE_DIR',))
    assert result['changed']
    assert result['rejected']


@pytest.mark.parametrize('mode', ['allowed', 'denied', 'sensitive', 'changed', 'legacy'])
def test_origin_context_is_bound_and_screened_before_model_use(mode):
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';
      import {fixture} from './packages/continual-learning/tests/memory-origin-harness.ts';
      import {loadMemoryOriginReviewContext} from './packages/continual-learning/extensions/inject-memory.ts';
      const mode='__MODE__',f=await fixture('review-origin',1,'private',false,mode==='legacy',mode==='sensitive'?{purpose:JSON.stringify({password:'historical-sensitive-value'})}:{});
      const existing=[{name:'contract.md',content:await fs.readFile(f.target,'utf8'),classification:'private',type:'project',description:'Source'}];
      const evidence={entries:[{role:'user',content:'Correct the currently observed contract.'}]};
      const loaded=await loadMemoryOriginReviewContext({cwd:f.cwd,evidence,existing,authorized:mode!=='denied'});
      let rejected=false;if(mode==='changed'&&loaded.bound){await fs.writeFile(f.target,'Manual edit');try{await loaded.bound.assertUnchanged()}catch{rejected=true}}
      console.log(JSON.stringify({bound:!!loaded.bound,origins:loaded.bound?.origins,diagnostics:loaded.diagnostics,rejected,paidRequests:0}));
    '''.replace('__MODE__', mode), temp_dirs=('PROBE_DIR',))
    if mode in ('allowed', 'changed'):
        assert value['bound'] and value['origins'][0]['transactions'][0]['snapshot']['entries']
    else:
        assert not value['bound']
    if mode == 'sensitive':
        assert value['diagnostics'][0]['reason'] == 'sensitive'
    if mode == 'changed':
        assert value['rejected']
    assert value['paidRequests'] == 0


def test_jev_uses_separate_complete_historical_context_without_relaxing_gates():
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import {createHash} from 'node:crypto';
      import {fixture} from './packages/continual-learning/tests/memory-origin-harness.ts';
      import {loadMemoryOriginReviewContext} from './packages/continual-learning/extensions/inject-memory.ts';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const f=await fixture('jev-origin',1),old=await fs.readFile(f.target,'utf8');
      const existing=[{name:'contract.md',content:old,classification:'private',type:'project',description:'Source V0.'}];
      const evidence={contextEnabled:true,entries:[{role:'user',content:'Correct the currently observed contract.'},{role:'toolResult',toolName:'read',toolCallId:'source',isError:false,content:[{type:'text',text:'Source V1.'}]}]};
      const candidates=[{name:'contract.md',kind:'rewrite',classification:'private',content:old.replaceAll('V0','V1'),evidence:[{index:1,quote:'Source V1.',role:'toolResult'}]},
        {name:'new-contract.md',kind:'project',classification:'private',content:'Source V1.',evidence:[{index:1,quote:'Source V1.',role:'toolResult'}]}];
      const loaded=await loadMemoryOriginReviewContext({cwd:f.cwd,evidence,existing,authorized:true}),rows=[];
      for(const mode of ['allowed','denied','uncertain','changed','secret']){
        const bound={...loaded.bound,origins:structuredClone(loaded.bound.origins)};let calls=0,states=[],questions=[],sourceStates=[],historicalEvidenceBindings=[],missingHistoryReferences=0;
        if(mode==='secret'){bound.origins[0].transactions[0].snapshot.hidden={password:'historical-sensitive-value'};bound.originsDigest=createHash('sha256').update(JSON.stringify(bound.origins)).digest('hex')}
        const judge=createJevJudge({enabled:true,scopes:['memory'],apiKey:'fixture',allowPrivateMemory:mode!=='denied',requestConcurrency:1,fetch:async(_u,init)=>{
          calls++;const r=JSON.parse(init.body);states.push(typeof r.state==='string'?JSON.parse(r.state):r.state);questions.push(...Object.values(r.questions));
          const state=states.at(-1);
          missingHistoryReferences+=Object.values(r.questions).filter(q=>q.instructions.question.includes('historicalMemoryOrigins')&&!state.historicalMemoryOrigins).length;
          if(state.historicalMemoryOrigins&&state.reviewEvidence)historicalEvidenceBindings.push(...Object.values(r.questions).map(q=>({
            hasSupport:!!state.supportEvidence,hasReview:!!state.reviewEvidence,
            referencesSupport:q.instructions.question.includes('complete supportEvidence and reviewEvidence'),
            referencesMissingFrozen:!state.frozenEvidence&&q.instructions.question.includes('frozenEvidence'),
          })));
          if(Object.keys(r.questions).some(key=>/^supported(?:_description)?_0$/.test(key)))sourceStates.push(states.at(-1));
          if(mode==='changed')bound.origins[0].transactions[0].snapshot.changed=true;
          return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{
            const labels=Object.keys(q.criteria),choice=['compatible','grounded','consistent','independent','unrelated'].find(x=>labels.includes(x))??labels[0],weak=mode==='uncertain'&&key.startsWith('counter_');
            return [key,{type:'choice',choice,confidence:weak?.79:1,probabilities:Object.fromEntries(labels.map(k=>[k,k===choice?(weak?.89:1):(weak?.11/(labels.length-1):0)]))}];
          }))}));
        }});
        const result=await judge.validate('memory',evidence,candidates,existing,undefined,undefined,undefined,undefined,bound);
        rows.push({mode,calls,decision:result.decision,complete:!!result.candidateReview?.complete,partial:!!result.incompleteReview,reason:result.telemetry.reason,usage:result.telemetry.inputTokens??result.telemetry.knownInputTokens,
          originsDigest:result.candidateReview?.originsDigest,expectedDigest:loaded.bound.originsDigest,
          historical:states.filter(s=>s.reviewEvidence&&s.proposedMemoryOperations?.some(op=>op.name==='contract.md')).every(s=>JSON.stringify(s.historicalMemoryOrigins?.[0])===JSON.stringify(loaded.bound.origins[0])),
          sourceIsolated:sourceStates.length>0&&sourceStates.every(s=>!s.historicalMemoryOrigins&&!s.existingMemories&&!s.mutationComparison&&s.proposedMemoryOperations?.[0]?.content===candidates[0].content),
          originalIndexes:states.flatMap(s=>s.reviewEvidence?.entries.map(e=>e.index)??[]),historicalEvidenceBindings,missingHistoryReferences,
          instruction:questions.some(q=>q.instructions.question.includes('historicalMemoryOrigins')&&q.instructions.question.includes('current permission'))});
      }
      console.log(JSON.stringify(rows));
    ''', temp_dirs=('PROBE_DIR',))
    allowed, denied, uncertain, changed, secret = value
    assert allowed['decision'] == 'allow' and allowed['complete'] and allowed['historical'] and allowed['instruction'], value
    assert allowed['sourceIsolated'] and uncertain['sourceIsolated']
    # Given historical context beside a normal counter window, When its
    # instructions name current evidence, Then both fields must exist on wire.
    assert allowed['historicalEvidenceBindings']
    assert all(q['hasSupport'] and q['hasReview'] and q['referencesSupport'] and not q['referencesMissingFrozen']
               for q in allowed['historicalEvidenceBindings'])
    assert allowed['missingHistoryReferences'] == uncertain['missingHistoryReferences'] == 0
    assert allowed['originsDigest'] == allowed['expectedDigest']
    assert set(allowed['originalIndexes']) == {0, 1}
    assert denied['calls'] == secret['calls'] == 0
    assert denied['decision'] == secret['decision'] == uncertain['decision'] == changed['decision'] == 'propose'
    assert not changed['complete'] and not changed['partial'] and changed['usage'] > 0


@pytest.mark.parametrize('mode', ['owned', 'foreign', 'changed-pending', 'changed-artifact'])
def test_origin_guards_admit_only_the_exact_parent_pending_transaction(mode):
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';
      import {fixture} from './packages/continual-learning/tests/memory-origin-harness.ts';
      import {readMemoryOriginContext,recordLearningMutation} from './packages/continual-learning/extensions/learning-history.ts';
      const mode='__MODE__',f=await fixture('origin-pending',1),loaded=await f.load();
      if(loaded.status!=='available')throw Error('Missing origin');
      let pendingSeen=false,applied=false,rejected=false;
      try{await recordLearningMutation(f.cwd,'memory',[f.target],async pending=>{
        pendingSeen=!!pending?.id&&!!pending?.digest;
        if(mode==='foreign')await fs.writeFile(f.records[0].file.replace(f.records[0].id,pending.id+'_extra'),await fs.readFile(f.records[0].file));
        if(mode==='changed-pending')await fs.appendFile(f.records[0].file.replace(f.records[0].id,pending.id),' ');
        await loaded.assertUnchanged(pending);
        await fs.writeFile(f.target,'Authorized new body.');
        if(mode==='changed-artifact')await fs.appendFile(f.records[0].runDir+'/snapshot.json',' ');
        await loaded.assertArtifactsUnchanged(pending);applied=true;
        return {outcome:'applied'};
      })}catch{rejected=true}
      console.log(JSON.stringify({pendingSeen,applied,rejected}));
    '''.replace('__MODE__', mode), temp_dirs=('PROBE_DIR',))
    assert value['pendingSeen']
    assert value['applied'] if mode == 'owned' else value['rejected'] and not value['applied']


@pytest.mark.parametrize('mode', ['allowed', 'secret', 'changed'])
def test_semantic_repair_receives_private_history_and_preserves_failure_usage(mode):
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import {mock} from 'bun:test';import {createHash} from 'node:crypto';
      const kit=await import('./packages/kit/src/index.ts');let calls=0,payload,tools,bound;
      const mode='__MODE__';
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        calls++;tools=input.tools;payload=JSON.parse(input.prompt.split('\n').at(-1));
        if(mode==='changed')bound.origins[0].transactions[0].snapshot.changed=true;
        const c=payload.repairCandidates[0];
        return {exitCode:0,stderr:'',cancelled:false,text:JSON.stringify({kind:'incremental-memory-amendment',version:1,...payload.identity,replacements:[{candidateId:c.candidateId,content:payload.rejectedPlan.operations[0].content.replaceAll('V1','V2'),evidence:[{ref:'e0.b0.l1'}]}]}),usage:{input:7,output:3,cacheRead:0,cacheWrite:0,totalTokens:10,cost:0}};
      }}));
      const {fixture}=await import('./packages/continual-learning/tests/memory-origin-harness.ts');
      const {loadMemoryOriginReviewContext,repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const f=await fixture('repair-origin',1),old=await fs.readFile(f.target,'utf8');
      const existing=[{name:'contract.md',content:old,classification:'private',type:'project',description:'Source V0.'}];
      const evidence={contextEnabled:true,entries:[{role:'toolResult',toolName:'read',toolCallId:'source',isError:false,content:[{type:'text',text:'Source V2.'}]}]};
      bound=(await loadMemoryOriginReviewContext({cwd:f.cwd,evidence,existing,authorized:true})).bound;
      if(mode==='secret'){bound.origins[0].transactions[0].snapshot.hidden={password:'historical-sensitive-value'};bound.originsDigest=createHash('sha256').update(JSON.stringify(bound.origins)).digest('hex')}
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'h',snapshotDigest:'h'};
      const original={kind:'incremental-memory-plan',version:1,...identity,operations:[{name:'contract.md',kind:'rewrite',classification:'private',content:old.replaceAll('V0','V1'),evidence:[{index:0,quote:'Source V2.'}]}],newMemories:[]};
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,selectedNames:['contract.md'],repairableNames:['contract.md'],repairableFields:{'contract.md':['body']},errors:['held'],memoryOrigins:bound,semanticContext:{frozenEvidence:evidence,existingMemories:existing}});
      console.log(JSON.stringify({calls,tools:tools?.length,hasHistory:!!payload?.historicalMemoryOrigins,historyComplete:payload?.historicalMemoryOrigins?.[0].transactions[0].snapshot.entries.length===3,currentIndexes:payload?.semanticContext.frozenEvidence.entries.length,result}));
    '''.replace('__MODE__', mode), temp_dirs=('PROBE_DIR',))
    if mode == 'allowed':
        assert value['calls'] == 1 and value['tools'] == 0 and value['hasHistory'] and value['historyComplete'] and value['currentIndexes'] == 1
        assert value['result']['outcome'] == 'repaired', value
    elif mode == 'secret':
        assert value['calls'] == 0 and value['result']['outcome'] == 'failed'
    else:
        assert value['calls'] == 1 and value['result']['outcome'] == 'failed' and 'plan' not in value['result']
        assert value['result']['usage']['input'] == 7
