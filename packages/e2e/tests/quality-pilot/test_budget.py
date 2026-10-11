"""Given a paid pilot, oversized requests must fail before forwarding."""
import pytest
from budget import validate_payload, MAX_REQUESTS, PRIOR_RESERVE_USD, REQUEST_RESERVE_USD


def test_total_reserved_cost_is_below_user_limit():
    assert PRIOR_RESERVE_USD + MAX_REQUESTS * REQUEST_RESERVE_USD < 20


def test_oversized_body_is_rejected():
    with pytest.raises(ValueError):
        validate_payload(b'x' * 65537, False)


def test_unbounded_completion_is_rejected():
    with pytest.raises(ValueError):
        validate_payload(b'{"max_tokens":384000}', False)


def test_normal_completion_is_accepted():
    validate_payload(b'{"max_tokens":8192}', False)


def test_missing_completion_bound_is_rejected():
    with pytest.raises(ValueError):
        validate_payload(b'{}', False)


@pytest.mark.parametrize('body', [b'{"max_completion_tokens":8192,"max_tokens":999999}',
                                  b'{"max_tokens":8192,"n":100}',
                                  b'{"max_tokens":8192,"best_of":2}',
                                  b'{"max_tokens":8192,"n":true}',
                                  b'{"max_tokens":8192,"max_output_tokens":4096}', b'[]'])
def test_multiple_completion_budget_bypasses_are_rejected(body):
    with pytest.raises(ValueError):
        validate_payload(body, False)


def test_semantic_question_fanout_is_bounded():
    validate_payload(b'{"questions":{"one":{}}}', True)
    with pytest.raises(ValueError):
        validate_payload(b'{"questions":{"one":{},"two":{}}}', True)
