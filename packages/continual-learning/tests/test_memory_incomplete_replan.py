from pathlib import Path

from support import run_bun_script


def test_explicit_maintenance_independently_replans_one_incomplete_response() -> None:
    fixture = Path(__file__).with_name('learning-policy-harness.ts')
    recovered = run_bun_script(fixture, 'remember-existing-maintenance', env={'CL_MEMORY_PREFIX_FAILURE': 'first'})
    assert recovered['planners'] == ['memory', 'memory']
    assert recovered['maintenanceClaimChecks'] == 3
    assert recovered['selectors'] == 1
    assert all(row['completeInline'] and row['noTools'] for row in recovered['initialMemoryInputs'])
    assert len({row['inlineDossierSha256'] for row in recovered['initialMemoryInputs']}) == 1
    attempts = [row for row in recovered['registryReceipt']['attempts'] if row['phase'] == 'memory' and row.get('usage')]
    assert [(row['attempt'], row['outcome']) for row in attempts] == [(0, 'failed'), (1, 'applied')]
    assert sum(row['usage']['cost'] for row in attempts) == .02
    assert attempts[0]['diagnostic'] == 'Incomplete Memory planner response; independent maintenance replan requested.'
    assert recovered['registryReceipt']['operations'] == 1
    assert not recovered['lock']
    failed = run_bun_script(fixture, 'remember-existing-maintenance', env={'CL_MEMORY_PREFIX_FAILURE': 'always'})
    assert failed['planners'] == ['memory', 'memory']
    assert failed['registryReceipt']['operations'] == 0
    ordinary = run_bun_script(fixture, 'remember-shared', env={'CL_MEMORY_PREFIX_FAILURE': 'first'})
    assert ordinary['planners'] == ['memory']
    assert ordinary['registryReceipt']['operations'] == 0
