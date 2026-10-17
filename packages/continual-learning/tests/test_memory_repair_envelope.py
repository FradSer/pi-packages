from support import isolated_run_bun


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
        const content='---\n'+(named?'name: Existing display name\n':'')+'description: Existing description\ntype: project\n---\nOld body.';
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
          asksInventedName:prompt.includes('complete replacement Markdown content including name/description/type frontmatter')});
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
