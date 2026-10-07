from support import isolated_run_bun


def test_temporal_research_keeps_all_original_evidence_and_checks() -> None:
    # Given a production counter request, When adding explicit chronology,
    # Then preserve all original entries, candidate and criteria with no verdict.
    value = isolated_run_bun(r'''
      import {temporalCounterRequest} from './packages/continual-learning/tests/jev-temporal-counter-research.ts';
      const state={supportEvidence:{entries:[{index:2,entry:{role:'user',content:'Current fact'}}]},reviewEvidence:{entries:[{index:0,entry:{role:'toolResult',content:'Prior failure'}},{index:1,entry:{role:'assistant',content:'Unverified claim'}},{index:2,entry:{role:'user',content:'Current fact'}}]}};
      const counter={type:'choice',instructions:{question:'Original counter question',candidate:{content:'Current fact'}},criteria:{compatible:'Same',contradicts:'Conflict',unclear:'Unknown'}};
      const original={model:'jev-1.13.0',state:JSON.stringify(state),questions:{counter_0_0:counter,counter_description_0_0:counter}};
      const before=JSON.stringify(original),body=temporalCounterRequest(before,[{evidence:[{index:2}]}]),after=JSON.parse(body);
      const support={model:original.model,state:JSON.stringify({frozenEvidence:state.supportEvidence}),questions:{supported_0:counter}};
      let denied=false;try{temporalCounterRequest(JSON.stringify({...original,questions:{counter_7_0:counter}}),[{evidence:[{index:2}]}])}catch{denied=true}
      console.log(JSON.stringify({unchanged:JSON.stringify(original)===before,state:JSON.parse(after.state),questions:after.questions,supportUnchanged:temporalCounterRequest(JSON.stringify(support),[])===JSON.stringify(support),denied}));
    ''')
    assert value['unchanged'] and value['supportUnchanged'] and value['denied']
    assert [x['index'] for x in value['state']['reviewEvidence']['entries']] == [0, 1, 2]
    assert value['state']['reviewEvidence']['entries'][1]['entry']['role'] == 'assistant'
    for question in value['questions'].values():
        assert question['instructions']['candidate'] == {'content': 'Current fact'}
        assert question['criteria'] == {'compatible': 'Same', 'contradicts': 'Conflict', 'unclear': 'Unknown'}
        assert question['instructions']['chronology']['originalCitedEntryIndexes'] == [2]
        assert question['instructions']['chronology']['originalWindowEntryIndexes'] == [0, 1, 2]
        assert 'verdict' not in question['instructions']['chronology']
