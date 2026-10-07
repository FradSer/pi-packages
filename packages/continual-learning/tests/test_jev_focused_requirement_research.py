from support import isolated_run_bun


def test_focus_preserves_source_context_bodies_and_exact_criteria() -> None:
    value = isolated_run_bun(r'''
      import {requestCompletenessQuestions} from './packages/continual-learning/tests/request-completeness-research.ts';
      import {focusedRequirementQuestions} from './packages/continual-learning/tests/focused-requirement-research.ts';
      const content='记住：报告以 READY 开头；错误报告绝不使用 READY。',quote='以 READY 开头',start=content.indexOf(quote);
      const source={contextEnabled:true,entries:[{role:'user',content}]},spans=[{index:0,start,end:start+quote.length,quote}],bodies=['报告使用 READY。','错误报告绝不使用 READY。'];
      const before=requestCompletenessQuestions(source,spans,bodies),after=focusedRequirementQuestions(source,spans,bodies);
      console.log(JSON.stringify({fragment:after.preserved_0.instructions.requestedFragment,context:after.preserved_0.instructions.originalUserEntry,
        bodies:after.preserved_0.instructions.resultingMemoryContents,criteriaSame:JSON.stringify(before.preserved_0.criteria)===JSON.stringify(after.preserved_0.criteria),
        hasCoordinates:JSON.stringify(after).includes('"start"'),sourceUnchanged:source.entries[0].content===content}));
    ''')
    assert value == {'fragment': '以 READY 开头', 'context': '记住：报告以 READY 开头；错误报告绝不使用 READY。',
                     'bodies': ['报告使用 READY。', '错误报告绝不使用 READY。'], 'criteriaSame': True, 'hasCoordinates': False, 'sourceUnchanged': True}


def test_focus_reuses_source_validation_before_building_questions() -> None:
    value = isolated_run_bun(r'''
      import {focusedRequirementQuestions} from './packages/continual-learning/tests/focused-requirement-research.ts';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:'Remember Node 22.'}]},good={index:0,start:9,end:17,quote:'Node 22.'};
      const inputs=[[],[good,good],[{...good,quote:'invented'}],[{...good,start:-1}],[{...good,index:1}],[{...good,expected:true}]];
      console.log(JSON.stringify(inputs.map(reqs=>{try{focusedRequirementQuestions(snapshot,reqs,['Node 22.']);return false;}catch{return true;}})));
    ''')
    assert value == [True] * 6


def test_fixed_cases_and_labels_do_not_change_or_enter_focused_questions() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {focusedRequirementQuestions} from './packages/continual-learning/tests/focused-requirement-research.ts';
      import {memoryQualityResultingContents} from './packages/continual-learning/tests/memory-quality-research.ts';
      const rows=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/jev-request-completeness-cases.json','utf8')).rows;
      let count=0,leaked=false;for(const row of rows){const q=focusedRequirementQuestions(row.snapshot,row.requirements,memoryQualityResultingContents(row.existing,row.changes));count+=Object.keys(q).length;leaked ||=JSON.stringify(q).includes('expectedPreserved');}
      console.log(JSON.stringify({cases:rows.length,count,leaked}));
    ''')
    assert value == {'cases': 20, 'count': 48, 'leaked': False}
