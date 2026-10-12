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


def test_repeated_extension_is_a_parent_bound_new_proposal_spelling_correction() -> None:
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let next,prompt='';
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{prompt=input.prompt;return {text:JSON.stringify(next),exitCode:0,stderr:'',cancelled:false};}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-repeated-memory-extension.json').json();
      const input={identity:f.original,rejectedPlan:f.original,selectedNames:f.selected,structuralCorrection:true,errors:['Consolidation plan contains an invalid memory filename']};
      next=f.corrected;const good=await repairIncrementalMemoryPlan(input);const parentMapping=prompt.includes('newProposalNameCorrections')&&prompt.includes('pnpm_test_node20_skip.md_keep_note.md')&&prompt.includes('pnpm_test_node20_skip_keep_note.md');
      const bad=[];
      for(const kind of ['rename','privacy','drop','duplicate','selected','path','other_extension','semantic','existing_target']) {
        next=structuredClone(f.corrected);const original=structuredClone(f.original);let selected=[...f.selected];
        if(kind==='rename')next.newMemories[1].name='unrelated.md';
        if(kind==='privacy')next.newMemories[1].classification='private';
        if(kind==='drop')next.newMemories.pop();
        if(kind==='duplicate')original.newMemories.push({...original.newMemories[1],name:next.newMemories[1].name});
        if(kind==='selected')selected.push(next.newMemories[1].name);
        if(kind==='path')original.newMemories[1].name='../pnpm_test_node20_skip.md_keep_note.md';
        if(kind==='other_extension')original.newMemories[1].name='pnpm_test_node20_skip.txt_keep_note.md';
        if(kind==='existing_target')original.operations[0].name='package_test_scripts.md_note.md';
        bad.push({kind,result:await repairIncrementalMemoryPlan({...input,rejectedPlan:original,selectedNames:selected,structuralCorrection:kind!=='semantic'})});
      }
      console.log(JSON.stringify({good,parentMapping,bad}));
    ''')
    assert result['good']['outcome'] == 'repaired'
    assert result['parentMapping']
    assert all(row['result']['outcome'] == 'failed' for row in result['bad'])
