from support import isolated_run_bun


def test_quality_judgments_are_independent_and_completeness_uses_whole_result() -> None:
    row = isolated_run_bun(r'''
      import {memoryQualityQuestions} from './packages/continual-learning/tests/memory-quality-research.ts';
      const q=memoryQualityQuestions(['candidate one','candidate two'],['retained existing','candidate one','candidate two']);
      console.log(JSON.stringify({keys:Object.keys(q),types:Object.values(q).map(v=>v.type),
        first:q.value_0.instructions.candidateContent, second:q.value_1.instructions.candidateContent,
        whole:q.omission.instructions.resultingMemoryContents}));
    ''')
    assert row == {'keys': ['value_0', 'value_1', 'omission'], 'types': ['noul'] * 3,
                   'first': 'candidate one', 'second': 'candidate two',
                   'whole': ['retained existing', 'candidate one', 'candidate two']}


def test_supported_but_transient_or_incomplete_memory_is_proposed() -> None:
    row = isolated_run_bun(r'''
      import {combineMemoryQualityAnswers} from './packages/continual-learning/tests/memory-quality-research.ts';
      const answer=noul=>({type:'noul',noul});
      console.log(JSON.stringify([
        combineMemoryQualityAnswers({value_0:answer(.99),omission:answer(.01)},1),
        combineMemoryQualityAnswers({value_0:answer(.01),omission:answer(.01)},1),
        combineMemoryQualityAnswers({value_0:answer(.99),omission:answer(.99)},1),
        combineMemoryQualityAnswers({value_0:answer(.99),value_1:answer(.01),omission:answer(.01)},2),
      ]));
    ''')
    assert row[0] == {'decision': 'allow', 'failures': []}
    assert row[1] == {'decision': 'propose', 'failures': [{'reason': 'no-lasting-value', 'candidateIndex': 0}]}
    assert row[2] == {'decision': 'propose', 'failures': [{'reason': 'requested-knowledge-missing'}]}
    assert row[3] == {'decision': 'propose', 'failures': [{'reason': 'no-lasting-value', 'candidateIndex': 1}]}


def test_unknown_or_invalid_quality_never_becomes_allow_or_false_no_opportunity() -> None:
    row = isolated_run_bun(r'''
      import {combineMemoryQualityAnswers} from './packages/continual-learning/tests/memory-quality-research.ts';
      const good={value_0:{type:'noul',noul:.99},omission:{type:'noul',noul:.01}};
      const inputs=[undefined,{}, {...good,value_0:{type:'noul',noul:.5}},
        {...good,omission:{type:'noul',noul:.5}}, {...good,value_0:{type:'noul',noul:NaN}},
        {...good,value_0:{type:'choice',noul:.99}}, {...good,extra:{type:'noul',noul:.99}}];
      console.log(JSON.stringify(inputs.map(x=>combineMemoryQualityAnswers(x,1))));
    ''')
    assert all(value['decision'] == 'propose' and value['failures'] for value in row)
    assert row[2]['failures'] == [{'reason': 'uncertain', 'candidateIndex': 0}]
    assert row[3]['failures'] == [{'reason': 'uncertain'}]


def test_result_inventory_does_not_count_deleted_or_rewritten_old_knowledge() -> None:
    row = isolated_run_bun(r'''
      import {memoryQualityResultingContents} from './packages/continual-learning/tests/memory-quality-research.ts';
      const existing=[{name:'keep.md',content:'preserved requirement'}, {name:'replace.md',content:'old required context'}, {name:'remove.md',content:'deleted fact'}];
      const changes=[{name:'replace.md',op:'rewrite',content:'replacement without context'}, {name:'remove.md',op:'delete'}, {name:'new.md',op:'create',content:'new fact'}];
      const result=memoryQualityResultingContents(existing,changes);
      const invalid=[[{name:'absent.md',op:'delete'}],[{name:'keep.md',op:'create',content:'overwrite'}],
        [{name:'replace.md',op:'rewrite',content:'first'},{name:'replace.md',op:'delete'}]];
      console.log(JSON.stringify({result,unchanged:existing[1].content, rejected:invalid.map(change=>{try{memoryQualityResultingContents(existing,change);return false;}catch{return true;}})}));
    ''')
    assert row == {'result': ['preserved requirement', 'replacement without context', 'new fact'],
                   'unchanged': 'old required context', 'rejected': [True, True, True]}


def test_frozen_quality_corpus_has_valid_source_quotes_and_complete_result_inventories() -> None:
    row = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {normalizeNewMemoryProposals} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {memoryQualityQuestions,memoryQualityResultingContents} from './packages/continual-learning/tests/memory-quality-research.ts';
      const corpus=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/jev-memory-quality-cases.json','utf8'));
      let valid=0;for(const row of corpus.rows){
        const candidates=normalizeNewMemoryProposals(row.plan,row.snapshot);
        const result=memoryQualityResultingContents(row.existing,row.changes);
        const questions=memoryQualityQuestions(candidates.map(c=>c.content),result);
        if(candidates.length===row.expected.value.length&&result.length===candidates.length+row.existing.length
          &&Object.keys(questions).length===candidates.length+1)valid++;
      }
      console.log(JSON.stringify({valid,count:corpus.rows.length,heldout:corpus.heldout,humanGold:corpus.humanGold,
        known:corpus.rows.filter(r=>r.baseline).length,fresh:corpus.rows.filter(r=>!r.baseline).length}));
    ''')
    assert row == {'valid': 48, 'count': 48, 'heldout': False, 'humanGold': False, 'known': 32, 'fresh': 16}


def test_completeness_cannot_use_a_forged_result_body_or_stale_write_target() -> None:
    row = isolated_run_bun(r'''
      import fs from 'node:fs';import {prepareMemoryQualityCreate} from './packages/continual-learning/tests/memory-quality-research.ts';
      const row=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/jev-memory-quality-cases.json','utf8')).rows[0];
      const modes=['valid','forged-body','changed-target','unsupported-quote','pretend-rewrite'];
      console.log(JSON.stringify(modes.map(mode=>{const plan=structuredClone(row.plan),changes=structuredClone(row.changes);
        if(mode==='forged-body')changes[0].content='A missing requirement is falsely preserved here.';
        if(mode==='changed-target')changes[0].name='other.md';if(mode==='unsupported-quote')plan.newMemories[0].evidence[0].quote='never in frozen evidence';
        if(mode==='pretend-rewrite')changes[0].op='rewrite';
        try{prepareMemoryQualityCreate(plan,row.snapshot,row.existing,changes);return true;}catch{return false;}
      })));
    ''')
    assert row == [True, False, False, False, False]


def test_create_research_rejects_hidden_operations_metadata_and_case_aliases() -> None:
    row = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {prepareMemoryQualityCreate,memoryQualityResultingContents} from './packages/continual-learning/tests/memory-quality-research.ts';
      const row=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/jev-memory-quality-cases.json','utf8')).rows[0];
      const modes=['operation','inventory','case-alias','duplicate-inventory','duplicate-touch'];
      console.log(JSON.stringify(modes.map(mode=>{
        const plan=structuredClone(row.plan),existing=structuredClone(row.existing);
        if(mode==='operation')plan.operations=[{op:'delete',name:'other.md'}];
        if(mode==='inventory')plan.inventory=[{name:'other.md',content:'forged'}];
        if(mode==='case-alias')existing.push({name:row.changes[0].name.toUpperCase(),content:'existing'});
        try{
          if(mode==='duplicate-inventory')memoryQualityResultingContents([{name:'A.md',content:'a'},{name:'a.md',content:'b'}],[]);
          else if(mode==='duplicate-touch')memoryQualityResultingContents([{name:'A.md',content:'a'}],[{op:'rewrite',name:'a.md',content:'b'},{op:'delete',name:'A.md'}]);
          else prepareMemoryQualityCreate(plan,row.snapshot,existing,row.changes);
          return false;
        }catch{return true;}
      })));
    ''')
    assert row == [True] * 5
