from pathlib import Path

from test_guardrails_extension import run_bun


def test_unchanged_invalid_guidance_is_rejected_without_mutation() -> None:
    result = run_bun('''
      import { validateHarnessWrite } from './packages/continual-learning/extensions/guardrails.ts';
      const prior = { policies: [], disabled: [], skillPrompts: { CM5: 'overlay', known: {prompt:'valid', target:'system'} } };
      const before = JSON.stringify(prior);
      const errors = validateHarnessWrite({ content: before }, new Set(['known']), prior);
      console.log(JSON.stringify({ errors, unchanged: JSON.stringify(prior) === before }));
    ''')
    assert result['errors']
    assert result['unchanged']


def test_runtime_registry_rejects_unknown_names_and_keeps_valid_siblings() -> None:
    result = run_bun('''
      import { mergeLayers } from './packages/continual-learning/extensions/guardrail-engine.ts';
      const config = mergeLayers([{source:'project', skillPrompts: {
        CM5:'overlay', unknown:{prompt:'inert',target:'system'}, known:{prompt:'valid',target:'system'}
      }}], new Set(['known']));
      console.log(JSON.stringify({names:Object.keys(config.skillPrompts), errors:config.errors}));
    ''')
    assert result['names'] == ['known']
    assert any('unknown' in error for error in result['errors'])


def test_prompt_preserves_semantic_boundary_and_existing_invalid_data() -> None:
    result = run_bun('''
      import { buildHarnessRulePrompt } from './packages/continual-learning/extensions/guardrails.ts';
      console.log(JSON.stringify({prompt:buildHarnessRulePrompt('fullscreen popup means overlay relationship', '/tmp/project/.pi/harness.json')}));
    ''')
    assert 'opacity, input, or scroll restrictions' in result['prompt']
    assert 'explicit user authorization' in result['prompt']
    assert 'Global configuration uses ~/.pi/agent/harness.json' in result['prompt']
    assert 'project shared .pi/harness.json' in result['prompt']
    assert 'explicit personal choice' in result['prompt']
    assert 'Work exclusively in /tmp/project/.pi/harness.json' in result['prompt']
    assert 'Do not ' not in result['prompt']
    assert 'Never ' not in result['prompt']


def test_global_personal_write_is_blocked() -> None:
    result = run_bun('''
      import path from 'node:path';
      import register from './packages/continual-learning/extensions/guardrails.ts';
      import { configPaths } from './packages/continual-learning/extensions/guardrail-config.ts';
      const hooks = {};
      register({on:(name,fn)=>hooks[name]=fn,registerEntryRenderer:()=>{},registerCommand:()=>{}});
      const cwd = '/tmp/harness-scope-probe';
      const target = path.join(path.dirname(configPaths(cwd).user), 'harness.local.json');
      const result = await hooks.tool_call({toolName:'write',input:{path:target,content:'{}'}},{cwd});
      console.log(JSON.stringify(result));
    ''')
    assert result['block'] is True
    assert result['reason'].startswith('Use ~/.pi/agent/harness.json for global configuration.')


def test_consolidation_default_target_is_project_shared() -> None:
    source = (Path(__file__).resolve().parents[1] / 'extensions' / 'harness-consolidation.ts').read_text()
    assert 'opts.targetPath ?? configPaths(opts.cwd).project;' in source

