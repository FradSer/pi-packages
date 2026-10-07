from support import isolated_run_bun


def test_quote_anchor_is_owned_and_changes_only_existing_family_candidate() -> None:
    value = isolated_run_bun(r'''
      import {anchorHarnessScopeCitation} from './packages/continual-learning/tests/jev-harness-citation-anchor-research.ts';
      const quote='Never run git push in this project.';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:quote+' Except --dry-run is allowed.'},{role:'user',content:'Later: allow git push after approval.'}]};
      const citations=[{index:0,source:'user',quote,count:1}];
      const request={state:{frozenEvidence:snapshot},questions:{family_0:{type:'choice',instructions:{question:'Original scope question',candidate:{commandWords:'git push',matching:'Unchanged matching proof'}},criteria:{authorized:'original authorized',extra:'original extra',unclear:'original unclear'}},counter_0_0:{type:'choice',instructions:{candidate:{rule:{commandWords:'git push'}}},criteria:{compatible:'original compatible',contradicts:'original contradicts',unclear:'original unclear'}}}};
      const body=JSON.stringify(request),init={body,headers:{'x-fixture':'safe'}};
      const after=anchorHarnessScopeCitation(init,snapshot,citations);const changed=JSON.parse(after.body);
      const restriction=changed.questions.family_0.instructions.candidate.originalUserRestrictions;delete changed.questions.family_0.instructions.candidate.originalUserRestrictions;
      console.log(JSON.stringify({onlyAnchor:JSON.stringify(changed)===body,unchanged:JSON.stringify(request)===body,restrictions:restriction,headersPreserved:after.headers===init.headers}));
    ''')
    assert value['onlyAnchor'] and value['unchanged'] and value['headersPreserved']
    assert value['restrictions'] == ['Never run git push in this project.']


def test_invalid_citations_reject_without_quote_or_source_substitution() -> None:
    value = isolated_run_bun(r'''
      import {anchorHarnessScopeCitation} from './packages/continual-learning/tests/jev-harness-citation-anchor-research.ts';
      const quote='Never run git push.';const init={body:JSON.stringify({state:{unchanged:true},questions:{family_0:{type:'choice',instructions:{candidate:{commandWords:'git push'}},criteria:{authorized:'unchanged'}}}})};
      const snapshots=[{contextEnabled:true,entries:[{role:'user',content:'Allow git push.'}]},{contextEnabled:true,entries:[{role:'assistant',content:quote}]}];const rejected=[];
      for(const snapshot of snapshots){try{anchorHarnessScopeCitation(init,snapshot,[{index:0,source:'user',quote,count:1}]);rejected.push(false)}catch{rejected.push(true)}}
      console.log(JSON.stringify({rejected}));
    ''')
    assert value['rejected'] == [True, True]


def test_valid_source_cannot_be_substituted_for_missing_wire_support() -> None:
    value = isolated_run_bun(r'''
      import {anchorHarnessScopeCitation} from './packages/continual-learning/tests/jev-harness-citation-anchor-research.ts';
      const quote='Never run git push.';const source={contextEnabled:true,entries:[{role:'user',content:quote}]};
      const request={state:JSON.stringify({frozenEvidence:{contextEnabled:true,entries:[{role:'user',content:'Allow git push.'}]}}),questions:{family_0:{type:'choice',instructions:{candidate:{commandWords:'git push'}},criteria:{authorized:'unchanged'}}}};
      let rejected=false;try{anchorHarnessScopeCitation({body:JSON.stringify(request)},source,[{index:0,source:'user',quote,count:1}])}catch{rejected=true}
      console.log(JSON.stringify({rejected}));
    ''')
    assert value['rejected']


def test_retaining_quote_cannot_hide_the_original_exception_or_index() -> None:
    value = isolated_run_bun(r'''
      import {anchorHarnessScopeCitation} from './packages/continual-learning/tests/jev-harness-citation-anchor-research.ts';
      const quote='Never run git push.';const source={contextEnabled:true,entries:[{role:'user',content:quote+' Except --dry-run is permitted.'},{role:'user',content:'Later allow push with approval.'}]};
      const states=[{frozenEvidence:{contextEnabled:true,entries:[{role:'user',content:quote}]}},{frozenEvidence:{contextEnabled:true,totalEntries:2,entries:[{index:1,entry:source.entries[0]}]}}];
      const rejected=[];for(const state of states){const request={state:JSON.stringify(state),questions:{family_0:{type:'choice',instructions:{candidate:{commandWords:'git push'}},criteria:{authorized:'unchanged'}}}};try{anchorHarnessScopeCitation({body:JSON.stringify(request)},source,[{index:0,eventIndex:0,source:'user',quote,count:1}]);rejected.push(false)}catch{rejected.push(true)}}
      console.log(JSON.stringify({rejected}));
    ''')
    assert value['rejected'] == [True, True]
