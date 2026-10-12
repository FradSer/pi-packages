from pathlib import Path
import re
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


def test_partial_success_does_not_skip_the_bounded_correction() -> None:
    # Given one held claim alongside independently supported knowledge, When
    # correction removes its unsupported generalization, Then review the entire
    # corrected plan before any partial application can end the learning run.
    value = run_case('subset-repair-complete')
    assert value['semanticRepairs'] == 1
    assert value['registryReceipt']['operations'] == 3
    assert {'tools.md', 'cache.md', 'license.md'} <= set(value['privateFiles'])
    assert not any(a.get('pendingOperations') for a in value['registryReceipt']['attempts'])


def test_failed_correction_retains_original_subset_and_accounts_for_its_writes() -> None:
    value = run_case('subset-repair-invalid')
    assert value['semanticRepairs'] == 1
    assert value['registryReceipt']['operations'] == 2
    attempts = value['registryReceipt']['attempts']
    assert any(a['attempt'] == 0 and a['outcome'] == 'applied'
               and a['operations'] == 2 and a['pendingOperations'] == 1 for a in attempts)
    assert any(a['attempt'] == 1 and a['outcome'] == 'failed' and a['operations'] == 0 for a in attempts)
    assert 'cache.md' not in value['privateFiles']


def test_original_subset_cannot_borrow_the_corrected_plans_retention_gate() -> None:
    # Given original unchanged knowledge was held, When a still-held correction
    # touches it, Then its absence from the corrected retained set does not clear
    # the original plan's independent-application gate.
    value = run_case('subset-retention-fallback')
    assert value['semanticRepairs'] == 1
    assert value['registryReceipt']['operations'] == 0
    assert not ({'tools.md', 'license.md', 'cache.md'} & set(value['privateFiles']))
    assert any(r['status'] == 'proposed' for r in value['history'])


def test_structurally_repaired_subset_is_not_credited_to_rejected_initial_attempt() -> None:
    value = run_case('structural-subset-repair-invalid')
    assert value['registryReceipt']['operations'] == 2
    attempts = [a for a in value['registryReceipt']['attempts'] if a['phase'] == 'memory']
    assert any(a['attempt'] == 0 and a['operations'] == 0 and a['outcome'] == 'rejected' for a in attempts)
    assert any(a['attempt'] == 1 and a['operations'] == 2 and a['outcome'] == 'applied' for a in attempts)
    assert any(a['attempt'] == 2 and a['operations'] == 0 and a['outcome'] == 'failed' for a in attempts)


def test_unrepairable_name_collision_does_not_spend_a_correction_or_review_call() -> None:
    value = run_case('subset-name-collision')
    assert value['totalRepairs'] == 0
    assert value['jevValidations'] == []
    assert value['registryReceipt']['operations'] == 0
    assert 'cache.md' in value['privateFiles']
    assert not ({'tools.md', 'license.md'} & set(value['privateFiles']))
    assert any(r['status'] == 'proposed' for r in value['history'])


def test_cancelled_collision_does_not_append_a_proposal_from_the_old_run() -> None:
    value = run_case('subset-name-collision-cancel')
    assert value['totalRepairs'] == 0
    assert value.get('registryReceipt', {}).get('operations', 0) == 0
    assert not any(r['status'] == 'proposed' for r in value['history'])
    assert not value['lock']


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
        assert value['summarySubject'] in {'finished with issues: memory failed', 'finished with issues: memory rejected'}
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
    assert value['summarySubject'] == 'finished with issues: memory failed' and not value['lock']


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


def test_production_pipeline_keeps_verified_independent_knowledge_available_to_next_task() -> None:
    value = run_case('subset-production')
    assert value['registryReceipt']['operations'] == 2
    assert value['relationValidations'] == 1
    assert value['productionJudgeOptions']['independentMemoryApplication'] is True
    assert value['productionJudgeOptions']['composedMemoryApplication'] is True
    assert any(a.get('pendingOperations') == 1 for a in value['registryReceipt']['attempts'])
    delivered = [item for hook in value['nextMemory'] for item in hook.get('message', {}).get('details', {}).get('retrieved', [])]
    # The user-requested discovery contract exposes filenames, not bodies.
    # Independent admitted facts remain discoverable; the held fact stays absent.
    assert delivered == []
    indexed = {name for hook in value['nextMemory'] for name in
               re.findall(r'^- ([^\n]+?\.md)(?: — |$)', hook.get('message', {}).get('content', ''), re.MULTILINE)}
    assert indexed == {'tools.md', 'license.md'}
    assert all('cache.md' not in str(hook) for hook in value['nextMemory'])
    assert any(record.get('proposal', {}).get('heldIndexes') == [1] for record in value['history'])


def test_verified_repair_subset_is_applied_and_keeps_unresolved_work_pending() -> None:
    value = run_case('subset-production-after-repair')
    assert value['registryReceipt']['operations'] == 2
    assert value['relationValidations'] == 1
    assert value['semanticRepairs'] == 1
    assert {'tools.md', 'license.md'} <= set(value['privateFiles'])
    assert 'cache.md' not in value['privateFiles']
    assert any(a['attempt'] == 1 and a['outcome'] == 'applied' and a.get('pendingOperations') == 1
               for a in value['registryReceipt']['attempts'])
    assert any(r.get('proposal', {}).get('heldIndexes') == [1] for r in value['history'])


def test_cancellation_during_relationship_review_stops_after_bounded_repair_without_writes() -> None:
    value = run_case('subset-cancel-relations')
    assert value.get('registryReceipt', {}).get('operations', 0) == 0
    assert value['semanticRepairs'] == 1
    assert not ({'tools.md', 'license.md', 'cache.md'} & set(value['privateFiles']))
    assert not value['lock']


def test_whole_held_proposal_binds_diagnostics_to_its_exact_original_plan() -> None:
    # Given a held whole plan after bounded correction, When preserving it,
    # Then parent diagnostics bind that exact plan rather than a later repair.
    import hashlib
    import json
    value = run_case('subset-disabled')
    proposals = [r['proposal'] for r in value['history'] if r['status'] == 'proposed'
                 and r.get('proposal', {}).get('kind') == 'independent-memory-review']
    assert len(proposals) == 1
    proposal = proposals[0]
    expected = hashlib.sha256(json.dumps(proposal['originalPlan'], ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    assert proposal['reviewedPlanDigest'] == expected
    assert proposal['eligibleIndexes'] == []
    assert proposal['heldIndexes'] == list(range(len(proposal['originalPlan']['newMemories'])))
    assert isinstance(proposal['candidateFailures'], list)
    assert value['registryReceipt']['operations'] == 0
