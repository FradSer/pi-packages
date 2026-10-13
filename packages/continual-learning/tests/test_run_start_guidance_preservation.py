"""Registered guidance hooks preserve scope across uncertain reads and scans."""
import json
from support import run_bun


def test_malformed_config_preserves_complete_scoped_branch_delivery(tmp_path):
    value = run_bun(f'''
      import fs from 'node:fs';
      import register from './packages/continual-learning/extensions/harness-guidance.ts';
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(cwd+'/.pi');
      fs.writeFileSync(cwd+'/.pi/harness.json','{{malformed');
      const scoped='[harness:saved] Only for subjects matching "needle"; a historical match does not extend this guidance to unrelated tasks.\\nCOMPLETE_SCOPED_GUIDANCE';
      const branch=[{{type:'custom',customType:'harness-guidance-delivery',data:{{entries:[{{id:'saved',revision:'old',status:'active',text:scoped,source:'project'}}]}}}}];
      const hooks={{}},appended=[];register({{on:(n,h)=>hooks[n]=h,registerEntryRenderer(){{}},appendEntry:(customType,data)=>appended.push({{customType,data}})}});
      const options={{sections:{{}},skills:[]}};
      const returned=hooks.before_agent_start({{prompt:'plain',systemPromptOptions:options}},{{cwd,sessionManager:{{getBranch:()=>branch,buildContextEntries:()=>[]}}}});
      console.log(JSON.stringify({{options,returned:returned??null,appended,scoped}}));
    ''', env={'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    assert value['returned'] is None
    assert value['options']['sections']['harness_guidance'] == value['scoped']
    assert any(entry['data'].get('kind') == 'text-incomplete' for entry in value['appended'])
    delivery = next(entry['data'] for entry in value['appended'] if entry['customType'] == 'harness-guidance-delivery')
    assert delivery['entries'][0]['text'] == value['scoped']
    assert delivery['entries'][0]['status'] == 'active'


def test_overbudget_scan_never_reintroduces_old_unscoped_guidance(tmp_path):
    value = run_bun(f'''
      import fs from 'node:fs';
      import register from './packages/continual-learning/extensions/harness-guidance.ts';
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(cwd+'/.pi');
      fs.writeFileSync(cwd+'/.pi/harness.json',JSON.stringify({{rules:[{{id:'old',text:'needle',instructions:'CURRENT_SCOPED_GUIDANCE'}}]}}));
      const scoped='[harness:valid] Only for subjects matching "other"; a historical match does not extend this guidance to unrelated tasks.\\nVALID_SCOPED_GUIDANCE';
      const branch=[{{type:'custom_message',customType:'harness-guidance',details:{{entries:[{{id:'old',revision:'old',status:'active',text:'UNSCOPED OLD GUIDANCE'}},{{id:'valid',revision:'saved',status:'active',text:scoped}}]}}}}];
      const hooks={{}},appended=[];register({{on:(n,h)=>hooks[n]=h,registerEntryRenderer(){{}},appendEntry:(customType,data)=>appended.push({{customType,data}})}});
      const options={{sections:{{}},skills:[]}};
      hooks.before_agent_start({{prompt:'x'.repeat(2000001),systemPromptOptions:options}},{{cwd,sessionManager:{{getBranch:()=>branch,buildContextEntries:()=>[]}}}});
      console.log(JSON.stringify({{options,appended,scoped}}));
    ''', env={'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    section = value['options']['sections'].get('harness_guidance', '')
    assert 'UNSCOPED OLD GUIDANCE' not in section
    assert value['scoped'] in section
    notices = [entry['data']['prompt'] for entry in value['appended'] if entry['data'].get('kind') == 'text-incomplete']
    assert any('scope' in notice.lower() for notice in notices)


def test_legacy_skill_guidance_has_task_scope_and_plain_read_does_not_invoke(tmp_path):
    value = run_bun(f'''
      import fs from 'node:fs';
      import register from './packages/continual-learning/extensions/harness-guidance.ts';
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(cwd+'/.pi');
      fs.writeFileSync(cwd+'/.pi/harness.json',JSON.stringify({{skillPrompts:{{review:{{prompt:'LEGACY_BODY',target:'user'}}}}}}));
      const hooks={{}};register({{on:(n,h)=>hooks[n]=h,registerEntryRenderer(){{}},appendEntry(){{}}}});
      const ctx={{cwd,sessionManager:{{getBranch:()=>[],buildContextEntries:()=>[]}}}};
      const start=prompt=>{{const options={{sections:{{}},skills:[{{name:'review'}}]}};const returned=hooks.before_agent_start({{prompt,systemPromptOptions:options}},ctx);return {{options,returned:returned??null}};}};
      console.log(JSON.stringify({{invoked:start('<skill name="review" location="/fixture/SKILL.md">\\nbody\\n</skill>\\n\\ntask'),plain:start('Read /fixture/SKILL.md')}}));
    ''', env={'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    section = value['invoked']['options']['sections']['harness_guidance']
    assert 'Only for this /skill:review task; retained history does not extend its scope.\nLEGACY_BODY' in section
    assert value['invoked']['returned'] is None
    assert 'harness_guidance' not in value['plain']['options']['sections']
