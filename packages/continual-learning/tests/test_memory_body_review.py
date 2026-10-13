from support import isolated_run_bun


def test_actual_body_judgments_bind_exact_complete_content_and_reject_stale_witnesses() -> None:
    value = isolated_run_bun(r'''
      import {prepareMemoryBodyTargets,bindMemoryBodyJudgments} from './packages/continual-learning/extensions/memory-body-review.ts';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-body-review.json').json();
      const targets=prepareMemoryBodyTargets([f.original,f.corrected],[]);
      const replies=[f.originalResponse,f.correctedResponse].map((r,i)=>({id:targets[i].id,...r}));
      const bound=bindMemoryBodyJudgments(targets,{reviews:replies});
      const reject=change=>{try{bindMemoryBodyJudgments(targets,change(structuredClone({reviews:replies})));return false}catch{return true}};
      console.log(JSON.stringify({bound,complete:targets[0].content===f.original.content&&targets[1].content===f.corrected.content,
        stale:reject(r=>{r.reviews[0].bodySha256=targets[1].bodySha256;return r}),
        quote:reject(r=>{r.reviews[0].conflictingQuotes[0]+=' invented';return r}),
        duplicate:reject(r=>{r.reviews[1].id=r.reviews[0].id;return r}),
        omitted:reject(r=>{r.reviews.pop();return r}),
        verdict:reject(r=>{r.reviews[0].verdict='allow';return r}),
        emptyWitness:reject(r=>{r.reviews[0].conflictingQuotes=[];return r})}));
    ''')
    assert value['complete']
    assert value['bound'][0]['verdict'] == 'contradictory'
    assert value['bound'][1]['verdict'] == 'consistent'
    assert all(value[key] for key in ['stale', 'quote', 'duplicate', 'omitted', 'verdict', 'emptyWitness'])


def test_body_worker_is_bounded_no_tool_and_preserves_complete_usage_on_refusal() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let inputs=[];
      const usage={input:20,output:10,cacheRead:0,cacheWrite:0,totalTokens:30,cost:0.001};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{inputs.push(input);return {exitCode:0,stderr:'',text:'not JSON',usage,usageLedger:{knownUsage:usage,assistantMessages:1,complete:true}}}}));
      const {reviewMemoryBodies}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const candidate={name:'fact.md',kind:'project',classification:'safe',content:'Complete body.'};
      const malformed=await reviewMemoryBodies({candidates:[candidate],retained:[],model:'fixture/model'});
      const bound=await reviewMemoryBodies({candidates:[{...candidate,content:'x'.repeat(65000)}],retained:[],maxRequestBytes:64_000});
      const targets=JSON.parse(inputs[0].prompt.split('\n').at(-1)).targets;
      console.log(JSON.stringify({malformed,bound:{status:bound.status,calls:bound.calls},calls:inputs.length,tools:inputs[0].tools,minimal:inputs[0].minimal,args:inputs[0].extraArgs,complete:targets[0].content===candidate.content}));
    ''')
    assert value['malformed']['status'] == 'invalid-response'
    assert value['malformed']['usage']['cost'] == 0.001
    assert value['malformed']['usageComplete']
    assert value['bound']['status'] == 'bounds' and value['bound']['calls'] == 0
    assert value['calls'] == 1 and value['tools'] == [] and value['minimal']
    assert value['args'][:2] == ['--thinking', 'xhigh'] and value['complete']
    assert value['args'][-4:] == ['--learning-output-schema', 'memory-body-review', '--learning-body-count', '1']


def test_parent_corrects_held_body_once_and_reviews_the_exact_replacement() -> None:
    from pathlib import Path
    from support import run_bun_script
    value = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'memory-apply', env={'CL_JEV_FIXTURE': 'body-correction'})
    assert value.get('bodyReviewCalls') == 2
    assert value['totalRepairs'] == 1
    assert value['registryReceipt']['operations'] == 1
    assert 'Never provide concise progress updates.' not in value['conciseMemory']
    assert 'Prefer concise progress updates.' in value['conciseMemory']
    body_attempts = [a for a in value['registryReceipt']['attempts'] if a.get('diagnostic', '').startswith('Independent Memory body review:')]
    assert [a['outcome'] for a in body_attempts] == ['proposed', 'noop']
    assert all(a['usage']['cost'] == 0.001 and a['usageComplete'] for a in body_attempts)


def test_complete_bodies_split_and_keep_each_call_cost_when_a_later_group_fails() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let requests=[];
      const usage={input:20,output:10,cacheRead:0,cacheWrite:0,totalTokens:30,cost:0.001};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        const targets=JSON.parse(input.prompt.split('\n').at(-1)).targets;requests.push({bytes:Buffer.byteLength(input.prompt),targets});
        if(requests.length===2)throw Error('interrupted');
        return {exitCode:0,usage,usageLedger:{knownUsage:usage,assistantMessages:1,complete:true},text:JSON.stringify({reviews:targets.map(t=>({targetIndex:t.targetIndex,verdict:'consistent',conflictingQuotes:[]}))})};
      }}));
      const {reviewMemoryBodies,memoryBodiesAllow}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const candidates=[0,1,2].map(i=>({name:`fact-${i}.md`,content:String(i)+'x'.repeat(40000)}));
      const result=await reviewMemoryBodies({candidates,retained:[],maxRequestBytes:64_000});
      console.log(JSON.stringify({status:result.status,calls:result.calls,allowed:memoryBodiesAllow(result),costs:result.batches.map(b=>({cost:b.usage?.cost,complete:b.usageComplete})),complete:requests.every((r,i)=>r.targets.length===1&&r.targets[0].content===candidates[i].content),maxBytes:Math.max(...requests.map(r=>r.bytes))}));
    ''')
    assert value['status'] == 'unavailable' and value['calls'] == 2 and not value['allowed']
    assert value['costs'] == [{'cost': 0.001, 'complete': True}, {'complete': False}]
    assert value['complete'] and value['maxBytes'] <= 64_000


def test_parent_retains_completed_source_and_body_costs_when_evidence_persistence_fails() -> None:
    from pathlib import Path
    from support import run_bun_script
    value = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'memory-apply', env={'CL_JEV_FIXTURE': 'body-artifact-failure'})
    receipt = value['registryReceipt']
    assert receipt['operations'] == 0
    source = [a for a in receipt['attempts'] if a.get('jev', {}).get('model') == 'jev-1.13.0']
    body = [a for a in receipt['attempts'] if a.get('diagnostic', '').startswith('Independent Memory body review:')]
    assert len(source) == 1 and source[0]['jev']['inputTokens'] == 10
    assert len(body) == 1 and body[0]['usage']['cost'] == 0.001


def test_parent_preserves_optional_judge_missing_key_behavior_without_claiming_body_review() -> None:
    from pathlib import Path
    from support import run_bun_script
    value = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'memory-apply', env={'CL_JEV_FIXTURE': 'body-missing-key'})
    assert value['registryReceipt']['operations'] == 1
    assert value['bodyReviewCalls'] == 0
    assert any(a.get('jev', {}).get('reason') == 'missing-key' for a in value['registryReceipt']['attempts'])


def test_invalid_body_response_retains_private_diagnostic_without_encoded_credentials() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const kit=await import('./packages/kit/src/index.ts');let raw='```json\n{"reviews":[]}\n```';
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>({exitCode:0,text:raw,usageLedger:{complete:true}})}));
      const {reviewMemoryBodies}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const dir=fs.mkdtempSync(path.join(os.tmpdir(),'body-response-'));
      try{
        const first=await reviewMemoryBodies({candidates:[{name:'fact.md',content:'Observed fact.'}],retained:[],outputDir:dir});
        let files=fs.readdirSync(dir).filter(n=>n.startsWith('memory-body-response-'));const file=files[0];
        const retained=file?JSON.parse(fs.readFileSync(path.join(dir,file),'utf8')):null;
        raw='{"reviews":[],"token":"'+String.raw`sk\u002d`+'abcdefghijklmnopqrstuvwx"}';
        await reviewMemoryBodies({candidates:[{name:'fact.md',content:'Observed fact.'}],retained:[],outputDir:dir});
        files=fs.readdirSync(dir).filter(n=>n.startsWith('memory-body-response-'));const second=files.find(n=>n!==file),redacted=second?JSON.parse(fs.readFileSync(path.join(dir,second),'utf8')):null;
        console.log(JSON.stringify({status:first.status,retained,privateMode:file?(fs.statSync(path.join(dir,file)).mode&0o777):null,redacted}));
      }finally{fs.rmSync(dir,{recursive:true,force:true})}
    ''')
    assert value['status'] == 'invalid-response'
    assert value['retained']['output'] == '```json\n{"reviews":[]}\n```'
    assert value['privateMode'] == 0o600
    assert value['redacted']['sensitive'] and 'output' not in value['redacted']


def test_body_model_selects_request_local_slots_instead_of_copying_parent_digests() -> None:
    value = isolated_run_bun(r'''
      const {prepareMemoryBodyTargets,bindMemoryBodySelections}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const targets=prepareMemoryBodyTargets([{name:'a.md',content:'Complete A.'},{name:'b.md',content:'Complete B.'}],[]);
      const input={reviews:[{targetIndex:1,verdict:'consistent',conflictingQuotes:[]},{targetIndex:0,verdict:'consistent',conflictingQuotes:[]}]};
      const bound=bindMemoryBodySelections(targets,input);
      const rejects=change=>{try{bindMemoryBodySelections(targets,change(structuredClone(input)));return false}catch{return true}};
      console.log(JSON.stringify({bound:bound.map(j=>j.id),expected:targets.map(t=>t.id),duplicate:rejects(r=>{r.reviews[0].targetIndex=0;return r}),foreign:rejects(r=>{r.reviews[0].targetIndex=2;return r}),digest:rejects(r=>{r.reviews[0].bodySha256=targets[0].bodySha256;return r})}));
    ''')
    assert value['bound'] == value['expected']
    assert value['duplicate'] and value['foreign'] and value['digest']


def test_actual_corrupted_id_response_remains_rejected_and_its_semantic_failure_is_preserved() -> None:
    value = isolated_run_bun(r'''
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-body-id-transcription.json').json();
      const {bindMemoryBodyJudgments,bindMemoryBodySelections}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      let oldRejected=false,newRejected=false;
      try{bindMemoryBodyJudgments([f.target],f.response)}catch{oldRejected=true}
      try{bindMemoryBodySelections([f.target],f.response)}catch{newRejected=true}
      console.log(JSON.stringify({oldRejected,newRejected,wrongSemanticVerdictRetained:f.response.reviews[0].verdict==='consistent',digestCopiedExactly:f.response.reviews[0].bodySha256===f.target.bodySha256,idChanged:f.response.reviews[0].id!==f.target.id}));
    ''')
    assert all(value.values())


def test_normal_body_review_sends_complete_large_body_without_local_byte_cap() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let complete=false,bytes=0;
      const content='Complete body. '+'x'.repeat(90000);
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        const targets=JSON.parse(input.prompt.split('\n').at(-1)).targets;complete=targets[0].content===content;bytes=Buffer.byteLength(input.prompt);
        return {exitCode:0,stderr:'',text:JSON.stringify({reviews:[{targetIndex:0,verdict:'consistent',conflictingQuotes:[]}]}),usageLedger:{complete:true}};
      }}));
      const {reviewMemoryBodies}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const review=await reviewMemoryBodies({candidates:[{name:'large.md',content}],retained:[]});
      console.log(JSON.stringify({status:review.status,calls:review.calls,complete,bytes}));
    ''')
    assert value['status'] == 'reviewed' and value['calls'] == 1
    assert value['complete'] and value['bytes'] > 64_000
