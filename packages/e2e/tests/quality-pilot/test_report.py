from report import exact_p, phase_cost, phase_finished


def test_paired_exact_test_does_not_overclaim_small_sample():
    assert exact_p(0, 0) == 1
    assert exact_p(2, 0) == .5
    assert exact_p(4, 0) == .125


def test_handoff_cost_is_counted_once_and_completion_is_separate():
    phase = {'costEstimatedUsd': .1, 'jevEstimatedUsd': .01, 'reportCompleted': False,
             'handoff': {'costEstimatedUsd': .02, 'reportCompleted': True}}
    assert abs(phase_cost(phase) - .13) < 1e-12
    assert phase_finished(phase)
