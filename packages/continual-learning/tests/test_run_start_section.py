"""Required sections must not silently fall back to ignored guidelines."""
from support import run_bun


def test_missing_sections_fails_clearly_without_mutating_guidelines():
    value = run_bun('''
      import {setRunStartSection} from './packages/continual-learning/extensions/run-start-section.ts';
      const rows=[];
      for(const sections of [undefined,null,[],"invalid"]) {
        const options={customPrompt:'OWNER',promptGuidelines:['KEEP'],...(sections===undefined?{}:{sections})};
        let error='';try {setRunStartSection(options,'required','GUIDANCE')} catch(e) {error=e.message}
        rows.push({error,options});
      }
      console.log(JSON.stringify(rows));
    ''')
    for row in value:
        assert row['error'] == 'Continual-learning requires Pi 1.2 structured prompt sections.'
        assert row['options']['promptGuidelines'] == ['KEEP']
        assert row['options']['customPrompt'] == 'OWNER'
