from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def run(source: str) -> dict:
    result = subprocess.run(['bun', '-e', source], cwd=REPO, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_changed_skill_entries_require_real_names_and_exact_object_schema() -> None:
    result = run('''
      import { validateHarnessWrite } from './packages/continual-learning/extensions/guardrails.ts';
      const known = new Set(['open-deskos-widget']);
      const check = (skillPrompts, previous) => validateHarnessWrite({content:JSON.stringify({policies:[],disabled:[],skillPrompts})}, known, previous);
      const stale = {unknown: 'old inert entry'};
      console.log(JSON.stringify({
        unknown: check({invented: {prompt:'do work',target:'system'}}),
        bare: check({'open-deskos-widget':'text'}),
        extra: check({'open-deskos-widget':{prompt:'test on device',target:'system',unexpected:true}}),
        blankPattern: check({'open-deskos-widget':{prompt:'test on device',target:'system',userMessagePattern:''}}),
        badPattern: check({'open-deskos-widget':{prompt:'test on device',target:'system',userMessagePattern:'(['}}),
        good: check({'open-deskos-widget':{prompt:'test on device',target:'system',userMessagePattern:'^live$'}}),
        preserved: check(stale,{policies:[],disabled:[],skillPrompts:stale}),
        reordered: check({unknown:{target:'system',prompt:'old'}},{policies:[],disabled:[],skillPrompts:{unknown:{prompt:'old',target:'system'}}}),
        removed: check({}, {policies:[],disabled:[],skillPrompts:stale})
      }));
    ''')
    assert result['unknown']
    assert result['bare']
    assert result['extra']
    assert result['blankPattern']
    assert result['badPattern']
    assert result['good'] == []
    assert result['preserved'] == []
    assert result['reordered'] == []
    assert result['removed'] == []


def test_complete_write_validates_root_fields_policies_disabled_and_user_owned_entries() -> None:
    result = run('''
      import { validateHarnessWrite } from './packages/continual-learning/extensions/guardrails.ts';
      const known = new Set(['known']);
      const previous = {
        policies:[{name:'keep',pattern:'keep',action:'block',reason:'keep'}],
        disabled:['old-disabled'],
        skillPrompts:{known:{prompt:'keep',target:'system'}},
        custom:{owner:'user'}
      };
      const check = (config) => validateHarnessWrite({content:JSON.stringify(config)}, known, previous);
      console.log(JSON.stringify({
        missingPolicies: check({disabled:previous.disabled,skillPrompts:previous.skillPrompts,custom:previous.custom}),
        malformedPolicies: check({policies:{},disabled:previous.disabled,skillPrompts:previous.skillPrompts,custom:previous.custom}),
        invalidPolicy: check({policies:[{name:'broken',scope:{tool:'bash'},rule:'x'}],disabled:previous.disabled,skillPrompts:previous.skillPrompts,custom:previous.custom}),
        malformedDisabled: check({policies:previous.policies,disabled:'old-disabled',skillPrompts:previous.skillPrompts,custom:previous.custom}),
        invalidDisabledEntry: check({policies:previous.policies,disabled:[''],skillPrompts:previous.skillPrompts,custom:previous.custom}),
        missingSkillPrompts: check({policies:previous.policies,disabled:previous.disabled,custom:previous.custom}),
        removedCustom: check({policies:previous.policies,disabled:previous.disabled,skillPrompts:previous.skillPrompts}),
        changedCustom: check({policies:previous.policies,disabled:previous.disabled,skillPrompts:previous.skillPrompts,custom:{owner:'agent'}}),
        addedRoot: check({...previous,newAgentField:true}),
        reorderedCustom: check({...previous,custom:{owner:'user',nested:{b:2,a:1}}}),
        reorderedCustomPrevious: validateHarnessWrite({content:JSON.stringify({...previous,custom:{nested:{a:1,b:2},owner:'user'}})}, known, {...previous,custom:{owner:'user',nested:{b:2,a:1}}}),
        valid: check(previous)
      }));
    ''')
    assert result['missingPolicies']
    assert result['malformedPolicies']
    assert result['invalidPolicy']
    assert result['malformedDisabled']
    assert result['invalidDisabledEntry']
    assert result['missingSkillPrompts']
    assert result['removedCustom']
    assert result['changedCustom']
    assert result['addedRoot']
    assert result['reorderedCustom']
    assert result['reorderedCustomPrevious'] == []
    assert result['valid'] == []


def test_automatic_apply_without_registry_cannot_add_invented_skill(tmp_path: Path) -> None:
    result = run(f'''
      import {{ applyHarnessOps }} from './packages/continual-learning/extensions/harness-consolidation.ts';
      console.log(JSON.stringify(await applyHarnessOps({json.dumps(str(tmp_path / 'harness.local.json'))},
        [{{op:'addSkillPrompt',name:'invented',prompt:'never test locally',target:'system'}}])));
    ''')
    assert result['ok'] is False
    assert not (tmp_path / 'harness.local.json').exists()
