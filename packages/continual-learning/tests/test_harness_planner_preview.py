"""Harness case evaluation is parent-owned; the child tool is retired."""
from __future__ import annotations

import json
from pathlib import Path

from support import PKG_DIR, run_bun

FIXTURE = Path(__file__).parent / 'fixtures/real-harness-case-rejections.json'


def test_real_rejected_cases_are_executable_inside_read_only_parent() -> None:
    frozen = json.loads(FIXTURE.read_text())
    result = run_bun(f'''
      import {{previewHarnessRuleCases}} from './packages/continual-learning/extensions/harness-consolidation.ts';
      console.log(JSON.stringify({json.dumps(frozen)}.map(x=>previewHarnessRuleCases(x.rule,x.cases))));
    ''')
    for actual, original in zip(result, frozen):
        assert actual['passed'] is False
        assert actual['errors'] == original['parentErrors']


def test_case_preview_is_parent_only_and_child_tool_is_retired() -> None:
    # The parent evaluator survives; the worker registration and both generated
    # planner tool-extension helpers are gone. No child can call a case tool.
    src = (PKG_DIR / "extensions" / "harness-consolidation.ts").read_text(encoding="utf-8")
    assert "export function previewHarnessRuleCases" in src
    assert "TOOL_NAMES.harnessCheckCases" not in src
    assert not (PKG_DIR / "extensions" / "harness-planner-preview.ts").exists()
    planner_read = (PKG_DIR / "extensions" / "planner-read-scope.ts").read_text(encoding="utf-8")
    assert "plannerReadArgs" not in planner_read
    # Parent evaluator still rejects a negative case that matches its own rule.
    result = run_bun(r'''
      import {previewHarnessRuleCases} from './packages/continual-learning/extensions/harness-consolidation.ts';
      const rule={id:'r',bash:'^npm(?:[ \t]|$)',action:'block',message:'use pnpm'};
      const cases={positive:[{bash:'npm test',expected:'block'}],negative:[{bash:'npm test'}]};
      console.log(JSON.stringify(previewHarnessRuleCases(rule,cases)));
    ''')
    assert result['passed'] is False
    assert any('unmatched' in error for error in result['errors'])
