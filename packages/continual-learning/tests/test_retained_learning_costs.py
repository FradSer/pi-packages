import json
import pytest
from continuous_failure_retention import retained_learning_costs


def usage(cost, tokens=5):
    return dict(input=2, output=3, cacheRead=0, cacheWrite=0, totalTokens=tokens, cost=cost)


def put(root, name, data):
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))


def test_retained_receipts_and_body_source_workers_are_counted_once(tmp_path):
    # Given interrupted recovery and a duplicate replay receipt, When costs
    # are recovered, Then count known calls once and keep missing cost unknown.
    u = usage(.25)
    receipt = dict(kind='learning-pipeline-receipt', batchId='batch', totals=u,
                   attempts=[dict(usageLedgerId='worker', usage=u)], costAvailable=True)
    put(tmp_path, 'memory/runs/scope/run/learning-pipeline-receipt.json', receipt)
    put(tmp_path, 'learning/scope/replay-fixture.json', {'attempts': [{'receipt': receipt}]})
    put(tmp_path, 'memory/runs/scope/run/memory-task-usage.json', dict(ledgerId='worker', knownUsage=u, complete=True))
    put(tmp_path, 'memory/runs/scope/unfinished/memory-body-usage-id.json', dict(ledgerId='body', knownUsage=usage(.1), complete=True))
    put(tmp_path, 'memory/runs/scope/audit/source-audit-usage.json', dict(ledgerId='source', knownUsage=usage(.05), complete=True))
    result = retained_learning_costs(tmp_path)
    assert result['knownLearningCost'] == pytest.approx(.4)
    assert result['knownLearningTokens'] == 15
    assert result['receiptBatches'] == ['batch']
    assert len(result['additionalWorkerLedgers']) == 2
    assert result['unknownCosts'] is True


def test_conflicting_usage_identity_is_not_accepted(tmp_path):
    for i, cost in enumerate((.1, .2)):
        put(tmp_path, f'memory/runs/scope/run{i}/memory-body-usage-id.json', dict(ledgerId='same', knownUsage=usage(cost), complete=True))
    with pytest.raises(ValueError, match='Conflicting'):
        retained_learning_costs(tmp_path)


def test_historical_source_audit_is_not_deduplicated_by_numeric_equality(tmp_path):
    receipt = dict(kind='learning-pipeline-receipt', batchId='batch', totals=usage(.1),
                   attempts=[dict(usage=usage(.1))])
    put(tmp_path, 'memory/runs/scope/run/learning-pipeline-receipt.json', receipt)
    put(tmp_path, 'memory/runs/scope/audit/source-audit-usage.json', dict(knownUsage=usage(.1), complete=True))
    result = retained_learning_costs(tmp_path)
    assert result['knownLearningCost'] == .1
    assert result['unresolvedLegacySourceAudits'] == ['memory/runs/scope/audit/source-audit-usage.json']


def test_project_model_and_snapshot_objects_cannot_inject_receipts(tmp_path):
    fake = dict(kind='learning-pipeline-receipt', batchId='fake', totals=usage(99), attempts=[])
    for name in ('project/fake.json', 'sessions/fake.json', 'memory/runs/scope/run/snapshot.json',
                 'memory/runs/scope/run/plan.json'):
        put(tmp_path, name, fake)
    result = retained_learning_costs(tmp_path)
    assert result['knownLearningCost'] == 0 and result['receiptBatches'] == []


def test_duplicate_worker_identity_inside_one_receipt_is_rejected(tmp_path):
    for equal in (False, True):
        put(tmp_path, 'memory/runs/scope/run/learning-pipeline-receipt.json', dict(
            kind='learning-pipeline-receipt', batchId='batch', totals=usage(.3), attempts=[
                dict(usageLedgerId='same', usage=usage(.1)),
                dict(usageLedgerId='same', usage=usage(.1 if equal else .2))]))
        with pytest.raises(ValueError, match='duplicate'):
            retained_learning_costs(tmp_path)
