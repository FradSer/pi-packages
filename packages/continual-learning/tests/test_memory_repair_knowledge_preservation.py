from support import isolated_run_bun


def test_real_lossy_correction_does_not_instruct_rewrite_bodies_to_be_one_fact() -> None:
    # Given v13's actual multi-fact predecessor and lossy repair, When another
    # semantic correction is requested, Then the worker gets the complete
    # predecessor and a preservation contract, not a one-sentence body contract.
    # Capturing this request proves the contract only, not real model compliance.
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let prompt;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        prompt=input.prompt;return {text:'{}',exitCode:0,stderr:'',cancelled:false};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-repair-knowledge-loss.json').json();
      await repairIncrementalMemoryPlan({identity:f.original,rejectedPlan:f.original,
        errors:['counterevidence uncertainty'],selectedNames:f.existingMemories.map(x=>x.name),
        repairableNames:f.original.operations.map(x=>x.name),
        repairableFields:Object.fromEntries(f.original.operations.map(x=>[x.name,['body']])),
        semanticContext:{existingMemories:f.existingMemories,frozenEvidence:{entries:[]}}});
      const payload=JSON.parse(prompt.split('\n').at(-1));
      console.log(JSON.stringify({prompt:prompt.slice(0,prompt.lastIndexOf('\n')),
        predecessorPreserved:JSON.stringify(payload.semanticContext.existingMemories)===JSON.stringify(f.existingMemories),
        originalBodies:f.original.operations.map(x=>({name:x.name,content:x.content})),
        correctedBodies:f.corrected.operations.map(x=>({name:x.name,content:x.content}))}));
    ''')
    before = {row['name']: row['content'] for row in result['originalBodies']}
    after = {row['name']: row['content'] for row in result['correctedBodies']}
    assert 'Promise.all' in before['clear_queue_pending_only.md']
    assert 'Promise.all' not in after['clear_queue_pending_only.md']
    assert 'PromiseLike<ReturnType> | ReturnType' in before['limit_function_type_contract.md']
    assert 'PromiseLike<ReturnType> | ReturnType' not in after['limit_function_type_contract.md']
    assert result['predecessorPreserved']
    prompt = result['prompt']
    assert 'Use the shortest directly supported fact;' not in prompt
    assert 'Preserve still-valid predecessor facts, conditions, unresolved observations and usage guidance' in prompt
    assert 'does not authorize compressing an already correct record or discarding still-valid predecessor knowledge' in prompt
    assert 'Preserve a supported unresolved failure instead of inventing a mechanism or discarding the observation' in prompt
