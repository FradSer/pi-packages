"""Predeclared post-draft comparison policy; no inference on import."""
from __future__ import annotations
import math
from typing import Any

TOTAL_SECONDS = 1200
TOTAL_REQUESTS = 80
REVIEW_SECONDS = 300


def remaining_seconds(elapsed: float) -> float:
    """Initial verification/review and repair share one post-draft deadline."""
    return max(0.0, TOTAL_SECONDS - elapsed)


def review_text(events: list[dict[str, Any]]) -> str | None:
    """Only a completed review response becomes repair guidance."""
    replies = [e['message'] for e in events if e.get('type') == 'message_end'
               and e.get('message', {}).get('role') == 'assistant'
               and e.get('message', {}).get('stopReason') == 'stop']
    if not replies:
        return None
    text = '\n'.join(c.get('text', '') for c in replies[-1].get('content', []) if c.get('type') == 'text').strip()
    return text or None


def usage_cost(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Provider/Pi usage estimate, never an account-billing assertion."""
    usages = [m.get('usage', {}) for m in messages]
    estimates = [u.get('cost', {}).get('total') for u in usages]
    known = bool(estimates) and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                  and math.isfinite(v) and v >= 0 for v in estimates)
    return {'completedAssistantMessages': len(messages),
            'tokens': {k: sum(u[k] for u in usages) if usages and all(isinstance(u.get(k), int) and not isinstance(u.get(k), bool) and u[k] >= 0 for u in usages) else None for k in ('input', 'output', 'cacheRead', 'cacheWrite')},
            'piEstimatedUsd': sum(estimates) if known else None,
            'billingVerified': False,
            'incompleteRequestUsageUnknown': True}


def valid_inference(messages: list[dict[str, Any]]) -> bool:
    """Successful repair response, independent of initial review success."""
    return any(m.get("stopReason") in {"stop", "toolUse", "length"} for m in messages)
