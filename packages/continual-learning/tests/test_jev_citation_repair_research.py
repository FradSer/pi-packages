from support import isolated_run_bun


def test_citation_research_preserves_original_knowledge_identity_and_source() -> None:
    value = isolated_run_bun(r'''
      import {completePublicResearchCitations} from './packages/continual-learning/tests/jev-citation-repair-research.ts';
      const quote='For future tasks this project uses Vitest.';
      const snapshot={contextEnabled:true,entries:[{role:'toolResult',content:'Verified migration: the current project now uses Vitest.'},{role:'assistant',content:'PRIVATE_ASSISTANT_TEXT'},{role:'user',content:quote}]};
      const candidate={name:'fact.md',kind:'project',classification:'safe',content:`---\nname: fact\ndescription: This project uses Vitest.\ntype: project\n---\nThis project uses Vitest.`,evidence:[{index:2,quote,role:'user'}]};
      const before=JSON.stringify({snapshot,candidate});const repaired=completePublicResearchCitations(snapshot,[candidate]);
      console.log(JSON.stringify({originalUnchanged:before===JSON.stringify({snapshot,candidate}),original:candidate,repaired}));
    ''')
    assert value['originalUnchanged']
    candidate = value['repaired'][0]
    assert {k: v for k, v in candidate.items() if k != 'evidence'} == {
        k: v for k, v in value['original'].items() if k != 'evidence'
    }
    assert candidate['evidence'][0] == value['original']['evidence'][0]
    assert [e['index'] for e in candidate['evidence']] == [2, 0]
    assert candidate['evidence'][1]['role'] == 'toolResult'
    assert 'PRIVATE_ASSISTANT_TEXT' not in str(candidate)


def test_citation_research_refuses_missing_bounds_privacy_or_class_changes() -> None:
    value = isolated_run_bun(r'''
      import {completePublicResearchCitations} from './packages/continual-learning/tests/jev-citation-repair-research.ts';
      const quote='This project uses pnpm.';
      const candidate={name:'fact.md',kind:'project',classification:'safe',content:`---\nname: fact\ndescription: ${quote}\ntype: project\n---\n${quote}`,evidence:[{index:0,quote,role:'user'}]};
      const rows=[];for(const mode of ['long','many','sensitive','private','missing']){
       const snapshot={contextEnabled:true,entries:[{role:'user',content:quote}]};const c=structuredClone(candidate);
       if(mode==='long')snapshot.entries.push({role:'toolResult',content:'x'.repeat(2001)});
       if(mode==='many')snapshot.entries.push(...Array.from({length:8},(_,i)=>({role:'toolResult',content:`Public observation ${i}.`})));
       if(mode==='sensitive')snapshot.entries.push({role:'toolResult',content:'Bearer sk-live-'+'x'.repeat(40)});
       if(mode==='private')c.classification='private';
       if(mode==='missing')c.evidence[0].quote='Invented evidence';
       let denied=false;try{completePublicResearchCitations(snapshot,[c])}catch{denied=true}rows.push({mode,denied});
      }console.log(JSON.stringify(rows));
    ''')
    assert all(row['denied'] for row in value)
