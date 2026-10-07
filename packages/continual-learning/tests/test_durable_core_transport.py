import pytest


def test_main_timeout_is_unknown_even_without_jev_requests() -> None:
    from durable_core_transport import transport_usage_unknown
    assert transport_usage_unknown(1, 0, 0, None)


@pytest.mark.parametrize('usage', [None, {}, {'input': 5}, {'input': 5, 'output': 2, 'cacheRead': 0, 'cacheWrite': 0, 'totalTokens': 0}])
def test_missing_or_partial_main_usage_is_unknown(usage) -> None:
    from durable_core_transport import transport_usage_unknown
    assert transport_usage_unknown(1, 0, 0, usage)


def test_complete_single_main_call_and_all_jev_responses_are_known() -> None:
    from durable_core_transport import transport_usage_unknown
    usage = {'input': 5, 'output': 2, 'cacheRead': 3, 'cacheWrite': 0, 'totalTokens': 10}
    assert not transport_usage_unknown(3, 2, 2, usage)
    assert transport_usage_unknown(3, 2, 1, usage)
    assert transport_usage_unknown(4, 2, 2, usage)
    assert transport_usage_unknown(None, None, None, usage)
    assert not transport_usage_unknown(0, 0, 0, None)
