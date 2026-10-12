from support import isolated_run_bun


def test_real_missing_suffix_repair_preserves_identity_and_privacy() -> None:
    # Given real new proposal names without .md, When structural repair adds
    # exactly the missing suffix, Then retain intent and reject scope changes.
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let next;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>({text:JSON.stringify(next),exitCode:0,stderr:'',cancelled:false})}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-missing-memory-suffix.json').json();
      const input={identity:f.original,rejectedPlan:f.original,selectedNames:f.selected,structuralCorrection:true,errors:['Consolidation plan contains an invalid memory filename']};
      next=f.corrected;const good=await repairIncrementalMemoryPlan(input);
      const errors=[];
      for(const kind of ['rename','privacy','drop','collision','selected','existing_target','semantic']) {
        next=structuredClone(f.corrected);const original=structuredClone(f.original);
        if(kind==='rename')next.newMemories[0].name='unrelated.md';
        if(kind==='privacy')next.newMemories[0].classification=next.newMemories[0].classification==='safe'?'private':'safe';
        if(kind==='drop')next.newMemories=[];
        if(kind==='existing_target')original.operations[0].name=original.operations[0].name.slice(0,-3);
        if(kind==='collision')original.newMemories.push({...original.newMemories[0],name:next.newMemories[0].name});
        if(kind==='selected'){original.newMemories[0].name='limit_function_type_contract';next.newMemories[0].name='limit_function_type_contract.md';}
        errors.push({kind,result:await repairIncrementalMemoryPlan({...input,rejectedPlan:original,structuralCorrection:kind!=='semantic'})});
      }
      console.log(JSON.stringify({good,errors,expected:f.corrected.newMemories.map(v=>v.name)}));
    ''')
    assert result['good']['outcome'] == 'repaired'
    assert [v['name'] for v in result['good']['plan']['newMemories']] == result['expected']
    assert all(row['result']['outcome'] == 'failed' for row in result['errors'])
