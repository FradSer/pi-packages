"""Research-only structural projection; original evidence remains authoritative."""
from __future__ import annotations

import copy
import json
from typing import Any


FIELDS = ('role', 'content', 'toolCallId', 'toolName', 'isError', 'timestamp', 'details', 'exitCode')


def structural_request(original: dict[str, Any]) -> dict[str, Any]:
    """Add auditable direct fields without rewriting instructions or source data."""
    if original.get('model') != 'jev-1.13.0' or not isinstance(original.get('questions'), dict):
        raise ValueError('Pinned research request required')
    try:
        state = json.loads(original['state']) if isinstance(original['state'], str) else copy.deepcopy(original['state'])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Invalid evidence state') from exc
    if not isinstance(state, dict) or 'structuralView' in state:
        raise ValueError('Invalid state or view collision')
    view: dict[str, Any] = {'schemaVersion': 1, 'writeAuthorized': False}
    for surface in ('supportEvidence', 'reviewEvidence'):
        evidence = state.get(surface)
        if not isinstance(evidence, dict) or not isinstance(evidence.get('entries'), list):
            raise ValueError('Full evidence entries required')
        rows = []
        calls: dict[str, list[str]] = {}
        for position, record in enumerate(evidence['entries']):
            if not isinstance(record, dict) or type(record.get('index')) is not int or not isinstance(record.get('entry'), dict):
                raise ValueError('Invalid evidence record')
            entry = record['entry']
            message = entry.get('message', entry)
            if not isinstance(message, dict):
                raise ValueError('Invalid message')
            prefix = f'{surface}.entries[{position}].entry' + ('.message' if 'message' in entry else '')
            fields = {key: copy.deepcopy(message[key]) for key in FIELDS if key in message}
            row: dict[str, Any] = {'position': position, 'index': record['index'], 'fields': fields,
                                   'fieldSources': {key: f'{prefix}.{key}' for key in fields}}
            call_id = message.get('toolCallId')
            if message.get('role') == 'toolResult':
                sources = calls.get(call_id, []) if isinstance(call_id, str) else []
                row['toolCallSources'] = list(sources)
                row['toolCallReference'] = 'unique' if len(sources) == 1 else 'ambiguous' if sources else 'missing'
            content = message.get('content')
            if message.get('role') == 'assistant' and isinstance(content, list):
                for part_position, part in enumerate(content):
                    if isinstance(part, dict) and part.get('type') == 'toolCall' and isinstance(part.get('id'), str):
                        calls.setdefault(part['id'], []).append(f'{prefix}.content[{part_position}]')
            rows.append(row)
        view[surface] = rows
    state['structuralView'] = view
    result = copy.deepcopy(original)
    result['state'] = json.dumps(state, ensure_ascii=False, separators=(',', ':')) if isinstance(original['state'], str) else state
    if len(result['questions']) > 32 or len(json.dumps(result, ensure_ascii=False).encode()) > 64000:
        raise ValueError('Research request byte bound exceeded')
    return result
