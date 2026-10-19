from support import isolated_run_bun


def test_complete_body_slots_are_required_without_choosing_the_verdict() -> None:
    # Given complete immutable bodies, When generating independent judgments,
    # Then require every slot exactly once; truth remains a parent judgment.
    value = isolated_run_bun(r'''
      import {Value} from 'typebox/value';import {createHash} from 'node:crypto';
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      import {prepareMemoryBodyTargets,bindMemoryBodySelections} from './packages/continual-learning/extensions/memory-body-review.ts';
      const targets=prepareMemoryBodyTargets([0,1,2].map(i=>({name:`fact-${i}.md`,content:`Complete body ${i}`})),[]);
      const schema=learningOutputSchema('memory-body-review',undefined,undefined,3);
      if(!schema)throw Error('Missing independent body output schema');
      const judgment={verdict:'consistent',conflictingQuotes:[],reason:'Internally consistent, not source proof'};
      const valid={reviews:{'0':judgment,'1':judgment,'2':judgment}};
      const invalid=[{reviews:{'0':judgment,'1':judgment}},
        {reviews:{...valid.reviews,'3':judgment}},
        {reviews:[{targetIndex:0,...judgment},{targetIndex:0,...judgment},{targetIndex:1,...judgment},{targetIndex:2,...judgment}]}];
      const bound=bindMemoryBodySelections(targets,valid);
      const reject=v=>{try{bindMemoryBodySelections(targets,v);return false}catch{return true}};
      const frozen=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-body-duplicate-selection.json').json();
      console.log(JSON.stringify({valid:Value.Check(schema,valid),invalid:invalid.map(v=>Value.Check(schema,v)),rejected:invalid.map(reject),
        frozenRejected:reject(JSON.parse(frozen.output)),frozenIntact:createHash('sha256').update(frozen.output).digest('hex')===frozen.responseSha256,
        bound:bound.map((b,i)=>b.id===targets[i].id&&b.verdict==='consistent'),
        uncertain:Value.Check(schema,{reviews:{...valid.reviews,'1':{...judgment,verdict:'uncertain'}}}),
        badCount:[undefined,0,33,1.5].map(n=>{try{learningOutputSchema('memory-body-review',undefined,undefined,n);return false}catch{return true}})}));
    ''')
    assert value['valid'] and value['uncertain'] and all(value['bound'])
    assert value['frozenRejected'] and value['frozenIntact']
    assert not any(value['invalid']) and all(value['rejected']) and all(value['badCount'])


def test_body_worker_loads_opt_in_contract_with_exact_parent_group_count() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let input;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async i=>{input=i;return {exitCode:0,text:JSON.stringify({reviews:{'0':{verdict:'consistent',conflictingQuotes:[],reason:'compatible'}}}),usageLedger:{complete:true}}}}));
      const {reviewMemoryBodies}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const result=await reviewMemoryBodies({candidates:[{name:'fact.md',content:'Full immutable body'}],retained:[]});
      const args=input.extraArgs;
      console.log(JSON.stringify({status:result.status,tools:input.tools,
        extension:args.some(v=>v.endsWith('/planner-json-output.ts')),
        kind:args[args.indexOf('--learning-output-schema')+1],
        count:args[args.indexOf('--learning-body-count')+1],
        complete:JSON.parse(input.prompt.split('\n').at(-1)).targets[0].content==='Full immutable body'}));
    ''')
    assert value['status'] == 'reviewed' and value['tools'] == [] and value['complete']
    assert value['extension'] and value['kind'] == 'memory-body-review' and value['count'] == '1'


def test_body_review_cannot_outlive_the_recorded_correction_budget() -> None:
    # Given an independent body reviewer that never answers, When the recorded
    # Memory correction budget expires, Then the reviewer is aborted and no
    # judgment is produced from the unresponsive worker.
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>new Promise((_resolve,reject)=>input.signal.addEventListener('abort',()=>reject(new Error('private worker abort'))))}));
      const {reviewMemoryBodies,MEMORY_CORRECTION_WORKER_DEADLINE_MS}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const timer=globalThis.setTimeout;let bound=null;
      globalThis.setTimeout=(fn,ms,...args)=>{if(ms===MEMORY_CORRECTION_WORKER_DEADLINE_MS){bound=ms;return timer(fn,10,...args)}return timer(fn,ms,...args)};
      const review=await reviewMemoryBodies({candidates:[{name:'fact.md',content:'Full immutable body'}],retained:[]});
      console.log(JSON.stringify({bound,recorded:MEMORY_CORRECTION_WORKER_DEADLINE_MS,status:review.status,judgments:review.judgments,calls:review.calls}));
    ''')
    assert value['recorded'] == 600000 and value['recorded'] > 230000
    assert value['bound'] == value['recorded']
    assert value['status'] == 'cancelled' and value['judgments'] == []
    assert 'private worker abort' not in str(value)
