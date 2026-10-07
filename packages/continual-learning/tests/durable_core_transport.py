"""Conservative usage accounting for the single-generation research arms."""

import math


def transport_usage_unknown(
    total_requests: int | None,
    jev_requests: int | None,
    jev_responses: int | None,
    main_usage: object,
) -> bool:
    counters = (total_requests, jev_requests, jev_responses)
    if any(type(value) is not int or value < 0 for value in counters):
        return True
    assert total_requests is not None and jev_requests is not None and jev_responses is not None
    if jev_requests > total_requests or jev_responses != jev_requests:
        return True
    main_requests = total_requests - jev_requests
    if main_requests == 0:
        return False
    # One result cannot establish coverage of multiple transport calls.
    if main_requests != 1 or not isinstance(main_usage, dict):
        return True
    fields = ("input", "output", "cacheRead", "cacheWrite", "totalTokens")
    values = [main_usage.get(field) for field in fields]
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in values):
        return True
    return values[-1] <= 0 or sum(values[:-1]) != values[-1]
