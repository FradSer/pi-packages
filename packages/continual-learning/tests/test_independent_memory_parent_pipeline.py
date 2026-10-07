from pathlib import Path
from typing import Any
from support import run_bun_script

FIXTURE = Path(__file__).with_name('learning-policy-harness.ts')


def run_case(reason: str) -> dict[str, Any]:
    return run_bun_script(FIXTURE, 'remember-subset', env={'CL_JEV_FIXTURE': reason})


def test_parent_applies_supported_original_subset_and_preserves_all_original_intent() -> None:
    value = run_case('subset-independent')
    assert value['relationValidations'] == 1
    assert {'tools.md', 'license.md'} <= set(value['privateFiles'])
    assert {'tools.md', 'license.md'} <= set(value['publicFiles'])
    assert 'cache.md' not in value['privateFiles'] and 'cache.md' not in value['publicFiles']
    assert value['registryReceipt']['operations'] == 2
    assert any(a['outcome'] == 'applied' and a.get('pendingOperations') == 1 for a in value['registryReceipt']['attempts'])
    preserved = [r['proposal'] for r in value['history'] if r['status'] == 'proposed' and r.get('proposal', {}).get('kind') == 'independent-memory-review']
    assert len(preserved) == 1
    assert [m['name'] for m in preserved[0]['originalPlan']['newMemories']] == ['tools.md', 'cache.md', 'license.md']
    assert preserved[0]['eligibleIndexes'] == [0, 2] and preserved[0]['heldIndexes'] == [1]
    assert value['requestCaptured'] and value['agentsUnchanged'] and not value['harnessExists'] and not value['lock']


def test_uncertain_unavailable_and_default_gate_keep_original_proposal_without_subset_writes() -> None:
    for reason in ['subset-uncertain', 'subset-unavailable', 'subset-disabled']:
        value = run_case(reason)
        assert value['registryReceipt']['operations'] == 0
        assert 'tools.md' not in value['privateFiles'] and 'license.md' not in value['privateFiles']
        assert any(r['status'] == 'proposed' for r in value['history'])
        assert value['relationValidations'] == (0 if reason == 'subset-disabled' else 1)
        assert value['requestCaptured'] and not value['harnessExists']


def test_preservation_failure_and_evidence_tamper_prevent_all_subset_writes() -> None:
    for reason in ['subset-preservation-fails', 'subset-tamper-queue']:
        value = run_case(reason)
        assert value['registryReceipt']['operations'] == 0
        assert 'tools.md' not in value['privateFiles'] and 'license.md' not in value['publicFiles']
        assert any(a['outcome'] == 'failed' for a in value['registryReceipt']['attempts'])
        assert value['summarySubject'] == 'finished with issues'
        assert not value['lock']


def test_final_validator_failure_rolls_back_written_subset_and_preserves_original_proposal() -> None:
    value = run_case('subset-final-validator-fails')
    assert value['finalVerificationObservedWrites'] is True
    assert value['memoryFilesRestored'] is True
    assert value['registryReceipt']['operations'] == 0
    assert not ({'tools.md', 'license.md', 'cache.md'} & set(value['privateFiles']))
    assert not ({'tools.md', 'license.md', 'cache.md'} & set(value['publicFiles']))
    assert value['newAppliedHistoryRecords'] == 0
    assert any(r.get('proposal', {}).get('kind') == 'independent-memory-review' for r in value['history'])
    assert value['summarySubject'] == 'finished with issues' and not value['lock']


def test_composed_parent_recovers_only_supported_records_and_preserves_full_proposal() -> None:
    value = run_case('subset-composed')
    assert value['registryReceipt']['operations'] == 2
    assert {'tools.md', 'license.md'} <= set(value['privateFiles'])
    assert 'cache.md' not in value['privateFiles']
    preserved = [r['proposal'] for r in value['history'] if r.get('proposal', {}).get('kind') == 'independent-memory-review']
    assert len(preserved) == 1
    assert preserved[0]['eligibleIndexes'] == [0, 2] and preserved[0]['heldIndexes'] == [1]
    assert len(preserved[0]['originalPlan']['newMemories']) == 3
    assert any(a.get('jev', {}).get('strategy') == 'standalone-memory' and a['outcome'] == 'noop' for a in value['registryReceipt']['attempts'])
    assert any(a['outcome'] == 'applied' and a.get('pendingOperations') == 1 for a in value['registryReceipt']['attempts'])
    assert value['agentsUnchanged'] and not value['harnessExists'] and not value['lock']


def test_composed_proof_without_parent_gate_cannot_change_original_selection() -> None:
    value = run_case('subset-composed-default')
    assert value['registryReceipt']['operations'] == 0
    assert not ({'tools.md', 'license.md', 'cache.md'} & set(value['privateFiles']))
    assert not value['harnessExists'] and value['agentsUnchanged']
