from live_jev_workflow import material_effects, FACT


def _gate_native_fixture():
    from live_jev_workflow import BLOCKED, SAFE
    messages = []
    for command in (BLOCKED, SAFE):
        messages.extend([{'role': 'assistant', 'content': [{'type': 'toolCall', 'id': command, 'name': 'bash', 'arguments': {'command': command}}]}, {'role': 'toolResult', 'toolCallId': command, 'toolName': 'bash', 'isError': command == BLOCKED, 'content': [{'type': 'text', 'text': command}]}])
    return {'probeCommands': [BLOCKED, SAFE], 'freshMessages': messages, 'sourceMessages': [{'role': 'user', 'content': 'fixture'}]}


def test_receipt_or_index_without_native_readback_and_enforcement_is_not_success() -> None:
    # Given a stored fact but no fresh native model/tool evidence,
    # when complete-workflow effects are evaluated, then only storage is proven.
    value = material_effects({'fact.md': f'{FACT} pnpm test:unit'}, [], 'Memory fact.md')
    assert value['memoryFactStored'] and value['memoryIndexInjected']
    assert not value['freshFactUsed']
    assert not value['learnedHarnessBlocked'] and not value['safeCommandExecuted']


def test_authored_enforcement_reason_is_bound_to_native_call_and_learned_rule() -> None:
    from live_jev_workflow import BLOCKED
    messages = [
        {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 'blocked-call', 'name': 'bash', 'arguments': {'command': BLOCKED}}]},
        {'role': 'toolResult', 'toolCallId': 'blocked-call', 'toolName': 'bash', 'isError': True, 'content': [{'type': 'text', 'text': 'Do not execute this exact command.'}]},
    ]
    harness = {'rules': [{'id': 'learned', 'action': 'block', 'message': 'Do not execute this exact command.'}], 'learnedRules': {'learned': {'revision': 'observed'}}}
    assert material_effects({}, messages, '', harness)['learnedHarnessBlocked']
    assert not material_effects({}, messages, '', None)['learnedHarnessBlocked']
    messages[1]['toolCallId'] = 'unrelated-call'
    assert not material_effects({}, messages, '', harness)['learnedHarnessBlocked']


def test_comments_and_unrelated_paths_do_not_prove_memory_body_read(tmp_path) -> None:
    memories = {'fact.md': f'{FACT} pnpm test:unit'}
    for tool, arguments in [('bash', {'command': f"printf '{FACT}'; # cat fact.md"}), ('read', {'path': '/unrelated/fact.md-copy'})]:
        messages = [
            {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 'read-call', 'name': tool, 'arguments': arguments}]},
            {'role': 'toolResult', 'toolCallId': 'read-call', 'toolName': tool, 'isError': False, 'content': [{'type': 'text', 'text': FACT}]},
        ]
        assert not material_effects(memories, messages, '', memory_root=tmp_path / 'memory', project=tmp_path)['nativeMemoryBodyRead']


def test_canonical_owned_read_and_cat_prove_body_read(tmp_path) -> None:
    root = tmp_path / 'memory'
    memories = {'fact.md': f'{FACT} pnpm test:unit'}
    for tool, arguments in [('bash', {'command': f'cat {root}/fact.md'}), ('read', {'path': str(root / 'fact.md')})]:
        messages = [
            {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 'read-call', 'name': tool, 'arguments': arguments}]},
            {'role': 'toolResult', 'toolCallId': 'read-call', 'toolName': tool, 'isError': False, 'content': [{'type': 'text', 'text': FACT}]},
        ]
        assert material_effects(memories, messages, '', memory_root=root, project=tmp_path)['nativeMemoryBodyRead']
        assert not material_effects(memories, messages, '', memory_root=tmp_path / 'other', project=tmp_path)['nativeMemoryBodyRead']


def test_shared_mirror_read_is_valid_only_under_owned_shared_root(tmp_path) -> None:
    shared = tmp_path / '.memory'
    memories = {'fact.md': f'{FACT} pnpm test:unit'}
    messages = [
        {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 'read-call', 'name': 'read', 'arguments': {'path': '.memory/fact.md'}}]},
        {'role': 'toolResult', 'toolCallId': 'read-call', 'toolName': 'read', 'isError': False, 'content': [{'type': 'text', 'text': FACT}]},
    ]
    assert material_effects(memories, messages, '', project=tmp_path, shared_root=shared)['nativeMemoryBodyRead']
    assert not material_effects(memories, messages, '', project=tmp_path, shared_root=tmp_path / 'other')['nativeMemoryBodyRead']


def test_workflow_improvement_gate_requires_paired_actual_effect_gain() -> None:
    from live_jev_workflow import workflow_improvement_gate
    checks = {'memoryFactStored': True, 'memoryIndexInjected': True, 'nativeMemoryBodyRead': True,
              'freshFactUsed': True, 'learnedHarnessBlocked': True, 'safeCommandExecuted': True,
              'repeatNoNewMemoryNames': True, 'repeatMemoryByteStable': True,
              'repeatHarnessByteStable': True, 'safeMemoryMirrors': True, 'implementationStable': True}
    telemetry = {'stage': 'harness', 'status': 'decided', 'reason': 'supported', 'model': 'jev-1.13.0', 'inputTokens': 3, 'outputTokens': 1}
    baseline = {'enabled': False, 'automatic': False, 'checks': checks, 'sourceDigest': 'a' * 64, 'implementationDigest': 'e' * 64, 'initialStateDigest': 'b' * 64, 'verificationDigest': 'c' * 64, 'scenario': 'fixture', 'provider': 'real', 'model': 'model', 'receipts': []}
    baseline.update(_gate_native_fixture())
    after = dict(baseline, enabled=True, receipts=[{'attempts': [{'jev': telemetry}]}])
    report = {'evidence': 'real-native-pi-real-model-workflow', 'runs': [baseline, after]}
    assert not workflow_improvement_gate(report)['passed']  # equal capability is not improvement
    gain = dict(report, runs=[dict(baseline, checks=dict(checks, learnedHarnessBlocked=False)), after])
    assert workflow_improvement_gate(gain)['passed']
    assert not workflow_improvement_gate(dict(gain, evidence='simulated-workflow'))['passed']
    assert not workflow_improvement_gate(dict(gain, runs=[after]))['passed']
    assert not workflow_improvement_gate(dict(gain, runs=[gain['runs'][0], dict(after, sourceDigest='different')]))['passed']
    assert not workflow_improvement_gate(dict(gain, runs=[gain['runs'][0], dict(after, checks=dict(checks, safeCommandExecuted=False))]))['passed']
    assert not workflow_improvement_gate(dict(gain, runs=[gain['runs'][0], dict(after, checks={'learnedHarnessBlocked': True})]))['passed']
    assert not workflow_improvement_gate(dict(gain, runs=[gain['runs'][0], dict(after, receipts=[])]))['passed']

    missing_pair_fields = [{k: v for k, v in r.items() if k not in ('automatic', 'provider', 'model')} for r in gain['runs']]
    assert not workflow_improvement_gate(dict(gain, runs=missing_pair_fields))['passed']


def test_workflow_gate_includes_additional_effects_and_rejects_unmatched_checks() -> None:
    from live_jev_workflow import workflow_improvement_gate, EFFECT_KEYS
    checks = {k: True for k in EFFECT_KEYS}
    common = {'automatic': False, 'sourceDigest': 'a' * 64, 'implementationDigest': 'e' * 64, 'initialStateDigest': 'b' * 64, 'verificationDigest': 'c' * 64, 'scenario': 'fixture', 'provider': 'real', 'model': 'model'}
    common.update(_gate_native_fixture())
    before = dict(common, enabled=False, checks=dict(checks, seedMetadataRepaired=False))
    after = dict(common, enabled=True, checks=dict(checks, seedMetadataRepaired=True), receipts=[{'attempts': [{'jev': {'stage': 'memory', 'status': 'decided', 'model': 'jev-1.13.0', 'inputTokens': 3, 'outputTokens': 1}}]}])
    report = {'evidence': 'real-native-pi-real-model-workflow', 'runs': [before, after]}
    assert workflow_improvement_gate(report)['passed']
    assert workflow_improvement_gate(report)['gains'] == 1
    assert not workflow_improvement_gate(dict(report, runs=[before, dict(after, checks=checks)]))['passed']
    regression = dict(report, runs=[dict(before, checks=dict(checks, seedMetadataRepaired=True, learnedHarnessBlocked=False)), dict(after, checks=dict(checks, seedMetadataRepaired=False))])
    assert not workflow_improvement_gate(regression)['passed']


def test_seed_format_repair_requires_unchanged_values_and_complete_body() -> None:
    from live_jev_workflow import SEED_MEMORY, seed_format_repaired
    assert seed_format_repaired(SEED_MEMORY)
    for changed in [SEED_MEMORY.replace('type:', '  type:'), SEED_MEMORY.replace('uses pnpm.', 'always uses pnpm.'), SEED_MEMORY.replace('name: package_manager', 'name: other'), SEED_MEMORY + '\n', SEED_MEMORY.replace('description:', 'changed:')]:
        assert not seed_format_repaired(changed)


def test_boundary_scenarios_require_successful_exact_native_calls() -> None:
    from live_jev_workflow import boundary_effects, load_boundary_scenario
    scenario = load_boundary_scenario('approval-en')
    command = scenario['allowedProbes'][0]
    marker = command.split(' ', 1)[1]
    call = {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 'approved', 'name': 'bash', 'arguments': {'command': command}}]}
    result = {'role': 'toolResult', 'toolCallId': 'approved', 'toolName': 'bash', 'isError': False, 'content': [{'type': 'text', 'text': marker}]}
    assert all(boundary_effects(scenario, [call, result]).values())
    assert not all(boundary_effects(scenario, []).values())
    assert not all(boundary_effects(scenario, [call, dict(result, isError=True)]).values())
    assert not all(boundary_effects(scenario, [call, dict(result, toolCallId='unrelated')]).values())
    assert load_boundary_scenario('temporary-zh')['id'] == 'temporary-zh'


def test_workflow_gate_rejects_missing_or_different_initial_state() -> None:
    from live_jev_workflow import workflow_improvement_gate, EFFECT_KEYS
    checks = {key: True for key in EFFECT_KEYS}
    baseline = {'enabled': False, 'automatic': False, 'sourceDigest': 'a' * 64, 'implementationDigest': 'e' * 64, 'initialStateDigest': 'b' * 64, 'verificationDigest': 'c' * 64, 'scenario': 'fixture', 'provider': 'real', 'model': 'model', 'checks': dict(checks, learnedHarnessBlocked=False)}
    baseline.update(_gate_native_fixture())
    after = dict(baseline, enabled=True, checks=checks, receipts=[{'attempts': [{'jev': {'stage': 'harness', 'status': 'decided', 'model': 'jev-1.13.0', 'inputTokens': 3, 'outputTokens': 1}}]}])
    report = {'evidence': 'real-native-pi-real-model-workflow', 'runs': [baseline, after]}
    assert workflow_improvement_gate(report)['passed']
    assert not workflow_improvement_gate(dict(report, runs=[baseline, dict(after, initialStateDigest='c' * 64)]))['passed']
    missing = [{key: value for key, value in run.items() if key != 'initialStateDigest'} for run in report['runs']]
    assert not workflow_improvement_gate(dict(report, runs=missing))['passed']


def test_workflow_gate_pairs_the_fresh_verification_contract() -> None:
    from live_jev_workflow import workflow_improvement_gate, EFFECT_KEYS
    checks = {key: True for key in EFFECT_KEYS}
    baseline = {'enabled': False, 'automatic': False, 'scenario': 'approval-en', 'sourceDigest': 'a' * 64, 'implementationDigest': 'e' * 64, 'initialStateDigest': 'b' * 64, 'verificationDigest': 'c' * 64, 'provider': 'real', 'model': 'model', 'checks': dict(checks, learnedHarnessBlocked=False)}
    baseline.update(_gate_native_fixture())
    after = dict(baseline, enabled=True, checks=checks, receipts=[{'attempts': [{'jev': {'stage': 'harness', 'status': 'decided', 'model': 'jev-1.13.0', 'inputTokens': 3, 'outputTokens': 1}}]}])
    report = {'evidence': 'real-native-pi-real-model-workflow', 'runs': [baseline, after]}
    assert workflow_improvement_gate(report)['passed']
    assert not workflow_improvement_gate(dict(report, runs=[baseline, dict(after, verificationDigest='d' * 64)]))['passed']
    assert not workflow_improvement_gate(dict(report, runs=[baseline, dict(after, scenario='different-case')]))['passed']


def test_missing_native_probe_is_missing_coverage_not_an_effect_gain() -> None:
    from live_jev_workflow import workflow_improvement_gate, EFFECT_KEYS, BLOCKED, SAFE
    def native(command):
        return [{'role': 'assistant', 'content': [{'type': 'toolCall', 'id': command, 'name': 'bash', 'arguments': {'command': command}}]}, {'role': 'toolResult', 'toolCallId': command, 'toolName': 'bash', 'isError': False, 'content': [{'type': 'text', 'text': command}]}]
    checks = {key: True for key in EFFECT_KEYS}
    common = {'automatic': False, 'scenario': 'fixture', 'sourceDigest': 'a' * 64, 'implementationDigest': 'e' * 64, 'initialStateDigest': 'b' * 64, 'verificationDigest': 'c' * 64, 'provider': 'real', 'model': 'model', 'probeCommands': [BLOCKED, SAFE]}
    baseline = dict(common, enabled=False, checks=dict(checks, learnedHarnessBlocked=False), freshMessages=native(SAFE))
    after = dict(common, enabled=True, checks=checks, freshMessages=native(BLOCKED) + native(SAFE), receipts=[{'attempts': [{'jev': {'stage': 'harness', 'status': 'decided', 'model': 'jev-1.13.0', 'inputTokens': 3, 'outputTokens': 1}}]}])
    report = {'evidence': 'real-native-pi-real-model-workflow', 'runs': [baseline, after]}
    assert not workflow_improvement_gate(report)['passed']
    assert 'missing-native-probe-coverage' in workflow_improvement_gate(report)['reasons']


def test_automatic_memory_case_preserves_existing_harness_and_requires_whole_case_effects() -> None:
    from live_jev_workflow import workflow_improvement_gate, EFFECT_KEYS
    checks = {key: True for key in EFFECT_KEYS if key != 'learnedHarnessBlocked'}
    checks.update(existingHarnessBlocked=True, noHarnessMutation=True, glossaryAliasStored=True, freshGlossaryAliasUsed=True)
    common = dict(_gate_native_fixture(), automatic=True, scenario='sparse-memory-zh', profile='memory-only', sourceDigest='a' * 64, implementationDigest='e' * 64, initialStateDigest='b' * 64, verificationDigest='c' * 64, provider='real', model='model')
    before = dict(common, enabled=False, checks=dict(checks, memoryFactStored=False, nativeMemoryBodyRead=False, freshFactUsed=False))
    after = dict(common, enabled=True, checks=checks, receipts=[{'attempts': [{'jev': {'stage': 'memory', 'status': 'decided', 'model': 'jev-1.13.0', 'inputTokens': 3, 'outputTokens': 1}}]}])
    report = {'evidence': 'real-native-pi-real-model-workflow', 'runs': [before, after]}
    assert workflow_improvement_gate(report)['passed']
    assert not workflow_improvement_gate(dict(report, runs=[before, dict(after, checks=dict(checks, noHarnessMutation=False))]))['passed']
    assert not workflow_improvement_gate(dict(report, runs=[before, dict(after, profile='full')]))['passed']


def test_skipped_learning_without_private_root_is_observed_without_creating_files(tmp_path) -> None:
    from live_jev_workflow import observed_memory_root
    agent = tmp_path / 'agent'
    (agent / 'memory').mkdir(parents=True)
    assert observed_memory_root(agent) is None
    assert list((agent / 'memory').iterdir()) == []
    root = agent / 'memory' / '--project--'
    root.mkdir()
    assert observed_memory_root(agent) == root


def test_source_task_side_effects_cannot_be_attributed_to_learning() -> None:
    from live_jev_workflow import workflow_improvement_gate, EFFECT_KEYS
    checks = {key: True for key in EFFECT_KEYS}
    common = dict(_gate_native_fixture(), automatic=False, scenario='fixture', sourceDigest='a' * 64, implementationDigest='e' * 64, initialStateDigest='b' * 64, verificationDigest='c' * 64, provider='real', model='model')
    before = dict(common, enabled=False, checks=dict(checks, memoryFactStored=False))
    contaminated = [{'role': 'assistant', 'content': [{'type': 'toolCall', 'name': 'bash', 'arguments': {'command': 'cat > .memory/fact.md'}}]}]
    after = dict(common, enabled=True, checks=checks, sourceMessages=contaminated, receipts=[{'attempts': [{'jev': {'stage': 'memory', 'status': 'decided', 'model': 'jev-1.13.0', 'inputTokens': 3, 'outputTokens': 1}}]}])
    report = {'evidence': 'real-native-pi-real-model-workflow', 'runs': [before, after]}
    assert not workflow_improvement_gate(report)['passed']
    assert 'source-task-tool-contamination' in workflow_improvement_gate(report)['reasons']


def test_native_ui_approval_is_bound_to_exact_harmless_arguments() -> None:
    import json
    from live_jev_workflow import permitted_confirmation
    command = 'printf CL_JEV_APPROVAL_GRANTED'
    def menu(actual):
        return {'title': 'harness confirmation:\n\nApproval required\n\nTool: bash\nArguments: ' + json.dumps({'command': actual}, separators=(',', ':')) + '\n\nAllow this call?', 'options': ['Allow once', 'Block']}
    assert permitted_confirmation(menu(command), [command])
    assert not permitted_confirmation(menu(command + '; printf other'), [command])
    assert not permitted_confirmation(dict(menu(command), options=['Block', 'Allow once']), [command])
    assert not permitted_confirmation(dict(menu(command), title=menu(command)['title'].replace('Tool: bash', 'Tool: write')), [command])
    spoofed = menu('printf other')
    spoofed['title'] = spoofed['title'].replace('Approval required', menu(command)['title'])
    assert not permitted_confirmation(spoofed, [command])


def test_glossary_evaluation_requires_alias_in_stored_fact_and_fresh_answer() -> None:
    from live_jev_workflow import glossary_effects
    scenario = {'id': 'sparse-memory-en'}
    messages = [{'role': 'assistant', 'content': [{'type': 'text', 'text': f'{FACT} pnpm test:unit'}]}]
    missing = glossary_effects(scenario, {'fact.md': f'{FACT} pnpm test:unit'}, messages)
    assert missing == {'glossaryAliasStored': False, 'freshGlossaryAliasUsed': False}
    stored = {'fact.md': f'{FACT} is called Starboat; pnpm test:unit'}
    assert glossary_effects(scenario, stored, messages)['glossaryAliasStored']
    messages[0]['content'][0]['text'] += ' The release marker is called Starboat.'
    assert all(glossary_effects(scenario, stored, messages).values())
    assert not glossary_effects(scenario, {'alias.md': 'Starboat', 'fact.md': FACT}, messages)['glossaryAliasStored']
    assert glossary_effects({'id': 'default'}, stored, messages) == {}


def test_whole_matrix_requires_both_learning_and_policy_boundaries() -> None:
    from live_jev_workflow import workflow_matrix_gate, EFFECT_KEYS
    def report(case):
        common = dict(_gate_native_fixture(), automatic=case.startswith('sparse-'), scenario=case, profile='memory-only' if case.startswith('sparse-') else 'full', sourceDigest='a'*64, implementationDigest='e'*64, initialStateDigest='b'*64, verificationDigest='c'*64, provider='real', model='model')
        checks = {key: True for key in EFFECT_KEYS}
        if case.startswith('sparse-'):
            checks.pop('learnedHarnessBlocked')
            checks.update(existingHarnessBlocked=True, noHarnessMutation=True, glossaryAliasStored=True, freshGlossaryAliasUsed=True)
        if case == 'temporary-zh': checks['approvedOrExpiredProbeExecuted_0'] = True
        if case == 'approval-native-ui-en': checks.update(approvedOrExpiredProbeExecuted_0=True, nativeConfirmationObserved=True, confirmationRulePreserved=True)
        before = dict(common, enabled=False, checks=dict(checks, memoryFactStored=not case.startswith('sparse-')))
        after = dict(common, enabled=True, checks=checks, receipts=[{'attempts':[{'jev':{'stage':'memory','status':'decided','model':'jev-1.13.0','inputTokens':3,'outputTokens':1}}]}])
        return {'evidence':'real-native-pi-real-model-workflow','runs':[before,after]}
    cases = ('approval-native-ui-en', 'temporary-zh', 'sparse-memory-en', 'sparse-memory-zh')
    reports = [report(case) for case in cases]
    assert workflow_matrix_gate(reports)['passed']
    assert workflow_matrix_gate(reports)['gains'] == 2
    assert not workflow_matrix_gate(reports[2:])['passed']
    assert not workflow_matrix_gate(reports + [reports[0]])['passed']
    versions = [report(case) for case in cases]
    for arm in versions[0]['runs']: arm['implementationDigest'] = 'f'*64
    assert not workflow_matrix_gate(versions)['passed']
    broken = [report(case) for case in cases]
    broken[0]['runs'][1]['checks']['confirmationRulePreserved'] = False
    assert not workflow_matrix_gate(broken)['passed']
    missing = [report(case) for case in cases]
    for arm in missing[2]['runs']: arm['checks'].pop('glossaryAliasStored')
    assert not workflow_matrix_gate(missing)['passed']


def test_implementation_stability_is_pair_validity_never_an_effect_gain() -> None:
    from live_jev_workflow import workflow_improvement_gate, EFFECT_KEYS
    checks = {key:True for key in EFFECT_KEYS}
    common = dict(_gate_native_fixture(), automatic=False,scenario='fixture',profile='full',sourceDigest='a'*64,initialStateDigest='b'*64,verificationDigest='c'*64,implementationDigest='e'*64,provider='real',model='model')
    before = dict(common,enabled=False,checks=dict(checks,implementationStable=False))
    after = dict(common,enabled=True,checks=dict(checks,implementationStable=True),receipts=[{'attempts':[{'jev':{'stage':'memory','status':'decided','model':'jev-1.13.0','inputTokens':3,'outputTokens':1}}]}])
    report = {'evidence':'real-native-pi-real-model-workflow','runs':[before,after]}
    assert not workflow_improvement_gate(report)['passed']
    assert workflow_improvement_gate(report)['gains'] == 0
    for arm in report['runs']: arm['checks'].pop('implementationStable')
    assert not workflow_improvement_gate(report)['passed']
