"""Evidence checks for the real study; these never create learned state."""
from __future__ import annotations
import hashlib
import base64
import copy
import json
import posixpath
import re
from urllib.parse import urlsplit, unquote
from pathlib import Path


def task_deadline_evidence(rows: list[dict], *, required: bool) -> dict:
    """A success needs the complete main lifecycle, never a lone status row."""
    records = [r for r in rows if r.get('customType') == 'continuous-study-task-deadline']
    events = [r.get('data') for r in records]
    def shaped(record: dict) -> bool:
        data = record.get('data')
        return (record.get('type') == 'custom' and isinstance(data, dict)
                and type(data.get('limitMs')) is int and data['limitMs'] == 900000
                and type(data.get('elapsedMs')) is int and data['elapsedMs'] >= 0)
    valid = (len(records) == 2 and all(shaped(r) for r in records)
             and events[0].get('stage') == 'started' and events[0]['elapsedMs'] <= 900000
             and events[1].get('stage') in ('settled', 'expired')
             and events[1]['elapsedMs'] >= events[0]['elapsedMs']
             and (events[1]['stage'] != 'settled' or events[1]['elapsedMs'] <= 900000))
    exceeded = any(isinstance(e, dict) and (e.get('stage') == 'expired'
                   or type(e.get('elapsedMs')) is int and e['elapsedMs'] > 900000) for e in events)
    return {'taskDeadlineEvents': events, 'taskDeadlineMissing': required and not valid,
            'taskDeadlineExceeded': exceeded}


def task_outcome(inference: dict, verification: dict) -> dict:
    """Code checks alone cannot make an aborted model task successful."""
    failures=[]
    if inference.get('exitCode')!=0:failures.append('process-exit')
    for field,label in (('timedOut','timeout'),('interrupted','interrupted'),
                        ('modelErrors','model-error'),('modelAborted','model-aborted'),('malformedSessionRows','malformed-session'),
                        ('temporaryInstructionLeaked','temporary-instruction-leaked'),
                        ('toolBudgetExceeded','tool-budget-exceeded'),
                        ('taskDeadlineExceeded','task-deadline-exceeded'),
                        ('taskDeadlineMissing','task-deadline-missing'),
                        ('verifierReadBoundaryViolations','verifier-read-boundary')):
        if inference.get(field):failures.append(label)
    if verification.get('passed') is not True:failures.append('verification-failed')
    return {'passed':not failures,'failures':failures}


def feedback_accepted(feedback: dict) -> bool:
    return task_outcome(feedback,{'passed':True})['passed'] and all(
        feedback.get(key) is True for key in ('originalObservationsPreserved','verifierObserved','taskSourceUnchanged')) and bool(feedback.get('queuedFailure'))


def exact_failure_processed(feedback: dict, learning: dict) -> bool:
    queued=feedback.get('queuedFailure') or {};observation=feedback.get('observation',{})
    if not queued.get('id') or not feedback.get('originalEntryIds'):return False
    acknowledged=any(a.get('outcome')=='completed' and a.get('receipt',{}).get('input',{}).get('backlogId')==queued['id']
        and bool(a.get('receiptDigest')) and learning.get('completedBacklog',{}).get(queued['id'])==a['receiptDigest']
        for a in learning.get('attempts',[]))
    def bound_observation(entries: dict) -> bool:
        return set(feedback['originalEntryIds']).issubset(entries.get('entryIds', [])) and any(
            o.get('sessionDigest') == observation.get('sessionDigest') and o.get('logsDigest') == observation.get('logsDigest')
            for o in entries.get('observations', []))
    observed = False
    for dossier in learning.get('dossiers', []):
        if dossier.get('taskSliceDigest') == queued.get('digest') and bound_observation(dossier):
            observed = True
        for prefix in dossier.get('originalPrefixProofs', []):
            start, end = queued.get('from'), queued.get('to')
            if (type(start) is int and type(end) is int and 0 <= start <= end
                    and prefix.get('from') == start and prefix.get('to') == end
                    and prefix.get('entryCount') == end - start + 1
                    and prefix.get('digest') == queued.get('digest')
                    and prefix.get('reviewDigest') == dossier.get('taskSliceDigest')
                    and bound_observation(prefix)):
                observed = True
    return acknowledged and observed


def initial_learning_continuation(stage: dict, *, verified_failure_learning: bool) -> bool:
    """A prospective safety/learning gate never changes original task outcomes."""
    arms=stage.get('arms',{});control=arms.get('without-learning',{});learner=arms.get('with-learning',{})
    if learner.get('validLearning') is not True:return False
    if not verified_failure_learning:return control.get('passed') is True and learner.get('passed') is True
    control_audit=control.get('failureMemoryAudit') or {};learner_audit=learner.get('failureMemoryAudit') or {}
    return (control_audit.get('mode')=='observed-failure-source-safety' and control_audit.get('passed') is True
            and learner_audit.get('mode') in ('observed-failure-record','observed-failure-feedback-record')
            and learner_audit.get('passed') is True)


def verifier_observation(task: str, verification: dict, output: Path, source_hashes: dict, session: bytes, *, inference: dict | None = None) -> dict:
    logs={name:(output/(name+'.log')).read_text() for name in ('hidden','types','upstream','public-reproducer') if (output/(name+'.log')).exists()}
    if sum(len(text.encode()) for text in logs.values()) > 1_000_000:
        raise ValueError('Verifier evidence exceeds bound; do not truncate it')
    return {'kind':'actual-project-verification','task':task,'verification':copy.deepcopy(verification),'logs':logs,
            'sourceHashes':copy.deepcopy(source_hashes),'sessionDigest':hashlib.sha256(session).hexdigest(),
            'logsDigest':hashlib.sha256(json.dumps(logs,sort_keys=True).encode()).hexdigest(),
            **({'taskOutcome':task_outcome(inference,verification)} if inference is not None else {})}


def _failure_memory_corpus(state: dict) -> None:
    entries = state['memoryEntries']
    if not entries:
        raise ValueError('Missing complete Memory corpus')
    bodies = {}
    for entry in entries:
        name, body, digest = entry['filename'], entry['content'], entry['revision']
        if (not isinstance(name, str) or Path(name).name != name or name == 'MEMORY.md'
                or not name.endswith('.md') or name in bodies or not isinstance(body, str)
                or not body.strip() or hashlib.sha256(body.encode()).hexdigest() != digest):
            raise ValueError('Invalid complete Memory entry')
        bodies[name] = digest
    seen = set()
    for key, snapshot in state['surfaceSnapshots'].items():
        if not snapshot.get('revision'):
            raise ValueError('Missing physical surface identity')
        prefix = next((p for p in ('private/', 'project/.memory/') if key.startswith(p)), None)
        if prefix is None or key[len(prefix):] == 'MEMORY.md':
            continue
        name = key[len(prefix):]
        if (name not in bodies or snapshot['digest'] != bodies[name]
                or hashlib.sha256(base64.b64decode(snapshot['bytes'], validate=True)).hexdigest() != bodies[name]):
            raise ValueError('Memory corpus and retained surfaces differ')
        seen.add(name)
    if seen != set(bodies):
        raise ValueError('Incomplete retained Memory corpus')


def _failure_native_observation(value: dict, text: dict[str, str], session: bytes, prompt: str, failed: bool, *, require_reproducer: bool = True) -> str:
    if (not session.endswith(b'\n') or value['kind'] != 'actual-project-verification'
            or hashlib.sha256(session).hexdigest() != value['sessionDigest']):
        raise ValueError('Changed native session evidence')
    rows = [json.loads(line) for line in session.decode('utf-8').splitlines()]
    if (not rows or rows[0].get('type') != 'session' or rows[0].get('cwd') != '/work/p-limit'
            or not isinstance(rows[0].get('id'), str) or not rows[0]['id']):
        raise ValueError('Missing native session identity')
    seen = {rows[0]['id']}
    parent = None
    for row in rows[1:]:
        if (not isinstance(row.get('id'), str) or not row['id'] or row['id'] in seen
                or 'parentId' not in row or row['parentId'] != parent):
            raise ValueError('Incomplete native parent chain')
        seen.add(row['id'])
        parent = row['id']
    deadline = task_deadline_evidence(rows, required=True)
    if deadline['taskDeadlineMissing'] or deadline['taskDeadlineExceeded']:
        raise ValueError('Incomplete successful main lifecycle')
    lifecycle = [index for index, row in enumerate(rows) if row.get('customType') == 'continuous-study-task-deadline']
    main_rows = [index for index, row in enumerate(rows) if row.get('message', {}).get('role') in ('user', 'assistant', 'toolResult')]
    if not main_rows or not lifecycle[0] < min(main_rows) <= max(main_rows) < lifecycle[1]:
        raise ValueError('Main task lies outside its native lifecycle')
    users = [row['message'] for row in rows if row.get('message', {}).get('role') == 'user']
    if (not isinstance(prompt, str) or not prompt.strip() or len(users) != 1
            or users[0].get('content') != [{'type': 'text', 'text': prompt}]):
        raise ValueError('Unexpected original task')
    calls, results = {}, {}
    last_assistant = None
    for index, row in enumerate(rows):
        message = row.get('message', {})
        if message.get('role') == 'assistant':
            last_assistant = message
            if message.get('stopReason') in ('error', 'aborted'):
                raise ValueError('Failed model task')
            for part in message.get('content', []):
                if part.get('type') != 'toolCall':
                    continue
                if not isinstance(part.get('id'), str) or not part['id'] or part['id'] in calls:
                    raise ValueError('Ambiguous native tool call')
                calls[part['id']] = (index, part)
        elif message.get('role') == 'toolResult':
            key = message.get('toolCallId')
            if key not in calls or key in results or message.get('toolName') != calls[key][1].get('name'):
                raise ValueError('Orphan or ambiguous native result')
            results[key] = (index, message)
    if (not calls or set(calls) != set(results) or last_assistant is None
            or last_assistant.get('stopReason') != 'stop'):
        raise ValueError('Incomplete native task/tool results')
    reproductions = [key for key, (_, call) in calls.items()
                    if call.get('name') == 'bash' and isinstance(call.get('arguments'), dict)
                    and call['arguments'].get('command', '').strip() == 'node observed-idle-failure.mjs']
    if require_reproducer and (not reproductions or results[reproductions[-1]][1].get('isError') is not failed
            or not results[reproductions[-1]][1].get('content')):
        raise ValueError('Actual final public reproducer result required')
    if (not value['logs'] or value['logsDigest'] != hashlib.sha256(json.dumps(value['logs'], sort_keys=True).encode()).hexdigest()
            or re.fullmatch(r'[a-f0-9]{64}', value['sessionDigest']) is None):
        raise ValueError('Missing or changed observation identity/logs')
    inventory = {name: digest for name, digest in value['sourceHashes'].items()
                 if name != '__configuration_paths__' and not name.startswith(('.memory/', '.pi/'))}
    if set(text) != set(inventory) or not {'index.js', 'index.d.ts', 'observed-idle-failure.mjs', 'package.json'}.issubset(text):
        raise ValueError('Complete bound source inventory required')
    for name, body in text.items():
        if (not isinstance(body, str) or hashlib.sha256(body.encode()).hexdigest() != inventory[name]
                or Path(name).is_absolute() or '..' in Path(name).parts):
            raise ValueError('Observation and complete source differ')
    return rows[0]['id']


def source_task_audit_input(observation: dict, sources: dict[str, str], session: bytes, prompt: str,
                            starting_sources: dict[str, str], starting_hashes: dict) -> dict:
    """Bind full task review to its actual native branch and complete revisions."""
    try:
        _failure_native_observation(observation, sources, session, prompt, False, require_reproducer=False)
        inventory = {name: digest for name, digest in starting_hashes.items()
                     if name != '__configuration_paths__' and not name.startswith(('.memory/', '.pi/'))}
        if set(starting_sources) != set(inventory) or any(hashlib.sha256(body.encode()).hexdigest() != inventory[name]
                                                        for name, body in starting_sources.items()):
            raise ValueError('Incomplete task starting source')
        if observation['verification']['passed'] is not True:
            raise ValueError('Independent source checks failed')
        return {'mode': 'observed-project-task', 'observation': copy.deepcopy(observation),
                'sources': dict(sources), 'startingSources': dict(starting_sources),
                'startingSourceHashes': inventory, 'nativeSession': session.decode(), 'prompt': prompt,
                'mutationAuthority': False, 'learningBenefitEstablished': False}
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ValueError('Incomplete or misbound source task evidence') from error


def failure_record_audit_input(prior: dict, current: dict, observation: dict, sources: dict[str, str],
                               session: bytes, protocol: dict, *, diagnosis_only: bool = False) -> dict:
    """Bind fresh diagnosis and optional meaningful initial failure knowledge."""
    return _initial_failure_audit_input(prior,current,observation,sources,session,protocol,
                                        diagnosis_only=diagnosis_only,require_diagnosis=True)


def failure_source_safety_audit_input(prior: dict, current: dict, observation: dict, sources: dict[str, str],
                                     session: bytes, protocol: dict) -> dict:
    """Review a failed control's read-only source safety, never its task success."""
    result=_initial_failure_audit_input(prior,current,observation,sources,session,protocol,
                                        diagnosis_only=True,require_diagnosis=False)
    return {**result,'mode':'observed-failure-source-safety'}


def failure_feedback_audit_input(prior: dict, current: dict, observation: dict, sources: dict[str, str],
                                session: bytes, protocol: dict, feedback: dict, feedback_evidence: dict) -> dict:
    """Bind a separate post-failure learning review to native observed feedback.

    The SDK runner must recompute the native observation proof before transport.
    These structural checks do not replace that proof or semantic review.
    """
    try:
        result=_initial_failure_audit_input(prior,current,observation,sources,session,protocol,
                                            diagnosis_only=False,require_diagnosis=False)
        queued=feedback['queuedFailure'];proof=feedback['failureObservationProof']
        raw=feedback_evidence['currentSession']
        if (observation.get('taskOutcome',{}).get('passed') is not False
                or feedback_evidence['originalSession']!=session.decode()
                or not isinstance(raw,str) or not raw.startswith(session.decode())
                or not raw.endswith('\n') or json.loads(feedback_evidence['verifierText'])!=observation
                or feedback.get('observation')!=observation or feedback_evidence['queued']!=queued
                or feedback_evidence['sourceBefore']!=observation['sourceHashes']
                or feedback_evidence['sourceAfter']!=observation['sourceHashes']
                or feedback_evidence['explicitBackfills']!=0
                or proof.get('ready') is not True or proof.get('backlogDigest')!=queued['digest']
                or proof.get('sessionDigest')!=hashlib.sha256(raw.encode()).hexdigest()
                or not all(feedback.get(key) is True for key in ('originalObservationsPreserved','verifierObserved','taskSourceUnchanged'))
                or not exact_failure_processed(feedback,current) or current['pendingLearningJobs']!=0
                or any(current['backlogStatus'].get(key) for key in ('error','malformed','unlearnable','unscoped'))):
            raise ValueError('Incomplete observed failure processing')
        expected_range={key:queued[key] for key in ('from','to','digest')}
        if not any(attempt.get('outcome')=='completed'
                   and current['completedBacklog'].get(queued['id'])==attempt.get('receiptDigest')
                   and (value:=attempt.get('receipt',{}).get('input',{})).get('backlogId')==queued['id']
                   and value.get('sourceDigest')==proof['sessionDigest']
                   and value.get('backlogRange')==expected_range
                   and value.get('entryCount')==queued['to']-queued['from']+1
                   for attempt in current['attempts']):
            raise ValueError('Missing exact acknowledged native failure receipt')
        return {**result,'mode':'observed-failure-feedback-record','feedback':copy.deepcopy(feedback),
                'feedbackEvidence':copy.deepcopy(feedback_evidence),'originalTaskPassed':False}
    except (KeyError,TypeError,ValueError,AttributeError) as error:
        raise ValueError('Incomplete or misbound post-failure learning evidence') from error


def _initial_failure_audit_input(prior: dict, current: dict, observation: dict, sources: dict[str, str],
                                 session: bytes, protocol: dict, *, diagnosis_only: bool, require_diagnosis: bool) -> dict:
    from recovery_integrity import verify_recovery_delta
    try:
        if any(prior[key] for key in ('memoryEntries', 'surfaceSnapshots', 'history', 'attempts')):
            raise ValueError('Initial learned state is not empty')
        inventory = protocol['initialSourceManifest']['files']
        if (set(sources) != set(inventory) or any(hashlib.sha256(sources[name].encode()).hexdigest() != metadata['sha256']
                                                 for name, metadata in inventory.items())):
            raise ValueError('Read-only diagnosis source changed')
        _failure_native_observation(observation, sources, session, protocol['originalPrompt'], True,
                                    require_reproducer=require_diagnosis)
        rows = [json.loads(line) for line in session.decode().splitlines()]
        calls = [part for row in rows if row.get('message', {}).get('role') == 'assistant'
                 for part in row['message'].get('content', []) if part.get('type') == 'toolCall']
        for command, failed in ((('node observed-idle-failure.mjs', True), ('pnpm test', False)) if require_diagnosis else ()):
            matches = [call for call in calls if call.get('name') == 'bash' and isinstance(call.get('arguments'), dict)
                       and call['arguments'].get('command', '').strip() == command]
            if len(matches) != 1 or not any(row.get('message', {}).get('toolCallId') == matches[0]['id']
                    and row['message'].get('isError') is failed for row in rows):
                raise ValueError('Actual once-only diagnostic and upstream results required')
        checks = observation['verification']
        if (checks['publicReproducer'] != {'passed': False, 'exitCode': 1}
                or checks['behavior'] != {'passed': False, 'exitCode': 1}
                or checks['existingChecksPreserved'] is not True
                or any(checks[key].get('passed') is not True or checks[key].get('exitCode') != 0
                       for key in ('upstream', 'types'))):
            raise ValueError('Expected actual source failure or green existing checks missing')
        integrity = verify_recovery_delta(prior, current)
        if not integrity['passed']:
            raise ValueError('Initial owned history incomplete')
        if diagnosis_only:
            if any(current[key] for key in ('memoryEntries', 'surfaceSnapshots', 'history', 'attempts')):
                raise ValueError('Baseline acquired learned state')
        else:
            _failure_memory_corpus(current)
            if not integrity['changedPaths']:
                raise ValueError('No actual initial knowledge stored')
        return {'mode': 'observed-failure-record', 'diagnosisOnly': diagnosis_only,
                'priorState': copy.deepcopy(prior), 'currentState': copy.deepcopy(current),
                'observation': copy.deepcopy(observation), 'sources': dict(sources),
                'nativeSession': session.decode(), 'protocol': copy.deepcopy(protocol),
                'historyIntegrity': integrity, 'mutationAuthority': False, 'learningBenefitEstablished': False}
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ValueError('Incomplete or misbound initial failure knowledge evidence') from error


def failure_transition_audit_input(prior: dict, current: dict, original_observation: dict,
                                   current_observation: dict, original_sources: dict[str, str],
                                   sources: dict[str, str], original_session: bytes, current_session: bytes, protocol: dict,
                                   *, original_feedback_record: dict | None = None) -> dict:
    """Bind one observed failure/status correction; grant no mutation authority.

    The caller must capture the learner's own source before source convergence.
    This checks retained evidence links, not semantic truth or learning benefit.
    """
    import base64
    from recovery_integrity import verify_recovery_delta



    try:
        integrity = verify_recovery_delta(prior, current)
        if not integrity['passed'] or not any(
                (key.startswith('private/') or key.startswith('project/.memory/'))
                and not key.endswith('/MEMORY.md') for key in integrity['changedPaths']):
            raise ValueError('No verified receipt-owned Memory correction')
        _failure_memory_corpus(prior)
        _failure_memory_corpus(current)
        initial_files = protocol['initialSourceManifest']['files']
        if (set(original_sources) != set(initial_files) or not set(initial_files).issubset(sources)
                or any(hashlib.sha256(original_sources[name].encode()).hexdigest() != metadata['sha256']
                       for name, metadata in initial_files.items())):
            raise ValueError('Original source differs from admitted source inventory')
        if original_feedback_record is not None:
            record=original_feedback_record
            reconstructed=failure_feedback_audit_input(record['priorState'],prior,original_observation,original_sources,
                original_session,record['protocol'],record['feedback'],record['feedbackEvidence'])
            if reconstructed!=record or record['protocol']['originalPrompt']!=protocol['originalPrompt']:
                raise ValueError('Changed original post-failure learning record')
        original_id = _failure_native_observation(original_observation, original_sources, original_session, protocol['originalPrompt'], True,
                                                 require_reproducer=original_feedback_record is None)
        current_id = _failure_native_observation(current_observation, sources, current_session, protocol['currentPrompt'], False)
        if (original_id == current_id or original_observation['sessionDigest'] == current_observation['sessionDigest']
                or original_sources['index.js'] == sources['index.js']
                or original_sources['observed-idle-failure.mjs'] != sources['observed-idle-failure.mjs']):
            raise ValueError('Fresh source repair and unchanged public case required')
        old, new = original_observation['verification'], current_observation['verification']
        if (old['publicReproducer'] != {'passed': False, 'exitCode': 1}
                or new['publicReproducer'] != {'passed': True, 'exitCode': 0}
                or any(old[name].get('passed') is not True or old[name].get('exitCode') != 0 for name in ('upstream', 'types'))
                or new['passed'] is not True or new['existingChecksPreserved'] is not True
                or any(new[name].get('passed') is not True or new[name].get('exitCode') != 0
                       for name in ('upstream', 'types', 'behavior'))):
            raise ValueError('Actual red-to-green independent source checks required')
        return {'mode': 'observed-failure-transition', 'priorState': copy.deepcopy(prior),
                'currentState': copy.deepcopy(current), 'originalObservation': copy.deepcopy(original_observation),
                'currentObservation': copy.deepcopy(current_observation), 'originalSources': dict(original_sources),
                'sources': dict(sources), 'originalSession': original_session.decode('utf-8'),
                'currentSession': current_session.decode('utf-8'), 'protocol': copy.deepcopy(protocol), 'historyIntegrity': integrity,
                **({'originalFeedbackRecord':copy.deepcopy(original_feedback_record)} if original_feedback_record is not None else {}),
                'mutationAuthority': False, 'learningBenefitEstablished': False}
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ValueError('Incomplete or misbound observed-failure correction evidence') from error


def observed_memory_reads(rows: list[dict], *, cwd: str, home: str, roots: tuple[str, ...]) -> list[dict]:
    """Bind actual successful reads to known study roots; hashes must separately
    equal retained learned bytes before coverage credits a complete revision.
    Partial reads or truncation notices will not equal the frozen file digest.
    This proves exposure through read, not adoption or useful task performance.
    """
    calls: dict[str, list[tuple[int, dict]]] = {}
    results: dict[str, list[tuple[int, dict]]] = {}
    for position, row in enumerate(rows):
        message = row.get('message', row)
        if not isinstance(message, dict):
            continue
        if message.get('role') == 'assistant' and isinstance(message.get('content'), list):
            for part in message['content']:
                if isinstance(part, dict) and part.get('type') == 'toolCall' and isinstance(part.get('id'), str):
                    calls.setdefault(part['id'], []).append((position, part))
        elif message.get('role') == 'toolResult' and isinstance(message.get('toolCallId'), str):
            results.setdefault(message['toolCallId'], []).append((position, message))
    observed = []
    for identity, invocations in calls.items():
        outcomes = results.get(identity, [])
        if len(invocations) != 1 or len(outcomes) != 1:
            continue
        call_position, call = invocations[0]
        result_position, result = outcomes[0]
        args = call.get('arguments')
        if (call.get('name') != 'read' or result.get('toolName') != 'read' or result.get('isError') is not False
                or call_position >= result_position or not isinstance(args, dict) or args.get('offset', 1) != 1
                or not isinstance(args.get('path'), str)):
            continue
        file = re.sub(r'[\u00A0\u2000-\u200A\u202F\u205F\u3000]', ' ', args['path']).removeprefix('@')
        if file.startswith('~/'):
            file = posixpath.join(home, file[2:])
        if file.startswith('file://'):
            try:
                uri = urlsplit(file)
                if uri.netloc.lower() not in ('', 'localhost') or re.search(r'%2f', uri.path, re.I):
                    continue
                file = unquote(uri.path, errors='strict')
            except (ValueError, UnicodeError):
                continue
        file = posixpath.normpath(posixpath.join(cwd, file))
        name = posixpath.basename(file)
        if posixpath.dirname(file) not in roots or name.lower() == 'memory.md' or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*\.md', name):
            continue
        content = result.get('content')
        if not isinstance(content, list) or not content or any(not isinstance(part, dict) or part.get('type') != 'text' or not isinstance(part.get('text'), str) for part in content):
            continue
        text = ''.join(part['text'] for part in content)
        if text:
            observed.append({'filename': name, 'revision': hashlib.sha256(text.encode()).hexdigest(),
                             'readPath': file, 'toolCallId': identity, 'callPosition': call_position, 'resultPosition': result_position})
    return observed


def continuous_coverage(report: dict) -> dict:
    stages=report.get('stages',[])
    version=report.get('coverageVersion',report.get('protocol',{}).get('coverageVersion',2))
    memory_evidence='observedMemoryReads' if version>=3 else 'deliveredMemoryEntries'
    arms={stage['id']:stage.get('arms',{}).get('with-learning',{}) for stage in stages}
    first=arms.get('orientation',{})
    entries=first.get('learning',{}).get('memoryEntries',[])
    old_contract=[e for e in entries if 'limitFunction' in e.get('content','') and 'PromiseLike' in e.get('content','')]
    used=False
    for stage in stages[1:]:
        arm=stage.get('arms',{}).get('with-learning',{})
        if any(ref.get('filename')==entry['filename'] and ref.get('revision')==entry['revision']
               for ref in arm.get('inference',{}).get(memory_evidence,[]) for entry in entries):used=True
    corrected=arms.get('repair-and-sync-wrapper',{}).get('learning',{}).get('memoryEntries',[])
    next_refs=arms.get('wrapper-map',{}).get('inference',{}).get(memory_evidence,[])
    audits=arms.get('repair-and-sync-wrapper',{}).get('memoryAudits',[])
    corrected_used=any(old['filename']==new['filename'] and old['revision']!=new['revision']
                       and hashlib.sha256(new.get('content','').encode()).hexdigest()==new['revision']
                       and any(audit.get('passed') is True and audit.get('filename')==new['filename'] and audit.get('priorRevision')==old['revision'] and audit.get('revision')==new['revision'] for audit in audits)
                       and any(ref.get('filename')==new['filename'] and ref.get('revision')==new['revision'] for ref in next_refs)
                       for old in old_contract for new in corrected)
    h0=first.get('harness',{});h2=arms.get('cancellable-idle',{}).get('harness',{});h3=arms.get('clear-reason',{}).get('harness',{})
    owned=h0.get('ownedRevisions',{})
    def history_link(arm: dict, before: str, after: str) -> bool:
        reachable={before}
        changes=[change for record in arm.get('learning',{}).get('history',[]) if record.get('phase')=='harness' and record.get('status')=='applied'
                 for change in record.get('changes',[]) if change.get('target')=={'root':'project','name':'.pi/harness.json'}]
        for _ in range(len(changes)+1):
            for change in changes:
                prior=(change.get('before') or {}).get('digest');current=(change.get('after') or {}).get('digest')
                if prior in reachable:reachable.add(current)
        return before!=after and after in reachable
    corrected_harness=False;retired=False;others_preserved=False
    for id,revision in owned.items():
        next_revision=h2.get('ownedRevisions',{}).get(id)
        if not next_revision or next_revision==revision:continue
        narrowed=next((r for r in h2.get('document',{}).get('rules',[]) if r.get('id')==id),None)
        tombstone=next((r for r in h3.get('document',{}).get('rules',[]) if r.get('id')==id),None)
        corrected_harness=bool(narrowed and narrowed.get('enabled') is not False and h2.get('passed')
                               and history_link(arms.get('cancellable-idle',{}),h0.get('documentDigest'),h2.get('documentDigest')))
        retired=bool(tombstone and tombstone.get('enabled') is False and id in h3.get('ownedRevisions',{}) and h3.get('passed')
                     and history_link(arms.get('clear-reason',{}),h2.get('documentDigest'),h3.get('documentDigest')))
        baseline=[r for r in h0.get('rules',[]) if r.get('id')!=id]
        others_preserved=all([r for r in h.get('rules',[]) if r.get('id')!=id]==baseline for h in (h2,h3))
        if corrected_harness and retired and others_preserved:break
    def failure_backfilled(arm: dict, *, learned: bool) -> bool:
        feedback=arm.get('verifierFeedback') or {};observation=feedback.get('observation',{});queued=feedback.get('queuedFailure') or {};learning=arm.get('learning',{})
        if not ((observation.get('verification',{}).get('passed') is False or observation.get('taskOutcome',{}).get('passed') is False) and feedback.get('originalObservationsPreserved') is True
                and feedback.get('verifierObserved') is True and feedback.get('taskSourceUnchanged') is True and arm.get('explicitRecovery')
                and bool(feedback.get('originalEntryIds')) and queued.get('id') in learning.get('completedBacklog',{}) and learning.get('pendingLearningJobs')==0):return False
        completed=[attempt for attempt in learning.get('attempts',[]) if attempt.get('outcome')=='completed' and attempt.get('receipt',{}).get('input',{}).get('backlogId')==queued['id']
                   and bool(attempt.get('receiptDigest')) and learning['completedBacklog'][queued['id']]==attempt['receiptDigest']]
        # Fresh source can extend the reviewed dossier beyond the queued task.
        # Use the same exact prefix and receipt proof as replay processing.
        if not completed or not exact_failure_processed(feedback,learning):return False
        if not learned:return True
        batches={a['receipt'].get('batchId') for a in completed if a['receipt'].get('operations',0)>0 and a['receipt'].get('batchId')}
        changed=[change for record in learning.get('history',[]) if record.get('status')=='applied' and record.get('batchId') in batches
                 for change in record.get('changes',[]) if change.get('after') and (change.get('before') or {}).get('digest')!=change['after'].get('digest')]
        # Delivery and execution are evidence of consumption, not a claim of benefit.
        later=False
        for stage in stages:
            candidate=stage.get('arms',{}).get('with-learning',{})
            if candidate is arm:later=True;continue
            if not later:continue
            for change in changed:
                target=change.get('target',{});digest=change['after'].get('digest')
                if target.get('root') in ('public','private') and target.get('name')!='MEMORY.md':
                    if any(ref.get('filename')==target.get('name') and ref.get('revision')==digest for ref in candidate.get('inference',{}).get(memory_evidence,[])):return True
                if target=={'root':'project','name':'.pi/harness.json'} and candidate.get('harness',{}).get('documentDigest')==digest and candidate.get('harness',{}).get('passed'):return True
        return False
    processed=any(failure_backfilled(arm,learned=False) for arm in arms.values())
    backfilled=any(failure_backfilled(arm,learned=True) for arm in arms.values())
    pairs=[]
    for stage in stages[1:]:
        pair=stage.get('arms',{});a=pair.get('without-learning',{});b=pair.get('with-learning',{})
        if not a or not b or not stage.get('validPairInput'):continue
        pairs.append({'task':stage['id'],'outcome':'tie' if bool(a.get('passed'))==bool(b.get('passed')) else 'win' if b.get('passed') else 'loss'})
    result={'memoryLearned':bool(entries),'originalTypeContractLearned':bool(old_contract),'memoryUsed':used,'memoryCorrectedAndUsed':corrected_used,
            'harnessCorrected':corrected_harness,'harnessRetired':retired,'otherRulesPreserved':others_preserved,'failedTaskProcessed':bool(processed),'failedTaskBackfilled':bool(backfilled),
            'pairedOutcomes':pairs,'learningValid':bool(stages) and all(s.get('arms',{}).get('with-learning',{}).get('validLearning') for s in stages)}
    result['coverageComplete']=len(stages)==6 and all(result[k] for k in ('memoryLearned','originalTypeContractLearned','memoryUsed','memoryCorrectedAndUsed','harnessCorrected','harnessRetired','otherRulesPreserved','failedTaskBackfilled','learningValid'))
    if report.get('observedFailureProtocolVersion') in (1,2):
        initial_audit=first.get('failureMemoryAudit') or {}
        repair=arms.get('idle',{});audit=repair.get('failureMemoryAudit') or {};capture=repair.get('candidateBeforeConvergence') or {}
        initial_modes=('observed-failure-record','observed-failure-feedback-record') if report.get('observedFailureProtocolVersion')==2 else ('observed-failure-record',)
        learned_failure=initial_audit.get('mode') in initial_modes and initial_audit.get('passed') is True and bool(entries)
        own_repair=(audit.get('mode')=='observed-failure-transition' and audit.get('passed') is True
                    and repair.get('verification',{}).get('sourceRepairPassed') is True
                    and capture.get('phase')=='post-main-before-source-convergence' and capture.get('canonicalImportApplied') is False)
        old_revisions={(entry['filename'],entry['revision']) for entry in entries}
        changed=[entry for entry in repair.get('learning',{}).get('memoryEntries',[])
                 if (entry['filename'],entry['revision']) not in old_revisions
                 and hashlib.sha256(entry.get('content','').encode()).hexdigest()==entry['revision']]
        later_reads=[ref for stage in stages[2:] for ref in stage.get('arms',{}).get('with-learning',{}).get('inference',{}).get(memory_evidence,[])]
        corpus=repair.get('learning',{}).get('memoryEntries',[])
        valid_corpus=bool(corpus) and len({entry['filename'] for entry in corpus})==len(corpus) and all(
            hashlib.sha256(entry.get('content','').encode()).hexdigest()==entry['revision'] for entry in corpus)
        corpus_digest=hashlib.sha256(json.dumps([[entry['filename'],entry['revision']] for entry in corpus],
                                               ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        bound_corpus=valid_corpus and audit.get('reviewedMemoryCorpusDigest')==corpus_digest and audit.get('ownedMemoryChange') is True
        corrected_failure_used=learned_failure and own_repair and bool(changed) and bound_corpus and all(
            any(ref.get('filename')==entry['filename'] and ref.get('revision')==entry['revision'] for ref in later_reads) for entry in corpus)
        result.update(failureKnowledgeLearned=bool(learned_failure),failureKnowledgeCorrectedAndUsed=bool(corrected_failure_used),
                      failureKnowledgeUseMetric='Every exact revision in the complete correction-reviewed corpus has a later complete native read; this does not establish attention, behavior adoption or causal benefit.',
                      memoryReadMetricLimit='Successful native read result only; zero does not establish absence of a complete body in mixed Bash output.')
        result['coverageComplete']=result['coverageComplete'] and learned_failure and corrected_failure_used
    result['improvementObserved']=result['coverageComplete'] and sum(x['outcome']=='win' for x in pairs)>sum(x['outcome']=='loss' for x in pairs)
    return result
