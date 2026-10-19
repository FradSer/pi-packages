from support import isolated_run_bun


def test_actual_comment_conflict_is_visible_to_initial_and_repair_guidance():
    # This retained V37 excerpt conflicts with the original task about discarded
    # unresolved promises. Prompt coverage is not semantic learning acceptance.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import {isDeepStrictEqual} from 'node:util';import {mock} from 'bun:test';
      import {MEMORY_CITATION_GUIDANCE} from './packages/continual-learning/extensions/planner-prompts.ts';
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
      console.log(JSON.stringify({guidance:MEMORY_CITATION_GUIDANCE,promptHasGuidance:prompt.includes(MEMORY_CITATION_GUIDANCE),initial,
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
      console.log(JSON.stringify({snapshotBound:hash(JSON.stringify(f.evidence,null,2)+'\n')===f.provenance.snapshotSha256,
        sourceBound:hash(source)===f.provenance.sourceTextSha256,
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
    assert value['noTools'] and value['unchanged']
    assert value['outcome'] == 'failed' and not value['planAdmitted']
