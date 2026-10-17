import pytest
from support import isolated_run_bun


def test_semantic_noop_normalizes_citation_order_and_inferred_roles():
    # Given a held proposal, When a patch only reorders the same valid sources,
    # Then retain failure and usage; real body or source changes remain reviewable.
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const kit=await import('./packages/kit/src/index.ts');let mode;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        const data=JSON.parse(input.prompt.split('\n').at(-1)),candidate=data.repairCandidates[0],prior=data.rejectedPlan.newMemories[0];
        const source=mode==='new-source'?[...prior.evidence,{index:2,quote:'Source C.'}]
          :mode==='reordered-roles'?[...prior.evidence].reverse().map(e=>({...e,role:'user'})):prior.evidence;
        return {exitCode:0,stderr:'',cancelled:false,usage:{input:3,output:2,cacheRead:0,cacheWrite:0,totalTokens:5,cost:0.1},
          text:JSON.stringify({kind:'incremental-memory-amendment',version:1,...data.identity,replacements:[{
            candidateRef:candidate.candidateRef,content:mode==='description'?prior.content.replace('description: Source A.','description: Source B.'):prior.content+(mode==='body'?'\nSource B.':''),evidence:source}]})};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const snapshot={contextEnabled:true,runId:'r',scopeKey:'s',scopeDigest:'d',entries:['Source A.','Source B.','Source C.'].map(content=>({role:'user',content}))};
      const h=sha256Digest(JSON.stringify(snapshot,null,2)+'\n'),identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:h,snapshotDigest:h};
      const candidate={name:'a.md',kind:'project',classification:'private',content:'---\nname: a.md\ndescription: Source A.\ntype: project\n---\nSource A.',
        evidence:[{index:0,quote:'Source A.'},{index:1,quote:'Source B.'}]};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[candidate]},before=JSON.stringify(original),rows=[];
      for(mode of ['same','reordered-roles','body','description','new-source']){
        const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,selectedNames:[],repairableNames:['a.md'],repairableFields:{'a.md':['body','description']},errors:['held'],
          semanticContext:{frozenEvidence:snapshot,existingMemories:[]}});
        rows.push({mode,outcome:result.outcome,failureKind:result.failureKind,usage:result.usage,plan:!!result.plan});
      }
      console.log(JSON.stringify({rows,unchanged:before===JSON.stringify(original)}));
    ''')
    assert result['unchanged']
    for row in result['rows']:
        if row['mode'] in ('same', 'reordered-roles'):
            assert row['outcome'] == 'failed' and row['failureKind'] == 'no-correction' and not row['plan'], row
        else:
            assert row['outcome'] == 'repaired' and row['plan'], row
        assert row['usage']['cost'] == 0.1 and row['usage']['totalTokens'] == 5


@pytest.mark.parametrize('native', [False, True])
def test_real_candidate_copy_failure_uses_exact_parent_bound_refs(tmp_path, native):
    import json
    # Given V52's malformed full ID, When a fresh worker explicitly selects a
    # short parent-bound reference, Then bind exact originals without repairing
    # the historical response or granting semantic approval.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import {mock} from 'bun:test';import {spawnSync} from 'node:child_process';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-candidate-copy.json','utf8'));
      const original=f.files['semantic-rejected-plan.json'].value,raw=f.files['repair-response.json'].value.output;
      const snapshot=f.files['snapshot.json'].value,kit=await import('./packages/kit/src/index.ts');let prompt,mode='original',calls=0;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        calls++;prompt=input.prompt;
        if(mode==='original')return {exitCode:0,stderr:'',text:raw,cancelled:false};
        const data=JSON.parse(prompt.split('\n').at(-1)),reply=JSON.parse(raw);
        reply.replacements=reply.replacements.map((patch,i)=>{const {candidateId,...rest}=patch;return {...rest,candidateRef:data.repairCandidates[i].candidateRef}});
        if(NATIVE){
          const root=ROOT,cli=path.resolve('node_modules/@earendil-works/pi-coding-agent/dist/cli.js');
          const version=spawnSync('node',[cli,'--version'],{encoding:'utf8'});if(version.status!==0||version.stdout.trim()!=='1.2.0')throw Error('Pi1.2 required');
          const native=spawnSync('node',[cli,'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-tools','-e',path.resolve('packages/continual-learning/tests/memory-amendment-live-fixture.ts'),
            '--provider','amendment-fixture','--model','fixed','--thinking','off','--no-session','--print','--mode','json','--bound-candidate-response',JSON.stringify(reply),input.prompt],{cwd:root,env:{PATH:process.env.PATH,HOME:root,PI_CODING_AGENT_DIR:path.join(root,'agent'),PI_OFFLINE:'1'},encoding:'utf8',timeout:40000,maxBuffer:32*1024*1024});
          fs.writeFileSync(path.join(root,'native-prompt.txt'),input.prompt);fs.writeFileSync(path.join(root,'native-pi-output.jsonl'),native.stdout);fs.writeFileSync(path.join(root,'native-version.txt'),version.stdout);
          if(native.status!==0)throw Error(native.stderr+'\n'+native.stdout.slice(-4000));
          return {...kit.parsePiWorkerOutput(native.stdout),exitCode:0,stderr:'',cancelled:false};
        }
        return {exitCode:0,stderr:'',text:JSON.stringify(reply),cancelled:false};
      }}));
      const {repairIncrementalMemoryPlan,semanticMemoryRepairCandidates}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {containsSensitiveMemoryMaterial}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,original[k]]));
      const names=original.newMemories.map(x=>x.name),retained=f.existing[0].name,before=JSON.stringify(f);
      const input={identity,rejectedPlan:original,selectedNames:[retained],errors:['held'],repairableNames:names,
        repairableFields:Object.fromEntries(names.map(n=>[n,['body','description']])),retainedRepairNames:[retained],
        semanticContext:{frozenEvidence:snapshot,existingMemories:f.existing}};
      const historical=await repairIncrementalMemoryPlan(input);mode='reference';const referenced=await repairIncrementalMemoryPlan(input);
      const candidates=semanticMemoryRepairCandidates(original),failed=JSON.parse(raw);
      console.log(JSON.stringify({historical,referenced,unchanged:before===JSON.stringify(f),sensitive:containsSensitiveMemoryMaterial(JSON.stringify(f)),
        validMarkdown:failed.replacements.every(x=>x.content.startsWith('---\n')),hashLengths:failed.replacements.map(x=>x.candidateId.split(':').at(-1).length),
        fullHashes:candidates.map(x=>x.candidateId.split(':').at(-1).length),refs:JSON.parse(prompt.split('\n').at(-1)).repairCandidates.map(x=>x.candidateRef),calls,
        memoryWritten:fs.existsSync(path.join(ROOT,'.memory'))}));
    '''.replace('ROOT', json.dumps(str(tmp_path))).replace('NATIVE',str(native).lower()))
    assert result['unchanged'] and not result['sensitive'] and result['validMarkdown']
    assert result['hashLengths'] == [64, 61] and result['fullHashes'] == [64, 64]
    assert result['historical']['failureKind'] == 'intent' and 'plan' not in result['historical']
    assert result['referenced']['outcome'] == 'repaired', result['referenced']
    assert result['refs'] == ['newMemories:0', 'newMemories:1']
    assert len(result['referenced']['plan']['newMemories']) == 2
    assert len(result['referenced']['plan']['operations']) == 1
    assert result['calls'] == 2 and not result['memoryWritten']


def test_candidate_refs_preserve_complete_parent_identity_and_stale_input_guards():
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {bindSemanticMemoryAmendment,bindMemoryCitationAmendment,semanticMemoryRepairCandidates} from './packages/continual-learning/extensions/inject-memory.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-candidate-copy.json','utf8'));
      const original=f.files['semantic-rejected-plan.json'].value,snapshot=f.files['snapshot.json'].value,raw=JSON.parse(f.files['repair-response.json'].value.output);
      const candidates=semanticMemoryRepairCandidates(original),names=candidates.map(x=>x.name);
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,original[k]]));
      const {operations,...response}=raw;
      const amendment={...response,replacements:response.replacements.map(({candidateId,...patch},i)=>({...patch,candidateRef:`newMemories:${i}`}))};
      const sources={frozenEvidence:snapshot,repairableFields:Object.fromEntries(names.map(n=>[n,['body','description']])),
        candidateBinding:{proposalDigest:sha256Digest(JSON.stringify(original)),references:candidates.map(c=>({ref:`${c.field}:${c.index}`,candidateId:c.candidateId}))}};
      const bind=(o,a,s=sources)=>bindSemanticMemoryAmendment(o,a,identity,names,s),rejects=(o,a,s=sources)=>{try{bind(o,a,s);return false}catch{return true}};
      const good=bind(original,amendment),invalid={};
      for(const key of Object.keys(identity))invalid['identity-'+key]=rejects(original,{...amendment,[key]:'foreign'});
      invalid.missingIdentity=rejects(original,{...amendment,runId:undefined});invalid.version=rejects(original,{...amendment,version:2});
      invalid.noBinding=rejects(original,amendment,{...sources,candidateBinding:undefined});
      invalid.foreignDigest=rejects(original,amendment,{...sources,candidateBinding:{...sources.candidateBinding,proposalDigest:'foreign'}});
      invalid.changedMap=rejects(original,amendment,{...sources,candidateBinding:{...sources.candidateBinding,references:[...sources.candidateBinding.references].reverse()}});
      invalid.changedSnapshot=rejects(original,amendment,{...sources,frozenEvidence:{...snapshot,entries:snapshot.entries.slice(1)}});
      for(const [label,change] of Object.entries({body:x=>x.newMemories[0].content+=' changed',privacy:x=>x.newMemories[0].classification='private',
        source:x=>x.newMemories[0].evidence=[],order:x=>x.newMemories.reverse()})){
        const changed=structuredClone(original);change(changed);invalid[label]=rejects(changed,amendment);
      }
      const first=amendment.replacements[0];
      for(const [label,patches] of Object.entries({unknownRef:[{...first,candidateRef:'newMemories:99'}],mixedSelector:[{...first,candidateId:candidates[0].candidateId}],
        missingSelector:[{content:first.content,evidence:first.evidence}],foreignProperty:[{...first,classification:'private'}],
        duplicateRef:[first,first],duplicateAliasAndId:[first,{candidateId:candidates[0].candidateId,content:first.content,evidence:first.evidence}]})){
        invalid[label]=rejects(original,{...amendment,replacements:patches});
      }
      invalid.originalMalformedId=rejects(original,response);
      try{bindMemoryCitationAmendment(original,amendment,identity);invalid.citationOnly=false}catch{invalid.citationOnly=true}
      console.log(JSON.stringify({invalid,good:good.newMemories.map(x=>x.name),original:original.newMemories.map(x=>x.name),unchangedContent:good.newMemories.every((x,i)=>x.content===raw.replacements[i].content)}));
    ''')
    assert all(result['invalid'].values()), result['invalid']
    assert result['good'] == result['original'] and result['unchangedContent']


def test_candidate_binding_is_captured_before_the_worker_and_cannot_drift():
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import {mock} from 'bun:test';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-candidate-copy.json','utf8'));
      const original=f.files['semantic-rejected-plan.json'].value,snapshot=f.files['snapshot.json'].value,kit=await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        const data=JSON.parse(input.prompt.split('\n').at(-1)),reply=JSON.parse(f.files['repair-response.json'].value.output);
        reply.replacements=reply.replacements.map(({candidateId,...patch},i)=>({...patch,candidateRef:data.repairCandidates[i].candidateRef}));
        original.newMemories[0].content+=' changed while worker ran';
        return {exitCode:0,stderr:'',text:JSON.stringify(reply),cancelled:false};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,original[k]]));
      const names=original.newMemories.map(x=>x.name),retained=f.existing[0].name;
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,selectedNames:[retained],errors:['held'],repairableNames:names,
        repairableFields:Object.fromEntries(names.map(n=>[n,['body','description']])),retainedRepairNames:[retained],semanticContext:{frozenEvidence:snapshot,existingMemories:f.existing}});
      console.log(JSON.stringify(result));
    ''')
    assert result['outcome'] == 'failed' and result['failureKind'] == 'intent' and 'plan' not in result


@pytest.mark.parametrize('native', [False, True])
def test_real_stale_repair_can_select_exact_parent_audited_source_without_regeneration(tmp_path, native) -> None:
    import json
    # Given V50's full retained evidence, When a controlled worker explicitly
    # selects its newer declaration, Then copy observed bytes, preserve metadata,
    # and keep the historical failed response and all semantic gates separate.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import {mock} from 'bun:test';import {spawnSync} from 'node:child_process';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const root=ROOT,fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-source-order.json','utf8'));
      fs.writeFileSync(path.join(root,'index.d.ts'),fixture.sourceFiles['index.d.ts']);
      const rebase=v=>typeof v==='string'?v.replaceAll('/work/p-limit',root):Array.isArray(v)?v.map(rebase):v&&typeof v==='object'?Object.fromEntries(Object.entries(v).map(([k,x])=>[k,rebase(x)])):v;
      const snapshot=rebase(fixture.snapshot),original=rebase(fixture.original),existing=rebase(fixture.existing);
      const snapshotDigest=sha256Digest(JSON.stringify(snapshot,null,2)+'\n');original.snapshotDigest=snapshotDigest;original.artifactHash=snapshotDigest;
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,original[k]]));
      const sources={evidenceDigest:sha256Digest(JSON.stringify(snapshot)),entryDigests:fixture.sourceEntryIndexes.map(i=>sha256Digest(JSON.stringify(snapshot.entries[i])))};
      const run={manifest:{cwd:root,...identity}},kit=await import('./packages/kit/src/index.ts');let prompt,mode='valid',calls=0;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        calls++;prompt=input.prompt;const context=JSON.parse(prompt.split('\n').at(-1)),candidate=context.repairCandidates[0];
        if(NATIVE && calls<=2){
          const cli=path.resolve('node_modules/@earendil-works/pi-coding-agent/dist/cli.js');
          const version=spawnSync('node',[cli,'--version'],{encoding:'utf8'});if(version.status!==0||version.stdout.trim()!=='1.2.0')throw Error('Pi1.2 required');
          const env={PATH:process.env.PATH,HOME:root,PI_CODING_AGENT_DIR:path.join(root,'agent'),PI_OFFLINE:'1'};
          const native=spawnSync('node',[cli,'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-tools','-e',path.resolve('packages/continual-learning/tests/memory-amendment-live-fixture.ts'),
            '--provider','amendment-fixture','--model','fixed','--thinking','off','--no-session','--print','--mode','json','--source-excerpt-selection',JSON.stringify({ref:'e56.b0.l146',endRef:'e56.b0.l149'}),input.prompt],{cwd:root,env,encoding:'utf8',timeout:40000,maxBuffer:32*1024*1024});
          fs.writeFileSync(path.join(root,'native-pi-output.jsonl'),native.stdout);fs.writeFileSync(path.join(root,'native-prompt.txt'),input.prompt);
          fs.writeFileSync(path.join(root,'native-version.txt'),version.stdout);
          if(native.status!==0)throw Error(JSON.stringify({status:native.status,signal:native.signal,error:String(native.error),stderr:native.stderr,stdoutTail:native.stdout.slice(-4000)}));
          return {...kit.parsePiWorkerOutput(native.stdout),exitCode:0,stderr:'',cancelled:false};
        }
        const patch={candidateId:candidate.candidateId,sourceExcerpt:{ref:'e56.b0.l146',endRef:'e56.b0.l149'},evidence:[{ref:'e56.b0.l146',endRef:'e56.b0.l149'}]};
        const response={kind:'incremental-memory-amendment',version:1,...identity,replacements:[patch]};
        if(mode==='mixed')patch.content='old';if(mode==='noEvidence')delete patch.evidence;if(mode==='foreign')patch.candidateId='foreign';
        if(mode==='ordinaryRead'){patch.sourceExcerpt={ref:'e3.b0.l1',endRef:'e3.b0.l3'};patch.evidence=[patch.sourceExcerpt]}
        if(mode==='uncovered')patch.evidence=[{ref:'e56.b0.l1'}];if(mode==='noIdentity')delete response.runId;
        return {exitCode:0,stderr:'',cancelled:false,text:JSON.stringify(response)};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const name=original.operations[0].name;
      const input={identity,rejectedPlan:original,errors:['held body'],selectedNames:existing.map(x=>x.name),repairableNames:[name],repairableFields:{[name]:['body']},
        memorySources:sources,sourceExcerptRun:run,semanticContext:{frozenEvidence:snapshot,existingMemories:existing},outputDir:root};
      const good=await repairIncrementalMemoryPlan(input),context=JSON.parse(prompt.split('\n').at(-1));
      const saved=JSON.parse(fs.readFileSync(path.join(root,'repair-response.json'),'utf8'));
      // Given the same already-rejected excerpt, When the repair selects the
      // same source again, Then retain failure and usage without a second review.
      const repeated=await repairIncrementalMemoryPlan({...input,rejectedPlan:good.plan});
      const rejected={};for(const value of ['mixed','noEvidence','foreign','uncovered','noIdentity','ordinaryRead']){mode=value;rejected[value]=(await repairIncrementalMemoryPlan(input)).outcome}
      mode='valid';for(const [key,change] of Object.entries({noRun:x=>delete x.sourceExcerptRun,noAudit:x=>delete x.memorySources,
        locked:x=>x.repairableFields={[name]:['description']},wrongRun:x=>x.sourceExcerptRun={manifest:{...run.manifest,runId:'foreign'}},
        wrongSnapshot:x=>x.semanticContext={...x.semanticContext,frozenEvidence:{...snapshot,runId:'foreign'}},
        safe:x=>x.rejectedPlan={...original,operations:original.operations.map(o=>({...o,classification:'safe'}))},
        preference:x=>x.semanticContext={...x.semanticContext,existingMemories:existing.map(o=>({...o,type:'preference'}))}})){
          const x={...input};change(x);rejected[key]=(await repairIncrementalMemoryPlan(x)).outcome}
      console.log(JSON.stringify({good,repeated,rejected,context:{repairCandidates:context.repairCandidates},saved,old:original.operations[0],historical:fixture.response.replacements[0],calls,
        memoryWritten:fs.existsSync(path.join(root,'.memory'))}));
    '''.replace('ROOT', json.dumps(str(tmp_path))).replace('NATIVE', str(native).lower()))
    assert result['good']['outcome'] == 'repaired', result['good']
    assert result['repeated']['outcome'] == 'failed', result['repeated']
    assert result['repeated']['failureKind'] == 'no-correction' and 'plan' not in result['repeated']
    operation = result['good']['plan']['operations'][0]
    assert '"clearQueue" | "onIdle"' in operation['content'] or "'clearQueue' | 'onIdle'" in operation['content']
    assert operation['content'].split('\n---\n')[0] == result['old']['content'].split('\n---\n')[0]
    assert operation['name'] == result['old']['name'] and operation['kind'] == 'rewrite'
    assert operation['classification'] == result['old']['classification'] == 'private'
    assert all(value == 'failed' for value in result['rejected'].values()), result['rejected']
    assert result['context']['repairCandidates'][0]['sourceExcerptAllowed'] is True
    assert 'sourceExcerpt' in result['saved']['output'] and not result['memoryWritten']
    assert 'onIdle' not in result['historical']['content']


def test_frozen_real_repair_keeps_candidate_identity_parent_owned() -> None:
    # Given the real v31 new->rewrite failure, When correcting held content,
    # Then the parent binds patches to the original proposal and still rejects
    # the actual failed response, foreign IDs, privacy changes and stale input.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {semanticMemoryRepairCandidates,bindSemanticMemoryAmendment,mergeSemanticMemoryRepairDelta,candidateCitationProblems} from './packages/continual-learning/extensions/inject-memory.ts';
      import {containsSensitiveMemoryMaterial} from './packages/continual-learning/extensions/consolidation-run.ts';
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-intent-failure.json','utf8'));
      const original=fixture.files['semantic-rejected-plan.json'].value;
      const failed=JSON.parse(fixture.files['repair-response.json'].value.output);
      const snapshot=fixture.files['snapshot.json'].value;
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,original[k]]));
      const candidates=semanticMemoryRepairCandidates(original);
      const prior=original.newMemories[0];
      const amendment={kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:candidates[0].candidateId,content:prior.content,evidence:prior.evidence}]};
      const bound=bindSemanticMemoryAmendment(original,amendment,identity);
      const merged=mergeSemanticMemoryRepairDelta(original,bound);
      const rejects=value=>{try{bindSemanticMemoryAmendment(original,value,identity);return false;}catch{return true;}};
      let oldRejected=false;try{mergeSemanticMemoryRepairDelta(original,failed)}catch{oldRejected=true}
      const invalid=[{...amendment,runId:'other'}, {...amendment,operations:[]},
        {...amendment,replacements:[{...amendment.replacements[0],classification:'safe'}]},
        {...amendment,replacements:[{...amendment.replacements[0],candidateId:'foreign'}]},
        {...amendment,replacements:[amendment.replacements[0],amendment.replacements[0]]}];
      let staleRejected=false;try{bindSemanticMemoryAmendment({...original,newMemories:[{...prior,content:'changed'},...original.newMemories.slice(1)]},amendment,identity)}catch{staleRejected=true}
      let unheldRejected=false;try{bindSemanticMemoryAmendment(original,amendment,identity,[])}catch{unheldRejected=true}
      console.log(JSON.stringify({oldRejected,invalid:invalid.map(rejects),staleRejected,unheldRejected,
        unchanged:JSON.stringify(merged)===JSON.stringify(original),boundOperations:bound.operations,
        candidates,sensitive:containsSensitiveMemoryMaterial(JSON.stringify(fixture)),
        citations:candidateCitationProblems(snapshot,merged.newMemories)}));
    ''')
    assert result['oldRejected']
    assert all(result['invalid'])
    assert result['staleRejected'] and result['unheldRejected']
    assert result['unchanged']
    assert result['boundOperations'] == []
    assert len(result['candidates']) == 2
    assert not result['sensitive']
    assert result['citations'] == []


def test_semantic_worker_uses_bound_amendments_and_preserves_omitted_candidates() -> None:
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let prompt,tools;
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const a={name:'a.md',kind:'project',classification:'private',content:'A',evidence:[{index:0,quote:'A'}]};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[a,{...a,name:'b.md',content:'B'}]};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        prompt=input.prompt;tools=input.tools;
        const context=JSON.parse(prompt.split('\n').at(-1));
        return {exitCode:0,stderr:'',cancelled:false,text:JSON.stringify({kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:context.repairCandidates[0].candidateId,content:'correct A',evidence:a.evidence}]})};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,errors:['a held'],selectedNames:[],repairableNames:['a.md'],semanticContext:{frozenEvidence:{entries:[]},existingMemories:[]}});
      console.log(JSON.stringify({result,prompt,tools}));
    ''')
    assert result['result']['outcome'] == 'repaired'
    assert [x['content'] for x in result['result']['plan']['newMemories']] == ['correct A', 'B']
    assert result['tools'] == []
    assert 'incremental-memory-amendment' in result['prompt']
    assert 'Candidate identity, operation kind and privacy are parent-owned' in result['prompt']


@pytest.mark.parametrize('raw_whitespace', [False, True])
def test_actual_pi_receives_parent_bound_amendment_prompt_without_tools(tmp_path, raw_whitespace) -> None:
    import json
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';import {spawnSync} from 'node:child_process';import fs from 'node:fs';import path from 'node:path';
      const kit=await import('./packages/kit/src/index.ts');const root=ROOT;const rawWhitespace=RAW_WHITESPACE;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        const env={PATH:process.env.PATH,HOME:root,PI_CODING_AGENT_DIR:path.join(root,'agent'),PI_OFFLINE:'1'};
        const native=spawnSync('node',[path.resolve('node_modules/@earendil-works/pi-coding-agent/dist/cli.js'),'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-tools','-e',path.resolve('packages/continual-learning/tests/memory-amendment-live-fixture.ts'),'--provider','amendment-fixture','--model','fixed','--thinking','off','--no-session','--print','--mode','json',...(rawWhitespace?['--raw-string-whitespace','enabled']:[]),input.prompt],{cwd:root,env,encoding:'utf8',timeout:40000,maxBuffer:32*1024*1024});
        fs.writeFileSync(path.join(root,'native-pi-output.jsonl'),native.stdout);
        if(native.status!==0)throw new Error(native.stderr+'\n'+native.stdout);
        return {...kit.parsePiWorkerOutput(native.stdout),exitCode:0,stderr:'',cancelled:false};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const suffix=rawWhitespace?'\n\tline':'';const candidate={name:'a.md',kind:'project',classification:'private',content:'Old claim'+suffix,evidence:[{index:0,quote:'Correct claim'+suffix}]};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[candidate]};
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,errors:['held'],selectedNames:[],repairableNames:['a.md'],semanticContext:{frozenEvidence:{entries:[{role:'toolResult',content:'Correct claim'+suffix}]},existingMemories:[]}});
      console.log(JSON.stringify({result,wroteMemory:fs.existsSync(path.join(root,'.memory'))}));
    '''.replace('ROOT', json.dumps(str(tmp_path))).replace('RAW_WHITESPACE', str(raw_whitespace).lower()))
    assert result['result']['outcome'] == 'repaired', result['result']
    assert result['result']['plan']['newMemories'][0]['content'] == 'Correct claim' + ('\n\tline' if raw_whitespace else '')
    assert not result['wroteMemory']


def test_empty_or_sensitive_amendments_do_not_acknowledge_correction(tmp_path) -> None:
    import json
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';import fs from 'node:fs';import path from 'node:path';
      const kit=await import('./packages/kit/src/index.ts');let output;let calls=0;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{calls++;return {exitCode:0,stderr:'',text:JSON.stringify(output),cancelled:false}}}));
      const {repairIncrementalMemoryPlan,semanticMemoryRepairCandidates}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const a={name:'a.md',kind:'project',classification:'private',content:'A',evidence:[{index:0,quote:'A'}]};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[a]};
      const input={identity,rejectedPlan:original,errors:['held'],selectedNames:[],repairableNames:['a.md'],outputDir:ROOT,semanticContext:{frozenEvidence:{entries:[]},existingMemories:[]}};
      output={kind:'incremental-memory-amendment',version:1,...identity,replacements:[]};
      const empty=await repairIncrementalMemoryPlan(input);
      output.replacements=[{candidateId:semanticMemoryRepairCandidates(original)[0].candidateId,content:'api_key=sk-'+'x'.repeat(40),evidence:a.evidence}];
      await repairIncrementalMemoryPlan(input);
      const saved=JSON.parse(fs.readFileSync(path.join(input.outputDir,'repair-response.json'),'utf8'));
      console.log(JSON.stringify({empty,saved,calls}));
    '''.replace('ROOT', json.dumps(str(tmp_path))))
    assert result['empty']['failureKind'] == 'no-correction'
    assert 'plan' not in result['empty']
    assert result['saved']['sensitive']
    assert 'output' not in result['saved']
    assert result['calls'] == 2


def test_real_raw_json_whitespace_repair_keeps_content_and_parent_bindings(tmp_path) -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let prompt;
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-amendment-raw-whitespace.json','utf8'));
      const original=fixture.files['semantic-rejected-plan.json'].value,snapshot=fixture.files['snapshot.json'].value,raw=fixture.files['repair-response.json'].value.output;
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,original[k]]));
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{prompt=input.prompt;return {exitCode:0,stderr:'',text:raw,cancelled:false};}}));
      const {repairIncrementalMemoryPlan,candidateCitationProblems}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {containsSensitiveMemoryMaterial,sha256Digest}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,errors:['description held'],selectedNames:[],repairableNames:original.newMemories.map(x=>x.name),repairableFields:Object.fromEntries(original.newMemories.map(x=>[x.name,['description']])),semanticContext:{frozenEvidence:snapshot,existingMemories:[]},outputDir:process.env.PROBE_DIR});
      const originalResponse=JSON.parse(fs.readFileSync(process.env.PROBE_DIR+'/repair-response.json','utf8'));
      const diagnosticFile=process.env.PROBE_DIR+'/repair-json-whitespace.json';
      const diagnostic=fs.existsSync(diagnosticFile)?JSON.parse(fs.readFileSync(diagnosticFile,'utf8')):null;
      console.log(JSON.stringify({result,original,rawPreserved:originalResponse.output===raw,diagnostic,prompt,sensitive:containsSensitiveMemoryMaterial(JSON.stringify(fixture)),sourceHash:sha256Digest(raw),citations:result.plan?candidateCitationProblems(snapshot,result.plan.newMemories):null}));
    ''', env={'PROBE_DIR': str(tmp_path)})
    assert result['result']['outcome'] == 'repaired', result['result']
    assert result['rawPreserved'] and not result['sensitive']
    assert result['sourceHash'] == '6e257b548cd02902a26fdcb52924af2086f289b87ff209a51285a74853f84e55'
    assert result['citations'] == []
    assert result['result']['plan']['operations'] == result['original']['operations']
    old, new = result['original']['newMemories'][0], result['result']['plan']['newMemories'][0]
    assert old['name'] == new['name'] and old['classification'] == new['classification']
    assert old['content'].split('\n---\n', 1)[1] == new['content'].split('\n---\n', 1)[1]
    assert result['diagnostic']['originalTextSha256'] == result['sourceHash']
    assert result['diagnostic']['serializationOnly'] and not result['diagnostic']['semanticAcceptance']
    assert 'Escape newline' in result['prompt']


def test_sensitive_normalized_amendment_keeps_hash_diagnostic_without_original_text(tmp_path):
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const item={name:'a.md',kind:'project',classification:'private',content:'A',evidence:[{index:0,quote:'A'}]};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[item]};
      let output;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>({exitCode:0,stderr:'',cancelled:false,text:output})}));
      const {repairIncrementalMemoryPlan,semanticMemoryRepairCandidates}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      output=JSON.stringify({kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:semanticMemoryRepairCandidates(original)[0].candidateId,content:'header\napi_key=sk-'+'x'.repeat(40),evidence:item.evidence}]}).replace('\\n','\n');
      await repairIncrementalMemoryPlan({identity,rejectedPlan:original,errors:['held'],selectedNames:[],repairableNames:['a.md'],semanticContext:{frozenEvidence:{entries:[]},existingMemories:[]},outputDir:process.env.PROBE_DIR});
      const saved=JSON.parse(fs.readFileSync(process.env.PROBE_DIR+'/repair-response.json','utf8'));
      const diagnostic=JSON.parse(fs.readFileSync(process.env.PROBE_DIR+'/repair-json-whitespace.json','utf8'));
      console.log(JSON.stringify({saved,diagnostic}));
    ''', env={'PROBE_DIR': str(tmp_path)})
    assert result['saved']['sensitive'] and 'output' not in result['saved']
    assert result['diagnostic']['counts']['newline'] == 1
    assert result['diagnostic']['serializationOnly'] and not result['diagnostic']['semanticAcceptance']


def test_real_content_patch_reuses_only_bound_original_citations(tmp_path):
    # Given the complete real V49 failure and a body-only repair grant, When
    # the semantic worker omits unchanged citations, Then retain those exact
    # verified sources without approval, metadata drift or a second model call.
    value=isolated_run_bun(r'''
      import fs from 'node:fs';import {mock} from 'bun:test';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-repair-source-inheritance.json').json();
      const kit=await import('./packages/kit/src/index.ts');let calls=0,prompt,args;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        calls++;prompt=input.prompt;args=input.extraArgs;return {exitCode:0,stderr:'',cancelled:false,text:JSON.stringify(f.response)};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {resolveMemoryPlanCitations}=await import('./packages/continual-learning/extensions/memory-citation-locations.ts');
      const original=f.original,before=JSON.stringify(f),identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,original[k]]));
      const name=original.operations[0].name,originalResolved=resolveMemoryPlanCitations(original,f.snapshot);
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,selectedNames:[name],repairableNames:[name],repairableFields:{[name]:['body']},errors:['counterevidence held'],
        semanticContext:{frozenEvidence:f.snapshot,existingMemories:[]},outputDir:process.env.PROBE_DIR});
      const content=result.plan?.operations[0].content;
      console.log(JSON.stringify({outcome:result.outcome,calls,unchanged:before===JSON.stringify(f),originalDescription:original.operations[0].content.split('\n').find(x=>x.startsWith('description:')),
        correctedDescription:content?.split('\n').find(x=>x.startsWith('description:')),bodyChanged:!!content&&content!==original.operations[0].content,
        evidenceUnchanged:JSON.stringify(result.plan?.operations[0].evidence)===JSON.stringify(originalResolved.operations[0].evidence),
        rawOutputUnchanged:JSON.parse(fs.readFileSync(process.env.PROBE_DIR+'/repair-response.json','utf8')).output===JSON.stringify(f.response),
        sourceContract:JSON.parse(prompt.split('\n').at(-1)).repairCandidates[0].reuseOriginalEvidence,
        outputKind:args[args.indexOf('--learning-output-schema')+1],proof:JSON.parse(fs.readFileSync(process.env.PROBE_DIR+'/semantic-repair-source-inheritance.json','utf8'))}));
    ''', env={'PROBE_DIR':str(tmp_path)})
    assert value['outcome']=='repaired'
    assert value['calls']==1 and value['unchanged'] and value['bodyChanged']
    assert value['originalDescription']==value['correctedDescription']
    assert value['evidenceUnchanged'] and value['rawOutputUnchanged']
    assert value['sourceContract'] is True
    assert value['outputKind']=='memory-semantic-amendment'
    assert value['proof']['originalCitationsOnly'] and not value['proof']['semanticAcceptance']


def test_content_patch_source_inheritance_rejects_unbound_invalid_or_empty_changes():
    rows=isolated_run_bun(r'''
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-repair-source-inheritance.json').json();
      const {bindSemanticMemoryAmendment,semanticMemoryRepairCandidates}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const modes=['valid','no-context','no-fields','tampered-snapshot','empty-evidence','null-evidence','undefined-evidence','missing-content','unchanged-content','locked-only','foreign-id','missing-identity','missing-original-evidence','invalid-original-quote'];
      const rows=[];for(const mode of modes){
        const original=structuredClone(f.original),response=structuredClone(f.response),snapshot=structuredClone(f.snapshot),name=original.operations[0].name;
        const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,original[k]]));
        if(mode==='tampered-snapshot')snapshot.entries[0].unboundChange=true;
        if(mode==='empty-evidence')response.replacements[0].evidence=[];
        if(mode==='null-evidence')response.replacements[0].evidence=null;
        if(mode==='undefined-evidence')response.replacements[0].evidence=undefined;
        if(mode==='missing-content')delete response.replacements[0].content;
        if(mode==='unchanged-content')response.replacements[0].content=original.operations[0].content;
        if(mode==='locked-only')response.replacements[0].content=original.operations[0].content.replace(/^description:.*$/m,'description: Changed locked description');
        if(mode==='foreign-id')response.replacements[0].candidateId='foreign';
        if(mode==='missing-identity')delete response.snapshotDigest;
        // A source change must not retain the stale candidate-bound identity.
        if(mode==='missing-original-evidence')delete original.operations[0].evidence;
        if(mode==='invalid-original-quote')original.operations[0].evidence=[{index:49,quote:'Not in the original source'}];
        if(mode==='missing-original-evidence'||mode==='invalid-original-quote')response.replacements[0].candidateId=semanticMemoryRepairCandidates(original)[0].candidateId;
        const before=JSON.stringify({original,response,snapshot});let accepted=false;
        try{bindSemanticMemoryAmendment(original,response,identity,[name],mode==='no-context'?undefined:{frozenEvidence:snapshot,repairableFields:mode==='no-fields'?{}:{[name]:['body']}});accepted=true;}catch{}
        rows.push({mode,accepted,unchanged:before===JSON.stringify({original,response,snapshot})});
      }console.log(JSON.stringify(rows));
    ''')
    assert rows[0]['accepted']
    assert all(not row['accepted'] for row in rows[1:])
    assert all(row['unchanged'] for row in rows)


def test_actual_pi_semantic_content_patch_retains_real_original_sources():
    value=isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import{repairIncrementalMemoryPlan}from'./packages/continual-learning/extensions/inject-memory.ts';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-repair-source-inheritance.json').json();
      const agent=process.env.PI_CODING_AGENT_DIR;let calls=0,tools;
      const server=Bun.serve({hostname:'127.0.0.1',port:0,fetch:async request=>{
        calls++;const wire=await request.json();tools=wire.tools;
        const reply=JSON.stringify(f.response),chunk=(delta,finish_reason)=>'data: '+JSON.stringify({id:'fixture',object:'chat.completion.chunk',model:'offline',choices:[{index:0,delta,finish_reason}]})+'\n\n';
        return new Response(chunk({role:'assistant',content:reply},null)+chunk({},'stop')+'data: [DONE]\n\n',{headers:{'content-type':'text/event-stream'}});
      }});
      fs.writeFileSync(path.join(agent,'models.json'),JSON.stringify({providers:{fixture:{baseUrl:`http://127.0.0.1:${server.port}/v1`,api:'openai-completions',apiKey:'offline',models:[{id:'offline',name:'offline',reasoning:false,input:['text'],contextWindow:1000000,maxTokens:4096,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}]}}}));
      fs.writeFileSync(path.join(agent,'settings.json'),JSON.stringify({packages:[],extensions:[],skills:[],retry:{enabled:false}}));
      process.env.PI_OFFLINE='1';process.argv[1]=fs.realpathSync('./node_modules/@earendil-works/pi-coding-agent/dist/cli.js');process.execPath=Bun.which('node');
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,f.original[k]])),name=f.original.operations[0].name,before=JSON.stringify(f);
      try{const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:f.original,selectedNames:[name],repairableNames:[name],repairableFields:{[name]:['body']},errors:['held'],model:'fixture/offline',semanticContext:{frozenEvidence:f.snapshot,existingMemories:[]}});
        console.log(JSON.stringify({outcome:result.outcome,calls,tools:tools?.length??0,unchanged:before===JSON.stringify(f),sourceCount:result.plan?.operations[0].evidence.length,
          piVersion:JSON.parse(fs.readFileSync('./node_modules/@earendil-works/pi-coding-agent/package.json','utf8')).version,externalRequests:0}));
      }finally{server.stop(true)}
    ''',timeout=45)
    assert value=={'outcome':'repaired','calls':1,'tools':0,'unchanged':True,'sourceCount':3,'piVersion':'1.2.0','externalRequests':0}
