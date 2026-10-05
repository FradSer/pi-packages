from support import isolated_run_bun


def test_diagnostic_output_rejects_untrusted_strings_and_labels() -> None:
    result = isolated_run_bun(r'''
      import {controlledJevAnswers} from './packages/continual-learning/tests/jev-controlled-diagnostics.ts';
      const question={type:'choice',criteria:{compatible:'known description',contradicts:'known description',unclear:'known description'}};
      const good={type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradicts:0,unclear:0}};
      console.log(JSON.stringify({
        good:controlledJevAnswers({answers:{counter_0_0:good}},{counter_0_0:question}),
        unsafe:controlledJevAnswers({answers:{counter_0_0:{...good,choice:'UNTRUSTED_PRIVATE_TEXT'},counter_1_0:{...good,probabilities:{...good.probabilities,UNTRUSTED_PRIVATE_TEXT:0}},counter_2_0:{...good,confidence:'UNTRUSTED_PRIVATE_TEXT'},UNTRUSTED_PRIVATE_TEXT:good}},{counter_0_0:question,counter_1_0:question,counter_2_0:question,UNTRUSTED_PRIVATE_TEXT:question})
      }));
    ''')
    assert result['good']['counter_0_0']['choice'] == 'compatible'
    assert result['unsafe'] == {}
