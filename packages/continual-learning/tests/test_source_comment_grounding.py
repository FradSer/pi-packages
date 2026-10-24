from support import isolated_run_bun


def test_real_trace_label_is_not_evidence_that_the_named_action_executed():
    # Given V107's actual log-only callback and unchanged rejected body,
    # When initial generation or repair receives its evidence,
    # Then preserve the entire source and separate labels from executed work.
    # This checks delivery only, not compliance, semantic approval or benefit.
    value = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';import {isDeepStrictEqual} from 'node:util';import {mock} from 'bun:test';
      import {buildIncrementalMemoryConsolidatorPrompt} from './packages/continual-learning/extensions/planner-prompts.ts';
      import {locatedMemoryEvidence} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const f=(await Bun.file('./packages/continual-learning/tests/fixtures/real-failure-label-state-conflict.json').json()).traceLabelCase;
      const h=x=>createHash('sha256').update(JSON.stringify(x,null,2)+'\n').digest('hex');
      const p=f.provenance,e=f.snapshot.entries;
      const call=e[p.traceCallIndex].message.content.find(x=>x.type==='toolCall');
      const result=e[p.traceResultIndex].message;
      const source=e[p.sourceResultIndex].message.content[0].text;
      const kit=await import('./packages/kit/src/index.ts');let actual;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{actual=input;return {exitCode:0,stderr:'',text:'invalid output',cancelled:false};}}));
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const initial=buildIncrementalMemoryConsolidatorPrompt({...identity,dossierPath:'/fixture/dossier',dossierContents:JSON.stringify({snapshot:f.snapshot})});
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const out=await repairIncrementalMemoryPlan({identity,rejectedPlan:f.repairedPlan,selectedNames:[],errors:['uncertain knowledge scope'],semanticContext:{frozenEvidence:f.snapshot,existingMemories:[]}});
      const marker='Log labels do not prove that the named action executed';
      const originalActual=actual;
      const premise=(await Bun.file('./packages/continual-learning/tests/fixtures/real-failure-label-state-conflict.json').json()).premiseCitationCase;
      const premiseBefore=JSON.stringify(premise),premiseBody=premise.repairedPlan.newMemories.find(x=>x.name===premise.provenance.failureName);
      const premiseSource=premise.snapshot.entries[premise.provenance.sourceResultIndex].message.content[0].text;
      const corrected=await repairIncrementalMemoryPlan({identity,rejectedPlan:premise.repairedPlan,selectedNames:[],errors:['held evidence-supported conditions'],
        semanticContext:{frozenEvidence:premise.snapshot,existingMemories:[]}});
      const sourceOrder='Derive source-established applicability before drafting';
      const citationOrder='Recheck source coverage for every factual clause added or changed during correction';
      const failure=plan=>plan.newMemories.find(x=>x.name.includes('onidle'));
      const body=plan=>failure(plan).content.replace(/^---\n[\s\S]*?\n---\n/,'');
      console.log(JSON.stringify({bound:Object.entries({snapshot:f.snapshot,initialPlan:f.initialPlan,repairedPlan:f.repairedPlan}).every(([k,v])=>h(v)===p.sha256[k]),
        logOnly:call.arguments.command.includes("initial.then(() => { log.push('reaction: enqueue followUp'); })")&&!call.arguments.command.includes('invoke(1)')&&!call.arguments.command.includes('second.promise'),
        paired:call.id===result.toolCallId&&!result.isError,resultText:result.content[0].text,
        fullReproducer:source.includes('followUp = invoke(1)')&&source.indexOf('await enqueued;')<source.indexOf("assert.equal(reported, false, 'onIdle")&&source.indexOf("assert.equal(reported, false, 'onIdle")<source.indexOf('second.resolve();'),
        bodyUnchanged:body(f.initialPlan)===body(f.repairedPlan),
        premiseBound:Object.entries(premise.provenance.canonicalSha256).every(([k,d])=>h(premise[k])===d),
        correctedUnfinishedWork:premiseBody.content.includes('second.promise` was still unsettled'),
        completeSourceHasPremises:premiseSource.includes('second.promise')&&premiseSource.includes('pLimit(1)'),
        selectedQuotesLackPremise:!premiseBody.evidence.some(x=>x.quote.includes('second.promise')),
        omittedSetupRetained:!premiseBody.content.includes('concurrency')&&!premiseBody.content.includes('pLimit(1)'),
        conditionFirstInitial:initial.includes(sourceOrder),conditionFirstRepair:actual.prompt.includes(sourceOrder),
        relationsInBody:[initial,actual.prompt].every(p=>p.includes('whose resource or result is involved')&&p.includes('Write supported relationships in the body, not only in citations or descriptions')),
        noBlanketExplanationBan:!actual.prompt.includes('Do not introduce new explanations while correcting an existing claim'),
        changedCitationCheck:actual.prompt.includes(citationOrder),
        premiseContextComplete:isDeepStrictEqual(JSON.parse(actual.prompt.split('\n').at(-1)).semanticContext.frozenEvidence,locatedMemoryEvidence(premise.snapshot)),
        premiseUnchanged:premiseBefore===JSON.stringify(premise),premiseRejected:corrected.outcome==='failed'&&!corrected.plan,
        initialGuidance:initial.includes("Read a diagnostic's executed operations before interpreting its printed labels."),
        legacyTraceGuidanceInInitial:initial.includes(marker),repairGuidance:actual.prompt.includes(marker),
        contextComplete:isDeepStrictEqual(JSON.parse(originalActual.prompt.split('\n').at(-1)).semanticContext.frozenEvidence,locatedMemoryEvidence(f.snapshot)),
        outcome:out.outcome,admitted:!!out.plan}));
    ''')
    assert value['bound'] and value['logOnly'] and value['paired']
    assert value['resultText'].startswith('idle resolved\nreaction: enqueue followUp\n')
    assert value['fullReproducer'] and value['bodyUnchanged'] and value['contextComplete']
    assert value['initialGuidance'] and value['repairGuidance']
    assert not value['legacyTraceGuidanceInInitial']
    assert value['premiseBound'] and value['correctedUnfinishedWork'] and value['completeSourceHasPremises']
    assert value['selectedQuotesLackPremise'] and value['omittedSetupRetained']
    assert value['conditionFirstInitial'] and value['conditionFirstRepair'] and value['changedCitationCheck']
    assert value['relationsInBody'] and value['noBlanketExplanationBan']
    assert value['premiseContextComplete'] and value['premiseUnchanged'] and value['premiseRejected']
    assert value['outcome'] == 'failed' and not value['admitted']


def test_actual_comment_conflict_is_visible_to_initial_and_repair_guidance():
    # This retained V37 excerpt conflicts with the original task about discarded
    # unresolved promises. Prompt coverage is not semantic learning acceptance.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import {isDeepStrictEqual} from 'node:util';import {mock} from 'bun:test';
      import {MEMORY_CITATION_GUIDANCE,buildIncrementalMemoryConsolidatorPrompt} from './packages/continual-learning/extensions/planner-prompts.ts';
      import {createHash} from 'node:crypto';
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-source-comment-conflict.json','utf8'));
      const kit=await import('./packages/kit/src/index.ts');let prompt;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        prompt=input.prompt;return {exitCode:0,stderr:'',text:'not a valid plan',cancelled:false};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const input={rejectedPlan:{operations:[],newMemories:[fixture.candidate]},errors:['uncertain source counterevidence'],
        selectedNames:[],identity:{runId:'r',scopeKey:'s',scopeDigest:'s',artifactHash:'a',snapshotDigest:'a'},
        semanticContext:{frozenEvidence:fixture.evidence,existingMemories:[]}};
      const out=await repairIncrementalMemoryPlan(input);
      const initial=fs.readFileSync('./packages/continual-learning/prompts/incremental-memory-consolidator.md','utf8');
      const context=JSON.parse(prompt.split('\n').at(-1)).semanticContext;
      const originalPrompt=prompt;
      const phase=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-failure-label-state-conflict.json','utf8')).phaseScopeCase;
      const phaseBefore=JSON.stringify(phase),hash=x=>createHash('sha256').update(JSON.stringify(x,null,2)+'\n').digest('hex');
      const phaseInitial=buildIncrementalMemoryConsolidatorPrompt({...input.identity,dossierPath:'/fixture/dossier',dossierContents:JSON.stringify({snapshot:phase.snapshot})});
      const phaseOut=await repairIncrementalMemoryPlan({...input,rejectedPlan:phase.repairedPlan,semanticContext:{frozenEvidence:phase.snapshot,existingMemories:[]}});
      const phaseContext=JSON.parse(prompt.split('\n').at(-1)).semanticContext.frozenEvidence;
      const phaseMarker='matching subject, execution phase and material conditions before calling them a contradiction or discrepancy';
      const restore=value=>{
        if(Array.isArray(value))return value.map(restore);
        if(!value||typeof value!=='object')return value;
        if(value.citationLines){
          const text=value.citationLines.lines.map(row=>row.text??row.chunks.map(chunk=>chunk.text).join('')).join('\n');
          const {citationLines,...metadata}=value;
          return Object.keys(metadata).length?{...metadata,text}:text;
        }
        return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,restore(item)]));
      };
      console.log(JSON.stringify({guidance:MEMORY_CITATION_GUIDANCE,promptHasGuidance:originalPrompt.includes(MEMORY_CITATION_GUIDANCE),initial,
        phaseBound:Object.entries(phase.provenance.canonicalSha256).every(([k,h])=>hash(phase[k])===h),
        phaseInitialGuidance:phaseInitial.includes('Quoted source comments establish observed wording, not verified behavior.')&&phaseInitial.includes('complete source observations')&&phaseInitial.includes('observation phase'),
        legacyPhaseGuidanceInInitial:phaseInitial.includes(phaseMarker),phaseRepairGuidance:prompt.includes(phaseMarker),
        phaseOriginalComparison:phase.repairedPlan.newMemories[0].content.includes('**Unresolved source-state mismatch**')&&phase.repairedPlan.newMemories[0].content.includes('the discrepancy is unresolved'),
        phaseOriginalSource:phase.snapshot.entries[4].message.content[0].text.includes('Any job enqueued while this one was resolving is already accounted for here.'),
        phaseEvents:phase.isolatedInstrumentation.events,phaseBaselineExit:phase.isolatedInstrumentation.baselineExit,phaseInstrumentedExit:phase.isolatedInstrumentation.instrumentedExit,
        phaseContextUnchanged:phaseContext.entries.every((item,index)=>item.snapshotIndex===index&&isDeepStrictEqual(restore(item.entry),phase.snapshot.entries[index]))&&phaseContext.entries.length===phase.snapshot.entries.length,
        phaseObservationNotImported:phase.isolatedInstrumentation.originalSnapshotEvidence===false&&!prompt.includes('flush:check'),
        phaseFixtureUnchanged:phaseBefore===JSON.stringify(phase),phaseOutcome:phaseOut.outcome,phaseAdmitted:!!phaseOut.plan,
        frozenContextUnchanged:context.frozenEvidence.entries.every((item,index)=>item.snapshotIndex===index&&isDeepStrictEqual(restore(item.entry),input.semanticContext.frozenEvidence.entries[index]))&&context.frozenEvidence.entries.length===input.semanticContext.frozenEvidence.entries.length,
        originalEntryCount:fixture.evidence.entries.length,
        citationInRange:fixture.candidate.evidence.every(item=>item.index<fixture.evidence.entries.length&&fixture.evidence.entries[item.index].message.role===item.role),
        requirement:fixture.evidence.entries[0].message.content[0].text,
        quotedComment:fixture.candidate.content,outcome:out.outcome,planAdmitted:!!out.plan}));
    ''')
    assert 'discarded promises stay unresolved' in value['requirement']
    assert 'all running and queued promises have settled' in value['quotedComment']
    assert value['originalEntryCount'] == 94 and value['citationInRange']
    assert 'Quoted source comments' in value['guidance']
    assert 'observed wording' in value['guidance']
    assert 'current user requirements' in value['guidance']
    assert value['promptHasGuidance'] and value['frozenContextUnchanged']
    assert 'misleading commentary' in value['initial']
    assert value['outcome'] == 'failed' and not value['planAdmitted']
    # Given V113's actual compared phases, the new isolated trace is diagnostic
    # evidence only. It never becomes evidence in the original rejected plan.
    assert value['phaseBound'] and value['phaseOriginalComparison'] and value['phaseOriginalSource']
    assert value['phaseBaselineExit'] == value['phaseInstrumentedExit'] == 1
    for case in ('limiter', 'wrapper'):
        events = [row['event'] for row in value['phaseEvents'] if row['case'] == case]
        assert events.index('flush:resolve-idle') < events.index('consumer:invoke-followup')
    assert value['phaseContextUnchanged'] and value['phaseObservationNotImported']
    assert value['phaseFixtureUnchanged'] and value['phaseOutcome'] == 'failed' and not value['phaseAdmitted']
    assert value['phaseInitialGuidance'] and value['phaseRepairGuidance']
    assert not value['legacyPhaseGuidanceInInitial']
    # The deliberately invalid mock output proves no semantic decision.


def test_real_failure_label_does_not_replace_the_actual_awaited_condition():
    # V95's failed generation is preserved, with the complete original snapshot.
    # This proves prompt/source delivery only, not a model's compliance or benefit.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import {createHash} from 'node:crypto';import {mock} from 'bun:test';
      import {isDeepStrictEqual} from 'node:util';
      import {MEMORY_CITATION_GUIDANCE} from './packages/continual-learning/extensions/planner-prompts.ts';
      import {locatedMemoryEvidence} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-failure-label-state-conflict.json','utf8'));
      const before=JSON.stringify(f),hash=text=>createHash('sha256').update(text).digest('hex');
      const kit=await import('./packages/kit/src/index.ts');let request;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        request=input;return {exitCode:0,stderr:'',text:'not a valid plan',cancelled:false};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const out=await repairIncrementalMemoryPlan({rejectedPlan:{operations:[],newMemories:[f.candidate]},
        errors:['held failure-label state claim'],selectedNames:[],identity:{runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'},
        semanticContext:{frozenEvidence:f.evidence,existingMemories:[]}});
      const actual=JSON.parse(request.prompt.split('\n').at(-1)).semanticContext.frozenEvidence;
      const source=f.sourceText,b=f.mechanicalBoundary;
      const observed=f.observedStateCase,observedSource=observed.sourceText;
      const raw=observed.rejectedPlan.newMemories[0].content,amended=observed.repairedPlan.newMemories[0].content;
      const exact=observed.evidence.entries[41].message;
      const sourceText=exact.content.filter(b=>b.type==='text').map(b=>b.text).join('\n');
      const conditioned=f.conditionedFailureCase,c=conditioned.provenance;
      const second=await repairIncrementalMemoryPlan({rejectedPlan:conditioned.rejectedPlan,errors:['held incomplete source conditions'],
        selectedNames:[],identity:{runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'},
        semanticContext:{frozenEvidence:conditioned.evidence,existingMemories:[]}});
      const conditionedContext=JSON.parse(request.prompt.split('\n').at(-1)).semanticContext.frozenEvidence;
      const failure=conditioned.repairedPlan.newMemories.find(x=>x.name.includes('onidle'));
      const failedText=conditioned.evidence.entries[c.failedResultIndex].message.content.filter(b=>b.type==='text').map(b=>b.text).join('\n');
      const lean=f.leanKnowledgeCase;
      const leanResult=await repairIncrementalMemoryPlan({rejectedPlan:lean.repairedPlan,errors:['held complete content review'],
        selectedNames:[],identity:{runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'},
        semanticContext:{frozenEvidence:lean.evidence,existingMemories:[]}});
      const leanContext=JSON.parse(request.prompt.split('\n').at(-1)).semanticContext.frozenEvidence;
      const leanContract=lean.repairedPlan.newMemories.find(x=>x.name.includes('input_output')).content;
      const leanFailure=lean.repairedPlan.newMemories.find(x=>x.name.includes('onidle')).content;
      console.log(JSON.stringify({snapshotBound:hash(JSON.stringify(f.evidence,null,2)+'\n')===f.provenance.snapshotSha256,
        sourceBound:hash(source)===f.provenance.sourceTextSha256,
        observedSnapshotBound:hash(JSON.stringify(observed.evidence,null,2)+'\n')===observed.provenance.snapshotSha256,
        observedSourceBound:hash(observedSource)===observed.provenance.sourceTextSha256&&sourceText.startsWith(observedSource.trimEnd()),
        unknownStateDraftsRetained:[raw,amended].every(text=>text.includes('does not establish the actual blocking state or cause')),
        completedReactionBeforeFailedAssertion:observedSource.indexOf('await enqueued;')<observedSource.indexOf(b.literalAssertionMessage),
        workReleaseAfterFailedAssertion:observedSource.indexOf(b.literalAssertionMessage)<observedSource.indexOf('second.resolve();'),
        conditionedSnapshotBound:hash(JSON.stringify(conditioned.evidence,null,2)+'\n')===c.sha256.snapshot,
        conditionedSourceBound:hash(conditioned.sourceText)===c.sha256.sourceText,
        conditionedContextComplete:isDeepStrictEqual(conditionedContext,locatedMemoryEvidence(conditioned.evidence)),
        sourceProvesReachedCheck:failedText.includes('observed-idle-failure.mjs:34:10')&&conditioned.sourceText.split('\n')[33].includes(b.literalAssertionMessage),
        finalPartialCorrectionRetained:failure.content.includes('callback that calls `invoke(1)` has run')&&!failure.content.includes('precise blocking subject'),
        originalConditionOmissionRetained:!failure.content.includes('second.promise'),
        conditionedOutcome:second.outcome,conditionedPlanAdmitted:!!second.plan,
        leanSnapshotBound:hash(JSON.stringify(lean.evidence,null,2)+'\n')===lean.provenance.snapshotSha256,
        leanPlanBound:hash(JSON.stringify(lean.repairedPlan,null,2)+'\n')===lean.provenance.planSha256,
        leanContextComplete:isDeepStrictEqual(leanContext,locatedMemoryEvidence(lean.evidence)),
        independentNamedTypeConditionsRetained:leanContract.includes('options` is a required `Options` object')&&leanContract.includes('readonly concurrency: number')&&leanContract.includes('readonly rejectOnClear?: boolean'),
        completeDeclarationRetained:leanContract.includes("): ((...arguments_: Arguments) => Promise<ReturnType>) & Pick<LimitFunction, 'clearQueue' | 'onIdle'>;"),
        knownConditionAndScopeRetained:leanFailure.includes('second.resolve()')&&leanFailure.includes('/work/p-limit/index.js'),
        oldBroadUncertaintyRetained:leanFailure.includes('the mechanism and the blocking subject are not established'),
        leanGuidanceDelivered:request.prompt.includes('Within a new record body, state each supported fact once')&&request.prompt.includes('Keep independent named-type requirements')&&request.prompt.includes('including locations requested by the user'),
        leanOutcome:leanResult.outcome,leanPlanAdmitted:!!leanResult.plan,
        contextComplete:isDeepStrictEqual(actual,locatedMemoryEvidence(f.evidence)),entries:actual.entries.length,
        awaitBeforeAssertion:source.indexOf(b.observedAwaitBeforeAssertion)<source.indexOf(b.literalAssertionMessage),
        releaseAfterAssertion:source.indexOf(b.literalAssertionMessage)<source.indexOf(b.unreleasedWorkAfterAssertion),
        originalWrongClaimRetained:f.candidate.content.includes(b.unsupportedMechanism),
        guidance:request.prompt.includes(MEMORY_CITATION_GUIDANCE)&&request.prompt.includes('trace the awaited reactions, completed callbacks and unreleased work'),
        noTools:request.tools.length===0,unchanged:before===JSON.stringify(f),outcome:out.outcome,planAdmitted:!!out.plan}));
    ''')
    assert value['snapshotBound'] and value['sourceBound'] and value['contextComplete']
    assert value['entries'] > 30 and value['awaitBeforeAssertion'] and value['releaseAfterAssertion']
    assert value['originalWrongClaimRetained'] and value['guidance']
    assert value['observedSnapshotBound'] and value['observedSourceBound']
    assert value['unknownStateDraftsRetained']
    assert value['completedReactionBeforeFailedAssertion'] and value['workReleaseAfterFailedAssertion']
    assert value['conditionedSnapshotBound'] and value['conditionedSourceBound'] and value['conditionedContextComplete']
    assert value['sourceProvesReachedCheck'] and value['finalPartialCorrectionRetained'] and value['originalConditionOmissionRetained']
    assert value['conditionedOutcome'] == 'failed' and not value['conditionedPlanAdmitted']
    # The complete V101 draft remains rejected, with its optional prose and
    # independently required type/condition/scope facts. A lean policy must not
    # rewrite the fixture, suppress a hold or drop these facts to obtain a pass.
    assert value['leanSnapshotBound'] and value['leanPlanBound'] and value['leanContextComplete']
    assert value['independentNamedTypeConditionsRetained'] and value['completeDeclarationRetained']
    assert value['knownConditionAndScopeRetained'] and value['oldBroadUncertaintyRetained']
    assert value['leanGuidanceDelivered']
    assert value['leanOutcome'] == 'failed' and not value['leanPlanAdmitted']
    assert value['noTools'] and value['unchanged']
    assert value['outcome'] == 'failed' and not value['planAdmitted']
