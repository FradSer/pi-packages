from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def run(source: str) -> dict:
    result = subprocess.run(['bun', '-e', source], cwd=REPO, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_changed_skill_entries_require_real_names_and_object_schema() -> None:
    result = run('''
      import { validateHarnessWrite } from './packages/continual-learning/extensions/guardrails.ts';
      const known = new Set(['open-deskos-widget']);
      const check = (skillPrompts, previous) => validateHarnessWrite({content:JSON.stringify({skillPrompts})}, known, previous);
      const stale = {unknown: 'old inert entry'};
      console.log(JSON.stringify({
        unknown: check({invented: {prompt:'do work',target:'system'}}),
        bare: check({'open-deskos-widget':'text'}),
        good: check({'open-deskos-widget':{prompt:'test on device',target:'system'}}),
        preserved: check(stale,{skillPrompts:stale}),
        removed: check({}, {skillPrompts:stale})
      }));
    ''')
    assert result['unknown']
    assert result['bare']
    assert result['good'] == []
    assert result['preserved'] == []
    assert result['removed'] == []


def test_automatic_apply_without_registry_cannot_add_invented_skill(tmp_path: Path) -> None:
    result = run(f'''
      import {{ applyHarnessOps }} from './packages/continual-learning/extensions/harness-consolidation.ts';
      console.log(JSON.stringify(await applyHarnessOps({json.dumps(str(tmp_path / 'harness.local.json'))},
        [{{op:'addSkillPrompt',name:'invented',prompt:'never test locally',target:'system'}}])));
    ''')
    assert result['ok'] is False
    assert not (tmp_path / 'harness.local.json').exists()
