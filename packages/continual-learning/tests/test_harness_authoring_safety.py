from __future__ import annotations

import json
from pathlib import Path

import pytest

from support import isolated_run_bun as run_bun


@pytest.mark.parametrize('rule_request', ['Every project change must preserve semantics', 'Make the popup better', '--local unknown semantic interception'])
def test_command_never_precreates_a_target_before_expressibility(tmp_path: Path, rule_request: str) -> None:
    result = run_bun(f'''
      import fs from 'node:fs';
      process.env.PI_CODING_AGENT_DIR = {json.dumps(str(tmp_path / 'agent'))};
      const {{default: register}} = await import('./packages/continual-learning/extensions/guardrails.ts');
      const commands = {{}}; const messages = [];
      register({{on(){{}}, registerEntryRenderer(){{}}, registerCommand:(n,c)=>commands[n]=c,
        getCommands:()=>[], sendUserMessage:(content)=>messages.push(content)}});
      await commands.harness.handler({json.dumps(rule_request)}, {{cwd:{json.dumps(str(tmp_path))},ui:{{notify(){{}}}}}});
      console.log(JSON.stringify({{files:fs.readdirSync({json.dumps(str(tmp_path))}),messages}}));
    ''')
    assert result['files'] == []
    assert len(result['messages']) == 1
    assert 'no file writes' in result['messages'][0]


def test_prompt_orders_assessment_before_one_complete_write_and_safe_verification() -> None:
    result = run_bun('''
      import {buildHarnessRulePrompt} from './packages/continual-learning/extensions/guardrails.ts';
      console.log(JSON.stringify(buildHarnessRulePrompt('fullscreen popup means an overlay relationship', '/tmp/project/.pi/harness.json')));
    ''')
    assert result.index('Read the exact target') < result.index('Assess expressibility') < result.index('Write once') < result.index('Read back')
    assert 'no preliminary empty file' in result
    assert 'no file writes' in result
    assert 'does not authorize' in result and 'AGENTS.md' in result
    assert 'non-executing evaluator' in result and 'dangerous' in result
    assert 'opacity, input, or scroll' not in result
    assert 'fullscreen popup' not in result.split('User request:')[0]
    assert 'Preserve the user' in result and 'clarify' in result
    assert 'explicit user authorization' in result
    assert len(result) < 6500


def test_invalid_flat_guidance_is_rejected_without_mutation() -> None:
    result = run_bun('''
      import {validateHarnessWrite} from './packages/continual-learning/extensions/guardrails.ts';
      const prior = {rules:[{id:'bad',skill:'unknown',instructions:'overlay'},{id:'ok',skill:'known',instructions:'valid'}]};
      const before=JSON.stringify(prior);
      console.log(JSON.stringify({errors:validateHarnessWrite({content:before},new Set(['known']),prior),unchanged:JSON.stringify(prior)===before}));
    ''')
    assert result['errors'] and result['unchanged']


def test_registry_rejects_unknown_names_without_hiding_valid_siblings() -> None:
    result = run_bun('''
      import {mergeLayers} from './packages/continual-learning/extensions/guardrail-engine.ts';
      const config=mergeLayers([{source:'project',rules:[{id:'bad',skill:'unknown',instructions:'inert'},{id:'ok',skill:'known',instructions:'valid'}]}],new Set(['known']));
      console.log(JSON.stringify({ids:config.rules.map(r=>r.id),errors:config.errors}));
    ''')
    assert result['ids'] == ['ok']
    assert any('unknown' in error for error in result['errors'])


def test_global_personal_write_is_blocked(tmp_path: Path) -> None:
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / 'agent'))};
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks={{}};
      register({{on:(n,f)=>hooks[n]=f,registerEntryRenderer(){{}},registerCommand(){{}},getCommands:()=>[]}});
      console.log(JSON.stringify(await hooks.tool_call({{toolName:'write',input:{{path:{json.dumps(str(tmp_path / 'agent/harness.local.json'))},content:'{{}}'}}}},{{cwd:{json.dumps(str(tmp_path))}}})));
    ''')
    assert result['block'] is True
    assert result['reason'].startswith('Use ~/.pi/agent/harness.json')
