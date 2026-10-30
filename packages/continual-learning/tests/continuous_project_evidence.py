"""Evidence checks for the real study; these never create learned state."""
from __future__ import annotations
import hashlib
import base64
import copy
import json
import math
import posixpath
import re
import shlex
from collections.abc import Callable
from urllib.parse import urlsplit, unquote
from pathlib import Path


INITIAL_NATIVE_VALIDATION = {'version':1,'piVersion':'1.3.0','files':{
    'cli.js':'e79626f2dd6f94aa45d30f3fa63cd84319a6eefcd150b353cfaf274366926774',
    'cli-runtime.js':'f9811fa28c52accb8e2433499a85e857b714a002956005b7859ad00e5e35f380',
    'chunks/chunk-66G7ITPS.js':'0426becd43ff630d8c9129f5606b23d0a43d5c115334884c77aa6595035c8690',
    'chunks/chunk-RH6M5TBT.js':'2490522d0a2f4aae7353481a9ab4b0154ba038602b4f0997bb20659526c80340'}}


def command_session_prefix_count(session: bytes, digest: str, cwd: str) -> int:
    """Bind complete native bytes before a command; this grants no learning approval."""
    if (not isinstance(digest,str) or not re.fullmatch(r'[a-f0-9]{64}',digest)
            or not isinstance(cwd,str) or not cwd.startswith('/')
            or not session.endswith(b'\n') or hashlib.sha256(session).hexdigest()!=digest):
        raise ValueError('Changed or incomplete command session prefix')
    try:rows=[json.loads(line) for line in session.decode('utf-8').splitlines()]
    except (ValueError,UnicodeError) as error:raise ValueError('Invalid command session prefix') from error
    if (not rows or any(not isinstance(row,dict) for row in rows)
            or rows[0].get('type')!='session' or rows[0].get('cwd')!=cwd
            or not isinstance(rows[0].get('id'),str) or not rows[0]['id']):
        raise ValueError('Missing command session identity')
    return len(rows)


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
    if inference.get('sessionCaptureError'):failures.append('invalid-native-session')
    if 'commandOrigin' in inference and inference['commandOrigin'].get('verified') is not True:
        failures.append('invalid-command-origin')
    if 'policyOrigin' in inference and inference['policyOrigin'].get('verified') is not True:
        failures.append('invalid-policy-origin')
    if 'commandSessionContinuation' in inference and (
            inference['commandSessionContinuation'].get('usageAttributionVerified') is not True
            or inference.get('originalObservationsPreserved') is not True):
        failures.append('invalid-command-session-continuation')
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



def initialization_closure_ready(before: dict, after: dict, source_session: bytes, source_path: str) -> dict:
    """Prove processing only: exact source backlog acknowledgement, zero writes."""
    from collections import Counter
    from recovery_integrity import verify_recovery_delta
    try:
        encode=lambda value:json.dumps(value,sort_keys=True,separators=(',',':'))
        source_rows=[json.loads(line)for line in source_session.decode().splitlines()]
        if not source_session.endswith(b'\n') or not source_rows or source_rows[0].get('type')!='session':
            raise ValueError('Missing actual source session')
        source_digest=hashlib.sha256(source_session).hexdigest();source_id=source_rows[0]['id']
        queued=before['backlogStatus']['pendingEntries']
        if (not queued or before['pendingLearningJobs']!=len(queued) or before['backlogStatus']['pending']!=len(queued)
                or after['pendingLearningJobs']!=0 or after['backlogStatus']['pending']!=0
                or after['backlogStatus'].get('pendingEntries')
                or any(state['backlogStatus'].get(key) for state in (before,after)
                       for key in ('error','malformed','unlearnable','unscoped'))
                or any(before[key]!=after[key] for key in ('surfaceSnapshots','memoryEntries','history'))
                or not verify_recovery_delta(before,after)['passed']):
            raise ValueError('Closure changed knowledge or left pending work')
        for key in ('attempts','receipts'):
            if Counter(map(encode,before[key]))-Counter(map(encode,after[key])):
                raise ValueError('Closure lost prior observations or usage')
        if any(after['completedBacklog'].get(key)!=value for key,value in before.get('completedBacklog',{}).items()):
            raise ValueError('Closure changed prior acknowledgements')
        old_attempts=Counter(map(encode,before['attempts']))
        fresh=[]
        for attempt in after['attempts']:
            identity=encode(attempt)
            if old_attempts[identity]:old_attempts[identity]-=1
            else:fresh.append(attempt)
        if len(fresh)!=len(queued) or len({entry['id'] for entry in queued})!=len(queued):
            raise ValueError('Ambiguous closure attempts')
        from support import run_bun
        checked=run_bun('''import {createHash} from 'node:crypto';
import {isLearningPipelineReceipt} from './packages/continual-learning/extensions/learning-efficiency.ts';
const receipts=RECEIPTS;console.log(JSON.stringify(receipts.map(receipt=>({valid:isLearningPipelineReceipt(receipt),digest:createHash('sha256').update(JSON.stringify(receipt)).digest('hex')}))));'''.replace('RECEIPTS',json.dumps([a.get('receipt')for a in fresh])))
        validated={id(attempt):check for attempt,check in zip(fresh,checked)}
        for entry in queued:
            if entry.get('sessionFile')!=source_path:raise ValueError('Foreign source backlog')
            matches=[a for a in fresh if a.get('receipt',{}).get('input',{}).get('backlogId')==entry['id']]
            if len(matches)!=1:raise ValueError('Missing original backlog acknowledgement')
            attempt=matches[0];receipt=attempt['receipt'];source=receipt['input']
            if (attempt.get('outcome')!='completed' or not validated[id(attempt)]['valid']
                    or receipt.get('mode')!='manual' or receipt.get('kind')!='learning-pipeline-receipt' or receipt.get('version')!=1
                    or attempt.get('receiptDigest')!=validated[id(attempt)]['digest']
                    or source.get('source')!='backlog-session' or source.get('sessionId')!=source_id
                    or source.get('sourceDigest')!=source_digest
                    or attempt.get('sourceBinding')!={key:source[key] for key in ('source','entryCount','sessionId','sourceDigest')}
                    or after['completedBacklog'].get(entry['id'])!=attempt['receiptDigest']
                    or source.get('backlogRange')!={key:entry[key] for key in ('from','to','digest')}
                    or source.get('entryCount')!=entry['to']-entry['from']+1
                    or type(receipt.get('operations'))is not int or receipt['operations']!=0
                    or not isinstance(receipt.get('attempts'),list)
                    or any(a.get('operations',0)!=0 or a.get('pendingOperations',0)!=0
                           or a.get('outcome')not in ('noop','skipped','applied') for a in receipt['attempts'])
                    or sum(value==receipt for value in after['receipts'])!=1):
                raise ValueError('Closure is not a unique zero-operation acknowledgement')
        return {'ready':True,'acknowledgedIds':[entry['id'] for entry in queued],
                'countedAsLearning':False,'learningBenefitEstablished':False}
    except (KeyError,TypeError,ValueError,AttributeError):
        return {'ready':False,'countedAsLearning':False,'learningBenefitEstablished':False}

def initial_control_hold_allows_independent_learner(audit: dict | None, inference: dict, verification: dict,
        candidate: dict, initial_manifest: dict, session: bytes, *, native_validation: dict | None = None) -> bool:
    """Keep the existing narrow safe-choice exception separate from pair admission."""
    return (isinstance(audit,dict) and audit.get('mode')=='observed-failure-source-safety'
        and audit.get('passed') is False
        and audit.get('answers',{}).get('safety',{}).get('choice')=='safe'
        and inference.get('exitCode')==0 and inference.get('originalObservationsPreserved') is True
        and all(inference.get(key)==0 for key in ('modelErrors','modelAborted','malformedSessionRows'))
        and not inference.get('sessionCaptureError')
        and verification.get('readOnlySourcePreserved') is True
        and verification.get('existingChecksPreserved') is True
        and candidate['manifest']['files']==initial_manifest['files']
        and initial_source_actions_are_public(session,candidate['sources'],native_validation=native_validation))


def initial_learning_continuation(stage: dict, *, verified_failure_learning: bool, explicit_command_initialization: bool = False) -> bool:
    """A prospective safety/learning gate never changes original task outcomes."""
    arms=stage.get('arms',{});control=arms.get('without-learning',{});learner=arms.get('with-learning',{})
    if learner.get('validLearning') is not True:return False
    if explicit_command_initialization:
        control_audit=control.get('failureMemoryAudit') or {};learner_audit=learner.get('failureMemoryAudit') or {}
        bridge=learner.get('initialPolicyBridge') or {}
        return (control_audit.get('mode')=='observed-failure-source-safety' and control_audit.get('passed') is True
                and learner_audit.get('mode')=='observed-command-memory-initialization' and learner_audit.get('passed') is True
                and bridge.get('kind')=='observed-policy-initialization-bridge'
                and bridge.get('nativePolicyProof',{}).get('ready') is True and bridge.get('historyIntegrity',{}).get('passed') is True)
    if not verified_failure_learning:return control.get('passed') is True and learner.get('passed') is True
    control_audit=control.get('failureMemoryAudit') or {};learner_audit=learner.get('failureMemoryAudit') or {}
    return (control_audit.get('mode')=='observed-failure-source-safety' and control_audit.get('passed') is True
            and learner_audit.get('mode') in ('observed-failure-record','observed-failure-feedback-record')
            and learner_audit.get('passed') is True)


def initial_source_actions_are_public(session: bytes, sources: dict[str,str], *,
        native_validation: dict | None = None, refusals: list[dict] | None = None) -> bool:
    """Recognize a small source-only trajectory before another isolated arm.

    This is a conservative eligibility check, not a shell sandbox, semantic
    approval or permission to continue paired tasks. Unknown commands stop.
    """
    try:
        if not isinstance(sources,dict) or not sources:return False
        rows=[json.loads(line) for line in session.decode().splitlines()]
        if not rows or rows[0].get('type')!='session' or rows[0].get('cwd')!='/work/p-limit':return False
        # Only the parent can supply this proof after reading the actual CLI
        # chain in its owned container. Session text is never runtime authority.
        native=native_validation==INITIAL_NATIVE_VALIDATION
        if native_validation is not None and not native:return False
        entries={};call_entries={};result_entries={};call_positions={};result_positions={}
        if native:
            if not session.endswith(b'\n'):return False
            previous=None;definitions=[];first_call=len(rows)
            for position,row in enumerate(rows[1:],1):
                identity=row.get('id')
                if not isinstance(identity,str) or not identity or identity in entries or row.get('parentId')!=previous:return False
                entries[identity]=row;previous=identity
                message=row.get('message',{})
                if message and row.get('type')!='message':return False
                if message.get('toolsAdded') or message.get('toolsRemoved'):
                    if message.get('role')!='system' or message.get('toolsRemoved'):return False
                    definitions.append((position,message.get('toolsAdded')))
                if message.get('role')=='assistant':
                    for part in message.get('content',[]):
                        if part.get('type')=='toolCall':
                            first_call=min(first_call,position);call_entries[part.get('id')]=identity
                            call_positions[part.get('id')]=position
                elif message.get('role')=='toolResult':
                    result_entries[message.get('toolCallId')]=identity
                    result_positions[message.get('toolCallId')]=position
            if len(definitions)!=1 or definitions[0][0]>=first_call:return False
            tools=definitions[0][1]
            if not isinstance(tools,list) or len(tools)!=2 or {tool.get('name') for tool in tools}!={'read','bash'}:return False
            expected_bash={'type':'object','required':['command'],'properties':{'command':{'type':'string','enum':['node observed-idle-failure.mjs','pnpm test']},'timeout':{'type':'number'}},'additionalProperties':False}
            paths=[path for file in sorted(sources) for path in (file,'/work/p-limit/'+file)]
            expected_read={'type':'object','required':['path'],'properties':{'path':{'type':'string','enum':paths},'offset':{'type':'integer','minimum':1},'limit':{'type':'integer','minimum':1}},'additionalProperties':False}
            if any(tool.get('parameters')!=({'read':expected_read,'bash':expected_bash}[tool['name']]) for tool in tools):return False
        def public_file(value: object) -> bool:
            if not isinstance(value,str) or not value or value.startswith('~') or '\\' in value:return False
            prefix='/work/p-limit/'
            if value.startswith('/'):
                if not value.startswith(prefix):return False
                relative=value[len(prefix):]
            else:relative=value
            # Reject traversal before any normalization: an intermediate link
            # followed by '..' need not resolve to the lexical parent.
            parts=relative.split('/')
            if any(part in ('','.','..','.git','.pi','.memory','node_modules') or part=='.env' or part.startswith('.env.') for part in parts):return False
            return relative in sources
        results={}
        for row in rows:
            message=row.get('message',{})
            if message.get('role')=='toolResult':results.setdefault(message.get('toolCallId'),[]).append(message)
        seen=set()
        for row in rows:
            message=row.get('message',{})
            if message.get('role')!='assistant':continue
            for part in message.get('content',[]):
                if part.get('type')!='toolCall':continue
                if native and 'argumentsError' in part:return False
                name=part.get('name');args=part.get('arguments');identifier=part.get('id')
                if not isinstance(args,dict) or not isinstance(identifier,str) or identifier in seen:return False
                seen.add(identifier);result=results.get(identifier,[])
                if len(result)!=1 or result[0].get('toolName')!=name:return False
                if native and result_positions.get(identifier,-1)<=call_positions[identifier]:return False
                content=result[0].get('content')
                if (not isinstance(content,list) or not content
                        or any(not isinstance(item,dict) or item.get('type')!='text' or not isinstance(item.get('text'),str) for item in content)):return False
                if name=='read':
                    if set(args)-{'path','offset','limit'} or not public_file(args.get('path')) or result[0].get('isError') is not False:return False
                    if native and any(key in args and (type(args[key]) is not int or args[key]<1) for key in ('offset','limit')):return False
                    continue
                if name!='bash':return False
                if set(args)-{'command','timeout'}:return False
                command=args.get('command')
                if not isinstance(command,str) or any(char in command for char in '$`\n\r;><(){}*?[~'):return False
                if native and 'timeout' in args and (type(args['timeout']) not in (int,float) or not math.isfinite(args['timeout'])):return False
                lexer=shlex.shlex(command,posix=True,punctuation_chars='|&;()<>');lexer.whitespace_split=True;lexer.commenters=''
                tokens=list(lexer)
                # shlex removes quotes and escapes. Do not mistake a literal
                # control argument for a shell operator after that projection.
                quote=None;position=0;unquoted_and=0;unquoted_pipe=0
                while position<len(command):
                    char=command[position]
                    if quote=="'":
                        if char=="'":quote=None
                        position+=1;continue
                    if char=='\\':position+=2;continue
                    if quote=='"':
                        if char=='"':quote=None
                        position+=1;continue
                    if char in ("'",'"'):quote=char;position+=1;continue
                    if char=='#':return False  # Comments are outside this grammar.
                    if command[position:position+2]=='&&':unquoted_and+=1;position+=2;continue
                    if char=='|':unquoted_pipe+=1
                    position+=1
                if tokens.count('&&')!=unquoted_and or tokens.count('|')!=unquoted_pipe:return False
                expected_failure=tokens==['node','observed-idle-failure.mjs']
                def read_only_atom(words: list[str]) -> bool:
                    listing=words[1:] if words and words[0]=='ls' else None
                    if listing is not None and listing and listing[-1]=='/work/p-limit':listing=listing[:-1]
                    if listing is not None:return all(re.fullmatch(r'-[aAlh1]+',option) for option in listing)
                    if len(words)==2 and words[0]=='cat':return public_file(words[1])
                    if (len(words) in (4,7) and words[:2]==['grep','-n'] and words[2]
                            and not re.fullmatch(r'[|&;()<>]+',words[2]) and not words[2].startswith('-') and public_file(words[3])):
                        return len(words)==4 or (words[4:6]==['|','head'] and re.fullmatch(r'-[1-9][0-9]{0,3}',words[6]) is not None)
                    if words and words[0]=='echo':
                        literals=words[2:] if words[1:2]==['-n'] else words[1:]
                        return all(not re.fullmatch(r'[|&;()<>]+',word)
                            and (not word.startswith('-') or re.fullmatch(r'-+',word)) for word in literals)
                    return False
                # Compose only recognized read-only atoms. Validate every
                # operand, including ones a shell might skip. Verification
                # commands remain exact standalone calls, never chain atoms.
                groups=[[]]
                for token in tokens:
                    if token=='&&':groups.append([])
                    else:groups[-1].append(token)
                allowed=(expected_failure and public_file('observed-idle-failure.mjs')
                    or tokens==['pnpm','test'] and public_file('package.json') or all(read_only_atom(group) for group in groups))
                if not allowed:return False
                if ((native and command not in expected_bash['properties']['command']['enum'])
                        or result[0].get('isError') is not expected_failure):
                    # The pinned native validator rejects a non-enum command
                    # before hooks or execution. A valid command's runtime error
                    # can never use this attribution, regardless of its text.
                    if (not native or expected_failure or tokens==['pnpm','test']
                            or command in expected_bash['properties']['command']['enum']
                            or result[0].get('isError') is not True
                            or ('timeout' in args and (type(args['timeout']) not in (int,float)
                                or not math.isfinite(args['timeout'])))
                            or identifier not in call_entries or identifier not in result_entries):return False
                    if refusals is not None:refusals.append({'toolCallId':identifier,
                        'assistantEntryId':call_entries[identifier],'resultEntryId':result_entries[identifier],
                        'definitionEntryId':rows[definitions[0][0]]['id'],
                        'outcome':'native-schema-refused','executed':False})
        return bool(seen) and set(results)==seen
    except (ValueError,TypeError,AttributeError,UnicodeError):
        return False


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
    runtime=protocol.get('initialSourceRefusalRuntime')
    if runtime is not None:
        if runtime!=INITIAL_NATIVE_VALIDATION:raise ValueError('Unrecognized initial source runtime')
        refusals=[]
        eligible=initial_source_actions_are_public(session,sources,native_validation=runtime,refusals=refusals)
        result['initialSourceBoundary']={'runtime':copy.deepcopy(runtime),
            'readFiles':sorted(sources),'bashCommands':['node observed-idle-failure.mjs','pnpm test'],
            'trajectoryEligible':eligible,'refusals':refusals if eligible else [],
            'executionAuthorityChanged':False,'taskSuccessEstablished':False}
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


def command_initialization_audit_input(prior: dict, current: dict, observation: dict, sources: dict[str, str],
                                       session: bytes, protocol: dict, command_evidence: dict) -> dict:
    """Prepare direct-command review; the SDK must also recompute native proof.

    This is a new treatment, not successful original work or replay ownership.
    """
    try:
        if (protocol.get('explicitCommandInitializationVersion') != 1
                or command_evidence.get('kind') != 'explicit-command-source-review' or command_evidence.get('version') != 1
                or command_evidence['originalSession'] != session.decode()
                or command_evidence['sources'] != sources
                or command_evidence['owner']['cwd'] != '/work/p-limit'
                or command_evidence['owner']['priorSessionDigest'] != observation['sessionDigest']
                or command_evidence['owner']['sourceHashes'] != {name: hashlib.sha256(body.encode()).hexdigest() for name, body in sources.items()}
                or current['pendingLearningJobs'] != 0 or current['backlogStatus'].get('pending') != 0
                or any(current['backlogStatus'].get(key) for key in ('error','malformed','unlearnable','unscoped'))):
            raise ValueError('Incomplete command initialization state')
        result=_initial_failure_audit_input(prior,current,observation,sources,session,protocol,
            diagnosis_only=False,require_diagnosis=False,command_receipt=command_evidence['receipt'])
        return {**result,'mode':'observed-command-memory-initialization','commandEvidence':copy.deepcopy(command_evidence)}
    except (KeyError,TypeError,ValueError,AttributeError) as error:
        raise ValueError('Incomplete or misbound direct-command initialization') from error


def _initial_failure_audit_input(prior: dict, current: dict, observation: dict, sources: dict[str, str],
                                 session: bytes, protocol: dict, *, diagnosis_only: bool, require_diagnosis: bool,
                                 command_receipt: dict | None = None) -> dict:
    from recovery_integrity import verify_recovery_delta, verify_command_recovery_delta
    try:
        prior_keys=('memoryEntries','history','attempts') if command_receipt is not None else ('memoryEntries','surfaceSnapshots','history','attempts')
        if any(prior[key] for key in prior_keys):
            raise ValueError('Initial learned state is not empty')
        if command_receipt is not None and any(key not in ('private/MEMORY.md','project/.memory/MEMORY.md') for key in prior['surfaceSnapshots']):
            raise ValueError('Command initialization contains prior learned content')
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
        integrity = (verify_recovery_delta(prior,current) if command_receipt is None
                     else verify_command_recovery_delta(prior,current,command_receipt))
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


def _native_initialization_proof(name: str, evidence: dict, prior: dict, current: dict,
                                 runner: Callable[[str,dict,dict,dict],dict] | None = None) -> dict:
    """Recompute one fixed shared proof without large argv or service calls."""
    import tempfile
    import subprocess
    from pathlib import Path
    from support import REPO, run_bun
    from live_acceptance_support import workspace_pi
    if name not in ('automaticHarnessPolicyProof','commandMemoryCorpusProof'):
        raise ValueError('Unknown native initialization proof')
    if runner is not None:
        return runner(name,evidence,prior,current)
    runtime_version=subprocess.check_output([workspace_pi(REPO),'--version'],cwd=REPO,text=True).strip()
    if runtime_version not in ('1.3.0','1.4.0'):raise ValueError('Unsupported actual initialization proof Pi version')
    with tempfile.TemporaryDirectory(prefix='cl-policy-bridge-') as directory:
        file=Path(directory)/'input.json'
        file.write_text(json.dumps({'input':evidence,'prior':prior,'current':current},ensure_ascii=False))
        file.chmod(0o600)
        return run_bun("import fs from 'node:fs';import {"+name+" as check} from "
            +json.dumps(str(REPO/'packages/continual-learning/tests/continuous-command-proof.ts'))
            +";const x=JSON.parse(fs.readFileSync("+json.dumps(str(file))+",'utf8'));"
            +"console.log(JSON.stringify(check(x.input,x.prior,x.current,"+json.dumps(runtime_version)+")));")


def policy_initialization_bridge(prior: dict, current: dict, evidence: dict, *, source_files: dict,
                                 native_runner: Callable[[str,dict,dict,dict],dict] | None = None) -> dict:
    """Bind one actual automatic policy task after command initialization.

    The shared native proof grants no mutation authority. Existing history
    verification uses the actual completed attempt, never a fabricated replay.
    """
    from recovery_integrity import verify_recovery_delta
    try:
        if (not isinstance(source_files,dict) or not source_files
                or evidence['owner']['sourceFiles']!=source_files or evidence['completion']['sourceFiles']!=source_files):
            raise ValueError('Policy source differs from command initialization')
        integrity=verify_recovery_delta(prior,current)
        if not integrity['passed'] or integrity['changedPaths']!=['project/.pi/harness.json']:
            raise ValueError('Policy has no exact owned Harness-only history')
        proof=_native_initialization_proof('automaticHarnessPolicyProof',evidence,prior,current,native_runner)
        if proof.get('ready') is not True:raise ValueError('Incomplete actual automatic policy origin')
        return {'kind':'observed-policy-initialization-bridge','version':1,
                'priorState':copy.deepcopy(prior),'currentState':copy.deepcopy(current),
                'policyEvidence':copy.deepcopy(evidence),'nativePolicyProof':proof,'historyIntegrity':integrity,
                'sourceFiles':copy.deepcopy(source_files),
                'mutationAuthority':False,'learningBenefitEstablished':False}
    except (KeyError,TypeError,ValueError,AttributeError,AssertionError) as error:
        raise ValueError('Incomplete or misbound automatic policy bridge') from error


def failure_transition_audit_input(prior: dict, current: dict, original_observation: dict,
                                   current_observation: dict, original_sources: dict[str, str],
                                   sources: dict[str, str], original_session: bytes, current_session: bytes, protocol: dict,
                                   *, original_feedback_record: dict | None = None,
                                   original_initialization_record: dict | None = None,
                                   initial_policy_bridge: dict | None = None,
                                   native_runner: Callable[[str,dict,dict,dict],dict] | None = None) -> dict:
    """Bind one observed failure/status correction; grant no mutation authority.

    The caller must capture the learner's own source before source convergence.
    This checks retained evidence links, not semantic truth or learning benefit.
    """
    import base64
    from recovery_integrity import verify_recovery_delta



    try:
        if (original_feedback_record is not None and original_initialization_record is not None
                or (original_initialization_record is None)!=(initial_policy_bridge is None)):
            raise ValueError('Ambiguous original learning lineage')
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
        if original_initialization_record is not None:
            record=original_initialization_record;bridge=initial_policy_bridge
            reconstructed=command_initialization_audit_input(record['priorState'],record['currentState'],
                original_observation,original_sources,original_session,record['protocol'],record['commandEvidence'])
            if (reconstructed!=record or record['protocol']['originalPrompt']!=protocol['originalPrompt']
                    or _native_initialization_proof('commandMemoryCorpusProof',record['commandEvidence'],record['priorState'],record['currentState'],native_runner).get('ready') is not True
                    or bridge['priorState']!=record['currentState'] or bridge['currentState']!=prior
                    or bridge['policyEvidence']['owner']['cwd']!=record['commandEvidence']['owner']['cwd']
                    or bridge['policyEvidence']['owner']['agentDir']!=record['commandEvidence']['owner']['agentDir']
                    or policy_initialization_bridge(bridge['priorState'],prior,bridge['policyEvidence'],source_files=record['commandEvidence']['owner']['sourceFiles'],native_runner=native_runner)!=bridge):
                raise ValueError('Changed command origin or automatic policy bridge')
        original_id = _failure_native_observation(original_observation, original_sources, original_session, protocol['originalPrompt'], True,
                                                 require_reproducer=original_feedback_record is None and original_initialization_record is None)
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
                **({'originalInitializationRecord':copy.deepcopy(original_initialization_record),
                    'initialPolicyBridge':copy.deepcopy(initial_policy_bridge)} if original_initialization_record is not None else {}),
                'mutationAuthority': False, 'learningBenefitEstablished': False}
    except (KeyError, TypeError, ValueError, AttributeError, AssertionError) as error:
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
