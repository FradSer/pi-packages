from pathlib import Path
from support import run_bun_script

FIXTURE = Path(__file__).with_name('harness-repair-harness.ts')


def test_semantic_repair_receives_parent_owned_exact_bindings() -> None:
    value = run_bun_script(FIXTURE, 'semantic-pruned-supported')
    assert value['repairHasImmutableBindings']
    assert value['repairLocksCitationFields']
    assert value['spawned'] == 2
    assert value['semanticCalls'] == 2


def test_protected_field_failures_remain_held_with_precise_categories() -> None:
    for scenario, category in [('semantic-pruned-foreign', 'identity-mismatch'), ('semantic-pruned-requoted', 'citation-mismatch')]:
        value = run_bun_script(FIXTURE, scenario)
        assert value['spawned'] == 2 and value['semanticCalls'] == 1
        assert value['semanticDecision'] == 'propose'
        assert value['targetExists'] is False
        assert category in value['attempts'][-1]['diagnostic']
