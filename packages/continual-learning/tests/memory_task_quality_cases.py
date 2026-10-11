"""Frozen synthetic task oracles; never sent to the learner or model as labels."""
from __future__ import annotations

import hashlib


def cases(split: str, task_type: str = 'recall') -> list[dict]:
    if split not in {'development', 'heldout'}:
        raise ValueError('Unknown split')
    if task_type not in {'recall','resolve'}: raise ValueError('Unknown task type')
    rows = []
    for n in range(1 if split == 'development' else 2):
        prefix = ('dev' if split == 'development' else 'held') + str(n)
        for category in ('durable', 'misremember', 'temporary', 'conflict', 'expired', 'correction'):
            domain = 'project release lane' if split == 'development' else ('backup destination alias' if n == 0 else 'documentation locale alias')
            subject = 'Project ' + hashlib.sha256((prefix+category+'subject').encode()).hexdigest()[:8] + ' ' + domain
            old = 'alias-' + hashlib.sha256((prefix+category+'obsolete').encode()).hexdigest()[:10]
            new = 'alias-' + hashlib.sha256((prefix+category+'current').encode()).hexdigest()[:10]
            train = []
            files = {}
            if category == 'durable':
                train = [f'The settled public project fact is: {subject} is {new}. This is the confirmed long-term lane for future releases. Remember this project fact.']
                expected = new
            elif category == 'misremember':
                train = [f'An unverified draft speculates that {subject} is {old}. That statement is unconfirmed and may be wrong. The owner has not decided any lane. Do not treat the draft as a settled fact.']
                expected = 'unknown'
            elif category == 'temporary':
                train = [f'For this task only, use {old} as the {subject}. This is a one-time demonstration and is not the project default or a standing preference.']
                expected = new
                files = {'current.json': {'subject': subject, 'currentLane': new, 'authority': 'current project configuration'}}
            elif category == 'conflict':
                train = [f'The settled public project fact is: {subject} is {old}. Remember this long-term decision.',
                         f'The project owner has changed the public project decision: {subject} is now {new}. This supersedes {old}; the old lane is no longer valid. Remember the new decision and update the old knowledge.']
                expected = new
            elif category == 'expired':
                train = [f'The public project incident exception is: {subject} is {old} only through 2026-09-30. This exception expires after that date; it must not be used as a permanent default.']
                expected = new
                files = {'current.json': {'subject': subject, 'currentLane': new, 'effectiveFrom': '2026-10-01', 'authority': 'current project configuration'}}
            else:
                train = [f'The settled public project fact is: {subject} is {old}. Remember it for future project tasks.',
                         f'Correction: I gave you the wrong project fact earlier. {subject} has always been {new}, never {old}. Replace the mistaken fact; do not retain {old} as an alternative current lane.']
                expected = new
            task = (f'Today is 2026-10-10. Resolve the current operational value for {subject}. '
                    'Use the current authoritative project configuration if available; otherwise use established project knowledge. '
                    'Do not guess. If no confirmed current lane is available, use "unknown". '
                    'Read relevant files as needed and write answer.json as a JSON object with exactly one key "value" containing the current lane. '
                    'Finish after writing the file. Do not modify other files.')
            rows.append({'id': f'{prefix}-{category}', 'category': category, 'subject':subject,
                         'oldAlias':old,'currentAlias':new,'training': train,
                         'task': task, 'files': files, 'expected': expected, 'obsolete': old})
    if task_type == 'resolve':
        for row in rows:
            old, current = row['oldAlias'], row['currentAlias']
            decoys = ['alias-' + hashlib.sha256((row['id']+'decoy'+str(i)).encode()).hexdigest()[:10] for i in range(3)]
            aliases = {alias:{'handoffValue':'target-' + hashlib.sha256((alias+'handoff').encode()).hexdigest()[:14]}
                       for alias in sorted((old,current,*decoys))}
            row['files']['catalog.json'] = {'aliases':aliases}
            row['knowledgeExpected'] = row['expected']
            row['expected'] = aliases[row['knowledgeExpected']]['handoffValue'] if row['knowledgeExpected'] != 'unknown' else 'unknown'
            row['obsolete'] = aliases[old]['handoffValue']
            row['id'] += '-resolve'
            row['task'] = ('Today is 2026-10-10. Generate the operational handoff configuration. '
                           + row['subject']
                           + ' is the subject whose current alias you must resolve. '
                           'Determine its confirmed current alias from current.json when present, otherwise established project knowledge. '
                           'An expired exception or an unconfirmed draft is not a current decision. '
                           'Then look up that alias in catalog.json and write its handoffValue as the value in answer.json. '
                           'If no confirmed current alias is known, write "unknown"; do not pick a catalogue entry by guessing. '
                           'Write exactly one JSON object with exactly one key "value". Do not modify any other files.')
    return rows
