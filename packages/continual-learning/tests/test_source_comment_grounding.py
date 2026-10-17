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
