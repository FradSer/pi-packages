from support import isolated_run_bun


def test_noul_pair_requires_all_original_negative_thresholds_for_independence() -> None:
    # Given four independent judgments, When any material risk is uncertain,
    # missing, positive or invalid, Then it cannot assert independence.
    rows = isolated_run_bun(r'''
      import {interpretMemoryPairNoul,memoryPairNoulQuestions} from './packages/continual-learning/tests/jev-memory-pair-noul.ts';
      const make=(changes={})=>Object.fromEntries(Object.keys(memoryPairNoulQuestions()).map(k=>[k,{type:'noul',noul:changes[k]??.1}]));
      const rows=[];for(const changes of [{},{dependent:.11},{missingContext:.9},{conflict:.9},{dependent:.9},{duplicate:.9},{duplicate:.5}])rows.push(interpretMemoryPairNoul(make(changes)));
      rows.push(interpretMemoryPairNoul({}));const malformed=make();malformed.conflict.noul=NaN;rows.push(interpretMemoryPairNoul(malformed));const extra=make();extra.privateOriginal={type:'noul',noul:0};rows.push(interpretMemoryPairNoul(extra));console.log(JSON.stringify(rows));
    ''')
    assert rows[0]['independenceObserved']
    assert all(not row['independenceObserved'] for row in rows[1:])
    assert [row['relation'] for row in rows[:7]] == ['independent', None, 'unclear', 'conflict', 'dependent', 'duplicate', None]
    assert all(row['status'] == 'invalid-response' for row in rows[7:])
    assert 'privateOriginal' not in str(rows)
