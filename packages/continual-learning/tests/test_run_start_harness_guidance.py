import json
from support import run_bun


def test_guidance_is_additive_repeated_and_old_injections_are_filtered(tmp_path):
    result = run_bun(f'''
      import fs from 'node:fs';
      import register from './packages/continual-learning/extensions/harness-guidance.ts';
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(cwd+'/.pi');
      fs.writeFileSync(cwd+'/.pi/harness.json',JSON.stringify({{rules:[{{id:'text',text:'needle',instructions:'SCOPED_TEXT'}},{{id:'skill',skill:'review',instructions:'SCOPED_SKILL'}}],skillPrompts:{{review:{{prompt:'LEGACY_GUIDANCE',target:'system'}}}}}}));
      const hooks={{}},entries=[];register({{on:(n,h)=>hooks[n]=h,registerEntryRenderer(){{}},appendEntry:(customType,data)=>entries.push({{type:'custom',customType,data}})}});
      const ctx={{cwd,sessionManager:{{buildContextEntries:()=>[],getBranch:()=>entries}}}};
      const start=()=>{{const options={{skills:[{{name:'review'}}],sections:{{other:'OTHER_MARKER'}},promptGuidelines:['EXISTING']}};const returned=hooks.before_agent_start({{prompt:'<skill name="review" location="/fixture/SKILL.md">\\nbody\\n</skill>\\n\\nneedle',systemPromptOptions:options}},ctx);return {{options,returned:returned??null}};}};
      const first=start(),second=start();
      ctx.sessionManager.buildContextEntries=()=>{{throw Error('incomplete')}};
      const incomplete=start();
      const filtered=hooks.context({{messages:[{{role:'custom',customType:'harness-guidance',content:'OLD'}},{{role:'custom',customType:'skill-prompt-guidance',content:'OLD'}},{{role:'custom',customType:'workflow',content:'KEEP'}}]}});
      console.log(JSON.stringify({{first,second,incomplete,entries,filtered}}));
    ''', env={'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    for run in ('first', 'second', 'incomplete'):
        assert result[run]['returned'] is None
        section = result[run]['options']['sections']['harness_guidance']
        assert all(marker in section for marker in ('SCOPED_TEXT', 'SCOPED_SKILL', 'LEGACY_GUIDANCE')), (run, result)
        assert result[run]['options']['sections']['other'] == 'OTHER_MARKER'
        assert result[run]['options']['promptGuidelines'] == ['EXISTING']
    assert result['filtered']['messages'] == [{'role': 'custom', 'customType': 'workflow', 'content': 'KEEP'}]
    assert any(entry['data'].get('entries') for entry in result['entries'])
