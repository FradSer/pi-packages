from support import isolated_run_bun


def test_structural_repair_uses_parent_inventory_not_rejected_classification() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let response,prompt;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{prompt=input.prompt;return {exitCode:0,stderr:'',text:JSON.stringify(response)}}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const outcomes=[];
      for(const classification of ['safe','private']) {
        const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[{name:'known.md',kind:'rewrite',classification:classification==='safe'?'private':'safe',content:'Observed source fact.',evidence:[{index:0,quote:'Observed source fact.'}]}],newMemories:[]};
        response=structuredClone(original);response.operations[0].classification=classification;
        const input={identity,rejectedPlan:original,errors:['citation too long'],selectedNames:['known.md'],structuralCorrection:true,semanticContext:{frozenEvidence:{entries:[{role:'toolResult',content:'Observed source fact.'}]},existingMemories:[{name:'known.md',classification,content:'Earlier source fact.',type:'project',description:'Source fact.'}]}};
        const result=await repairIncrementalMemoryPlan(input);
        const framing=JSON.parse(prompt.split('\n').at(-1));
        outcomes.push({classification,outcome:result.outcome,table:framing.selectedClassifications,errors:framing.errors});
        response.operations[0].classification=original.operations[0].classification;
        const wrong=await repairIncrementalMemoryPlan(input);outcomes.push({wrong:wrong.outcome});
        response.operations[0].classification=classification;
        const semantic=await repairIncrementalMemoryPlan({...input,structuralCorrection:false});outcomes.push({semantic:semantic.outcome});
      }
      console.log(JSON.stringify(outcomes));
    ''')
    for index, classification in ((0, 'safe'), (3, 'private')):
        assert value[index]['outcome'] == 'repaired'
        assert value[index]['table'] == {'known.md': classification}
        assert any('parent-derived inventory' in error for error in value[index]['errors'])
        assert value[index + 1]['wrong'] == 'failed'
        assert value[index + 2]['semantic'] == 'failed'
