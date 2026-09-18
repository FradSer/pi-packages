from __future__ import annotations

import json
from pathlib import Path

from test_guardrails_extension import run_bun


def test_skill_rules_use_real_names_and_exact_schema() -> None:
    result = run_bun('''
      import {validateHarnessWrite} from './packages/continual-learning/extensions/guardrails.ts';
      const check=rule=>validateHarnessWrite({content:JSON.stringify({rules:[rule]})},new Set(['known']));
      const good={id:'guide',skill:'known',instructions:'Guide only the known workflow.'};
      console.log(JSON.stringify({good:check(good),unknown:check({...good,skill:'invented'}),bare:check('text'),extra:check({...good,target:'system'}),narrowed:check({...good,userMessagePattern:'^live$'})}));
    ''')
    assert result['good'] == []
    assert all(result[key] for key in ['unknown','bare','extra','narrowed'])


def test_apply_without_registry_fails_closed_for_skill_guidance(tmp_path: Path) -> None:
    result = run_bun(f'''
      import {{applyHarnessOps}} from './packages/continual-learning/extensions/harness-consolidation.ts';
      console.log(JSON.stringify(await applyHarnessOps({json.dumps(str(tmp_path/'harness.json'))},[{{op:'addRule',rule:{{id:'invented',skill:'invented',instructions:'guide'}}}}])));
    ''')
    assert not result['ok'] and not (tmp_path/'harness.json').exists()
