from __future__ import annotations

import json
from test_guardrails_extension import run_bun


def test_rule_validation_accepts_valid_selectors() -> None:
    result = run_bun('''
      import { validateRuleDeclaration } from './packages/continual-learning/extensions/guardrail-engine.ts';
      const available = new Set(['open-deskos-widget']);

      const validSkill = validateRuleDeclaration({
        id: 'overlay',
        skill: 'open-deskos-widget',
        instructions: 'Fullscreen popup is an overlay.',
      }, available);

      const validBashBlock = validateRuleDeclaration({
        id: 'no-rm',
        bash: '^rm -rf',
        action: 'block',
        message: 'Do not use rm -rf.',
      }, available);

      const validBashConfirm = validateRuleDeclaration({
        id: 'confirm-push',
        bash: '\\bgit\\s+push\\b',
        action: 'confirm',
        message: 'Confirm push target.',
      }, available);

      const validBashPass = validateRuleDeclaration({
        id: 'push-guidance',
        bash: '\\bgit\\s+push\\b',
        message: 'Report push status.',
      }, available);

      const validText = validateRuleDeclaration({
        id: 'proj-status',
        text: 'A项目|Project A',
        instructions: 'Project A is deprecated.',
      }, available);

      const validDisabled = validateRuleDeclaration({
        id: 'disabled-rule',
        enabled: false,
      }, available);

      console.log(JSON.stringify({
        validSkill,
        validBashBlock,
        validBashConfirm,
        validBashPass,
        validText,
        validDisabled,
      }));
    ''')
    assert result['validSkill'] == []
    assert result['validBashBlock'] == []
    assert result['validBashConfirm'] == []
    assert result['validBashPass'] == []
    assert result['validText'] == []
    assert result['validDisabled'] == []


def test_rule_validation_rejects_ambiguous_or_malformed_forms() -> None:
    result = run_bun('''
      import { validateRuleDeclaration } from './packages/continual-learning/extensions/guardrail-engine.ts';
      const available = new Set(['open-deskos-widget']);

      const emptyAction = validateRuleDeclaration({
        id: 'bad-action',
        bash: 'git',
        action: '',
        message: 'msg',
      }, available);

      const nullAction = validateRuleDeclaration({
        id: 'null-action',
        bash: 'git',
        action: null,
        message: 'msg',
      }, available);

      const multiSelectors = validateRuleDeclaration({
        id: 'multi',
        skill: 'open-deskos-widget',
        bash: 'git',
        instructions: 'inst',
      }, available);

      const actionOnSkill = validateRuleDeclaration({
        id: 'act-skill',
        skill: 'open-deskos-widget',
        action: 'block',
        instructions: 'inst',
      }, available);

      const unknownSkill = validateRuleDeclaration({
        id: 'unk',
        skill: 'nonexistent-skill',
        instructions: 'inst',
      }, available);

      const invalidRegex = validateRuleDeclaration({
        id: 'bad-re',
        bash: '[unclosed',
        message: 'msg',
      }, available);

      console.log(JSON.stringify({
        emptyAction,
        nullAction,
        multiSelectors,
        actionOnSkill,
        unknownSkill,
        invalidRegex,
      }));
    ''')
    assert len(result['emptyAction']) > 0
    assert len(result['nullAction']) > 0
    assert len(result['multiSelectors']) > 0
    assert len(result['actionOnSkill']) > 0
    assert len(result['unknownSkill']) > 0
    assert len(result['invalidRegex']) > 0


def test_layer_merging_precedence() -> None:
    result = run_bun('''
      import { mergeLayers } from './packages/continual-learning/extensions/guardrail-engine.ts';

      const globalLayer = {
        source: 'user',
        rules: [
          { id: 'shared', bash: 'git push', action: 'block', message: 'Global block' },
          { id: 'to-disable', skill: 'demo', instructions: 'Global instructions' },
          { id: 'to-change', skill: 'demo', instructions: 'Global skill' },
          { id: 'global-only', bash: 'curl', message: 'Global curl' },
        ],
      };

      const projectLayer = {
        source: 'project',
        rules: [
          // Project overrides bash block with pass + message
          { id: 'shared', bash: 'git push', message: 'Project message' },
          // Project disables to-disable
          { id: 'to-disable', enabled: false },
          // Project changes selector from skill to text
          { id: 'to-change', text: 'Keyword', instructions: 'Project text' },
        ],
      };

      const config = mergeLayers([globalLayer, projectLayer], new Set(['demo']));
      const rules = config.rules;

      console.log(JSON.stringify({
        rules,
        errors: config.errors,
      }));
    ''')
    rules = {r['id']: r for r in result['rules']}
    # shared is overridden: bash rule without action (pass + message), message is 'Project message'
    assert rules['shared']['source'] == 'project'
    assert rules['shared'].get('action') is None
    assert rules['shared']['message'] == 'Project message'

    # to-disable is disabled
    assert rules['to-disable']['enabled'] is False
    assert rules['to-disable']['source'] == 'project'

    # to-change selector changed to text
    assert rules['to-change']['source'] == 'project'
    assert 'text' in rules['to-change']
    assert 'skill' not in rules['to-change']

    # global-only is inherited
    assert rules['global-only']['source'] == 'user'


def test_layer_merging_reenable_and_duplicate_ids() -> None:
    result = run_bun('''
      import { mergeLayers } from './packages/continual-learning/extensions/guardrail-engine.ts';

      const userLayer = {
        source: 'user',
        rules: [
          { id: 're-enabled', enabled: false },
        ],
      };

      const projectLayer = {
        source: 'project',
        rules: [
          { id: 're-enabled', bash: 'test', message: 'Now enabled' },
          { id: 'dup', text: 'A', instructions: 'First' },
          { id: 'dup', text: 'B', instructions: 'Second' },
        ],
      };

      const config = mergeLayers([userLayer, projectLayer]);
      const valid = mergeLayers([userLayer, { source: 'project', rules: [projectLayer.rules[0]] }]);
      console.log(JSON.stringify({
        rules: config.rules, validRules: valid.rules,
        errors: config.errors,
        complete: config.bashEvaluationComplete,
      }));
    ''')
    rules = {r['id']: r for r in result['rules']}
    assert rules['re-enabled']['enabled'] is False
    assert result['complete'] is False
    assert any('dup' in e for e in result['errors'])
    assert result['validRules'][0]['enabled'] is True
    assert result['validRules'][0]['message'] == 'Now enabled'


def test_bash_evaluation_decisions() -> None:
    result = run_bun('''
      import { evaluateBash, mergeLayers } from './packages/continual-learning/extensions/guardrail-engine.ts';

      const layer = {
        source: 'project',
        rules: [
          { id: 'msg-only-1', bash: 'push', message: 'Msg 1' },
          { id: 'msg-only-2', bash: 'push', message: 'Msg 2' },
          { id: 'confirm-push', bash: 'git push', action: 'confirm', message: 'Confirm push' },
          { id: 'block-force', bash: '--force', action: 'block', message: 'No force' },
        ],
      };
      const config = mergeLayers([layer]);

      const passResult = evaluateBash(config, 'git status');
      const msgResult = evaluateBash(config, 'npm push-all');
      const confirmResult = evaluateBash(config, 'git push origin');
      const blockResult = evaluateBash(config, 'git push origin --force');

      console.log(JSON.stringify({
        passResult,
        msgResult,
        confirmResult,
        blockResult,
      }));
    ''')
    # No matches -> execute, no messages
    assert result['passResult']['decision'] == 'execute'
    assert result['passResult']['messages'] == []

    # Omitted action -> execute with messages
    assert result['msgResult']['decision'] == 'execute'
    assert set(result['msgResult']['messages']) == {'Msg 1', 'Msg 2'}

    # Confirm + omitted -> confirm, collects all messages
    assert result['confirmResult']['decision'] == 'confirm'
    assert 'Confirm push' in result['confirmResult']['messages']
    assert 'Msg 1' in result['confirmResult']['messages']

    # Block + confirm + omitted -> block (block wins), collects all messages
    assert result['blockResult']['decision'] == 'block'
    assert 'No force' in result['blockResult']['messages']
    assert 'Confirm push' in result['blockResult']['messages']


def test_skill_and_text_evaluation() -> None:
    result = run_bun('''
      import { evaluateSkill, evaluateText, mergeLayers } from './packages/continual-learning/extensions/guardrail-engine.ts';

      const layer = {
        source: 'project',
        rules: [
          { id: 'skill-1', skill: 'open-deskos-widget', instructions: 'Overlay semantics' },
          { id: 'skill-2', skill: 'open-deskos-widget', instructions: 'Test via SSH' },
          { id: 'skill-other', skill: 'commit', instructions: 'Commit conventions' },
          { id: 'text-proj', text: 'A项目|Project A', instructions: 'Project A deprecated' },
          { id: 'text-ui', text: 'dialog|modal', instructions: 'Use Dialog component' },
        ],
      };
      const config = mergeLayers([layer], new Set(['open-deskos-widget', 'commit']));

      const widgetMatches = evaluateSkill(config, 'open-deskos-widget');
      const textResult = evaluateText(config, ['Talking about Project A status', 'unrelated text']);

      console.log(JSON.stringify({
        widgetMatches,
        textMatches: textResult.matches,
        textIncomplete: textResult.incomplete,
      }));
    ''')
    assert len(result['widgetMatches']) == 2
    assert {r['id'] for r in result['widgetMatches']} == {'skill-1', 'skill-2'}

    assert result['textIncomplete'] is False
    assert len(result['textMatches']) == 1
    assert result['textMatches'][0]['id'] == 'text-proj'


def test_text_guidance_planner_lifecycle() -> None:
    result = run_bun('''
      import { planTextGuidance, HARNESS_GUIDANCE_CUSTOM_TYPE } from './packages/continual-learning/extensions/harness-guidance-planner.ts';
      import { mergeLayers } from './packages/continual-learning/extensions/guardrail-engine.ts';

      const config = mergeLayers([{ source:'project', rules:[
        { id:'proj-a', text:'A项目|Project A', instructions:'A项目已废弃。' },
      ]}]);

      // Turn 1: prompt mentions Project A, nothing retained yet.
      const step1 = planTextGuidance([], '请问 Project A 现在的进展？', config);
      // before_agent_start persists this message; it is retained on the branch.
      const delivered = {
        role:'custom', customType: HARNESS_GUIDANCE_CUSTOM_TYPE, display:false,
        content: step1.entries.map(e=>e.text).join('\\n\\n'),
        details: { entries: step1.entries },
      };

      // Turn 2: guidance retained; new prompt without keyword -> dedup, no copy.
      const retained2 = [ {role:'user',content:'请问 Project A 现在的进展？'}, delivered ];
      const step2 = planTextGuidance(retained2, '后续怎么做？', config);

      // Turn 3: instructions updated -> one update entry (new revision).
      const updated = mergeLayers([{ source:'project', rules:[
        { id:'proj-a', text:'A项目|Project A', instructions:'A项目已废弃，请使用方案 B。' },
      ]}]);
      const step3 = planTextGuidance(retained2, '关于 A项目', updated);

      // Turn 4: rule disabled -> one retired entry.
      const disabled = mergeLayers([{ source:'project', rules:[ { id:'proj-a', enabled:false } ]}]);
      const step4 = planTextGuidance(retained2, '关于 A项目', disabled);

      console.log(JSON.stringify({
        step1: step1.entries, step1Incomplete: step1.incomplete,
        step2Count: step2.entries.length,
        step3: step3.entries, step4: step4.entries,
      }));
    ''')
    assert result['step1Incomplete'] is False
    assert len(result['step1']) == 1
    assert result['step1'][0]['status'] == 'active'
    assert 'A项目已废弃' in result['step1'][0]['text']
    # Dedup: same revision already retained -> no new copy (prefix stays stable).
    assert result['step2Count'] == 0
    # Update: new revision -> one update entry.
    assert len(result['step3']) == 1
    assert result['step3'][0]['status'] == 'update'
    assert '方案 B' in result['step3'][0]['text']
    # Retire: disabled -> one retired entry.
    assert len(result['step4']) == 1
    assert result['step4'][0]['status'] == 'retired'


def test_text_guidance_revision_covers_selector_and_action() -> None:
    result = run_bun('''
      import { planTextGuidance, HARNESS_GUIDANCE_CUSTOM_TYPE, hashRuleRevision } from './packages/continual-learning/extensions/harness-guidance-planner.ts';
      import { mergeLayers } from './packages/continual-learning/extensions/guardrail-engine.ts';

      const cfgA = mergeLayers([{ source:'project', rules:[ { id:'r', text:'A项目', instructions:'dep' } ]}]);
      const cfgB = mergeLayers([{ source:'project', rules:[ { id:'r', text:'B项目|A项目', instructions:'dep' } ]}]);
      const revA = hashRuleRevision(cfgA.rules[0]);
      const revB = hashRuleRevision(cfgB.rules[0]);

      // Deliver revA, then present revB (selector widened, same instructions):
      // the changed selector is a new revision -> update, not silent no-op.
      const delivered = { role:'custom', customType: HARNESS_GUIDANCE_CUSTOM_TYPE, display:false,
        content:'x', details:{ entries:[ { id:'r', revision: revA, status:'active' } ] } };
      const retained = [ {role:'user',content:'A项目'}, delivered ];
      const plan = planTextGuidance(retained, 'A项目', cfgB);

      console.log(JSON.stringify({ revDiffers: revA !== revB, entries: plan.entries }));
    ''')
    assert result['revDiffers'] is True
    assert len(result['entries']) == 1
    assert result['entries'][0]['status'] == 'update'


def test_retained_unscoped_guidance_gets_one_scoped_replacement() -> None:
    result = run_bun('''
      import { createHash } from 'node:crypto';
      import { planTextGuidance, HARNESS_GUIDANCE_CUSTOM_TYPE } from './packages/continual-learning/extensions/harness-guidance-planner.ts';
      import { mergeLayers } from './packages/continual-learning/extensions/guardrail-engine.ts';
      const config = mergeLayers([{ source:'project', rules:[{ id:'alpha', text:'Project A', instructions:'Use the confirmed replacement plan.' }] }]);
      const previousRevision = createHash('sha256').update(JSON.stringify({ id:'alpha', k:'text', text:'Project A', instructions:'Use the confirmed replacement plan.' })).digest('hex').slice(0,16);
      const old = { role:'custom', customType:HARNESS_GUIDANCE_CUSTOM_TYPE, content:'[harness:alpha] Use the confirmed replacement plan.', details:{ entries:[{id:'alpha',revision:previousRevision,status:'active'}] } };
      const retained = [{role:'user',content:'Project A'}, old];
      const updated = planTextGuidance(retained, 'Now discuss Project B', config);
      const scoped = { role:'custom', customType:HARNESS_GUIDANCE_CUSTOM_TYPE, content:updated.entries.map(e=>e.text).join(' '), details:{entries:updated.entries} };
      const again = planTextGuidance([...retained,scoped], 'Continue Project B', config);
      console.log(JSON.stringify({updated,again,old}));
    ''')
    assert len(result['updated']['entries']) == 1
    assert result['updated']['entries'][0]['status'] == 'update'
    assert 'Only for subjects matching "Project A"' in result['updated']['entries'][0]['text']
    assert result['again']['entries'] == []
    assert result['old']['content'] == '[harness:alpha] Use the confirmed replacement plan.'


def test_old_unscoped_delivery_retires_when_compaction_removed_its_trigger() -> None:
    result = run_bun('''
      import { createHash } from 'node:crypto';
      import { planTextGuidance, HARNESS_GUIDANCE_CUSTOM_TYPE } from './packages/continual-learning/extensions/harness-guidance-planner.ts';
      import { mergeLayers } from './packages/continual-learning/extensions/guardrail-engine.ts';
      const config = mergeLayers([{ source:'project', rules:[{ id:'alpha', text:'Project A', instructions:'Use the confirmed replacement plan.' }] }]);
      const revision = createHash('sha256').update(JSON.stringify({ id:'alpha', k:'text', text:'Project A', instructions:'Use the confirmed replacement plan.' })).digest('hex').slice(0,16);
      const old = { role:'custom', customType:HARNESS_GUIDANCE_CUSTOM_TYPE, content:'[harness:alpha] Use the confirmed replacement plan.', details:{entries:[{id:'alpha',revision,status:'active'}]} };
      const retired = planTextGuidance([old], 'Project B task', config);
      const notice = {role:'custom',customType:HARNESS_GUIDANCE_CUSTOM_TYPE,content:retired.entries.map(e=>e.text).join(' '),details:{entries:retired.entries}};
      const again = planTextGuidance([old,notice], 'Continue Project B', config);
      const active = planTextGuidance([old,notice], 'Return to Project A', config);
      console.log(JSON.stringify({retired,again,active}));
    ''')
    assert len(result['retired']['entries']) == 1
    assert result['retired']['entries'][0]['status'] == 'retired'
    assert 'Use the confirmed replacement plan.' not in result['retired']['entries'][0]['text']
    assert result['again']['entries'] == []
    assert len(result['active']['entries']) == 1
    assert result['active']['entries'][0]['status'] == 'active'
    assert 'Only for subjects matching "Project A"' in result['active']['entries'][0]['text']


def test_bash_incomplete_scoping_is_structural_not_prose() -> None:
    result = run_bun('''
      import { evaluateBash, mergeLayers } from './packages/continual-learning/extensions/guardrail-engine.ts';

      // Invalid skill rule (message on a skill rule): clearly skill-scoped.
      const skillBad = mergeLayers([{ source:'project', rules:[
        { id:'s', skill:'demo', instructions:'x', message:'nope' },
      ]}], new Set(['demo']));
      // Invalid text rule (action on a text rule): clearly text-scoped.
      const textBad = mergeLayers([{ source:'project', rules:[
        { id:'t', text:'A', instructions:'x', action:'block' },
      ]}]);
      // Invalid bash rule (bad regex): bash-scoped.
      const bashBad = mergeLayers([{ source:'project', rules:[
        { id:'b', bash:'[unclosed', message:'x' },
      ]}]);

      console.log(JSON.stringify({
        skillComplete: skillBad.bashEvaluationComplete,
        skillLs: evaluateBash(skillBad, 'ls').decision,
        textComplete: textBad.bashEvaluationComplete,
        textLs: evaluateBash(textBad, 'ls').decision,
        bashComplete: bashBad.bashEvaluationComplete,
        bashLs: evaluateBash(bashBad, 'ls').decision,
        bashIds: evaluateBash(bashBad, 'ls').incompleteRuleIds,
      }));
    ''')
    # A clearly skill- or text-scoped invalid rule does NOT hold bash.
    assert result['skillComplete'] is True
    assert result['skillLs'] == 'execute'
    assert result['textComplete'] is True
    assert result['textLs'] == 'execute'
    # A bash-scoped invalid rule makes bash evaluation incomplete (fail closed).
    assert result['bashComplete'] is False
    assert result['bashLs'] == 'incomplete'
    assert result['bashIds'] == ['b']


def test_stale_config_does_not_force_false_retirement() -> None:
    result = run_bun('''
      import { planTextGuidance, HARNESS_GUIDANCE_CUSTOM_TYPE } from './packages/continual-learning/extensions/harness-guidance-planner.ts';
      import { mergeLayers } from './packages/continual-learning/extensions/guardrail-engine.ts';

      // A layer that fell back to a stale snapshot: proj-a is absent from the
      // resolved rules, but configReadIncomplete marks the absence indeterminate.
      const stale = mergeLayers([{ source:'project', stale:true, rules:[] }]);
      const delivered = { role:'custom', customType: HARNESS_GUIDANCE_CUSTOM_TYPE, display:false,
        content:'x', details:{ entries:[ { id:'proj-a', revision:'r1', status:'active' } ] } };
      const retained = [ {role:'user',content:'A项目'}, delivered ];
      const plan = planTextGuidance(retained, 'A项目', stale);

      console.log(JSON.stringify({ incomplete: stale.configReadIncomplete, entries: plan.entries }));
    ''')
    assert result['incomplete'] is True
    # No definitive retirement is emitted while the config read is incomplete.
    assert result['entries'] == []


def test_duplicate_id_is_structural_not_positional() -> None:
    result = run_bun('''
      import { mergeLayers } from './packages/continual-learning/extensions/guardrail-engine.ts';
      const config = mergeLayers([{ source:'project', rules:[
        { id:'dup', text:'A', instructions:'first' },
        { id:'dup', text:'B', instructions:'second' },
      ]}]);
      console.log(JSON.stringify({
        ruleIds: config.rules.map(r=>r.id),
        complete: config.bashEvaluationComplete,
        incomplete: config.configReadIncomplete,
        hasDupError: config.errors.some(e=>e.includes('duplicate')),
      }));
    ''')
    # No positional winner: the ambiguous layer cannot establish coverage.
    assert result['ruleIds'] == []
    assert result['complete'] is False and result['incomplete'] is True
    assert result['hasDupError'] is True


def test_text_guidance_no_self_trigger_and_extracts_all_visible_sources() -> None:
    result = run_bun('''
      import { extractModelVisibleTexts } from './packages/continual-learning/extensions/harness-guidance-planner.ts';

      const messages = [
        { role: 'user', content: 'User text' },
        { role: 'assistant', content: [
          { type: 'text', text: 'Assistant text' },
          { type: 'toolCall', id: 'c1', name: 'read', arguments: { path: 'proj-a/readme.md' } },
        ]},
        { role: 'toolResult', toolCallId: 'c1', toolName: 'read', content: [
          { type: 'text', text: 'Tool result content with keyword' },
        ], isError: false },
        { role: 'compactionSummary', summary: 'Summary mentioning A项目' },
        // Harness-owned message must be ignored
        { role: 'custom', customType: 'harness-text-guidance', content: 'Secret keyword A项目 inside guidance', details: { id: 'test' } },
      ];

      const texts = extractModelVisibleTexts(messages);
      console.log(JSON.stringify({
        texts,
        hasUser: texts.includes('User text'),
        hasAssistant: texts.includes('Assistant text'),
        hasArg: texts.some(t => t.includes('proj-a/readme.md')),
        hasToolResult: texts.some(t => t.includes('Tool result content with keyword')),
        hasSummary: texts.some(t => t.includes('Summary mentioning A项目')),
        hasGuidance: texts.some(t => t.includes('Secret keyword')),
      }));
    ''')
    assert result['hasUser'] is True
    assert result['hasAssistant'] is True
    assert result['hasArg'] is True
    assert result['hasToolResult'] is True
    assert result['hasSummary'] is True
    assert result['hasGuidance'] is False


def test_bash_hook_integration() -> None:
    result = run_bun('''
      import path from 'node:path';
      import fs from 'node:fs';
      import os from 'node:os';
      import registerGuardrails from './packages/continual-learning/extensions/guardrails.ts';

      const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'harness-bash-test-'));
      const piDir = path.join(tmpDir, '.pi');
      fs.mkdirSync(piDir, { recursive: true });

      // Write harness.json with bash rules
      fs.writeFileSync(path.join(piDir, 'harness.json'), JSON.stringify({
        rules: [
          { id: 'push-notice', bash: 'git push', message: 'Report push status.' },
          { id: 'block-force', bash: '--force', action: 'block', message: 'Force push is forbidden.' },
          { id: 'confirm-deploy', bash: 'deploy', action: 'confirm', message: 'Confirm deploy.' },
        ],
      }));

      const hooks = {};
      const entries = [];
      const fakePi = {
        on: (event, handler) => { hooks[event] = handler; },
        registerEntryRenderer: () => {},
        registerCommand: () => {},
        appendEntry: (type, data) => { entries.push({ type, data }); },
      };

      registerGuardrails(fakePi);

      const ctxHeadless = { cwd: tmpDir, hasUI: false };

      // 1. Pass with message (omitted action)
      const call1 = await hooks['tool_call']({
        toolName: 'bash',
        toolCallId: 'call_1',
        input: { command: 'git push origin main' },
      }, ctxHeadless);

      const res1 = await hooks['tool_result']({
        toolName: 'bash',
        toolCallId: 'call_1',
        input: { command: 'git push origin main' },
        content: [{ type: 'text', text: 'Everything up-to-date' }],
        details: {},
        isError: false,
      }, ctxHeadless);

      // 2. Block action
      const call2 = await hooks['tool_call']({
        toolName: 'bash',
        toolCallId: 'call_2',
        input: { command: 'git push origin main --force' },
      }, ctxHeadless);

      // 3. Confirm action in headless mode -> fails closed
      const call3 = await hooks['tool_call']({
        toolName: 'bash',
        toolCallId: 'call_3',
        input: { command: 'npm run deploy' },
      }, ctxHeadless);

      fs.rmSync(tmpDir, { recursive: true, force: true });

      console.log(JSON.stringify({
        call1Blocked: call1?.block ?? false,
        res1Blocks: res1?.content ?? [],
        call2Blocked: call2?.block ?? false,
        call2Reason: call2?.reason ?? '',
        call3Blocked: call3?.block ?? false,
        call3Reason: call3?.reason ?? '',
      }));
    ''')
    assert result['call1Blocked'] is False
    blocks = result['res1Blocks']
    # Native output block is intact (not rewritten); Harness adds a separate,
    # identifiable block carrying the rule id.
    assert blocks[0]['text'] == 'Everything up-to-date'
    assert len(blocks) == 2
    note = blocks[1]['text']
    assert note.startswith('[harness-bash-note]')
    assert '[harness:push-notice]' in note
    assert 'Report push status.' in note
    assert result['call2Blocked'] is True
    assert 'Force push is forbidden.' in result['call2Reason']
    assert result['call3Blocked'] is True
    assert 'no UI available to confirm' in result['call3Reason']


def test_harness_guidance_hook_integration() -> None:
    result = run_bun('''
      import path from 'node:path';
      import fs from 'node:fs';
      import os from 'node:os';
      import registerHarnessGuidance from './packages/continual-learning/extensions/harness-guidance.ts';

      const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'harness-ctx-test-'));
      const piDir = path.join(tmpDir, '.pi');
      fs.mkdirSync(piDir, { recursive: true });

      fs.writeFileSync(path.join(piDir, 'harness.json'), JSON.stringify({
        rules: [
          { id: 'skill-rule', skill: 'open-deskos-widget', instructions: 'Overlay relationship.' },
          { id: 'text-rule', text: 'A项目|Project A', instructions: 'Project A is deprecated.' },
        ],
      }));

      const hooks = {};
      const entries = [];
      const fakePi = {
        on: (event, handler) => { hooks[event] = handler; },
        registerEntryRenderer: () => {},
        appendEntry: (type, data) => { entries.push({ type, data }); },
      };
      registerHarnessGuidance(fakePi);

      // before_agent_start fires once per user prompt; sessionManager exposes the
      // retained branch. Empty retained -> first-turn delivery from the prompt.
      const ctx = { cwd: tmpDir, sessionManager: { buildContextEntries: () => [] } };

      // Text rule triggers from the user prompt.
      const textRes = await hooks['before_agent_start']({
        type: 'before_agent_start',
        prompt: '关于 Project A 有什么要求？',
        systemPrompt: '',
        systemPromptOptions: { skills: [] },
      }, ctx);

      // Skill rule triggers from an expanded skill invocation.
      const NL = String.fromCharCode(10);
      const expanded = ['<skill name="open-deskos-widget" location="/tmp/w/SKILL.md">', 'body', '</skill>', '', 'build a fullscreen popup'].join(NL);
      const skillRes = await hooks['before_agent_start']({
        type: 'before_agent_start',
        prompt: expanded,
        systemPrompt: '',
        systemPromptOptions: { skills: [{ name: 'open-deskos-widget' }] },
      }, ctx);

      fs.rmSync(tmpDir, { recursive: true, force: true });

      console.log(JSON.stringify({
        textCustomType: textRes?.message?.customType,
        textContent: textRes?.message?.content,
        textEntries: textRes?.message?.details?.entries,
        skillContent: skillRes?.message?.content,
        skillRuleIds: skillRes?.message?.details?.skillRuleIds,
      }));
    ''')
    # Text guidance is delivered as ONE persistent message (durable, retained).
    assert result['textCustomType'] == 'harness-guidance'
    assert 'Project A is deprecated.' in result['textContent']
    assert result['textEntries'][0]['id'] == 'text-rule'
    assert result['textEntries'][0]['status'] == 'active'
    assert 'A项目|Project A' in result['textContent']
    assert 'Only for subjects matching' in result['textContent']
    # Skill guidance carries its task scope in model-visible text, not only details.
    assert 'Only for this /skill:open-deskos-widget task' in result['skillContent']
    assert 'Overlay relationship.' in result['skillContent']
    assert result['skillRuleIds'] == ['skill-rule']


