"""Runtime readonly means state preservation, not one exception convention."""
from __future__ import annotations

import subprocess


def test_readonly_oracle_accepts_ignored_writes_and_rejects_mutation() -> None:
    from real_project_tasks import P_LIMIT_ORACLE, P_LIMIT_READONLY_PROBE

    script = "import assert from 'node:assert/strict';\n" + P_LIMIT_READONLY_PROBE + r'''
for (const original of [false, true]) {
  assertReadonlyPause({get isPaused() {return original;}});
  assertReadonlyPause({get isPaused() {return original;}, set isPaused(value) {}});
  let state=original;
  assert.throws(() => assertReadonlyPause({get isPaused() {return state;}, set isPaused(value) {state=value;}}), assert.AssertionError);
  assert.throws(() => assertReadonlyPause({get isPaused() {return original;}, set isPaused(value) {throw new Error('unrelated');}}), assert.AssertionError);
}
'''
    result = subprocess.run(['node', '--input-type=module', '-'], input=script,
                            text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert P_LIMIT_READONLY_PROBE in P_LIMIT_ORACLE
    assert 'assertReadonlyPause(l);' in P_LIMIT_ORACLE
    assert 'assertReadonlyPause(f);' in P_LIMIT_ORACLE
    assert 'l.pause(); assertReadonlyPause(l);' in P_LIMIT_ORACLE
    assert 'f.pause(); assertReadonlyPause(f);' in P_LIMIT_ORACLE
