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
        getCommands:()=>[], sendMessage:(message)=>messages.push(message.content)}});
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


def test_first_resource_safeguard_request_carries_absent_target_and_supported_path(tmp_path: Path) -> None:
    result = run_bun(f'''
      import fs from 'node:fs';
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / 'agent'))};
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const commands={{}},messages=[];
      register({{on(){{}},registerEntryRenderer(){{}},registerCommand:(n,c)=>commands[n]=c,
        getCommands:()=>[],sendMessage:m=>messages.push(m)}});
      await commands.harness.handler('避免后续 D0 的流量被打爆',{{cwd:{json.dumps(str(tmp_path))},ui:{{notify(){{}}}}}});
      console.log(JSON.stringify({{messages,files:fs.readdirSync({json.dumps(str(tmp_path))})}}));
    ''')
    assert result['files'] == []
    assert len(result['messages']) == 1
    prompt = result['messages'][0]['content']
    assert 'Target state checked by the parent: absent' in prompt
    assert 'Missing configuration is not a blocker' in prompt
    assert 'scoped text guidance' in prompt
    assert 'Do not invent' in prompt and 'rate limit' in prompt
    assert 'ask one concise' in prompt
    assert '避免后续 D0 的流量被打爆' in prompt


def test_native_first_run_fixture_enforces_exact_target_boundary(tmp_path: Path) -> None:
    result = run_bun(f'''
      process.env.PI_HARNESS_REAL='1';
      process.env.PI_HARNESS_SCHEMA_DOCS=JSON.stringify(['/tmp/public-sdk/README.md']);
      const {{default:register}}=await import('./packages/continual-learning/tests/harness-first-run-fixture.ts');
      const hooks={{}},events=[];
      register({{on:(n,f)=>(hooks[n]??=[]).push(f),registerEntryRenderer(){{}},registerCommand(){{}},
        getCommands:()=>[],appendEntry:(type,data)=>events.push({{type,data}})}});
      const gate=hooks.tool_call.at(-1);
      const target=process.cwd()+'/.pi/harness.json';
      const docRead=gate({{toolName:'read',input:{{path:'/tmp/public-sdk/README.md'}}}});
      const docWrite=gate({{toolName:'write',input:{{path:'/tmp/public-sdk/README.md',content:'x'}}}});
      const results=[gate({{toolName:'read',input:{{path:'/tmp/host-private'}}}}),
        gate({{toolName:'write',input:{{path:'/tmp/production',content:'x'}}}}),
        gate({{toolName:'bash',input:{{command:'true'}}}}),
        gate({{toolName:'read',input:{{path:target,offset:1}}}}),
        gate({{toolName:'read',input:{{path:'.pi/harness.json'}}}}),
        gate({{toolName:'write',input:{{path:target,content:'{{"rules":[]}}'}}}}),
        gate({{toolName:'write',input:{{path:target,content:'{{"rules":[]}}'}}}})];
      process.env.PI_HARNESS_FOLLOWUP='1';
      register({{on:(n,f)=>(hooks[n]??=[]).push(f),registerEntryRenderer(){{}},registerCommand(){{}},getCommands:()=>[],appendEntry:(type,data)=>events.push({{type,data}})}});
      const followup=hooks.tool_call.at(-1)({{toolName:'write',input:{{path:target,content:'{{"rules":[]}}'}}}});
      console.log(JSON.stringify({{results,events,followup,docRead:docRead??null,docWrite}}));
    ''')
    assert all(row and row['block'] for row in result['results'][:4])
    assert result['results'][4:6] == [None, None]
    assert result['results'][6]['block']
    assert len(result['events']) == 7
    assert result['docRead'] is None and result['docWrite']['block']
    assert result['followup']['block']


def test_regex_json_examples_decode_to_the_described_selector() -> None:
    prompt = run_bun('''
      import {buildHarnessRulePrompt} from './packages/continual-learning/extensions/guardrails.ts';
      console.log(JSON.stringify(buildHarnessRulePrompt('resource safeguard','/tmp/project/.pi/harness.json')));
    ''')
    import re
    examples = [json.loads(value)['text'] for value in re.findall(r'\{"text":"[^\n]*?"\}', prompt)]
    assert len(examples) == 2
    assert re.search(examples[0], 'plain RESOURCE mention')
    assert not re.search(examples[1], 'plain RESOURCE mention')


def test_first_creation_uses_project_relative_access_and_no_scratch_verification() -> None:
    prompt = run_bun('''
      import {buildHarnessRulePrompt} from './packages/continual-learning/extensions/guardrails.ts';
      console.log(JSON.stringify(buildHarnessRulePrompt('避免后续 D0 的流量被打爆', '/tmp/random-project/.pi/harness.json', 'project shared harness.json (git-tracked)', [], 'absent', '/tmp/random-project')));
    ''')
    assert 'Read the exact target .pi/harness.json' in prompt
    assert 'use write at .pi/harness.json' in prompt
    assert 'Read back .pi/harness.json' in prompt
    assert 'Do not create verification scripts or scratch files' in prompt
    assert 'If no non-executing evaluator is available' in prompt
    assert 'report trigger verification as unverified' in prompt


def test_global_target_outside_project_keeps_exact_absolute_access() -> None:
    prompt = run_bun('''
      import {buildHarnessRulePrompt} from './packages/continual-learning/extensions/guardrails.ts';
      console.log(JSON.stringify(buildHarnessRulePrompt('resource safeguard', '/tmp/agent/harness.json', 'global shared harness.json', [], 'absent', '/tmp/project')));
    ''')
    assert 'Read the exact target /tmp/agent/harness.json' in prompt
    assert 'use write at /tmp/agent/harness.json' in prompt
    assert 'Read back /tmp/agent/harness.json' in prompt
    assert '../agent' not in prompt


def test_project_protocol_has_one_canonical_tool_path_and_parent_schema_authority() -> None:
    prompt = run_bun('''
      import {buildHarnessRulePrompt} from './packages/continual-learning/extensions/guardrails.ts';
      console.log(JSON.stringify(buildHarnessRulePrompt('resource safeguard', '/tmp/random-project/.pi/harness.json', 'project shared harness.json (git-tracked)', [], 'absent', '/tmp/random-project')));
    ''')
    assert '/tmp/random-project' not in prompt
    assert 'Use the exact tool path .pi/harness.json; do not expand' in prompt
    assert 'Do not search SDK documentation' in prompt
    assert 'parent validates the complete candidate before write' in prompt


def test_authoring_requires_same_kind_resource_negative_not_only_unrelated_topic() -> None:
    prompt = run_bun('''
      import {buildHarnessRulePrompt} from './packages/continual-learning/extensions/guardrails.ts';
      console.log(JSON.stringify(buildHarnessRulePrompt('resource safeguard','/tmp/project/.pi/harness.json')));
    ''')
    assert 'another resource with the same action' in prompt
    assert 'Never broaden a resource-specific rule with a standalone incident phrase' in prompt
