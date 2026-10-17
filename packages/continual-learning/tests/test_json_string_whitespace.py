"""Only lossless string-whitespace serialization may recover a repair response."""
from support import isolated_run_bun


def test_whitespace_normalization_preserves_literal_values_and_refuses_other_damage():
    result = isolated_run_bun(r'''
      import {normalizeJsonStringWhitespace} from './packages/continual-learning/extensions/json-string-whitespace.ts';
      const normalize=text=>normalizeJsonStringWhitespace(text,4096);
      const expected='one\n\ttwo\rthree\\n escaped "quoted" 文';
      const raw=JSON.stringify({kind:'incremental-memory-amendment',body:expected}).replace('\\n','\n').replace('\\t','\t').replace('\\r','\r');
      const corrected=normalize(raw),value=corrected?JSON.parse(corrected.text):null;
      const invalid=[JSON.stringify({body:'valid\nwhitespace'}),'{"body":"unterminated\n',
        '{"body":"a\n"}{"body":"b"}','[{"body":"a\n"}]',
        'prose {"body":"a\n"}','{"body":"a\n",}',
        '{"body":"a\n\\q"}','{"body":"a\\\nb"}',
        '{"body":"a\n\u0000b"}','{"body":"a\n\u0001b"}',
        '{"body":"a\n"} trailing','{"body":"a\n","missing":}'];
      const big='{"body":"'+'\n'.repeat(40)+'"}';
      console.log(JSON.stringify({corrected,value,invalid:invalid.map(normalize),rawBound:normalizeJsonStringWhitespace(raw,10),expandedBound:normalizeJsonStringWhitespace(big,60)}));
    ''')
    assert result['value']['body'] == 'one\n\ttwo\rthree\\n escaped "quoted" 文'
    assert result['corrected']['counts'] == {'newline': 1, 'carriageReturn': 1, 'tab': 1}
    assert all(item is None for item in result['invalid'])
    assert result.get('rawBound') is None and result.get('expandedBound') is None
