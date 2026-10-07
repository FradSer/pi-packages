from support import isolated_run_bun


def test_structured_pair_retains_original_fields_and_material_conditions() -> None:
    # Given two normalized candidates, When exposing semantic views, Then raw
    # records/evidence remain exact and descriptions cannot hide conflicting claims.
    rows = isolated_run_bun(r'''
      import {structuredMemoryPairState,structuredMemoryPairQuestion} from './packages/continual-learning/tests/jev-memory-pair-structured.ts';
      const snapshot={entries:[{role:'user',content:'If Node 20 is available, run pnpm test.'}],contextEnabled:true};
      const candidates=[{name:'a.md',content:'---\nname: a\ndescription: Linux only\ntype: project\n---\nWindows only\n'}, {name:'b.md',content:'---\r\nname: b\r\ndescription: If Node 20 is available, run pnpm test.\r\ntype: project\r\n---\r\nIf Node 20 is available, run pnpm test.\r\n'}];
      const state=structuredMemoryPairState(snapshot,candidates);const question=structuredMemoryPairQuestion();
      console.log(JSON.stringify({state,unchanged:JSON.stringify(state.originalCandidates)===JSON.stringify(candidates),evidenceSame:JSON.stringify(state.originalEvidence)===JSON.stringify(snapshot),question,guard:JSON.stringify(question).includes('self-contained')}));
    ''')
    assert rows['unchanged'] and rows['evidenceSame'] and rows['guard']
    assert rows['state']['candidateA']['description'] == 'Linux only'
    assert rows['state']['candidateA']['body'] == 'Windows only\n'
    assert rows['state']['candidateB']['body'] == 'If Node 20 is available, run pnpm test.\r\n'
    assert set(rows['question']['criteria']) == {'independent', 'duplicate', 'conflict', 'dependent', 'unclear'}


def test_structured_pair_missing_description_denies_inference() -> None:
    # Given missing/malformed frontmatter, When deriving views, Then deny rather
    # than guess or strip original material into a favorable state.
    rows = isolated_run_bun(r'''
      import {structuredMemoryPairState} from './packages/continual-learning/tests/jev-memory-pair-structured.ts';
      const good={content:'---\nname: a\ndescription: fact\ntype: project\n---\nfact'};const out=[];
      for(const bad of [{content:'fact'}, {content:'---\ndescription: \n---\nfact'}, {content:3}]){try{structuredMemoryPairState({},[good,bad]);out.push(false);}catch{out.push(true);}}
      console.log(JSON.stringify(out));
    ''')
    assert rows == [True, True, True]
