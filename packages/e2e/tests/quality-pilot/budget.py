"""Conservative reservation, including failed and interrupted requests."""
import json

MAX_REQUESTS = 200
PRIOR_RESERVE_USD = 7.0
# At configured rates: <=65536 input bytes +8192 framing-token allowance,
# <=24576 output tokens. Cache discounts are deliberately ignored.
REQUEST_RESERVE_USD = 0.06


def validate_payload(body: bytes, is_jev: bool) -> None:
    if len(body) > 65536:
        raise ValueError('Request exceeds prepaid input reservation')
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError('Expected a request object')
    if not is_jev:
        outputs = [payload[k] for k in ('max_completion_tokens', 'max_tokens', 'max_output_tokens') if k in payload]
        if (not outputs or any(type(n) is not int or not 0 < n <= 24576 for n in outputs)
                or len(set(outputs)) != 1):
            raise ValueError('Completion exceeds prepaid output reservation')
        for key in ('n', 'best_of'):
            if key in payload and (type(payload[key]) is not int or payload[key] != 1):
                raise ValueError('Multiple candidates exceed prepaid reservation')
    elif not isinstance(payload.get('questions'), dict) or len(payload['questions']) != 1:
        raise ValueError('Only one semantic question fits this study reservation')
