from support import isolated_run_bun


def test_parent_repair_provenance_binds_worker_and_validated_plan_without_authorizing_writes():
    # Given an actual parent-created repair result and a pretty rejected artifact,
    # When the parent validates its expanded plan, Then retain one causal receipt.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
      import {mock} from 'bun:test';import {execFileSync} from 'node:child_process';
      const kit=await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        const data=JSON.parse(input.prompt.split('\n').at(-1));
        return {exitCode:0,stderr:'',cancelled:false,text:JSON.stringify({kind:'incremental-memory-amendment',version:1,...data.identity,
          replacements:[{candidateRef:data.repairCandidates[0].candidateRef,
            content:data.rejectedPlan.newMemories[0].content.replace('Old body.','Current body.'),evidence:[{ref:'e0.b0.l1'}]}]}),
          usageLedger:{complete:true,knownUsage:{input:1,output:1,cacheRead:0,cacheWrite:0,total:2,cost:0},records:[]}};
      }}));
      const {createConsolidationRun,releaseConsolidationRun,sha256Digest}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const {repairIncrementalMemoryPlan,prepareSemanticMemoryRepairProposal}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'repair-provenance-'))),cwd=path.join(root,'project');fs.mkdirSync(cwd);execFileSync('git',['init','-q',cwd]);
      process.env.PI_CODING_AGENT_DIR=path.join(root,'agent');
      const entries=[{message:{role:'user',content:'Current body.'}}];
      const run=await createConsolidationRun({cwd,sessionManager:{getBranch:()=>entries,buildContextEntries:()=>entries}},cwd,false);
      try {
        const m=run.manifest,identity={runId:m.runId,scopeKey:m.scopeKey,scopeDigest:m.scopeDigest,artifactHash:m.snapshotDigest,snapshotDigest:m.snapshotDigest};
        const snapshot=JSON.parse(fs.readFileSync(run.paths.snapshotFile,'utf8'));
        const prior={name:'contract.md',kind:'project',classification:'private',content:'---\nname: contract\ndescription: Current body\ntype: project\n---\nOld body.',evidence:[{ref:'e0.b0.l1'}]};
        const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[prior]};
        const rejectedBytes=JSON.stringify(original,null,2)+'\n';fs.writeFileSync(path.join(m.runDir,'semantic-rejected-plan.json'),rejectedBytes);
        const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,selectedNames:[],repairableNames:[prior.name],repairableFields:{[prior.name]:['body']},errors:['held'],outputDir:m.runDir,semanticContext:{frozenEvidence:snapshot,existingMemories:[]}});
        const prepared=await prepareSemanticMemoryRepairProposal({result,run,pkgDir:path.resolve('./packages/continual-learning'),selectedScope:[],preSelected:[],candidates:[prior],existing:[],frozenEvidence:snapshot});
        const artifact=name=>JSON.parse(fs.readFileSync(path.join(m.runDir,name),'utf8'));
        const receipt=artifact('semantic-repair-provenance-'+result.usageLedgerId+'.json');
        const response=artifact('repair-response.json'),closed=artifact('memory-repair-lifecycle-'+result.usageLedgerId+'-closed.json'),usage=artifact('memory-repair-usage-'+result.usageLedgerId+'.json');
        console.log(JSON.stringify({outcome:result.outcome,receipt,response,closed,usage,
          expected:{ledgerId:result.usageLedgerId,rejectedCanonical:sha256Digest(JSON.stringify(original)),rejectedBytes:sha256Digest(rejectedBytes),planBytes:sha256Digest(fs.readFileSync(prepared.correctedPath)),responseBytes:sha256Digest(fs.readFileSync(path.join(m.runDir,'repair-response.json')))},
          stored:fs.existsSync(path.join(m.harnessDir,prior.name))}));
      } finally {await releaseConsolidationRun(run);fs.rmSync(root,{recursive:true,force:true});}
    ''')
    receipt = value['receipt']
    assert value['outcome'] == 'repaired' and not value['stored']
    assert receipt['ledgerId'] == value['expected']['ledgerId']
    assert receipt['status'] == 'validated-repair-proposal'
    assert receipt['rejectedPlanCanonicalSha256'] == value['expected']['rejectedCanonical']
    assert receipt['rejectedPlanBytesSha256'] == value['expected']['rejectedBytes']
    assert receipt['rejectedPlanCanonicalSha256'] != receipt['rejectedPlanBytesSha256']
    assert receipt['semanticPlanBytesSha256'] == value['expected']['planBytes']
    assert receipt['responseArtifactSha256'] == value['expected']['responseBytes']
    assert receipt['responseArtifactFile'] == f"memory-repair-response-{receipt['ledgerId']}.json"
    for artifact in ('response', 'closed', 'usage'):
        assert value[artifact]['parentRepairProvenance']['ledgerId'] == receipt['ledgerId']
        assert value[artifact]['parentRepairProvenance']['taskInputSha256'] == receipt['taskInputSha256']
        assert value[artifact]['parentRepairProvenance']['outputSha256'] == receipt['outputSha256']
    assert receipt['semanticApproval'] is False and receipt['writeAuthorized'] is False
    assert receipt['learningBenefitEstablished'] is False


def test_parent_repair_provenance_rejects_copied_results_swaps_tampering_and_invalid_workers():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
      import {mock} from 'bun:test';import {execFileSync} from 'node:child_process';
      const kit=await import('./packages/kit/src/index.ts');let mode='valid';
      const promises=(await import('node:fs/promises')).default;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        const data=JSON.parse(input.prompt.split('\n').at(-1));
        const response={kind:'incremental-memory-amendment',version:1,...data.identity,replacements:[{
          candidateRef:data.repairCandidates[0].candidateRef,content:data.rejectedPlan.newMemories[0].content.replace('Old body.','Current body.'),evidence:[{ref:'e0.b0.l1'}]}]};
        if(mode==='identity')response.runId='foreign';
        if(mode==='citation')response.replacements[0].evidence=[{ref:'e0.b0.l999'}];
        if(mode==='sensitive')response.extra=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/sensitive_memory_corpus.json','utf8')).sensitive[0];
        const usageLedger=mode==='partial'?kit.parsePiWorkerUsageLedger(JSON.stringify({type:'message_end',message:{role:'assistant',usage:{input:1}}}))
          :{complete:true,knownUsage:{input:1,output:1,cacheRead:0,cacheWrite:0,total:2,cost:0},records:[]};
        return {exitCode:0,stderr:'',cancelled:false,text:JSON.stringify(response),...(mode==='missing-ledger'?{}:{usageLedger})};
      }}));
      const {createConsolidationRun,releaseConsolidationRun,sha256Digest}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const {repairIncrementalMemoryPlan,prepareSemanticMemoryRepairProposal}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'repair-provenance-negatives-')));process.env.PI_CODING_AGENT_DIR=path.join(root,'agent');
      const runs=[],rows=[];let serial=0;
      const fixture=async workerMode=>{
        mode=workerMode;const cwd=path.join(root,'project-'+serial++);fs.mkdirSync(cwd);execFileSync('git',['init','-q',cwd]);
        const entries=[{message:{role:'user',content:'Current body.'}}];
        const run=await createConsolidationRun({cwd,sessionManager:{getBranch:()=>entries,buildContextEntries:()=>entries}},cwd,false);runs.push(run);
        const m=run.manifest,identity={runId:m.runId,scopeKey:m.scopeKey,scopeDigest:m.scopeDigest,artifactHash:m.snapshotDigest,snapshotDigest:m.snapshotDigest};
        const snapshot=JSON.parse(fs.readFileSync(run.paths.snapshotFile,'utf8'));
        const prior={name:'contract.md',kind:'project',classification:'private',content:'---\nname: contract\ndescription: Current body\ntype: project\n---\nOld body.',evidence:[{ref:'e0.b0.l1'}]};
        const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[prior]};
        fs.writeFileSync(path.join(m.runDir,'semantic-rejected-plan.json'),JSON.stringify(original,null,2)+'\n');
        const nativeSignal=new AbortController();
        const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,selectedNames:[],repairableNames:[prior.name],repairableFields:{[prior.name]:['body']},errors:['held'],outputDir:m.runDir,signal:nativeSignal.signal,semanticContext:{frozenEvidence:snapshot,existingMemories:[]}});
        return {result,run,pkgDir:path.resolve('./packages/continual-learning'),selectedScope:[],preSelected:[],candidates:[prior],existing:[],frozenEvidence:snapshot,nativeSignal};
      };
      const receipts=f=>fs.readdirSync(f.run.manifest.runDir).filter(x=>x.startsWith('semantic-repair-provenance-'));
      const reject=async(label,f)=>{let denied=false;try{denied=!(await prepareSemanticMemoryRepairProposal(f))}catch{denied=true}rows.push({label,denied,receipts:receipts(f).length});};
      try{
        const a=await fixture('valid'),b=await fixture('valid');
        await reject('copied-result',{...a,result:{...a.result}});
        await reject('foreign-result',{...b,result:a.result});
        const delta=await fixture('valid');delta.result.plan.newMemories[0].content+=' drift';await reject('changed-returned-delta',delta);
        const cross=await fixture('valid');cross.result.plan=b.result.plan;await reject('cross-result-plan-swap',cross);
        const output=await fixture('valid'),dir=output.run.manifest.runDir,id=output.result.usageLedgerId;
        for(const name of ['repair-response.json','memory-repair-response-'+id+'.json','memory-repair-lifecycle-'+id+'-closed.json','memory-repair-usage-'+id+'.json']){
          const file=path.join(dir,name),data=JSON.parse(fs.readFileSync(file,'utf8'));
          if(name==='repair-response.json'||name.startsWith('memory-repair-response-'))data.output=data.output.replace('Current body.','Forged body.');
          data.parentRepairProvenance.outputSha256=sha256Digest('forged output');fs.writeFileSync(file,JSON.stringify(data));
        }
        await reject('changed-output-and-public-hashes',output);
        const ledger=await fixture('valid'),ledgerPath=path.join(ledger.run.manifest.runDir,'memory-repair-usage-'+ledger.result.usageLedgerId+'.json');
        const usage=JSON.parse(fs.readFileSync(ledgerPath,'utf8'));usage.ledgerId=a.result.usageLedgerId;usage.parentRepairProvenance.ledgerId=a.result.usageLedgerId;fs.writeFileSync(ledgerPath,JSON.stringify(usage));await reject('foreign-ledger',ledger);
        const previous=await fixture('valid');fs.writeFileSync(path.join(previous.run.manifest.runDir,'semantic-rejected-plan.json'),JSON.stringify(a.result.plan));await reject('foreign-rejected-plan',previous);
        const malformed=await fixture('valid');fs.writeFileSync(path.join(malformed.run.manifest.runDir,'semantic-rejected-plan.json'),'{ confidential-native-fixture');
        let sanitized=false;try{await prepareSemanticMemoryRepairProposal(malformed)}catch(error){sanitized=error.message==='Parent Memory repair predecessor is invalid'}
        rows.push({label:'malformed-predecessor-diagnostic-is-sanitized',denied:sanitized,receipts:receipts(malformed).length});
        const source=await fixture('valid');fs.appendFileSync(source.run.paths.snapshotFile,' ');await reject('changed-frozen-snapshot',source);
        const linked=await fixture('valid'),outside=path.join(root,'unrelated-public-file.txt');fs.writeFileSync(outside,'unrelated-evidence');
        fs.symlinkSync(outside,path.join(linked.run.manifest.runDir,'semantic-repair-plan.json'));
        await reject('symlink-plan-target-rejected-before-write',linked);
        rows.push({label:'symlink-plan-does-not-change-outside-evidence',denied:fs.readFileSync(outside,'utf8')==='unrelated-evidence',receipts:receipts(linked).length});
        const cancelled=await fixture('valid'),abort=new AbortController();abort.abort();await reject('parent-cancelled',{...cancelled,signal:abort.signal});
        const nativeCancelled=await fixture('valid');nativeCancelled.nativeSignal.abort();await reject('original-invocation-cancelled',nativeCancelled);
        await reject('missing-native-usage-artifact',await fixture('missing-ledger'));
        const shared=await fixture('valid'),sharedDir=shared.run.manifest.runDir;
        const firstResponse=path.join(sharedDir,'memory-repair-response-'+shared.result.usageLedgerId+'.json'),firstBytes=fs.readFileSync(firstResponse);
        const originalShared=JSON.parse(fs.readFileSync(path.join(sharedDir,'semantic-rejected-plan.json'),'utf8'));
        const sharedIdentity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(key=>[key,originalShared[key]]));mode='valid';
        const second=await repairIncrementalMemoryPlan({identity:sharedIdentity,rejectedPlan:originalShared,selectedNames:[],repairableNames:['contract.md'],repairableFields:{'contract.md':['body']},errors:['held'],outputDir:sharedDir,semanticContext:{frozenEvidence:shared.frozenEvidence,existingMemories:[]}});
        const secondBytes=fs.readFileSync(path.join(sharedDir,'memory-repair-response-'+second.usageLedgerId+'.json'));
        rows.push({label:'shared-output-dir-keeps-every-attempt-response',denied:shared.result.usageLedgerId!==second.usageLedgerId&&firstBytes.equals(fs.readFileSync(firstResponse))&&secondBytes.equals(fs.readFileSync(path.join(sharedDir,'repair-response.json')))&&!firstBytes.equals(secondBytes),receipts:receipts(shared).length});
        for(const workerMode of ['identity','citation','sensitive']){
          const f=await fixture(workerMode);await reject('invalid-worker-'+workerMode,f);
          const response=JSON.parse(fs.readFileSync(path.join(f.run.manifest.runDir,'repair-response.json'),'utf8'));
          if(workerMode==='sensitive')rows.push({label:'sensitive-hash-only',denied:response.sensitive===true&&!('output' in response)&&!!response.parentRepairProvenance.outputSha256,receipts:receipts(f).length});
          rows.push({label:'failed-worker-'+workerMode,denied:f.result.outcome!=='repaired',receipts:receipts(f).length});
        }
        const once=await fixture('valid');const both=await Promise.allSettled([prepareSemanticMemoryRepairProposal(once),prepareSemanticMemoryRepairProposal(once)]);
        const file=path.join(once.run.manifest.runDir,receipts(once)[0]),hash=sha256Digest(fs.readFileSync(file));
        let repeatedRejected=false;try{await prepareSemanticMemoryRepairProposal(once)}catch{repeatedRejected=true}
        rows.push({label:'one-result-one-receipt',denied:both.filter(x=>x.status==='fulfilled').length===1&&repeatedRejected&&receipts(once).length===1&&sha256Digest(fs.readFileSync(file))===hash,receipts:receipts(once).length});
        const partial=await fixture('partial'),partialPrepared=await prepareSemanticMemoryRepairProposal(partial);
        const partialUsage=JSON.parse(fs.readFileSync(path.join(partial.run.manifest.runDir,'memory-repair-usage-'+partial.result.usageLedgerId+'.json'),'utf8'));
        rows.push({label:'partial-usage-retains-causal-provenance',denied:!!partialPrepared&&partial.result.usageComplete===false&&partialUsage.complete===false&&partialUsage.knownUsage.input===1,receipts:receipts(partial).length});
        const race=await fixture('valid'),raceFile=path.join(race.run.manifest.runDir,'semantic-repair-provenance-'+race.result.usageLedgerId+'.json');
        const originalLstat=promises.lstat;let injected=false,raceRejected=false;
        promises.lstat=async(file,...args)=>{
          if(String(file)===raceFile&&!injected){injected=true;fs.writeFileSync(raceFile,'pre-existing-evidence');const error=new Error('fixture raced ENOENT');error.code='ENOENT';throw error;}
          return originalLstat(file,...args);
        };
        try{await prepareSemanticMemoryRepairProposal(race)}catch{raceRejected=true}finally{promises.lstat=originalLstat}
        const preserved=fs.readFileSync(raceFile,'utf8')==='pre-existing-evidence';fs.unlinkSync(raceFile);
        const afterRace=await prepareSemanticMemoryRepairProposal(race);
        rows.push({label:'receipt-race-preserves-evidence-and-does-not-consume-result',denied:injected&&raceRejected&&preserved&&!!afterRace,receipts:receipts(race).length});
        console.log(JSON.stringify(rows));
      }finally{for(const run of runs)await releaseConsolidationRun(run);fs.rmSync(root,{recursive:true,force:true});}
    ''', timeout=30)
    assert all(row['denied'] for row in value), value
    assert all(row['receipts'] == (1 if row['label'] in {'one-result-one-receipt', 'partial-usage-retains-causal-provenance', 'receipt-race-preserves-evidence-and-does-not-consume-result'} else 0) for row in value)


def test_real_missing_envelope_stays_rejected_and_prompt_requires_complete_identity():
    # Given V33's actual identity-free repair, When generating a candidate-bound
    # amendment, Then require the complete envelope without weakening admission.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let prompt;
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-missing-envelope.json','utf8'));
      const original=f.files['semantic-rejected-plan.json'].value;
      const raw=f.files['repair-response.json'].value.output;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        prompt=input.prompt;return {exitCode:0,stderr:'',text:raw,cancelled:false};
      }}));
      const {repairIncrementalMemoryPlan,bindSemanticMemoryAmendment}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,original[k]]));
      const input={identity,rejectedPlan:original,selectedNames:original.operations.map(x=>x.name),errors:['held'],
        repairableNames:[...original.operations,...original.newMemories].map(x=>x.name),
        semanticContext:{frozenEvidence:{entries:[]},existingMemories:[]}};
      const failure=await repairIncrementalMemoryPlan(input);
      let rejected=false;try{bindSemanticMemoryAmendment(original,JSON.parse(raw),identity)}catch{rejected=true}
      const context=JSON.parse(prompt.split('\n').at(-1));
      console.log(JSON.stringify({failure,rejected,contract:context.amendmentOutputContract,
        expected:{kind:'incremental-memory-amendment',version:1,...identity},
        ambiguous:prompt.includes('Return only candidate-bound replacement patches.')||prompt.includes('Never output names, kinds, classifications, operations or newMemories.')}));
    ''')
    assert result['failure']['failureKind'] == 'framing'
    assert 'plan' not in result['failure'] and result['rejected']
    assert result.get('contract') == {
        'requiredTopLevelValues': result['expected'],
        'requiredPatchArrays': ['replacements'],
        'omitEnvelope': False,
    }
    assert not result['ambiguous']


def test_retained_repair_distinguishes_operation_kind_from_memory_type():
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let prompt;
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-retained-operation-kind.json','utf8'));
      const raw=JSON.parse(f.response.output),old=f.original,retained=raw.operations[0];
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{prompt=input.prompt;return {exitCode:0,stderr:'',text:f.response.output,cancelled:false};}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,old[k]]));
      const failure=await repairIncrementalMemoryPlan({identity,rejectedPlan:old,selectedNames:[retained.name],errors:['held'],
        repairableNames:old.newMemories.map(x=>x.name),retainedRepairNames:[retained.name],
        semanticContext:{frozenEvidence:f.snapshot,existingMemories:[{name:retained.name,classification:retained.classification,content:retained.content}]}});
      const context=JSON.parse(prompt.split('\n').at(-1));
      console.log(JSON.stringify({failure,contract:context.retainedOperationContract,name:retained.name,classification:retained.classification,explicit:prompt.includes('kind must be exactly "rewrite" or "delete"')}));
    ''')
    assert result['failure']['failureKind'] == 'intent' and 'plan' not in result['failure']
    assert result['explicit']
    assert result.get('contract') == {
        'records': [{'name': result['name'], 'classification': result['classification']}],
        'allowedOperationKinds': ['rewrite', 'delete'],
        'memoryTypeIsNotOperationKind': True,
        'rewriteRequiredFields': ['name', 'kind', 'classification', 'content', 'evidence'],
        'deleteRequiredFields': ['name', 'kind', 'classification', 'verdict', 'preservedIn', 'evidence'],
        'mutationAuthority': False,
    }


def test_semantic_repair_examples_preserve_original_frontmatter_including_absent_name():
    # Given supported Memory formats with and without a name field,
    # When a held body or description is corrected,
    # Then examples keep the original protected header and do not invent metadata.
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const kit=await import('./packages/kit/src/index.ts');let prompt;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        prompt=input.prompt;const data=JSON.parse(prompt.split('\n').at(-1));
        const candidate=data.repairCandidates[0],prior=data.rejectedPlan.operations[0];
        return {exitCode:0,stderr:'',cancelled:false,text:JSON.stringify({kind:'incremental-memory-amendment',version:1,...data.identity,
          replacements:[{candidateRef:candidate.candidateRef,content:prior.content.replace('Old body.','Current body.'),evidence:prior.evidence}]})};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const snapshot={contextEnabled:true,runId:'r',scopeKey:'s',scopeDigest:'d',entries:[{role:'user',content:'Current body.'}]};
      const h=sha256Digest(JSON.stringify(snapshot,null,2)+'\n'),identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:h,snapshotDigest:h};
      const rows=[];
      const header=content=>/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(content)?.[1];
      const protectedHeader=text=>text.split(/\r?\n/).filter(line=>!line.startsWith('description:')).join('\n');
      for(const named of [false,true])for(const heldDescription of [false,true]){
        const content='---\n'+(named?'name: Existing display name\n':'')+'description: Existing description\ntype: project\n---\nOld body.\n\n**Why**: Later maintenance.\n\n**How to apply**: Compare current source.';
        const prior={name:'contract.md',kind:'rewrite',classification:'safe',content,evidence:[{index:0,quote:'Current body.'}]};
        const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[prior],newMemories:[]};
        const repaired=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,selectedNames:[prior.name],repairableNames:[prior.name],
          repairableFields:{[prior.name]:heldDescription?['body','description']:['body']},errors:['held'],
          semanticContext:{frozenEvidence:snapshot,existingMemories:[{...prior,type:'project'}]}});
        const lines=prompt.split('\n'),start=lines.indexOf('{'),end=lines.indexOf('}',start);
        const example=JSON.parse(lines.slice(start,end+1).join('\n')).replacements[0].content;
        rows.push({named,heldDescription,outcome:repaired.outcome,
          exampleProtectedHeader:protectedHeader(header(example)),originalProtectedHeader:protectedHeader(header(content)),
          exampleDescription:header(example).split('\n').find(line=>line.startsWith('description:')),
          resultHeader:header(repaired.plan?.operations[0].content??''),originalHeader:header(content),
          asksInventedName:prompt.includes('complete replacement Markdown content including name/description/type frontmatter'),
          purposeSections:JSON.parse(prompt.split('\n').at(-1)).repairCandidates[0].requiredKnowledgeSections,
          examplePurpose:example.includes('**Why**:')&&example.includes('**How to apply**:')});
      }
      console.log(JSON.stringify(rows));
    ''')
    for row in result:
        assert row['outcome'] == 'repaired', row
        assert row['resultHeader'] == row['originalHeader'], row
        assert row['exampleProtectedHeader'] == row['originalProtectedHeader'], row
        if not row['heldDescription']:
            assert row['exampleDescription'] == 'description: Existing description', row
        assert not row['asksInventedName'], row
        assert row['purposeSections'] == ['Why', 'How to apply'], row
        assert row['examplePurpose'], row


def test_correction_decision_guidance_is_scoped_to_candidate_bound_amendments():
    # Given semantic and structural correction slots, When a worker returns no
    # correction, Then only the amendment slot receives its decision protocol.
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let prompt;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        prompt=input.prompt;const data=JSON.parse(prompt.split('\n').at(-1));
        return {exitCode:0,stderr:'',cancelled:false,usage:{input:3,output:2,cacheRead:0,cacheWrite:0,totalTokens:5,cost:0.1},
          text:JSON.stringify({kind:'incremental-memory-amendment',version:1,...data.identity,replacements:[]})};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'h',snapshotDigest:'h'},rows=[];
      const prior={name:'a.md',kind:'project',classification:'private',content:'---\ndescription: Claim.\ntype: project\n---\nClaim.',evidence:[{index:0,quote:'Claim.'}]};
      for(const structuralCorrection of [false,true]){
        const repaired=await repairIncrementalMemoryPlan({identity,rejectedPlan:{kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[prior]},
          selectedNames:[],repairableNames:structuralCorrection?undefined:['a.md'],repairableFields:structuralCorrection?undefined:{'a.md':['body']},structuralCorrection,errors:['held'],
          semanticContext:{frozenEvidence:{entries:[{role:'user',content:'Claim.'}]},existingMemories:[]}});
        rows.push({structuralCorrection,decision:prompt.startsWith('Repair decision order for this single correction slot:'),
          noFalseSuccess:prompt.includes('refusal is not successful learning'),outcome:repaired.outcome,hasPlan:!!repaired.plan,usage:repaired.usage});
      }
      console.log(JSON.stringify(rows));
    ''')
    for row in result:
        assert row['decision'] is not row['structuralCorrection'], row
        if not row['structuralCorrection']:
            assert row['noFalseSuccess'], row
        assert row['outcome'] == 'failed' and not row['hasPlan'], row
        assert row['usage']['cost'] == 0.1, row
