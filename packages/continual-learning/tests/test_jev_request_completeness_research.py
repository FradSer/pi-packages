from support import isolated_run_bun


def test_requirements_are_original_user_spans_with_whole_result_context() -> None:
    row = isolated_run_bun(r'''
      import {requestCompletenessQuestions} from './packages/continual-learning/tests/request-completeness-research.ts';
      const content='Remember: reports must begin with READY; errors never use READY.';
      const snapshot={contextEnabled:true,entries:[{role:'user',content}]};
      const quote='begin with READY',start=content.indexOf(quote);
      const q=requestCompletenessQuestions(snapshot,[{index:0,start,end:start+quote.length,quote}],['Reports use READY.','Errors never use READY.']);
      console.log(JSON.stringify({keys:Object.keys(q),type:q.preserved_0.type,quote:q.preserved_0.instructions.requirement.quote,
        entry:q.preserved_0.instructions.originalUserEntry,whole:q.preserved_0.instructions.resultingMemoryContents}));
    ''')
    assert row == {'keys': ['preserved_0'], 'type': 'noul', 'quote': 'begin with READY',
                   'entry': 'Remember: reports must begin with READY; errors never use READY.',
                   'whole': ['Reports use READY.', 'Errors never use READY.']}


def test_source_offsets_roles_duplicate_spans_and_empty_coverage_reject_before_transport() -> None:
    row = isolated_run_bun(r'''
      import {requestCompletenessQuestions} from './packages/continual-learning/tests/request-completeness-research.ts';
      const content='Remember Node 22.23.2.',quote='Node 22.23.2.',good={index:0,start:9,end:9+quote.length,quote};
      const inputs=[[],[good,good],[{...good,quote:'invented'}],[{...good,start:-1}],[{...good,index:1}],[{...good,expected:false}],[null]];
      const snapshot={contextEnabled:true,entries:[{role:'user',content},{role:'toolResult',content}]};
      const valid=Object.keys(requestCompletenessQuestions(snapshot,[good],['Node 22.23.2.'])).length===1;
      console.log(JSON.stringify({valid,rejected:inputs.map(requirements=>{try{requestCompletenessQuestions(snapshot,requirements,['Node 22.23.2.']);return false;}catch{return true;}})}));
    ''')
    assert row == {'valid': True, 'rejected': [True] * 7}


def test_incomplete_uncertain_and_invalid_never_become_complete() -> None:
    row = isolated_run_bun(r'''
      import {combineRequestCompletenessAnswers} from './packages/continual-learning/tests/request-completeness-research.ts';
      const n=noul=>({type:'noul',noul});
      const inputs=[{preserved_0:n(.99),preserved_1:n(.99)},{preserved_0:n(.99),preserved_1:n(.01)},
        {preserved_0:n(.99),preserved_1:n(.5)},{preserved_0:n(.99)},
        {preserved_0:n(.99),preserved_1:n(NaN)},{preserved_0:n(.99),preserved_1:n(.99),extra:n(.99)}];
      console.log(JSON.stringify(inputs.map(x=>combineRequestCompletenessAnswers(x,2))));
    ''')
    assert [r['status'] for r in row] == ['complete', 'incomplete', 'uncertain', 'invalid-response', 'invalid-response', 'invalid-response']
    assert row[1]['missing'] == [1]
    assert row[2]['uncertain'] == [1]
    assert all(r['writeAuthorized'] is False for r in row)


def test_fixed_corpus_has_valid_original_spans_and_labels_never_enter_questions() -> None:
    row = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {prepareMemoryQualityCreate,memoryQualityResultingContents} from './packages/continual-learning/tests/memory-quality-research.ts';
      import {requestCompletenessQuestions} from './packages/continual-learning/tests/request-completeness-research.ts';
      const data=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/jev-request-completeness-cases.json','utf8'));
      let valid=0,questions=0;for(const row of data.rows){
        prepareMemoryQualityCreate(row.plan,row.snapshot,row.existing,row.changes);
        const contents=memoryQualityResultingContents(row.existing,row.changes);
        const q=requestCompletenessQuestions(row.snapshot,row.requirements,contents);
        if(Object.keys(q).length===row.expectedPreserved.length&&!JSON.stringify(q).includes('expectedPreserved')
          &&row.expected.omission===!row.expectedPreserved.every(Boolean))valid++;
        questions+=Object.keys(q).length;
      }
      console.log(JSON.stringify({valid,count:data.rows.length,questions,heldout:data.heldout,humanGold:data.humanGold}));
    ''')
    assert row == {'valid': 20, 'count': 20, 'questions': 48, 'heldout': False, 'humanGold': False}
