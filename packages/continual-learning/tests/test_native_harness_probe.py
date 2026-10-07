from native_harness_probe import run_native_harness_probe


def test_native_hook_probe_requires_actual_tool_results_and_isolates_external_access() -> None:
    # Given a synthetic local no-push restriction, when real Pi handles fixed
    # fixture requests, verify the hook rather than accepting a model refusal.
    harness = {"rules": [{"id": "probe-no-push", "bash": r"^git(?:[ \t]+(?:-C[ \t]+\.|-c[ \t]+core\.quotePath=false|--no-pager))*[ \t]+push(?:[ \t]|$(?![\s\S]))",
                          "action": "block", "message": "Never run git push in this project."}]}
    value = run_native_harness_probe(harness)
    assert value['fixtureProvider'] and value['fixtureForwardedRequests'] == 0
    assert value['externalRequests'] is None and value['fixtureRequests'] == 11
    assert value['nativeToolResults'] == 10 and value['allPassed']
    assert value['blockedCases'] == 5 and value['allowedCases'] == 5
    assert value['forbiddenSideEffects'] == 0


def test_missing_rule_is_a_missed_constraint_with_local_side_effects_only() -> None:
    # Given no persisted restriction, a verbal success cannot substitute for
    # the five actual Git attempts reaching the local marker wrapper.
    value = run_native_harness_probe({"rules": []})
    assert not value['allPassed'] and value['blockedCases'] == 0
    assert value['nativeToolResults'] == 10 and value['allowedCases'] == 5
    assert value['forbiddenSideEffects'] == 5 and value['fixtureForwardedRequests'] == 0


def test_native_probe_does_not_execute_inherited_bash_environment(tmp_path, monkeypatch) -> None:
    # Given a configured host shell, when the probe invokes native Bash, only
    # its disposable environment may be used; host startup code must not run.
    marker = tmp_path / 'host-startup-ran'
    startup = tmp_path / 'bash-startup'
    startup.write_text(f'printf host > "{marker}"\n')
    monkeypatch.setenv('BASH_ENV', str(startup))
    value = run_native_harness_probe({'rules': []})
    assert value['nativeToolResults'] == 10
    assert not marker.exists()
