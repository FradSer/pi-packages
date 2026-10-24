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


def test_coverage_accounts_bind_conditions_to_original_evidence_and_exact_body():
    # Given a reached failed check and a separately observed pending condition,
    # When the diagnosis names that condition but the record omits it,
    # Then exact citation/body binding cannot turn it into covered knowledge.
    value = isolated_run_bun(r'''
      import {prepareMemoryBodyTargets} from './packages/continual-learning/extensions/memory-body-review.ts';
      import {bindMemoryCoverageSelections} from './packages/continual-learning/extensions/memory-knowledge-coverage.ts';
      const evidence={contextEnabled:true,entries:[
        {role:'user',content:'Remember the observed failure with its applicability conditions.'},
        {role:'toolResult',content:'await reachedCheck;\nconst followUp = second.promise;\nassert.equal(early, false);\nfinally { second.resolve(); }',isError:false},
        {role:'toolResult',content:'AssertionError: true !== false',isError:true}]};
      const body='Observed: AssertionError: true !== false. Cause unresolved.';
      const targets=prepareMemoryBodyTargets([{name:'failure.md',content:body}],[]);
      const diagnosis={scope:{basis:'requested',statement:'The observed failure and its applicability conditions',evidence:[{ref:'e0.b0.l1'}]},
        claims:[{statement:'The verification failed',bodyQuote:'AssertionError: true !== false',evidence:[{ref:'e2.b0.l1'}],
          conditions:[{statement:'The follow-up depends on second.promise before cleanup releases it',bodyQuote:null,evidence:[{ref:'e1.b0.l2',endRef:'e1.b0.l4'}]}]}],
        uncovered:[{statement:'The known pending follow-up condition is absent from the record',evidence:[{ref:'e1.b0.l2',endRef:'e1.b0.l4'}]}],verdict:'incomplete'};
      const parse=(d=diagnosis,t=targets,s=evidence)=>bindMemoryCoverageSelections(t,s,[],{reviews:{'0':d}});
      const out=parse();
      const variants={inventedRef:d=>d.uncovered[0].evidence[0].ref='e99.b0.l1',
        assistantRef:d=>d.uncovered[0].evidence=[{ref:'e3.b0.l1'}],
        wrongRequestRole:d=>d.scope.evidence=[{ref:'e1.b0.l1'}],
        inventedBody:d=>d.claims[0].bodyQuote='fixed and verified',
        falseCovered:d=>{d.verdict='covered';d.uncovered=[]},
        emptyIncomplete:d=>d.uncovered=[],
        foreignField:d=>d.writeAuthorized=true,
        unsupportedPredecessor:d=>{d.scope.basis='predecessor';d.scope.evidence=[]},
        legacyQuote:d=>d.uncovered[0].evidence=[{index:1,quote:'const followUp = second.promise;'}],
        sensitive:d=>d.uncovered[0].statement='api_key="abcdefghijklmnopqrstuvwxyz0123456789"'};
      const bad={};for(const [key,mutate] of Object.entries(variants)){const d=structuredClone(diagnosis);mutate(d);
        try{parse(d,targets,{...evidence,entries:[...evidence.entries,{role:'assistant',content:'a guessed condition'}]});bad[key]=false}catch{bad[key]=true}}
      const optional=structuredClone(diagnosis);optional.scope.basis='optional';optional.scope.evidence=[{ref:'e1.b0.l1'}];
      const uncertain=structuredClone(diagnosis);uncertain.verdict='uncertain';uncertain.uncovered=[];
      // A reviewer can select an existing whitespace-only line. Keep the
      // rejection and its exact source location; do not guess another line.
      const blank=structuredClone(diagnosis);blank.claims[0].evidence=[{ref:'e1.b0.l5'}];
      let blankFailure;try{parse(blank,targets,{...evidence,entries:evidence.entries.map((entry,i)=>
        i===1?{...entry,content:entry.content+'\n    '}:entry)})}catch(error){blankFailure=error.bindingFailure}
      console.log(JSON.stringify({out,bad,blankFailure,optional:parse(optional)[0].scope.basis,uncertain:parse(uncertain)[0].verdict,
        frozen:targets[0].content===body,originalCount:evidence.entries.length}));
    ''')
    assert all(value['bad'].values()), value['bad']
    assert value['blankFailure'] == {'kind': 'invalid-original-source-reference', 'ref': 'e1.b0.l5'}
    account = value['out'][0]
    assert account['verdict'] == 'incomplete'
    assert account['claims'][0]['conditions'][0]['bodyWitness'] is None
    assert account['uncovered'][0]['evidence'][0]['index'] == 1
    assert 'second.promise' in account['uncovered'][0]['evidence'][0]['quote']
    assert value['optional'] == 'optional' and value['uncertain'] == 'uncertain'
    assert value['frozen'] and value['originalCount'] == 3
    assert 'writeAuthorized' not in account


def test_real_omission_stays_incomplete_even_with_literal_source_citations():
    # Frozen V102 evidence and record are unchanged. The selected reviewer answer
    # below is controlled: this tests the contract, never semantic detection.
    value = isolated_run_bun(r'''
      import {prepareMemoryBodyTargets} from './packages/continual-learning/extensions/memory-body-review.ts';
      import {bindMemoryCoverageSelections} from './packages/continual-learning/extensions/memory-knowledge-coverage.ts';
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      import {Value} from 'typebox/value';import {createHash} from 'node:crypto';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-failure-label-state-conflict.json').json();
      const c=f.coverageCase,s=c.evidence,source=s.entries[6].message.content[0].text;
      const record=c.rejectedPlan.newMemories.find(m=>m.name==='onidle_early_report_failure.md');
      const targets=prepareMemoryBodyTargets([record],[]);
      const ref={ref:'e6.b0.l1',endRef:'e6.b0.l51'};
      const diagnosis={scope:{basis:'optional',statement:'Observed failed check and its source-state conditions',evidence:[ref]},
        claims:[{statement:'The complete observed failure is limited to these source conditions',bodyQuote:record.content.split('\n---\n')[1].trim(),evidence:[ref],
          conditions:[{statement:'The follow-up adopts second.promise and second.resolve occurs after the failed check',bodyQuote:null,evidence:[ref]}]}],
        uncovered:[{statement:'The record omits the known unreleased follow-up condition',evidence:[ref]}],verdict:'incomplete'};
      // The full claim witness is larger than the bounded diagnostic selector.
      diagnosis.claims[0].bodyQuote=record.content.split('\n---\n')[1].trim().split('\n')[0];
      const raw={reviews:{'0':diagnosis}},schema=learningOutputSchema('memory-coverage-review',undefined,undefined,1);
      const out=bindMemoryCoverageSelections(targets,s,[],raw)[0];
      const wrong=structuredClone(raw);wrong.reviews['0'].verdict='covered';wrong.reviews['0'].uncovered=[];
      let refused=false;try{bindMemoryCoverageSelections(targets,s,[],wrong)}catch{refused=true}
      // A condition not named at all can escape shape checks. Only the separate
      // semantic coverage review of complete evidence can decide that omission.
      const omitted=structuredClone(wrong);omitted.reviews['0'].claims[0].conditions=[];
      const shapeOnly=bindMemoryCoverageSelections(targets,s,[],omitted)[0];
      console.log(JSON.stringify({valid:Value.Check(schema,{plan:{verdict:'covered',obligations:[]},...raw}),out,refused,shapeOnly:shapeOnly.verdict,
        sourcePreserved:source.includes('second.promise')&&source.indexOf('second.resolve()')>source.indexOf("'onIdle reported"),
        planUnchanged:createHash('sha256').update(JSON.stringify(c.rejectedPlan)).digest('hex')===c.provenance.planSha256,
        snapshotUnchanged:createHash('sha256').update(JSON.stringify(s,null,2)+'\n').digest('hex')===c.provenance.snapshotSha256,
        oldKeysPreserved:!!f.leanKnowledgeCase&&!!f.conditionedFailureCase}));
    ''')
    assert value['valid'] and value['sourcePreserved'] and value['oldKeysPreserved']
    assert value['planUnchanged'] and value['snapshotUnchanged']
    assert value['out']['verdict'] == 'incomplete' and value['refused']
    assert value['shapeOnly'] == 'covered'  # Explicit limit: this is not approval.
    assert value['out']['claims'][0]['conditions'][0]['bodyWitness'] is None


def test_separate_coverage_worker_keeps_complete_input_accounting_and_refusals():
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');const inputs=[];
      let response,mutate;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{inputs.push(input);mutate?.();return {
        exitCode:0,text:JSON.stringify(response),usage:{input:11,output:7,total:18,cost:0.01},usageLedger:{complete:false}}}}));
      const {reviewMemoryCoverage}=await import('./packages/continual-learning/extensions/memory-knowledge-coverage.ts');
      const {reviewMemoryBodies}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const {learningOutputSchema}=await import('./packages/continual-learning/extensions/planner-output-schema.ts');
      const {Value}=await import('typebox/value');
      const {createHash}=await import('node:crypto');
      const frozen=(await Bun.file('./packages/continual-learning/tests/fixtures/real-description-body-conflict.json').json()).coverageEmptyConditionsCase;
      const rejected=JSON.parse(frozen.output),explicit=structuredClone(rejected);
      const missing=explicit.reviews['0'].claims.flatMap((claim,index)=>Object.hasOwn(claim,'conditions')?[]:[index]);
      for(const index of missing)explicit.reviews['0'].claims[index].conditions=[];
      const accountSchema=learningOutputSchema('memory-coverage-review',undefined,undefined,1,undefined,true);
      const evidence={contextEnabled:true,entries:[{role:'user',content:'A project fact with one necessary condition.'}]};
      const candidates=[{name:'fact.md',content:'A project fact.'}];
      response={plan:{verdict:'covered',obligations:[]},reviews:{'0':{scope:{basis:'optional',statement:'A bounded project fact',evidence:[{ref:'e0.b0.l1'}]},
        claims:[{statement:'A project fact',evidence:[{ref:'e0.b0.l1'}],bodyQuote:'A project fact.',conditions:[]}],
        uncovered:[],verdict:'uncertain'}}};
      const input={candidates,retained:[],evidence,predecessors:[],plan:{operations:[],newMemories:candidates}};
      const uncertain=await reviewMemoryCoverage(input);
      const payload=JSON.parse(inputs[0].prompt.split('\n').at(-1));
      mutate=()=>evidence.entries.push({role:'user',content:'A later revocation'});
      const raced=await reviewMemoryCoverage(input);mutate=null;
      const before=inputs.length;
      const sensitive=await reviewMemoryCoverage({...input,evidence:{contextEnabled:true,entries:[{role:'user',content:{api_key:'abcdefghijklmnopqrstuvwxyz0123456789'}}]}});
      const bounded=await reviewMemoryCoverage({...input,maxRequestBytes:10});
      const refusedCalls=inputs.length-before;
      response={reviews:{'0':{verdict:'consistent',conflictingQuotes:[],reason:'Source blind body consistency'}}};
      const body=await reviewMemoryBodies({candidates,retained:[]});
      console.log(JSON.stringify({uncertain,raced,sensitive,bounded,refusedCalls,body,
        frozenAccount:{intact:createHash('sha256').update(frozen.output).digest('hex')===frozen.provenance.responseSha256,
          missing,expectedMissing:frozen.missingConditionsClaimIndexes,rejected:!Value.Check(accountSchema,rejected),
          explicitEmptyHasValidShape:Value.Check(accountSchema,explicit)},
        wireKind:inputs[0].extraArgs[inputs[0].extraArgs.indexOf('--learning-output-schema')+1],
        tools:inputs[0].tools,initialComplete:payload.frozenEvidence.entries.length===1,
        coverageGuidance:inputs[0].prompt.split('\n').slice(0,-1).join('\n'),
        unchangedText:payload.frozenEvidence.entries[0].entry.content.citationLines.lines[0].text,
        separateBody:!inputs.at(-1).prompt.includes('frozenEvidence')}));
    ''')
    assert value['uncertain']['status'] == 'reviewed'
    assert value['uncertain']['accounts'][0]['verdict'] == 'uncertain'
    assert value['uncertain']['calls'] == 1 and not value['uncertain']['usageComplete']
    assert value['uncertain']['usage']['cost'] == 0.01
    assert value['raced']['status'] == 'invalid-response' and value['raced']['calls'] == 1
    assert value['raced']['accounts'] == []
    assert value['sensitive']['status'] == 'invalid-response' and value['sensitive']['calls'] == 0
    assert value['bounded']['status'] == 'bounds' and value['bounded']['calls'] == 0
    assert value['refusedCalls'] == 0 and value['tools'] == [] and value['initialComplete']
    assert value['wireKind'] == 'memory-coverage-review'
    assert value['frozenAccount'] == {'intact': True, 'missing': [1, 3, 4], 'expectedMissing': [1, 3, 4],
                                      'rejected': True, 'explicitEmptyHasValidShape': True}
    assert value['body']['status'] == 'reviewed' and value['separateBody']
    assert value['unchangedText'] == 'A project fact with one necessary condition.'
    # Coverage must separate a task's report from a durable storage request,
    # while retaining conditions that make the nominated knowledge usable.
    assert 'A request to perform or report a task is not itself a request to store its results.' in value['coverageGuidance']
    assert 'Do not recursively expand every referenced type or member definition.' in value['coverageGuidance']
    assert 'Separate completed callbacks from work they start or return' in value['coverageGuidance']
    assert 'Every claim requires a conditions array; use [] only when no material condition is identified, never omit the key.' in value['coverageGuidance']
    # The observable worker contract must derive the scoped requirements from
    # original evidence before matching existing claims. This checks delivery,
    # not whether a real reviewer follows that order or improves later tasks.
    guidance = value['coverageGuidance']
    source_scope = guidance.find('First derive the necessary facts and relations within the target')
    body_match = guidance.find('Then compare these requirements and every actual claim')
    assert 0 <= source_scope < body_match
    paragraph = next(line for line in guidance.splitlines() if line.startswith('First derive'))
    assert len(paragraph) <= 1023
    for relation in ('whose resource or result is involved', 'which event changes its state',
                     'what stays unchanged', 'material default or selected branches'):
        assert paragraph.count(relation) == 1
    assert 'not an assumed exhaustive draft' in paragraph
    assert 'Keep optional nominations optional and omit unrelated facts.' in paragraph
    assert 'or null if missing' in paragraph
    assert 'An unknown cause does not erase an observed state' in paragraph
    assert 'guards and still-held work at the reached observation' in paragraph
    assert 'List the facts this record claims' not in guidance


def test_predecessor_coverage_binds_the_original_body_and_rejects_async_target_change():
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let input,mutate;
      const diagnosis={scope:{basis:'predecessor',statement:'Keep the existing documented condition',evidence:[],predecessorQuote:'Only during maintenance.'},
        claims:[{statement:'The documented condition',evidence:[{ref:'e0.b0.l1'}],bodyQuote:'Only during maintenance.',conditions:[]}],uncovered:[],verdict:'covered'};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async i=>{input=i;mutate?.();return {exitCode:0,text:JSON.stringify({plan:{verdict:'covered',obligations:[]},reviews:{'0':diagnosis}}),usageLedger:{complete:true}}}}));
      const {prepareMemoryBodyTargets}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const {bindMemoryCoverageSelections,reviewMemoryCoverage,memoryCoverageReviewDigest}=await import('./packages/continual-learning/extensions/memory-knowledge-coverage.ts');
      const evidence={contextEnabled:true,entries:[{role:'user',content:'Only during maintenance.'}]};
      const candidates=[{name:'fact.md',kind:'rewrite',content:'Only during maintenance.'}],targets=prepareMemoryBodyTargets(candidates,[]);
      const old=[{name:'fact.md',content:'Only during maintenance. Preserve this other fact.'}];
      const bind=p=>bindMemoryCoverageSelections(targets,evidence,p,{reviews:{'0':diagnosis}})[0];
      const first=bind(old),changed=bind([{name:'fact.md',content:old[0].content+' Additional restriction.'}]);
      const copy=structuredClone(diagnosis);delete copy.scope.predecessorQuote;
      let missing=false;try{bindMemoryCoverageSelections(targets,evidence,old,{reviews:{'0':copy}})}catch{missing=true}
      const plan={operations:candidates,newMemories:[]};
      const valid=await reviewMemoryCoverage({candidates,retained:[],evidence,predecessors:old,plan});
      const expectedPriorDigest=memoryCoverageReviewDigest(valid);
      const prior={priorPlan:valid.plan,priorEffectivePlan:structuredClone(plan),expectedPriorDigest};
      const correctedCandidates=[{...candidates[0],content:candidates[0].content+' Added a condition.'}];
      const repaired=await reviewMemoryCoverage({candidates:correctedCandidates,plan:{operations:correctedCandidates,newMemories:[]},
        retained:[],evidence,predecessors:old,priorAccounts:[first],priorTargets:targets,...prior});
      const badPrior=await reviewMemoryCoverage({candidates,retained:[],evidence,predecessors:old,plan,...prior,priorAccounts:[first],
        priorTargets:[{...targets[0],content:'An unbound prior body'}],expectedPriorDigest});
      const forgedAccount=structuredClone(first);forgedAccount.scope.statement='A different old obligation';
      const badAccount=await reviewMemoryCoverage({candidates,retained:[],evidence,predecessors:old,plan,...prior,priorAccounts:[forgedAccount],
        priorTargets:targets,expectedPriorDigest});
      mutate=()=>candidates[0].content='A racing replacement';
      const raced=await reviewMemoryCoverage({candidates,retained:[],evidence,predecessors:old,plan});
      console.log(JSON.stringify({first,changed,missing,valid,repaired,badPrior,badAccount,raced}));
    ''')
    assert value['first']['contextDigest'] != value['changed']['contextDigest']
    assert value['first']['predecessor']['bodySha256'] != value['changed']['predecessor']['bodySha256']
    assert value['first']['predecessor']['witness'] == {'start': 0, 'end': len('Only during maintenance.')}
    assert value['missing'] and value['valid']['status'] == 'reviewed'
    assert value['repaired']['status'] == 'reviewed'
    assert value['badPrior']['status'] == 'invalid-response' and value['badPrior']['calls'] == 0
    assert value['badAccount']['status'] == 'invalid-response' and value['badAccount']['calls'] == 0
    assert value['raced']['status'] == 'invalid-response' and value['raced']['accounts'] == []


def test_whole_plan_coverage_cannot_skip_an_empty_explicit_request():
    # Given a complete task with a requested fact and no proposed/retained body,
    # When reviewing coverage, Then a required plan slot must still be reviewed.
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let called=0,prompt;
      const planAccount={verdict:'incomplete',obligations:[{basis:'requested',statement:'Remember the named project fact',
        evidence:[{ref:'e0.b0.l1'}],coveredBy:[],status:'missing'}]};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{called++;prompt=input.prompt;return {
        exitCode:0,text:JSON.stringify({plan:planAccount,reviews:{}}),usageLedger:{complete:true}}}}));
      const {reviewMemoryCoverage}=await import('./packages/continual-learning/extensions/memory-knowledge-coverage.ts');
      const evidence={contextEnabled:true,entries:[{role:'user',content:'Remember the project fact: alpha uses beta.'}]};
      const plan={operations:[],newMemories:[]};
      const result=await reviewMemoryCoverage({candidates:[],retained:[],evidence,predecessors:[],plan});
      console.log(JSON.stringify({result,called,completeEvidence:prompt?.includes('alpha uses beta')}));
    ''')
    assert value['called'] == 1 and value['completeEvidence']
    assert value['result']['status'] == 'reviewed'
    assert value['result']['plan']['verdict'] == 'incomplete'
    assert value['result']['plan']['obligations'][0]['status'] == 'missing'
    assert value['result']['accounts'] == []


def test_plan_coverage_binds_every_candidate_and_rejects_invalid_witnesses():
    # Given two proposed bodies and a separate requested goal, When one record
    # account is valid, Then it cannot hide the missing plan obligation or slot.
    value = isolated_run_bun(r'''
      import {Value} from 'typebox/value';
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      import {prepareMemoryBodyTargets} from './packages/continual-learning/extensions/memory-body-review.ts';
      import {bindMemoryPlanCoverage} from './packages/continual-learning/extensions/memory-knowledge-coverage.ts';
      const evidence={contextEnabled:true,entries:[{role:'user',content:'Remember alpha and beta.'},
        {role:'toolResult',content:'alpha was observed.\nbeta was observed.'},
        {role:'assistant',content:'Store a different fact.'}]};
      const candidates=[{name:'alpha.md',content:'alpha was observed.'},{name:'beta.md',content:'beta was observed.'}];
      const plan={operations:[],newMemories:candidates},targets=prepareMemoryBodyTargets(candidates,[]);
      const required={basis:'requested',statement:'Remember beta',evidence:[{ref:'e0.b0.l1'}],coveredBy:[],status:'missing'};
      const raw={plan:{verdict:'incomplete',obligations:[required]},reviews:{'0':{},'1':{}}};
      const parse=(r=raw,t=targets,p=plan)=>bindMemoryPlanCoverage(t,evidence,[],p,r);
      const bound=parse();const rejected={};
      const variants={noPlan:r=>delete r.plan,extra:r=>r.authorized=true,missingSlot:r=>delete r.reviews['1'],
        wrongUser:r=>r.plan.obligations[0].evidence=[{ref:'e1.b0.l1'}],
        badRef:r=>r.plan.obligations[0].evidence=[{ref:'e99.b0.l1'}],
        badCovered:r=>r.plan.verdict='covered',coveredNoWitness:r=>{r.plan.verdict='covered';r.plan.obligations[0].status='covered'},
        wrongBody:r=>{r.plan.obligations[0].coveredBy=[{targetIndex:1,bodyQuote:'never observed'}]},
        guessedTarget:r=>{r.plan.obligations[0].coveredBy=[{targetIndex:2,bodyQuote:'alpha was observed.'}]},
        assistantSource:r=>{r.plan.obligations[0].coveredBy=[{sourceEvidence:[{ref:'e2.b0.l1'}]}]},
        foreignPredecessor:r=>{r.plan.obligations[0].basis='predecessor';r.plan.obligations[0].evidence=[];
          r.plan.obligations[0].predecessorName='missing.md';r.plan.obligations[0].predecessorQuote='A previous obligation'}};
      for(const [key,change] of Object.entries(variants)){const r=structuredClone(raw);change(r);try{parse(r);rejected[key]=false}catch{rejected[key]=true}}
      let omitted=false;try{parse({...raw,reviews:{'0':{}}},targets.slice(0,1))}catch{omitted=true}
      const actual=structuredClone(raw);actual.plan.verdict='covered';actual.plan.obligations[0].status='covered';
      actual.plan.obligations[0].coveredBy=[{targetIndex:1,bodyQuote:'beta was observed.'}];
      const resolved=parse(actual);const source=structuredClone(actual);source.plan.obligations[0].coveredBy=[{sourceEvidence:[{ref:'e1.b0.l2'}]}];
      let sourceRejected=false;try{parse(source)}catch{sourceRejected=true}
      const empty={operations:[],newMemories:[]},emptyResponse={plan:{verdict:'covered',obligations:[]},reviews:{}};
      const optional=bindMemoryPlanCoverage([],evidence,[],empty,emptyResponse);
      console.log(JSON.stringify({bound,rejected,omitted,resolved,sourceRejected,optional,
        emptySchema:Value.Check(learningOutputSchema('memory-coverage-review',undefined,undefined,0),emptyResponse)}));
    ''')
    assert all(value['rejected'].values()), value['rejected']
    assert value['omitted']
    assert value['bound']['verdict'] == 'incomplete'
    assert value['resolved']['obligations'][0]['coveredBy'][0]['name'] == 'beta.md'
    assert value['sourceRejected']
    assert value['optional']['obligations'] == [] and value['emptySchema']


def test_coverage_rejects_a_partial_plan_before_worker_transport():
    # Given a caller omits one actual planned body, When preparing the worker,
    # Then no transport can present partial record coverage as a full review.
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let calls=0;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{calls++;return {exitCode:0,
        text:JSON.stringify({plan:{verdict:'covered',obligations:[]},reviews:{}}),usageLedger:{complete:true}}}}));
      const {reviewMemoryCoverage}=await import('./packages/continual-learning/extensions/memory-knowledge-coverage.ts');
      const evidence={contextEnabled:true,entries:[{role:'user',content:'Remember alpha and beta.'}]};
      const alpha={name:'alpha.md',content:'alpha'},beta={name:'beta.md',content:'beta'};
      const result=await reviewMemoryCoverage({candidates:[alpha],retained:[],evidence,predecessors:[],
        plan:{operations:[],newMemories:[alpha,beta]}});
      console.log(JSON.stringify({calls,result}));
    ''')
    assert value['calls'] == 0
    assert value['result']['status'] == 'invalid-response'


def test_empty_plan_review_keeps_cancellation_failure_and_original_plan_binding():
    # Given the plan account still runs with no record bodies, When it fails,
    # is cancelled or races, Then it grants no coverage and retains spent usage.
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const output=fs.mkdtempSync(path.join(os.tmpdir(),'coverage-binding-race-'));
      const kit=await import('./packages/kit/src/index.ts');let calls=0,mode='valid',inputPlan;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{calls++;
        if(mode==='race') inputPlan.newMemories.push({name:'raced.md',content:'A new live body'});
        if(mode==='evidence-race') evidence.entries[0].content='Changed original source';
        if(mode==='cancel') {await new Promise(resolve=>input.signal.addEventListener('abort',resolve));throw Error('private abort detail')}
        return {exitCode:mode==='failed'?1:0,text:JSON.stringify({plan:{verdict:'covered',obligations:[]},reviews:{}}),
          usage:{input:5,output:2,cacheRead:0,cacheWrite:0,totalTokens:7,cost:.01},usageLedger:{complete:true}}}}));
      const {reviewMemoryCoverage}=await import('./packages/continual-learning/extensions/memory-knowledge-coverage.ts');
      const evidence={contextEnabled:true,entries:[{role:'user',content:'Inspect the source only. Do not save memory.'}]};
      const review=async(signal)=>{evidence.entries[0].content='Inspect the source only. Do not save memory.';inputPlan={operations:[],newMemories:[]};return reviewMemoryCoverage({candidates:[],retained:[],evidence,predecessors:[],plan:inputPlan,signal,outputDir:output})};
      const valid=await review();mode='failed';const failed=await review();mode='race';const raced=await review();
      mode='evidence-race';const evidenceRaced=await review();
      const stopped=new AbortController();stopped.abort();const before=calls,early=await review(stopped.signal),earlyCalls=calls-before;
      mode='cancel';const controller=new AbortController();const promise=review(controller.signal);setTimeout(()=>controller.abort(),10);const cancelled=await promise;
      fs.rmSync(output,{recursive:true});
      console.log(JSON.stringify({valid,failed,raced,evidenceRaced,early,earlyCalls,cancelled}));
    ''')
    assert value['valid']['status'] == 'reviewed' and value['valid']['plan']['obligations'] == []
    assert value['failed']['status'] == 'unavailable' and 'plan' not in value['failed']
    assert value['failed']['usage']['cost'] == .01 and value['failed']['calls'] == 1
    assert value['raced']['status'] == 'invalid-response' and 'plan' not in value['raced']
    assert value['raced']['usage']['cost'] == .01 and value['raced']['calls'] == 1
    assert value['evidenceRaced']['status'] == 'invalid-response'
    assert value['evidenceRaced']['usage']['cost'] == .01
    assert all(not value[key].get('diagnosticContinuation') for key in ['failed', 'raced', 'evidenceRaced', 'early', 'cancelled'])
    assert value['early']['status'] == 'cancelled' and value['earlyCalls'] == 0
    assert value['cancelled']['status'] == 'cancelled' and value['cancelled']['calls'] == 1
    assert 'private abort detail' not in str(value)


def test_deleted_or_replaced_memory_cannot_be_a_retained_coverage_witness():
    # Given an operation removes or replaces an old record, When coverage calls
    # that old body retained, Then refuse it before transport and at binding.
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let calls=0;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{calls++;return {exitCode:1,usageLedger:{complete:true}}}}));
      const {prepareMemoryBodyTargets}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const {bindMemoryPlanCoverage,reviewMemoryCoverage}=await import('./packages/continual-learning/extensions/memory-knowledge-coverage.ts');
      const evidence={contextEnabled:true,entries:[{role:'user',content:'Remember the still-required fact.'}]};
      const old={name:'fact.md',content:'The still-required fact.'};const results=[];
      for(const op of [{name:'fact.md',kind:'delete',preservedIn:['new.md']},
          {name:'fact.md',kind:'rewrite',content:'Replacement without the old fact.'}]){
        const plan={operations:[op],newMemories:[]},targets=prepareMemoryBodyTargets([op],[old]);
        const raw={plan:{verdict:'covered',obligations:[{basis:'requested',statement:'Keep the fact',evidence:[{ref:'e0.b0.l1'}],
          coveredBy:[{targetIndex:targets.length-1,bodyQuote:old.content}],status:'covered'}]},reviews:Object.fromEntries(targets.map((_,i)=>[i,{}]))};
        let rejected=false;try{bindMemoryPlanCoverage(targets,evidence,[old],plan,raw)}catch{rejected=true}
        const result=await reviewMemoryCoverage({candidates:[op],retained:[old],evidence,predecessors:[old],plan});
        results.push({rejected,status:result.status});
      }
      console.log(JSON.stringify({results,calls}));
    ''')
    assert value['calls'] == 0
    assert all(item['rejected'] and item['status'] == 'invalid-response' for item in value['results'])


def test_prior_retained_diagnosis_survives_a_bound_current_rewrite():
    # Given a frozen diagnosis for a retained record, When the parent proposes
    # a same-name correction, Then its old account remains a question bound to
    # the complete old bytes, even though the current target is a candidate.
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let calls=0;
      const answer={plan:{verdict:'covered',obligations:[]},reviews:{'0':{scope:{basis:'predecessor',statement:'Keep the documented limit',
        evidence:[],predecessorQuote:'Only during maintenance.'},claims:[{statement:'The documented limit',bodyQuote:'Only during maintenance.',
        evidence:[{ref:'e0.b0.l1'}],conditions:[]}],uncovered:[],verdict:'uncertain'}}};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{calls++;return {exitCode:0,text:JSON.stringify(answer),usageLedger:{complete:true}}}}));
      const {reviewMemoryCoverage,memoryCoverageReviewDigest}=await import('./packages/continual-learning/extensions/memory-knowledge-coverage.ts');
      const evidence={contextEnabled:true,entries:[{role:'user',content:'Only during maintenance.'}]};
      const existing=[{name:'fact.md',content:'Only during maintenance.'}],plan={operations:[],newMemories:[]};
      const prior=await reviewMemoryCoverage({candidates:[],retained:existing,evidence,predecessors:existing,plan});
      const candidates=[{name:'fact.md',kind:'rewrite',content:'Only during maintenance. A source-backed correction.'}];
      const result=await reviewMemoryCoverage({candidates,retained:[],evidence,predecessors:existing,
        plan:{operations:candidates,newMemories:[]},priorAccounts:prior.accounts,priorTargets:prior.targets,priorPlan:prior.plan,
        priorEffectivePlan:plan,expectedPriorDigest:memoryCoverageReviewDigest(prior)});
      console.log(JSON.stringify({calls,prior:prior.status,result}));
    ''')
    assert value['prior'] == 'reviewed'
    assert value['result']['status'] == 'reviewed' and value['calls'] == 2


def test_coverage_preserves_an_admitted_legacy_plan_without_new_memories_field():
    # The existing parent normalizer permits an omitted empty newMemories list.
    # Coverage must bind its actual bytes, never insert a missing field or skip it.
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';import {createHash} from 'node:crypto';const kit=await import('./packages/kit/src/index.ts');let calls=0;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{calls++;return {exitCode:0,
        text:JSON.stringify({plan:{verdict:'covered',obligations:[]},reviews:{}}),usageLedger:{complete:true}}}}));
      const {reviewMemoryCoverage}=await import('./packages/continual-learning/extensions/memory-knowledge-coverage.ts');
      const {normalizeNewMemoryProposals}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const evidence={contextEnabled:true,entries:[{role:'user',content:'Keep the existing records.'}]},plan={kind:'memory-consolidation-plan',operations:[]};
      const normalized=normalizeNewMemoryProposals(plan,evidence);
      const result=await reviewMemoryCoverage({candidates:normalized,retained:[],evidence,predecessors:[],plan});
      console.log(JSON.stringify({result,calls,unchanged:!Object.hasOwn(plan,'newMemories'),digest:createHash('sha256').update(JSON.stringify(plan)).digest('hex')}));
    ''')
    assert value['result']['status'] == 'reviewed' and value['calls'] == 1
    assert value['unchanged'] and value['result']['plan']['planDigest'] == value['digest']


def test_body_reference_witnesses_cannot_select_source_or_another_record() -> None:
    """Given V121's source/body wording difference, When selecting a witness, Then only body positions bind."""
    from support import run_bun
    result = run_bun(r'''
      import {prepareMemoryBodyTargets} from './packages/continual-learning/extensions/memory-body-review.ts';
      import {bindMemoryCoverageSelections,bindMemoryPlanCoverage,memoryCoveragePrompt} from './packages/continual-learning/extensions/memory-knowledge-coverage.ts';
      const {learningOutputSchema}=await import('./packages/continual-learning/extensions/planner-output-schema.ts');
      const body='---\nname: failure\ndescription: observed failure\ntype: project\n---\nThe command exits with code 1.';
      const targets=prepareMemoryBodyTargets([{name:'failure.md',content:body}],[]);
      const evidence={contextEnabled:true,entries:[{role:'user',content:'Remember the failure.'},{role:'toolResult',content:'Command exited with code 1'}]};
      const account={scope:{basis:'requested',statement:'Failure',evidence:[{ref:'e0.b0.l1'}]},claims:[{statement:'Failure was observed',evidence:[{ref:'e1.b0.l1'}],bodyQuote:{ref:'m0.b0.l6'},conditions:[]}],uncovered:[],verdict:'covered'};
      const bind=a=>bindMemoryCoverageSelections(targets,evidence,[],{reviews:{'0':a}},'reference');
      const good=bind(account);const denied=[];
      for(const quote of ['Command exited with code 1',{ref:'e1.b0.l1'},{ref:'m1.b0.l6'},{ref:'m0.b0.l99'},{ref:'m0.b0.l6',endRef:'e1.b0.l1'},
        {ref:'m0.b0.l3'},{ref:'m0.b0.l3',endRef:'m0.b0.l6'},{ref:'m0.b0.l5',endRef:'m0.b0.l6'}]){const a=structuredClone(account);a.claims[0].bodyQuote=quote;try{bind(a);denied.push(false)}catch{denied.push(true)}}
      const condition=structuredClone(account);condition.claims[0].conditions=[{statement:'Observed failure',evidence:[{ref:'e1.b0.l1'}],bodyQuote:{ref:'m0.b0.l3'}}];
      let metadataConditionRejected=false;try{bind(condition)}catch{metadataConditionRejected=true}
      const bomTargets=prepareMemoryBodyTargets([],[{name:'failure.md',content:'\uFEFF'+body}]);
      const bom=structuredClone(account);bom.claims[0].bodyQuote={ref:'m0.b0.l3'};
      let bomMetadataRejected=false;try{bindMemoryCoverageSelections(bomTargets,evidence,[],{reviews:{'0':bom}},'reference')}catch{bomMetadataRejected=true}
      const bomBody=bindMemoryCoverageSelections(bomTargets,evidence,[],{reviews:{'0':account}},'reference')[0].claims[0].bodyWitness;
      const plan={operations:[],newMemories:[{name:'failure.md',content:body}]};
      const raw={plan:{verdict:'covered',obligations:[{basis:'requested',statement:'Remember failure',evidence:[{ref:'e0.b0.l1'}],
        coveredBy:[{targetIndex:0,bodyQuote:{ref:'m0.b0.l3'}}],status:'covered'}]},reviews:{'0':account}};
      let metadataPlanRejected=false;try{bindMemoryPlanCoverage(targets,evidence,[],plan,raw,'reference')}catch{metadataPlanRejected=true}
      raw.plan.obligations[0].coveredBy[0].bodyQuote={ref:'m0.b0.l6'};
      const actualPlan=bindMemoryPlanCoverage(targets,evidence,[],plan,raw,'reference');
      const foreign=structuredClone(account);foreign.claims[0].evidence=[{ref:'m0.b0.l6'}];try{bind(foreign);denied.push(false)}catch{denied.push(true)}
      const schema=learningOutputSchema('memory-coverage-review',undefined,undefined,1,undefined,true);
      const sourcePattern=schema.properties.reviews.properties['0'].properties.claims.items.properties.evidence.items.properties.ref.pattern;
      const acceptedSources=['e0.b0.l1','e12.b3.p7','e1.b0.l2.c512-1024'].map(ref=>new RegExp(sourcePattern).test(ref));
      const refusedSources=['m0.b0.l6','p0.b0.l6','e0.b0.l0','anything'].map(ref=>!new RegExp(sourcePattern).test(ref));
      const prompt=memoryCoveragePrompt(targets,evidence,[],[],[],{operations:[],newMemories:[]},undefined,undefined,'reference');
      console.log(JSON.stringify({good,denied,prompt,acceptedSources,refusedSources,metadataConditionRejected,metadataPlanRejected,actualPlan,bomMetadataRejected,bomBody,bomBodyStart:body.indexOf('The command')+1}));
    ''')
    assert all(result['denied'])
    assert result['metadataConditionRejected'] and result['metadataPlanRejected']
    assert result['bomMetadataRejected']
    assert result['bomBody']['start'] == result['bomBodyStart']
    assert result['actualPlan']['verdict'] == 'covered'
    assert result['good'][0]['claims'][0]['bodyWitness']['start'] > 0
    assert 'm0.b0.l6' in result['prompt']

    assert all(result['acceptedSources']) and all(result['refusedSources'])
    assert '"ref":"original ref"' not in result['prompt']
    assert 'knowledge body after frontmatter' in result['prompt']
    assert '"bodyQuote":{"ref":"m0.b0.l6"}' in result['prompt']

def test_body_reference_preserves_duplicate_crlf_and_chunk_positions() -> None:
    from live_learning_loop import controlled_body_reference

    controlled = '\ufeff---\r\nname: fact\r\ndescription: Repeated fact.\r\ntype: project\r\n---\r\n\r\nRepeated fact.'
    assert controlled_body_reference(controlled, 'Repeated fact.', 'm0') == {'ref': 'm0.b0.l7'}
    result = isolated_run_bun(r'''
      import {prepareMemoryBodyTargets} from './packages/continual-learning/extensions/memory-body-review.ts';
      import {bindMemoryCoverageSelections,memoryCoveragePrompt} from './packages/continual-learning/extensions/memory-knowledge-coverage.ts';
      const evidence={contextEnabled:true,entries:[{role:'toolResult',content:'Observed fact.'}]};
      const bind=(body,ref,endRef)=>{const targets=prepareMemoryBodyTargets([{name:'fact.md',content:body}],[]);return bindMemoryCoverageSelections(targets,evidence,[],{reviews:{'0':{scope:{basis:'optional',statement:'Fact',evidence:[{ref:'e0.b0.l1'}]},claims:[{statement:'Fact',evidence:[{ref:'e0.b0.l1'}],bodyQuote:{ref,...(endRef?{endRef}:{})},conditions:[]}],uncovered:[],verdict:'covered'}}},'reference')[0].claims[0].bodyWitness};
      const repeated='Repeated fact.\r\nOther context.\r\nRepeated fact.';
      const duplicate=bind(repeated,'m0.b0.l3');const multiline=bind(repeated,'m0.b0.l2','m0.b0.l3');
      const line='x'.repeat(3072);const chunked='Header😀\r\n'+line;
      const chunk=bind(chunked,'m0.b0.l2.c512-1024');
      const header='---\r\nname: fact\r\ndescription: Repeated fact.\r\ntype: project\r\n---\r\n\r\nRepeated fact.';
      const headerDuplicate=bind(header,'m0.b0.l7');
      const targets=prepareMemoryBodyTargets([{name:'fact.md',content:header}],[]);
      const prompt=memoryCoveragePrompt(targets,evidence,[],[],[],{operations:[],newMemories:[]},undefined,undefined,'reference');
      const missingPrompts=['','   ','---\nname: fact\n---','\uFEFF---\nname: fact\n---','---\r\nname: fact\r\n---\r\n   \r\n'].map(content=>
        memoryCoveragePrompt(prepareMemoryBodyTargets([{name:'fact.md',content}],[]),evidence,[],[],[],{operations:[],newMemories:[]},undefined,undefined,'reference'));
      console.log(JSON.stringify({duplicate,expected:repeated.lastIndexOf('Repeated fact.'),multiline,multilineStart:repeated.indexOf('Other context.'),chunk,chunkStart:chunked.indexOf(line)+512,
        headerDuplicate,headerExpected:header.lastIndexOf('Repeated fact.'),prompt,missingPrompts}));
    ''')
    assert result['duplicate']['start'] == result['expected']
    assert result['multiline']['start'] == result['multilineStart']
    assert result['chunk']['start'] == result['chunkStart']
    assert result['headerDuplicate']['start'] == result['headerExpected']
    assert '"bodyQuote":{"ref":"m0.b0.l7"}' in result['prompt']
    for prompt in result['missingPrompts']:
        assert '"bodyQuote":null' in prompt and '"coveredBy":[]' in prompt
        assert '"bodyQuote":{"ref":"m0.b0.l1"}' not in prompt


def test_parent_memory_phase_reaches_account_worker_and_jev_without_overriding_holds():
    # Controlled responses prove exact phase delivery and unchanged gates only.
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let worker;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{worker=input;return {exitCode:0,text:JSON.stringify({
        plan:{verdict:'covered',obligations:[]},reviews:{'0':{scope:{basis:'optional',statement:'Observed fact',evidence:[{ref:'e1.b0.l1'}]},
        claims:[{statement:'Observed source fact.',evidence:[{ref:'e1.b0.l1'}],bodyQuote:'Observed source fact.',conditions:[]}],uncovered:[],verdict:'covered'}}}),usageLedger:{complete:true}}}}));
      const {captureMemoryCommandPhase,captureConsolidationSnapshot,resolveConsolidationRunPaths}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const {manualMemoryTaskSlice}=await import('./packages/continual-learning/extensions/learning-input.ts');
      const {reviewMemoryCoverage,memoryCoverageReviewDigest}=await import('./packages/continual-learning/extensions/memory-knowledge-coverage.ts');
      const {createJevJudge}=await import('./packages/continual-learning/extensions/jev-learning.ts');
      const fs=await import('node:fs/promises'),os=await import('node:os'),path=await import('node:path');
      const cwd=await fs.mkdtemp(path.join(os.tmpdir(),'phase-wire-'));
      try {
        const task=manualMemoryTaskSlice('organize memory',[{role:'user',content:'Only edit examples. Do not edit Memory directly. Never remember temporary tokens.'},{role:'toolResult',content:'Observed source fact.'}]);
        const ctx={cwd,sessionManager:{getBranch:()=>task.entries}},phase=captureMemoryCommandPhase(ctx,'organize memory',task);
        const {snapshot:evidence}=await captureConsolidationSnapshot(ctx,resolveConsolidationRunPaths(cwd,'run_wire'),undefined,undefined,phase);
        const candidates=[{name:'fact.md',kind:'project',classification:'safe',content:'Observed source fact.',evidence:[{index:1,quote:'Observed source fact.'}]}];
        const plan={operations:[],newMemories:candidates};
        const review=await reviewMemoryCoverage({candidates,retained:[],evidence,predecessors:[],plan});
        const context={protocol:'memory-knowledge-coverage-v2',questionContractVersion:2,plan,review,expectedReviewDigest:memoryCoverageReviewDigest(review)};
        const calls=[];let hold=false;
        const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_u,init)=>{
          const r=JSON.parse(init.body);calls.push(r);return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{
            const positive=key.startsWith('coverage_')?'complete':key.startsWith('supported_')?'grounded':key.startsWith('relation_')?'unrelated':'compatible';
            const p=hold&&key==='coverage_plan'?.89:1;
            return[key,{type:'choice',choice:positive,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===positive?p:k==='missing'?1-p:0]))}];
          }))}));
        }});
        const accepted=await judge.validate('memory',evidence,candidates,[],undefined,undefined,undefined,undefined,undefined,context);
        const firstCalls=[...calls];hold=true;
        const held=await judge.validate('memory',evidence,candidates,[],undefined,undefined,undefined,undefined,undefined,context);
        console.log(JSON.stringify({accepted,held,worker:JSON.parse(worker.prompt.split('\n').at(-1)),workerGuidance:worker.prompt.split('\n')[0],
          coverage:firstCalls.filter(r=>'coverage_plan'in r.questions),phase:evidence.currentMemoryCommandPhase,
          sourceOriginal:evidence.entries[0]}));
      } finally {await fs.rm(cwd,{recursive:true,force:true});}
    ''')
    assert value['accepted']['decision']=='allow', value['accepted']
    assert value['held']['decision']=='propose'
    assert value['worker']['currentMemoryCommandPhase']==value['phase']
    assert value['coverage'] and all(r['state']['currentMemoryCommandPhase']==value['phase'] for r in value['coverage'])
    assert 'Never remember temporary tokens.' in value['sourceOriginal']['content']
    assert 'privacy restrictions' in value['workerGuidance']
    for request in value['coverage']:
        for question in request['questions'].values():
            assert question['instructions'].count('currentMemoryCommandPhase binds')==1


def test_failed_review_retains_only_safe_terminal_metadata_without_accepting_text() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const kit=await import('./packages/kit/src/index.ts');let calls=0;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{calls++;return {exitCode:1,text:'',stderr:'PRIVATE',
        terminal:{kind:'model-error',nativeExitCode:0,errorMessage:'PRIVATE',thinking:'PRIVATE'},
        usageLedger:{complete:false,assistantMessages:1,knownUsage:{input:0,output:0}}}}}));
      const {runMemoryReviewBatch,reviewMemoryBodies}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'memory-terminal-'));
      const results=[];const artifacts=[];
      for(const kind of ['memory-body-review','memory-coverage-review']){
        const dir=path.join(root,kind);fs.mkdirSync(dir);
        results.push(await runMemoryReviewBatch({prompt:'inspect',signal:new AbortController().signal,kind,count:1,outputDir:dir}));
        artifacts.push(JSON.parse(fs.readFileSync(path.join(dir,fs.readdirSync(dir).find(name=>name.includes('-response-'))),'utf8')));
      }
      const review=await reviewMemoryBodies({candidates:[{name:'fact.md',content:'Full immutable body'}],retained:[]});
      fs.rmSync(root,{recursive:true,force:true});console.log(JSON.stringify({calls,results,artifacts,review}));
    ''')
    expected = {'kind': 'model-error', 'nativeExitCode': 0}
    assert value['calls'] == 3
    for result, artifact in zip(value['results'], value['artifacts']):
        assert result['status'] == 'unavailable' and result['usageComplete'] is False
        assert 'text' not in result and result['terminal'] == expected
        assert artifact['output'] == '' and artifact['terminal'] == expected
        assert artifact['responseSha256'] == 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    assert value['review']['status'] == 'unavailable' and value['review']['judgments'] == []
    assert value['review']['batches'][0]['terminal'] == expected
    assert 'PRIVATE' not in str(value)


def test_malformed_terminal_values_are_omitted_without_serializing_private_values() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const kit=await import('./packages/kit/src/index.ts');let terminal;let exitCode=1;let calls=0;let serialized=0;
      const privateObject={toJSON(){serialized++;throw Error('PRIVATE must not serialize')}};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{calls++;return {exitCode,text:'',terminal,
        usageLedger:{complete:false,assistantMessages:1,knownUsage:{input:0,output:0}}}}}));
      const {runMemoryReviewBatch}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'memory-invalid-terminal-'));
      const values=['PRIVATE',privateObject,null,[],
        {kind:'PRIVATE',nativeExitCode:0},{kind:privateObject,nativeExitCode:0},
        ...['PRIVATE',privateObject,undefined,true,-1,256,1.5,NaN,Infinity].map(nativeExitCode=>({kind:'model-error',nativeExitCode}))];
      const rows=[];
      try {for(const [index,item] of values.entries()){
        terminal=item;const dir=path.join(root,String(index));fs.mkdirSync(dir);
        const result=await runMemoryReviewBatch({prompt:'inspect',signal:new AbortController().signal,kind:index%2?'memory-body-review':'memory-coverage-review',count:1,outputDir:dir});
        const artifact=JSON.parse(fs.readFileSync(path.join(dir,fs.readdirSync(dir).find(name=>name.includes('-response-'))),'utf8'));
        rows.push({result,artifact});
      }
      const valid=[];for(const nativeExitCode of [null,0,255]){
        terminal={kind:'process-exit',nativeExitCode};
        valid.push(await runMemoryReviewBatch({prompt:'inspect',signal:new AbortController().signal,kind:'memory-body-review',count:1}));
      }
      exitCode=0;terminal={kind:'model-error',nativeExitCode:0};
      const dir=path.join(root,'success');fs.mkdirSync(dir);
      const success=await runMemoryReviewBatch({prompt:'inspect',signal:new AbortController().signal,kind:'memory-body-review',count:1,outputDir:dir});
      const successArtifact=JSON.parse(fs.readFileSync(path.join(dir,fs.readdirSync(dir).find(name=>name.includes('-response-'))),'utf8'));
      console.log(JSON.stringify({rows,valid,success,successArtifact,calls,serialized}));
      } finally {fs.rmSync(root,{recursive:true,force:true})}
    ''')
    assert value['serialized'] == 0
    assert value['calls'] == len(value['rows']) + 4
    for row in value['rows']:
        assert row['result']['status'] == 'unavailable' and row['result']['usageComplete'] is False
        assert 'terminal' not in row['result'] and 'terminal' not in row['artifact']
        assert row['artifact']['output'] == ''
    assert [row['terminal']['nativeExitCode'] for row in value['valid']] == [None, 0, 255]
    assert value['success']['status'] == 'reviewed'
    assert 'terminal' not in value['success'] and 'terminal' not in value['successArtifact']
    assert 'PRIVATE' not in str(value)
