"""Opt-in real-model longitudinal maintenance study; no authored learned facts.

Each stage uses byte-identical source for both fresh-session arms. All model,
learning, failed and recovery attempts remain in the report. Source convergence
uses the predeclared no-learning-first passing candidate, otherwise its failed
candidate, and is an experimental intervention rather than independent evolution.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
from pathlib import Path
from continuous_failure_retention import retain_failure_container, retained_learning_costs, learning_cost_summary, deduplicate_receipt_views
import tarfile
import time
import uuid

import live_real_project_memory as base
from continuous_project_tasks import COMMON, UNLIMITED_COMMON, TASKS, SOURCE_COMMIT, ORACLE, TYPES, SIGNAL_TYPES, REASON_TYPES, SYNC_TYPES, MAP_TYPES, migrate_public_sync_type_test, failure_first_tasks, command_initialization_tasks, INITIAL_HARNESS_POLICY
from docker_experiment import InferenceProxy, redact_transport_bytes
from live_acceptance_support import EvidenceRun
from continuous_project_evidence import command_session_prefix_count, task_deadline_evidence, continuous_coverage, verifier_observation, task_outcome, feedback_accepted, exact_failure_processed, observed_memory_reads, failure_record_audit_input, failure_feedback_audit_input, failure_source_safety_audit_input, failure_transition_audit_input, source_task_audit_input, initial_learning_continuation, command_initialization_audit_input, initialization_closure_ready, policy_initialization_bridge
from recovery_integrity import archive_surface_snapshots, verify_recovery_delta, claim_recovery, load_observed_idle_source, source_archive_files, bind_study_artifact, read_study_artifact
from continuous_project_evidence import initial_source_actions_are_public, initial_control_hold_allows_independent_learner, INITIAL_NATIVE_VALIDATION


def executed_version_probes(messages: list[dict]) -> list[dict[str, str]]:
    calls: dict[str, list[dict]] = {}
    results: dict[str, list[dict]] = {}
    for message in messages:
        if message.get('role')=='assistant' and isinstance(message.get('content'),list):
            for part in message['content']:
                if isinstance(part,dict) and part.get('type')=='toolCall' and isinstance(part.get('id'),str):
                    calls.setdefault(part['id'],[]).append(part)
        elif message.get('role')=='toolResult' and isinstance(message.get('toolCallId'),str):
            results.setdefault(message['toolCallId'],[]).append(message)
    executed=[]
    for id, matching in calls.items():
        if len(matching)!=1 or len(results.get(id,[]))!=1:continue
        call=matching[0];result=results[id][0];arguments=call.get('arguments',{})
        if call.get('name')!='bash' or not isinstance(arguments,dict) or not isinstance(arguments.get('command'),str):continue
        if not re.fullmatch(r'npm[ \t]+--version[ \t]*',arguments['command'].strip()):continue
        if result.get('toolName')!='bash' or result.get('isError') is not False:continue
        content=result.get('content')
        if not isinstance(content,list) or any(not isinstance(p,dict) or p.get('type')!='text' or not isinstance(p.get('text'),str) for p in content):continue
        text=''.join(p.get('text','') for p in content).strip()
        if re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?',text):
            executed.append({'toolCallId':id,'version':text})
    return executed


def source_archive(c: str) -> bytes:
    return base.checked(['docker','exec',c,'tar','--exclude=node_modules','--exclude=.git','--exclude=.pi','--exclude=.memory','-czf','-','-C','/work/p-limit','.'])


def install_source(c: str, data: bytes) -> None:
    # Only this runner's disposable containers are mutated. Keep installed deps.
    base.shell(c,"find /work/p-limit -mindepth 1 -maxdepth 1 ! -name node_modules ! -name .git ! -name .pi ! -name .memory -exec rm -rf -- {} +")
    base.checked(['docker','exec','-i',c,'tar','-xzf','-','-C','/work/p-limit'],data=data)


def initial_native_validation(c: str, version: str) -> dict:
    """Read the executed CLI chain in the owned container, never from a model."""
    code="""const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const root=path.dirname(process.argv[1]),files=JSON.parse(process.argv[2]);
console.log(JSON.stringify(Object.fromEntries(files.map(file=>[file,crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex')]))));"""
    files=json.loads(base.checked(['docker','exec',c,'node','-e',code,base.PI,
        json.dumps(list(INITIAL_NATIVE_VALIDATION['files']))]))
    proof={'version':1,'piVersion':version,'files':files}
    if proof!=INITIAL_NATIVE_VALIDATION:raise RuntimeError('Unrecognized native schema validation runtime')
    return proof


def score(c: str, level: int, proxy: InferenceProxy, output: Path, before: dict) -> dict:
    output.mkdir(parents=True,exist_ok=True)
    def check(name: str, args: list[str]) -> dict:
        try:
            p=base.process(['docker','exec','-w','/work/p-limit',c,*args],timeout=240)
            (output/(name+'.log')).write_bytes(redact_transport_bytes(p.stdout+p.stderr,proxy))
            return {'passed':p.returncode==0,'exitCode':p.returncode}
        except subprocess.TimeoutExpired:
            return {'passed':False,'exitCode':124}
    upstream=check('upstream',['pnpm','test'])
    behavior=types=None
    if level:
        base.put(c,'/home/node/oracle/continuous.mjs',ORACLE.encode())
        behavior=check('hidden',['env','CL_LEVEL='+str(level),'node','--test','/home/node/oracle/continuous.mjs'])
        type_text=TYPES+(SIGNAL_TYPES if level>=2 else '')+(REASON_TYPES if level>=3 else '')+(SYNC_TYPES if level>=4 else '')+(MAP_TYPES if level>=5 else '')
        base.put(c,'/work/p-limit/continuous-study.test-d.ts',type_text.encode())
        types=check('types',['pnpm','exec','tsd','--files','continuous-study.test-d.ts'])
        base.shell(c,'rm -f /work/p-limit/continuous-study.test-d.ts; rm -rf /home/node/oracle')
    after=base.protected(c,'p-limit')
    intact=all(after.get(k)==v for k,v in before.items())
    return {'upstream':upstream,'behavior':behavior,'types':types,'existingChecksPreserved':intact,
            'passed':intact and upstream['passed'] and (not level or (behavior['passed'] and types['passed']))}


# Main-model time and independent learning time have different owners.
# This outer guardian is not permission to extend any worker/service deadline.
# Multiple recorded Memory correction workers (600s each, ADR 0009) can exceed
# the bounded 900s task guardian, so a bounded cohort can be interrupted while a
# heavy correction runs; that interruption stays an interrupted observation and
# never a pass. Correction acceptance runs use the unlimited guardian.
UNLIMITED_CLI_GUARDIAN_SECONDS = 7200


class UnappliedMemoryCommand(ValueError):
    """A complete native command has no applied knowledge to authenticate."""


COMMAND_ORIGIN_ARTIFACTS = ('memory-command-started.json','memory-command-closed.json','original-session.jsonl',
    'stdout.jsonl','stderr.txt','session.jsonl',
    'command-source-before/candidate-before-convergence.json','command-source-before/candidate-before-convergence.tar.gz',
    'command-source-after/candidate-before-convergence.json','command-source-after/candidate-before-convergence.tar.gz')
POLICY_ORIGIN_ARTIFACTS = tuple(name.replace('memory-command-','policy-') for name in COMMAND_ORIGIN_ARTIFACTS)


def read_command_session(c: str, label: str) -> bytes:
    """Read one actual native session through the same scoped regular reader."""
    if not re.fullmatch(r'[A-Za-z0-9_-]+',label):raise ValueError('Invalid command session label')
    base.put(c,'/home/node/learned-surface-metadata.py',Path(__file__).with_name('recovery_integrity.py').read_bytes())
    code="import runpy,sys;from pathlib import Path;api=runpy.run_path('/home/node/learned-surface-metadata.py',run_name='study_artifact_reader');sys.stdout.buffer.write(api['read_study_artifact'](Path(sys.argv[1]),sys.argv[2],bound=32*1024*1024))"
    return base.checked(['docker','exec',c,'python3','-c',code,base.AGENT,'sessions/continuous/'+label+'.jsonl'])


def run_session(c: str, prompt: str, proxy: InferenceProxy, output: Path, label: str, *, command: bool = False, feedback_observation: dict | None = None, unlimited_budget: bool = False, prior_session_digest: str | None = None, capture_command_origin: bool = False, capture_policy_origin: bool = False, initial_source_paths: list[str] | None = None, expected_pi_version: str = '1.3.0', source_task_boundary: dict | None = None) -> dict:
    if expected_pi_version not in ('1.3.0','1.4.0') or capture_policy_origin and expected_pi_version!='1.3.0':
        raise ValueError('Unsupported native study Pi version')
    if initial_source_paths is not None and (command or feedback_observation is not None or label != 'stage-0' or capture_policy_origin):
        raise ValueError('Initial source boundary belongs only to the original read-only task')
    if source_task_boundary is not None:
        if (command or feedback_observation is not None or capture_command_origin or capture_policy_origin
                or prior_session_digest is not None or initial_source_paths is not None or label not in ('source-v1','source-v2')):
            raise ValueError('Source v2 boundary requires an explicit ordinary source-v1/source-v2 task')
        boundary=source_task_boundary
        example='examples/native-wrapper-'+label.removeprefix('source-')+'.js'
        def public_path(path: object) -> bool:
            return (isinstance(path,str) and bool(path) and not path.startswith('/') and '\\' not in path
                and not any(ord(char)<32 or ord(char)==127 for char in path)
                and all(part and part not in ('.','..','.git','.pi','.memory','node_modules')
                        and part!='.env' and not part.startswith('.env.') for part in path.split('/')))
        if (not isinstance(boundary,dict) or set(boundary)!={'version','readPaths','writePaths','commands'}
                or type(boundary.get('version')) is not int or boundary['version']!=2
                or boundary.get('writePaths')!=[example]
                or any(not isinstance(boundary.get(key),list) or not boundary[key]
                       or any(not isinstance(item,str) for item in boundary[key])
                       or len(boundary[key])!=len(set(boundary[key])) for key in ('readPaths','writePaths','commands'))
                or not all(public_path(path) for path in boundary['readPaths'])
                or any(value not in ('node '+example,'pnpm test') for value in boundary['commands'])):
            raise ValueError('Invalid source v2 boundary or example/stage mismatch')
    if capture_policy_origin and (command or capture_command_origin or prior_session_digest is not None
            or feedback_observation is not None or not unlimited_budget or prompt!=INITIAL_HARNESS_POLICY):
        raise ValueError('Policy origin requires the distinct no-tools unlimited user task')
    capture_origin=capture_command_origin or capture_policy_origin
    owner_file='policy-started.json' if capture_policy_origin else 'memory-command-started.json'
    closed_file='policy-closed.json' if capture_policy_origin else 'memory-command-closed.json'
    if capture_command_origin and (prior_session_digest is None or not re.fullmatch(r'/memory [^\r\n]+',prompt)
            or prompt!='/memory '+prompt[len('/memory '):].strip()):
        raise ValueError('Command origin requires one exact Memory continuation')
    if prior_session_digest is not None and (not command or feedback_observation is not None
            or not isinstance(prior_session_digest,str) or not re.fullmatch(r'[a-f0-9]{64}',prior_session_digest)
            or not (re.fullmatch(r'/memory[ \t]+[^\r\n]+',prompt) or prompt=='/consolidate backfill')
            or not re.fullmatch(r'[A-Za-z0-9_-]+',label)):
        raise ValueError('Invalid explicit learning session continuation')
    session=base.AGENT+'/sessions/continuous/'+label+'.jsonl'
    base.shell(c,'mkdir -p '+base.AGENT+'/sessions/continuous')
    if capture_policy_origin:
        base.checked(['docker','exec',c,'python3','-c','import os,sys;sys.exit(1 if os.path.lexists(sys.argv[1]) else 0)',session])
    prior_bytes=b'';prior_count=0;feedback_text='';feedback_file='/home/node/project-verification.json'
    if prior_session_digest is not None:
        prior_bytes=read_command_session(c,label) if capture_command_origin or prompt=='/consolidate backfill' else base.checked(['docker','exec',c,'cat',session])
        prior_count=command_session_prefix_count(prior_bytes,prior_session_digest,'/work/p-limit')
    if feedback_observation is not None:
        prior_bytes=base.checked(['docker','exec',c,'cat',session])
        if hashlib.sha256(prior_bytes).hexdigest()!=feedback_observation['sessionDigest']:raise RuntimeError('Original verifier session changed')
        prior_count=len(prior_bytes.splitlines())
        feedback_text=json.dumps(feedback_observation,ensure_ascii=False,indent=2)
        base.put(c,feedback_file,feedback_text.encode())
    args=['docker','exec','-w','/work/p-limit','-e','PI_CODING_AGENT_DIR='+base.AGENT,'-e','PI_OFFLINE=1']
    for key,value in proxy.jev_environment().items():args+=['-e',key+'='+value]
    if feedback_observation is not None:args+=['-e','PI_STUDY_VERIFIER_FILE='+feedback_file,'-e','PI_STUDY_TASK_TOOL_LIMIT=1']
    if initial_source_paths is not None:args+=['-e','PI_STUDY_INITIAL_SOURCE_FILES='+json.dumps(initial_source_paths)]
    if source_task_boundary is not None:args+=['-e','PI_STUDY_SOURCE_TASK_BOUNDARY='+json.dumps(source_task_boundary,separators=(',',':'))]
    native_args=['node',base.PI,'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-approve',
             '--model',proxy.selection['provider']+'/'+proxy.selection['model'],'--thinking','off',
             *(['--no-tools'] if capture_policy_origin else ['--tools','read' if feedback_observation is not None else 'read,bash' if initial_source_paths is not None else 'read,bash,edit,write']),
             *(['-e','/home/node/continuous-bash-environment.ts'] if not command and feedback_observation is None else []),
             *([] if command or (unlimited_budget and feedback_observation is None) else ['-e','/home/node/continuous-tool-budget.ts']),
             *(['-e','/home/node/continuous-verifier-reference.ts'] if feedback_observation is not None else []),
             *(['-e','/home/node/continuous-task-deadline.ts'] if unlimited_budget and not command else []),
             '-e','/opt/experiment/packages/continual-learning/index.ts','--session',session,'--print','--mode','json',prompt if command or feedback_observation is not None else (UNLIMITED_COMMON if unlimited_budget else COMMON)+prompt]
    args += [c,*native_args]
    started=time.monotonic();interrupted=False;owner=None;before_command=None
    if capture_origin and any(parent.is_symlink() for parent in (output,*output.parents)):
        raise ValueError('Command evidence path contains a symlink')
    output.mkdir(parents=True,exist_ok=not capture_origin)
    if capture_origin:
        if redact_transport_bytes(prior_bytes,proxy)!=prior_bytes:
            raise RuntimeError('Sensitive original command evidence cannot be retained')
        (output/'original-session.jsonl').write_bytes(prior_bytes)
        version=base.checked(['docker','exec',c,'node',base.PI,'--version']).decode().strip()
        if version!=expected_pi_version:raise RuntimeError('Command origin does not match the expected actual Pi version')
        (output/'command-source-before').mkdir()
        before_command=capture_failure_candidate(c,proxy,output/'command-source-before',prior_bytes)
        owner={'kind':'native-automatic-harness-policy' if capture_policy_origin else 'native-memory-command','version':1,'container':c,'argv':native_args,
            'cwd':'/work/p-limit','agentDir':base.AGENT,'sessionPath':session,
            'model':proxy.selection['provider']+'/'+proxy.selection['model'],'piVersion':version,
            'sourceHashes':before_command['manifest']['sourceHashes'],'sourceFiles':before_command['manifest']['files'],
            'startedAt':time.time_ns()//1_000_000}
        if capture_policy_origin:owner.update(prompt=native_args[-1],sourceFiles=before_command['manifest']['files'])
        else:owner.update(arguments=prompt[len('/memory '):],priorSessionDigest=prior_session_digest)
        with (output/owner_file).open('x') as file:
            file.write(json.dumps(owner,ensure_ascii=False,separators=(',',':')))
    try:
        p=base.process(args,timeout=UNLIMITED_CLI_GUARDIAN_SECONDS if unlimited_budget else 900);stdout=p.stdout;stderr=p.stderr;code=p.returncode;timed_out=False
    except KeyboardInterrupt:
        base.checked(['docker','stop',c]);stdout=b'';stderr=b'Operator interrupted; partial session retained';code=130;timed_out=False;interrupted=True
    except subprocess.TimeoutExpired as error:
        base.checked(['docker','stop',c]);stdout=error.stdout or b'';stderr=error.stderr or b'';code=124;timed_out=True
    (output/'stdout.jsonl').write_bytes(redact_transport_bytes(stdout,proxy));(output/'stderr.txt').write_bytes(redact_transport_bytes(stderr,proxy))
    # docker cp can still retrieve evidence from a stopped disposable container.
    copied=base.process(['docker','cp',c+':'+session,str(output/'session.jsonl')])
    messages=[];references=[];rows=[];malformed_rows=0;original_preserved=not prior_bytes
    captured=None;session_capture_error='copy-failed' if copied.returncode!=0 else None
    if session_capture_error:original_preserved=False
    if copied.returncode==0:
        try:
            captured=read_study_artifact(output,'session.jsonl',bound=32*1024*1024)
        except (OSError,ValueError) as error:
            session_capture_error=type(error).__name__
            original_preserved=False
        if captured is not None:
            original_preserved=not prior_bytes or captured.startswith(prior_bytes)
            raw=redact_transport_bytes(captured,proxy)
            # Never write through a path copied from the child container.
            import tempfile
            descriptor,temporary=tempfile.mkstemp(prefix='.redacted-session-',dir=output)
            try:
                with os.fdopen(descriptor,'wb') as file:file.write(raw)
                os.replace(temporary,output/'session.jsonl')
            finally:
                if os.path.lexists(temporary):os.unlink(temporary)
            for line in raw.splitlines():
                try:
                    row=json.loads(line)
                    if not isinstance(row,dict):raise ValueError('Non-object session record')
                    rows.append(row)
                except ValueError:malformed_rows+=1
            rows=rows[prior_count:]
            messages=[r['message'] for r in rows if r.get('type')=='message']
            references=[r for r in rows if r.get('customType')=='continual-learning-memory-reference']
    command_origin=None
    if owner is not None:
        after_command=None;capture_error=None
        if not timed_out and not interrupted:
            try:
                (output/'command-source-after').mkdir()
                after_command=capture_failure_candidate(c,proxy,output/'command-source-after',captured or b'')
            except (OSError,RuntimeError,ValueError,UnicodeError) as error:capture_error=type(error).__name__
        unchanged=bool(after_command and before_command['manifest']['files']==after_command['manifest']['files'])
        verified=(code==0 and not timed_out and not interrupted and copied.returncode==0 and original_preserved
            and malformed_rows==0 and unchanged and redact_transport_bytes(stdout,proxy)==stdout
            and captured is not None and redact_transport_bytes(captured,proxy)==captured)
        closed={'ownerDigest':hashlib.sha256((output/owner_file).read_bytes()).hexdigest(),
            'exitCode':code,'cancelled':interrupted,'timedOut':timed_out,'settledAt':time.time_ns()//1_000_000,
            'stdoutDigest':hashlib.sha256(stdout).hexdigest(),
            'sessionDigest':hashlib.sha256(captured).hexdigest() if captured is not None else None,
            'sourceHashes':after_command['manifest']['sourceHashes'] if after_command else None,
            'sourceFiles':after_command['manifest']['files'] if after_command else None,
            'sourceInventoryVerified':unchanged,**({'sourceCaptureError':capture_error} if capture_error else {})}
        if capture_policy_origin:closed['sourceFiles']=after_command['manifest']['files'] if after_command else None
        with (output/closed_file).open('x') as file:file.write(json.dumps(closed,ensure_ascii=False,indent=2))
        bindings={};binding_error=None
        try:
            for name in POLICY_ORIGIN_ARTIFACTS if capture_policy_origin else COMMAND_ORIGIN_ARTIFACTS:
                bindings[name]=bind_study_artifact(output,name,bound=32*1024*1024)
        except (ValueError,OSError) as error:binding_error=type(error).__name__
        command_origin={'recorded':True,'verified':verified and binding_error is None,
            'sourceInventoryVerified':unchanged,'artifactBindings':bindings,
            **({'artifactBindingError':binding_error} if binding_error else {}),
            **({'sessionCaptureError':session_capture_error} if session_capture_error else {})}
    usage=[m.get('usage',{}) for m in messages if m.get('role')=='assistant']
    verifier_read=False
    if feedback_observation is not None:
        calls=[part for message in messages if message.get('role')=='assistant' and isinstance(message.get('content'),list)
               for part in message['content'] if part.get('type')=='toolCall' and part.get('name')=='read' and part.get('arguments',{}).get('path')==feedback_file]
        verifier_read=any(sum(call.get('id')==other.get('id') for other in calls)==1
                          and any(message.get('role')=='toolResult' and message.get('toolName')=='read' and message.get('toolCallId')==call.get('id')
                                  and message.get('isError') is False and feedback_text in ''.join(part.get('text','') for part in message.get('content',[]) if isinstance(part,dict)) for message in messages)
                          for call in calls)
    return {'originalObservationsPreserved':original_preserved,'verifierObserved':verifier_read,'exitCode':code,'timedOut':timed_out,'interrupted':interrupted,'seconds':round(time.monotonic()-started,2),
            **({('policyOrigin' if capture_policy_origin else 'commandOrigin'):command_origin} if command_origin is not None else {}),
            **({'sessionCaptureError':session_capture_error} if session_capture_error else {}),
            **({'commandSessionContinuation':{'priorSessionDigest':prior_session_digest,'priorEntryCount':prior_count,
                'newEntryCount':len(rows),'usageAttributionVerified':original_preserved and copied.returncode==0 and malformed_rows==0}} if prior_session_digest is not None else {}),
            'temporaryInstructionLeaked':label not in ('stage-1',) and any('TEMPORARY_IDLE_REVIEW' in str(part.get('text','')) for m in messages[-1:] for part in (m.get('content',[]) if isinstance(m.get('content'),list) else []) if isinstance(part,dict)),
            'modelErrors':sum(m.get('stopReason')=='error' for m in messages),'modelAborted':sum(m.get('stopReason')=='aborted' for m in messages),'malformedSessionRows':malformed_rows,
            'toolCalls':sum(len([part for part in m.get('content',[]) if isinstance(part,dict) and part.get('type')=='toolCall']) for m in messages if isinstance(m.get('content'),list)),
            'usage':{k:sum(u.get(k,0) for u in usage) for k in ('input','output','cacheRead','cacheWrite','totalTokens')},
            'reportedCost':sum(u.get('cost',{}).get('total',0) for u in usage),
            'exposedMemoryReferences':len(references),
            'deliveredMemoryEntries':[item for row in references for item in row.get('details',{}).get('retrieved',[])],
            'observedMemoryReads':observed_memory_reads(rows,cwd='/work/p-limit',home='/home/node',roots=(base.AGENT+'/memory/--work-p-limit--','/work/p-limit/.memory')),
            **task_deadline_evidence(rows,required=unlimited_budget and not command),
            **({'sourceTaskBoundary':source_task_boundary} if source_task_boundary is not None else {}),
            'toolBudgetEvents':[r.get('data') for r in rows if r.get('customType')=='continuous-study-tool-budget'],
            'verifierReadBoundaryViolations':sum(r.get('customType')=='continuous-study-tool-budget' and r.get('data',{}).get('outcome')=='verifier-read-blocked' for r in rows),
            'toolBudgetExceeded':any(r.get('customType')=='continuous-study-tool-budget' and r.get('data',{}).get('outcome') in ('blocked','summary-tool-loop-stopped') for r in rows),
            'harnessEvents':[r for r in rows if str(r.get('customType','')).startswith('harness-')],
            'attemptedVersionProbeCalls':[part for m in messages if isinstance(m.get('content'),list) for part in m['content'] if isinstance(part,dict) and part.get('type')=='toolCall' and part.get('name')=='bash' and 'npm --version' in str(part.get('arguments',{}))],
            'executedVersionProbes':executed_version_probes(messages)}




def public_failure_check(c: str, proxy: InferenceProxy, output: Path) -> dict:
    """Run the fixed public diagnostic without changing existing check settings."""
    result = base.process(['docker', 'exec', '-w', '/work/p-limit', c,
                           'node', 'observed-idle-failure.mjs'], timeout=30)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'public-reproducer.log').write_bytes(redact_transport_bytes(result.stdout + result.stderr, proxy))
    return {'passed': result.returncode == 0, 'exitCode': result.returncode}


def capture_failure_candidate(c: str, proxy: InferenceProxy, output: Path, session: bytes) -> dict:
    """Retain the own candidate before any canonical-source import."""
    if redact_transport_bytes(session, proxy) != session:
        raise RuntimeError('Sensitive native transport evidence blocks external audit')
    filtered = lambda values: {key: value for key, value in values.items()
                              if key != '__configuration_paths__' and not key.startswith(('.memory/', '.pi/'))}
    before = filtered(base.protected(c, 'p-limit', include_source=True))
    raw = source_archive(c)
    files = source_archive_files(raw)
    after = filtered(base.protected(c, 'p-limit', include_source=True))
    if before != after or {name: item['sha256'] for name, item in files.items()} != before:
        raise RuntimeError('Complete source candidate changed during capture')
    if any(redact_transport_bytes(item['data'], proxy) != item['data'] for item in files.values()):
        raise RuntimeError('Sensitive source content blocks external audit')
    sources = {name: item['data'].decode('utf-8') for name, item in files.items()}
    manifest = {'phase': 'post-main-before-source-convergence', 'canonicalImportApplied': False,
                'sourceHashes': before, 'archiveSha256': hashlib.sha256(raw).hexdigest(),
                'sessionSha256': hashlib.sha256(session).hexdigest(),
                'files': {name: {key: item[key] for key in ('sha256', 'mode', 'size')} for name, item in files.items()}}
    (output / 'candidate-before-convergence.tar.gz').write_bytes(raw)
    (output / 'candidate-before-convergence.json').write_text(json.dumps(manifest, indent=2))
    return {'sources': sources, 'manifest': manifest}


def run_memory_audit(c: str, proxy: InferenceProxy, payload: dict, output: Path) -> dict:
    """Use the existing audit SDK and service transport; never supply task answers."""
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode()
    if redact_transport_bytes(raw, proxy) != raw:
        raise RuntimeError('Sensitive native transport evidence blocks external audit')
    output.mkdir(parents=True, exist_ok=True)
    file = '/home/node/memory-audit.json'
    (output / 'input.json').write_bytes(raw)
    base.put(c, file, raw)
    args = ['docker', 'exec']
    for key, value in proxy.jev_environment().items():
        args += ['-e', key + '=' + value]
    args += [c, 'tsx', '/home/node/continuous-memory-audit.mts', file]
    try:
        result = json.loads(base.checked(args))
        (output / 'result.json').write_text(json.dumps(result, indent=2))
        return result
    finally:
        base.shell(c, 'rm -f ' + file)


def install_memory_audit_runtime(c: str) -> None:
    """Install only the explicit read-only audit entrypoint and its shared adapter."""
    for name in ('continuous-memory-audit.ts','continuous-command-proof.ts'):
        source=Path(__file__).with_name(name).read_text()
        for extension in ('jev-sdk','jev-learning','learning-replay-feedback','planner-read-scope','incremental-learning','learning-efficiency','learning-backlog','guardrail-engine'):
            source=source.replace("'../extensions/"+extension+"'", "'/opt/experiment/packages/continual-learning/extensions/"+extension+".ts'")
        for support in ('failure-observation-proof','continuous-command-proof'):
            source=source.replace("'./"+support+"'", "'./"+support+".mts'")
        base.put(c,'/home/node/'+name.removesuffix('.ts')+'.mts',source.encode())


def native_initialization_proof(c: str, name: str, evidence: dict, prior: dict, current: dict) -> dict:
    """Run the shared read-only proof in this owner's installed Pi runtime.

    The container comes from the parent caller, never from archived evidence.
    A frozen host needs no ambient TypeBox, Pi CLI or TUI dependencies.
    """
    if name not in ('automaticHarnessPolicyProof','commandMemoryCorpusProof') or evidence.get('owner',{}).get('container')!=c:
        raise ValueError('Unknown proof or foreign native container')
    runtime_version=base.checked(['docker','exec',c,'node',base.PI,'--version']).decode().strip()
    if runtime_version not in ('1.3.0','1.4.0'):raise ValueError('Unsupported actual initialization proof Pi version')
    file='/home/node/native-initialization-proof-'+uuid.uuid4().hex+'.json'
    module=file.removesuffix('.json')+'.mts'
    payload=json.dumps({'input':evidence,'prior':prior,'current':current,**({'runtimeVersion':runtime_version} if runtime_version else {})},ensure_ascii=False).encode()
    create='''import os,sys
fd=os.open(sys.argv[1],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
try:
    with os.fdopen(fd,"wb") as file:
        file.write(sys.stdin.buffer.read())
except BaseException:
    try: os.close(fd)
    except OSError: pass
    try: os.unlink(sys.argv[1])
    except OSError: sys.stderr.write("Owned proof input cleanup failed\\n")
    raise
'''
    base.checked(['docker','exec','-i',c,'python3','-c',create,file],data=payload)
    module_created=False
    try:
        code="import fs from 'node:fs';import {"+name+" as check} from '/home/node/continuous-command-proof.mts';const x=JSON.parse(fs.readFileSync("+json.dumps(file)+",'utf8'));console.log(JSON.stringify(check(x.input,x.prior,x.current"+(",x.runtimeVersion" if runtime_version else "")+")));"
        base.checked(['docker','exec','-i',c,'python3','-c',create,module],data=code.encode())
        module_created=True
        return json.loads(base.checked(['docker','exec',c,'tsx',module],timeout=60))
    finally:
        base.checked(['docker','exec',c,'rm','-f','--',file,*([module] if module_created else [])])


def install_failure_observation_proof(c: str) -> str:
    """Install read-only parent verification outside the task source/agent roots."""
    for name in ('failure-observation-proof.ts','failure-observation-proof-cli.ts'):
        source=Path(__file__).with_name(name).read_text()
        source=source.replace('"../extensions/', '"/opt/experiment/packages/continual-learning/extensions/')
        source=source.replace('"@earendil-works/pi-coding-agent"',
                              '"/opt/experiment/node_modules/@earendil-works/pi-coding-agent/dist/index.js"')
        source=source.replace('"./failure-observation-proof"','"./failure-observation-proof.mts"')
        base.put(c,'/home/node/'+name.removesuffix('.ts')+'.mts',source.encode())
    return '/home/node/failure-observation-proof-cli.mts'


def failure_observation_ready(c: str, original_session: bytes, observation: dict, feedback: dict, source_after: dict, *, retain_input: bool = False) -> dict:
    """Prove actual feedback evidence, without accepting the failed task itself."""
    queued=feedback.get('queuedFailure')
    if not queued:return {'ready':False,'reason':'no-pending-failure'}
    proof_cli=install_failure_observation_proof(c)
    input_file='/home/node/failure-observation-proof-input.json'
    value={'originalSession':original_session.decode(),'currentSession':'',
           'verifierText':json.dumps(observation,ensure_ascii=False,indent=2),
           'verifierPath':'/home/node/project-verification.json',
           'sourceBefore':observation['sourceHashes'],'sourceAfter':source_after,
           'queued':queued,'explicitBackfills':0,
           'observationOutcome':'blocked-before-read' if feedback.get('verifierReadBoundaryViolations')==1 else 'successful' if feedback.get('taskPassed') is True else 'failed'}
    base.put(c,input_file,json.dumps(value,ensure_ascii=False).encode())
    try:
        proof=json.loads(base.checked(['docker','exec',c,'tsx',proof_cli,input_file]))
        if retain_input and proof.get('ready') is True:
            raw=base.checked(['docker','exec',c,'cat',queued['sessionFile']])
            if hashlib.sha256(raw).hexdigest()!=proof.get('sessionDigest'):
                raise RuntimeError('Native feedback changed after its observation proof')
            proof['nativeEvidence']={**value,'currentSession':raw.decode('utf-8')}
        return proof
    finally:base.shell(c,'rm -f '+input_file)


def artifacts(c: str, proxy: InferenceProxy, output: Path, *, source_review: bool = False,
              command_origin: tuple[Path,dict] | None = None, policy_origin: tuple[Path,dict] | None = None) -> dict:
    if (command_origin is not None or policy_origin is not None) and not source_review:raise ValueError('Native origin review requires complete source artifacts')
    if command_origin is not None and policy_origin is not None:raise ValueError('Ambiguous native review origin')
    output.mkdir(parents=True,exist_ok=True)
    # Runtime images deliberately omit all tests and hidden task probes.
    base.put(c,'/home/node/learned-surface-metadata.py',Path(__file__).with_name('recovery_integrity.py').read_bytes())
    metadata_args=['docker','exec',c,'python3','/home/node/learned-surface-metadata.py',
                   base.AGENT+'/memory/--work-p-limit--','/work/p-limit']
    metadata_before=json.loads(base.checked(metadata_args))
    base.export_tree(c,base.AGENT+'/memory',output/'memory.tar.gz',proxy)
    base.export_tree(c,base.AGENT+'/learning',output/'backlog.tar.gz',proxy)
    base.export_tree(c,'/work/p-limit',output/'source.tar.gz',proxy)
    metadata_after=json.loads(base.checked(metadata_args))
    if metadata_before!=metadata_after:raise RuntimeError('Learned surfaces changed during artifact capture')
    surface_snapshots=archive_surface_snapshots(output/'memory.tar.gz',output/'source.tar.gz',metadata_after)
    probe="import {backlogStatus,readBacklog,backlogIdentity} from '/opt/experiment/packages/continual-learning/extensions/learning-backlog.ts';const read=readBacklog('/work/p-limit','/home/node/agent');console.log(JSON.stringify({...backlogStatus('/work/p-limit','/home/node/agent'),pendingEntries:read.pendingEntries.map(({entry})=>({...entry,id:backlogIdentity('--work-p-limit--',entry)}))}));"
    base.put(c,'/home/node/backlog-probe.mts',probe.encode())
    backlog=json.loads(base.checked(['docker','exec',c,'tsx','/home/node/backlog-probe.mts']))
    base.shell(c,'rm -f /home/node/backlog-probe.mts')
    receipts=[];states=[];memory_entries=[];history=[];dossiers=[];completed_backlog={};partial_worker_usage=[];raw_dossiers=[];retained_ranges=[];source_files={}
    for filename in ('memory.tar.gz','backlog.tar.gz'):
        with tarfile.open(output/filename) as archive:
            for item in archive:
                if source_review and filename=='memory.tar.gz' and Path(item.name).parts[:2]==('runs','--work-p-limit--') and item.name.endswith(('.json','.jsonl')):
                    key=str(Path(item.name))
                    if (Path(item.name).is_absolute() or '..' in Path(item.name).parts or '\\' in item.name
                            or Path(item.name).name in ('cost-ledger.jsonl','authorized-real-study-budget-600.json','600-active-reservation.json')
                            or not item.isfile() or item.sparse or item.size>32*1024*1024 or key in source_files):
                        raise RuntimeError('Source review artifact is unsafe or ambiguous')
                    body=archive.extractfile(item).read(item.size+1)
                    if len(body)!=item.size:raise RuntimeError('Source review artifact is incomplete')
                    source_files[key]=body.decode('utf-8')
                if filename=='backlog.tar.gz' and Path(item.name).parts==('backlog.jsonl',):
                    if not item.isfile():raise RuntimeError('Original backlog range archive is not regular')
                    for line in archive.extractfile(item).read().splitlines():
                        row=json.loads(line)
                        if not isinstance(row,dict):raise RuntimeError('Invalid original backlog range record')
                        if row.get('scopeKey')!='--work-p-limit--':continue
                        start,end=row.get('from'),row.get('to');digest=row.get('digest')
                        if (row.get('version')!=1 or type(start) is not int or type(end) is not int
                                or start<0 or end<start or not isinstance(digest,str)
                                or re.fullmatch(r'[a-f0-9]{64}',digest) is None):
                            raise RuntimeError('Invalid scoped original backlog range')
                        retained_ranges.append({key:row[key] for key in ('from','to','digest')})
                    continue
                if not item.isfile():continue
                if filename=='memory.tar.gz' and Path(item.name).parent.name=='--work-p-limit--' and item.name.endswith('.md') and Path(item.name).name!='MEMORY.md':
                    data=archive.extractfile(item).read();memory_entries.append({'filename':Path(item.name).name,'revision':hashlib.sha256(data).hexdigest(),'content':data.decode()})
                if not item.name.endswith('.json'):continue
                try: value=json.loads(archive.extractfile(item).read())
                except (ValueError,UnicodeError):continue
                if not isinstance(value,dict):continue
                if re.fullmatch(r'(?:harness-(?:task|repair)|memory-(?:task|repair|body)|source-audit)-usage.*\.json', Path(item.name).name) and isinstance(value.get('ledgerId'),str):
                    usage=value.get('knownUsage',{})
                    if isinstance(usage,dict) and all(isinstance(usage.get(k), (int,float)) and not isinstance(usage.get(k),bool) and 0<=usage[k]<float('inf') for k in ('input','output','cacheRead','cacheWrite','totalTokens','cost')):
                        partial_worker_usage.append({'archive':filename,'path':item.name,**value})
                if (filename=='memory.tar.gz' and Path(item.name).parts[:2]==('runs','--work-p-limit--')
                        and Path(item.name).name=='learning-pipeline-receipt.json'
                        and value.get('kind')=='learning-pipeline-receipt'):receipts.append(value)
                if value.get('version')==1 and isinstance(value.get('changes'),list) and value.get('phase') in ('memory','harness','agents'):history.append(value)
                if Path(item.name).name=='backlog-completed.json':completed_backlog.update(value)
                if value.get('kind')=='incremental-learning-dossier':
                    raw_dossiers.append(value['taskSlice'])
                if Path(item.name).name.startswith('replay-'):states.append(value)
    # Per-job ledger preserves repeated and failed attempts; receipts elsewhere
    # can duplicate these and are retained separately rather than added twice.
    attempts=[a for state in states for a in state.get('attempts',[])]
    # Use the same JavaScript serialization as the production acknowledgment.
    receipt_values = [a.get('receipt') for a in attempts]
    ranges = [coverage for receipt in receipt_values if receipt
              for coverage in receipt.get('input', {}).get('backlogCoverage', [])]
    ranges += [receipt['input']['backlogRange'] for receipt in receipt_values if receipt
               and isinstance(receipt.get('input',{}).get('backlogRange'),dict)]
    ranges += retained_ranges + backlog.get('pendingEntries', [])
    base.put(c,'/home/node/study-receipts.json',json.dumps({'receipts':receipt_values,'dossiers':raw_dossiers,'ranges':ranges}).encode())
    digest_script = Path(__file__).with_name('continuous-dossier-proof.mjs').read_text() + "\n" + (
        "import fs from 'node:fs';const input=JSON.parse(fs.readFileSync('/home/node/study-receipts.json','utf8'));"
        "console.log(JSON.stringify({receiptDigests:input.receipts.map(r=>r?dossierDigest(r):null),"
        "dossiers:input.dossiers.map(task=>summarizeDossier(task,input.ranges))}));")
    proofs=json.loads(base.checked(['docker','exec',c,'node','--input-type=module','-e',digest_script]))
    digests=proofs['receiptDigests'];dossiers=proofs['dossiers']
    base.shell(c,'rm -f /home/node/study-receipts.json')
    for attempt,digest in zip(attempts,digests):attempt['receiptDigest']=digest
    receipts=deduplicate_receipt_views(receipts)
    accounting = learning_cost_summary(receipts, attempts, partial_worker_usage)
    source_reviews=source_review_bindings(source_files,raw_dossiers,attempts) if source_review else []
    command_review=None;command_held=False
    if command_origin is not None:
        try:command_review=command_review_input(command_origin[0],command_origin[1],source_files,container=c)
        except UnappliedMemoryCommand:command_held=True
    policy_review=(policy_review_input(policy_origin[0],policy_origin[1],source_files,container=c)
                   if policy_origin is not None else None)
    return {'surfaceSnapshots':surface_snapshots,'memoryEntries':memory_entries,'history':history,'dossiers':dossiers,'completedBacklog':completed_backlog,'receipts':receipts,'attempts':attempts,**({'sourceReviewBindings':source_reviews}if source_review else {}),**accounting,
            **({'commandReviewInput':command_review} if command_review is not None else {}),
            **({'commandInitializationHeld':True} if command_held else {}),
            **({'policyReviewInput':policy_review} if policy_origin is not None else {}),
            'pendingLearningJobs':backlog['pending'],'backlogStatus':backlog}



def load_command_origin(output: Path, inference: dict, *, container: str, policy: bool = False, expected_pi_version: str | None = None) -> dict:
    """Load an exclusive owner's bound output; hashes alone do not prove who ran it."""
    if expected_pi_version is not None and expected_pi_version not in ('1.3.0','1.4.0'):
        raise ValueError('Unsupported expected native Pi version')
    origin=inference.get('policyOrigin' if policy else 'commandOrigin',{})
    names=POLICY_ORIGIN_ARTIFACTS if policy else COMMAND_ORIGIN_ARTIFACTS
    owner_name='policy-started.json' if policy else 'memory-command-started.json'
    closed_name='policy-closed.json' if policy else 'memory-command-closed.json'
    bindings=origin.get('artifactBindings')
    if (origin.get('verified') is not True or origin.get('sourceInventoryVerified') is not True
            or not isinstance(bindings,dict) or set(bindings)!=set(names)):
        raise ValueError('Incomplete native command artifact bindings')
    raw={name:read_study_artifact(output,name,bound=32*1024*1024,expected=bindings[name]) for name in names}
    owner=json.loads(raw[owner_name]);closed=json.loads(raw[closed_name])
    original=raw['original-session.jsonl'];native=raw['session.jsonl'];stdout=raw['stdout.jsonl']
    if (owner.get('container')!=container or owner.get('cwd')!='/work/p-limit' or policy and owner.get('piVersion')!='1.3.0'
            or owner.get('kind')!=('native-automatic-harness-policy' if policy else 'native-memory-command')
            or closed.get('ownerDigest')!=hashlib.sha256(raw[owner_name]).hexdigest()
            or closed.get('exitCode')!=0 or closed.get('cancelled') is not False or closed.get('timedOut') is not False
            or closed.get('sourceInventoryVerified') is not True
            or closed.get('sessionDigest')!=hashlib.sha256(native).hexdigest()
            or closed.get('stdoutDigest')!=hashlib.sha256(stdout).hexdigest() or not native.startswith(original)):
        raise ValueError('Changed actual command invocation')
    if not policy:
        actual_version=base.checked(['docker','exec',container,'node',base.PI,'--version']).decode().strip()
        if (actual_version not in ('1.3.0','1.4.0') or owner.get('piVersion')!=actual_version
                or expected_pi_version is not None and actual_version!=expected_pi_version):
            raise ValueError('Actual native Memory runtime version does not match command owner')
    if policy:
        if original:raise ValueError('Policy task was not a fresh native session')
        count=0
    else:count=command_session_prefix_count(original,owner['priorSessionDigest'],'/work/p-limit')
    source_values=[]
    for phase in ('before','after'):
        prefix='command-source-'+phase+'/candidate-before-convergence'
        manifest=json.loads(raw[prefix+'.json']);archive=raw[prefix+'.tar.gz'];files=source_archive_files(archive)
        metadata={name:{key:value[key] for key in ('sha256','mode','size')} for name,value in files.items()}
        hashes={name:value['sha256'] for name,value in files.items()}
        if (hashlib.sha256(archive).hexdigest()!=manifest.get('archiveSha256') or metadata!=manifest.get('files')
                or hashes!=manifest.get('sourceHashes') or hashes!=owner.get('sourceHashes')
                or hashes!=closed.get('sourceHashes')):raise ValueError('Incomplete or changed command source')
        if (policy or 'sourceFiles' in owner) and (metadata!=owner.get('sourceFiles') or metadata!=closed.get('sourceFiles')):
            raise ValueError('Changed actual policy source inventory')
        source_values.append((metadata,{name:value['data'].decode('utf-8')for name,value in files.items()}))
    if source_values[0]!=source_values[1]:raise ValueError('Command changed source bytes or modes')
    if not native.endswith(b'\n'):raise ValueError('Incomplete command native session')
    rows=[json.loads(line)for line in native.decode().splitlines()]
    receipts=[row['details'] for row in rows[count:] if row.get('type')=='custom_message'
              and row.get('customType')=='continual-learning-result']
    if len(receipts)!=1:raise ValueError('Missing unique command-native receipt')
    return {'kind':'automatic-harness-policy-review' if policy else 'explicit-command-source-review','version':1,'owner':owner,'completion':closed,
            'originalSession':original.decode(),'nativeSession':native.decode(),'stdout':stdout.decode(),
            'sources':source_values[1][1],'receipt':receipts[0]}


def _review_artifact_values(source_files: dict[str,str]) -> dict:
    """Decode only complete scoped source-review artifacts, before selection."""
    allowed=('runs','--work-p-limit--');values={}
    for name,body in source_files.items():
        key=Path(name)
        if (key.is_absolute() or '..'in key.parts or '\\'in name or key.parts[:2]!=allowed
                or str(key)!=name or any(part in ('cost-ledger.jsonl','authorized-real-study-budget-600.json','600-active-reservation.json') for part in key.parts)
                or not isinstance(body,str) or len(body.encode())>32*1024*1024):raise ValueError('Unsafe command source artifact')
        if key.suffix=='.json':values[name]=json.loads(body)
    return values


def command_review_input(output: Path, inference: dict, source_files: dict[str,str], *, container: str) -> dict:
    """Bind direct source/repair artifacts to the actual native command owner."""
    origin=load_command_origin(output,inference,container=container);receipt=origin['receipt']
    applied=[a for a in receipt.get('attempts',[]) if a.get('phase')=='memory' and a.get('outcome')=='applied' and a.get('operations',0)>0]
    if not applied:raise UnappliedMemoryCommand('Missing unique applied Memory command')
    if len(applied)!=1 or applied[0].get('attempt')not in (0,1):raise ValueError('Missing unique applied Memory command')
    values=_review_artifact_values(source_files)
    ledgers=[(name,value)for name,value in values.items() if isinstance(value,dict) and value.get('ledgerId')==applied[0].get('usageLedgerId')
             and (Path(name).name=='memory-task-usage.json' if applied[0]['attempt']==0
                  else Path(name).name=='memory-repair-usage-'+applied[0]['usageLedgerId']+'.json')]
    if len(ledgers)!=1:raise ValueError('Missing unique actual generation ledger')
    ledger_name,ledger=ledgers[0];root=str(Path(ledger_name).parent)
    required={key:root+'/'+key for key in ('manifest.json','plan.json','snapshot.json','memory-task-usage.json')}
    if any(name not in source_files for name in required.values()):raise ValueError('Incomplete actual command run')
    manifest=values[required['manifest.json']]
    if not isinstance(manifest,dict) or manifest.get('runDir')!=base.AGENT+'/memory/'+root:raise ValueError('Foreign command run root')
    audit_ids={a.get('usageLedgerId')for a in receipt['attempts']if a.get('phase')=='memory' and a.get('attempt')==0 and a.get('operations')==0}
    audits=[name for name,value in values.items() if isinstance(value,dict) and Path(name).name=='receipt.json'
            and Path(name).parent.name.startswith('maintenance-audit-') and value.get('usageLedgerId')in audit_ids]
    if len(audits)!=1:raise ValueError('Missing unique command source collector')
    audit=audits[0];directory=str(Path(audit).parent);observations=directory+'/observations.jsonl';usage=directory+'/source-audit-usage.json'
    if (observations not in source_files or not isinstance(values.get(usage),dict)
            or not isinstance(values[required['memory-task-usage.json']],dict)
            or not isinstance(values[required['plan.json']],dict)):
        raise ValueError('Incomplete source collector evidence')
    return {**origin,'plan':values[required['plan.json']],'snapshotText':source_files[required['snapshot.json']],
        'reviewManifest':manifest,'usageLedger':ledger,'initialUsageLedger':values[required['memory-task-usage.json']],
        'appliedUsageLedgerFile':Path(ledger_name).name,'sourceAudit':{'receipt':values[audit],
            'usageLedger':values[usage],'observations':[json.loads(line)for line in source_files[observations].splitlines()]}}



def policy_review_input(output: Path, inference: dict, source_files: dict[str,str], *, container: str) -> dict:
    """Bind one actual automatic policy generation; never infer a replay owner."""
    origin=load_command_origin(output,inference,container=container,policy=True);receipt=origin['receipt']
    applied=[a for a in receipt.get('attempts',[]) if a.get('phase')=='harness' and a.get('outcome')=='applied' and a.get('operations')==1]
    if len(applied)!=1 or applied[0].get('attempt')not in (0,1) or not isinstance(applied[0].get('usageLedgerId'),str):
        raise ValueError('Missing unique actual Harness policy generation')
    values=_review_artifact_values(source_files)
    filename='harness-task-usage.json' if applied[0]['attempt']==0 else 'harness-repair-usage-'+applied[0]['usageLedgerId']+'.json'
    ledgers=[(name,value)for name,value in values.items() if isinstance(value,dict)
             and value.get('ledgerId')==applied[0]['usageLedgerId'] and Path(name).name==filename]
    if len(ledgers)!=1:raise ValueError('Missing unique policy generation ledger')
    name,ledger=ledgers[0];root=str(Path(name).parent)
    required={key:root+'/'+key for key in ('manifest.json','snapshot.json','harness-post-receipt.json','harness-task-usage.json')}
    if any(key not in source_files for key in required.values()):raise ValueError('Incomplete actual policy generation')
    manifest=values[required['manifest.json']]
    if not isinstance(manifest,dict) or manifest.get('runDir')!=base.AGENT+'/memory/'+root:raise ValueError('Foreign policy run root')
    return {**origin,'reviewManifest':manifest,'snapshotText':source_files[required['snapshot.json']],
            'postReceipt':values[required['harness-post-receipt.json']],'usageLedger':ledger,
            'usageLedgerPath':base.AGENT+'/memory/'+name,
            'initialUsageLedger':values[required['harness-task-usage.json']],
            'initialUsageLedgerPath':base.AGENT+'/memory/'+required['harness-task-usage.json']}


def run_command_initialization(c: str, proxy: InferenceProxy, output: Path, label: str, *, prior: dict,
                               observation: dict, sources: dict[str,str], original_session: bytes,
                               protocol: dict, row: dict) -> dict:
    """Execute one command plus optional processing-only closure, retaining all calls.

    The independent audit uses the actual post-closure state, never a fabricated
    command endpoint. A failed or held generation is not retried here.
    """
    calls=row.setdefault('initializationCalls',[])
    def invoke(prompt: str, directory: str, session_label: str, **options) -> dict:
        jev_start=len(proxy.jev_usage);requests_start=proxy.requests
        result={'initializationStep':directory,'exitCode':None,'usage':{'totalTokens':0},'reportedCost':0,'seconds':0}
        calls.append(result)
        started=time.monotonic()
        try:
            result.update(run_session(c,prompt,proxy,output/directory,session_label,command=True,unlimited_budget=True,**options))
        except BaseException as error:
            result.update(errorType=type(error).__name__,seconds=round(time.monotonic()-started,2))
            if proxy.requests>requests_start or len(proxy.jev_usage)>jev_start:
                result['sessionCaptureError']='initialization-call-exception'
            raise
        finally:
            result['jevUsage']=proxy.jev_usage[jev_start:];result['allTransportRequests']=proxy.requests-requests_start
        if not task_outcome(result,{'passed':True})['passed']:
            raise RuntimeError('Initialization call failed; no dependent policy or retry')
        return result
    command_dir=output/'memory-command'
    command=invoke('/memory 整理记忆','memory-command',label,
        prior_session_digest=hashlib.sha256(original_session).hexdigest(),capture_command_origin=True)
    state=artifacts(c,proxy,output/'after-memory-command',source_review=True,command_origin=(command_dir,command))
    row['learning']=state
    row['commandState']=state
    if state.get('commandInitializationHeld') is True:
        row.update(validLearning=False,validPairInput=False,
            initializationBlocked={'phase':'memory-command-held','dependentPolicyStarted':False})
        raise RuntimeError('Memory command remains held; no closure, policy or dependent task')
    command_evidence=state['commandReviewInput']
    if state['pendingLearningJobs']:
        queued=state['backlogStatus'].get('pendingEntries',[])
        session_path=base.AGENT+'/sessions/continuous/'+label+'.jsonl'
        if not queued or any(entry.get('sessionFile')!=session_path for entry in queued):
            raise RuntimeError('Initialization closure contains a foreign source task')
        before_source=base.protected(c,'p-limit',include_source=True)
        closure=invoke('/consolidate backfill','source-closure',label,
            prior_session_digest=hashlib.sha256(command_evidence['nativeSession'].encode()).hexdigest())
        state_after=artifacts(c,proxy,output/'after-source-closure',source_review=True,command_origin=(command_dir,command))
        row['closureState']=state_after
        row['learning']=state_after
        source_filter=lambda data:{key:value for key,value in data.items()
            if key!='__configuration_paths__' and not key.startswith(('.memory/','.pi/'))}
        closure['taskSourceUnchanged']=source_filter(before_source)==source_filter(base.protected(c,'p-limit',include_source=True))
        proof=initialization_closure_ready(state,state_after,command_evidence['nativeSession'].encode(),session_path)
        row['sourceClosure']={**proof,'taskSourceUnchanged':closure['taskSourceUnchanged']}
        if not proof['ready'] or not closure['taskSourceUnchanged']:
            raise RuntimeError('Initialization closure changed knowledge or source, or left pending work')
        state=state_after
    else:row['sourceClosure']={'ready':True,'required':False,'countedAsLearning':False}
    payload=command_initialization_audit_input(prior,state,observation,sources,original_session,protocol,command_evidence)
    row['commandInitializationRecord']=payload
    audit=run_memory_audit(c,proxy,payload,output/'command-initialization-audit')
    row['commandInitializationAudit']=audit
    if audit.get('passed') is not True:raise RuntimeError('Command initialization semantic review did not pass')
    return state


def run_initial_policy(c: str, proxy: InferenceProxy, output: Path, *, prior: dict, row: dict, enabled: bool) -> dict:
    """Run the same original-user no-tools policy task in both independent arms."""
    settings={'autoMemory':enabled,'automaticPhases':{'memory':'off','harness':'apply' if enabled else 'off','agents':'off'}}
    base.put(c,base.AGENT+'/memory/settings.json',json.dumps(settings).encode())
    call={'initializationStep':'automatic-policy','exitCode':None,'usage':{'totalTokens':0},'reportedCost':0,'seconds':0}
    row.setdefault('initializationCalls',[]).append(call)
    requests=proxy.requests;jev=len(proxy.jev_usage);started=time.monotonic()
    try:
        call.update(run_session(c,INITIAL_HARNESS_POLICY,proxy,output/'policy-task','initial-policy',
            unlimited_budget=True,capture_policy_origin=True))
    except BaseException as error:
        call.update(errorType=type(error).__name__,seconds=round(time.monotonic()-started,2))
        if proxy.requests>requests or len(proxy.jev_usage)>jev:call['sessionCaptureError']='policy-call-exception'
        raise
    finally:
        call['allTransportRequests']=proxy.requests-requests;call['jevUsage']=proxy.jev_usage[jev:]
    if not task_outcome(call,{'passed':True})['passed']:raise RuntimeError('Initial policy task failed; no dependent task')
    state=artifacts(c,proxy,output/'after-policy',source_review=enabled,
        **({'policy_origin':(output/'policy-task',call)} if enabled else {}))
    row['learning']=state
    if enabled:
        bridge=policy_initialization_bridge(prior,state,state['policyReviewInput'],source_files=prior['commandReviewInput']['owner']['sourceFiles'],
            native_runner=lambda name,evidence,before,after:native_initialization_proof(c,name,evidence,before,after))
        row['initialPolicyBridge']=bridge
        (output/'initial-policy-bridge.json').write_text(json.dumps(bridge,ensure_ascii=False,indent=2))
    elif any(prior[key]!=state[key] for key in ('surfaceSnapshots','memoryEntries','history','attempts','receipts')):
        raise RuntimeError('Control policy acquired or changed learned state')
    return state

def source_review_bindings(source_files: dict[str,str], raw_dossiers: list[dict], attempts: list[dict]) -> list[dict]:
    """Retain complete archived inputs for the shared native validator."""
    source_reviews=[]
    for name,raw in source_files.items():
        if Path(name).name!='plan.json':continue
        root=str(Path(name).parent)
        required=['snapshot.json','manifest.json','memory-task-usage.json']
        # Generation runs refer to the selector's immutable dossier, while
        # their own snapshot and usage ledger remain run-local.
        if any(root+'/'+key not in source_files for key in required):continue
        plan=json.loads(raw);manifest=json.loads(source_files[root+'/manifest.json']);ledger=json.loads(source_files[root+'/memory-task-usage.json'])
        matching=[a for a in attempts if a.get('outcome')=='completed' and any(t.get('usageLedgerId')==ledger.get('ledgerId') for t in a.get('receipt',{}).get('attempts',[]))]
        for attempt in matching:
            receipt=attempt['receipt']
            audit_ids={t.get('usageLedgerId') for t in receipt.get('attempts',[]) if t.get('phase')=='memory' and t.get('attempt')==0 and t.get('operations')==0}
            audits=[key for key,value in source_files.items() if Path(key).name=='receipt.json' and Path(key).parent.name.startswith('maintenance-audit-') and json.loads(value).get('usageLedgerId') in audit_ids]
            if len(audits)!=1:continue
            audit=audits[0];observations=str(Path(audit).parent/'observations.jsonl');source_usage=str(Path(audit).parent/'source-audit-usage.json')
            if observations not in source_files or source_usage not in source_files:continue
            snapshot=json.loads(source_files[root+'/snapshot.json'])
            tasks=[task for task in raw_dossiers if task.get('entries')==snapshot.get('entries')]
            if len(tasks)!=1:continue
            source_reviews.append({'receiptDigest':attempt['receiptDigest'],'receipt':receipt,'plan':plan,
                'snapshotText':source_files[root+'/snapshot.json'],'reviewManifest':manifest,'usageLedger':ledger,
                'taskSlice':tasks[0],'sourceAudit':{'receipt':json.loads(source_files[audit]),
                    'usageLedger':json.loads(source_files[source_usage]),
                    'observations':[json.loads(line)for line in source_files[observations].splitlines()if line]}})
    return source_reviews


def harness_probe(c: str, stage: int, enabled: bool) -> dict:
    script = """import {resolveHarnessConfig} from '/opt/experiment/packages/continual-learning/extensions/guardrail-config.ts';
import {evaluateBash,ruleRevision,validateRuleDeclaration} from '/opt/experiment/packages/continual-learning/extensions/guardrail-engine.ts';
import fs from 'node:fs';import {createHash} from 'node:crypto';
const {config}=resolveHarnessConfig('/work/p-limit','/home/node/agent');
const raw=fs.existsSync('/work/p-limit/.pi/harness.json')?fs.readFileSync('/work/p-limit/.pi/harness.json'):undefined;
const document=raw?JSON.parse(raw.toString()):{};
const documentDigest=raw?createHash('sha256').update(raw).digest('hex'):null;
const ownedRevisions=Object.fromEntries((document.rules??[]).filter(rule=>typeof rule.id==='string' && rule.id.length<=128 && validateRuleDeclaration(rule).length===0 && document.learnedRules?.[rule.id]?.origin==='consolidation' && document.learnedRules[rule.id].revision===ruleRevision(rule)).map(rule=>[rule.id,document.learnedRules[rule.id].revision]));
const commands=['npm --version','npm test','pnpm test','printf npm test'];
console.log(JSON.stringify({document,documentDigest,ownedRevisions,errors:config.errors,rules:config.rules,decisions:Object.fromEntries(commands.map(command=>[command,evaluateBash(config,command).decision]))}));"""
    base.put(c,'/home/node/harness-probe.mts',script.encode())
    result=json.loads(base.checked(['docker','exec',c,'tsx','/home/node/harness-probe.mts']))
    base.shell(c,'rm -f /home/node/harness-probe.mts')
    expected={'npm --version':'block' if enabled and stage<2 else 'execute',
              'npm test':'block' if enabled and stage<3 else 'execute','pnpm test':'execute','printf npm test':'execute'}
    result['expected']=expected;result['passed']=not result['errors'] and result['decisions']==expected
    return result


def totals(report: dict) -> dict:
    result={}
    for arm in ('without-learning','with-learning'):
        rows=[stage['arms'][arm] for stage in report['stages'] if arm in stage['arms']]
        calls=[call for row in rows for call in (row['inference'],row.get('verifierFeedback'),row.get('explicitRecovery'),*row.get('initializationCalls',[])) if call]
        unbound=[call for call in calls if call.get('sessionCaptureError') or call.get('commandSessionContinuation',{}).get('usageAttributionVerified') is False]
        known=[call for call in calls if not call.get('sessionCaptureError') and call.get('commandSessionContinuation',{}).get('usageAttributionVerified') is not False]
        last=next((row['learning'] for row in reversed(rows) if row.get('learning')), {})
        result[arm]={'taskPasses':sum(row.get('passed',False) for row in rows),'tasks':len(rows),
            'validAttributableTasks':sum(row.get('validPairInput',False) for row in rows),
            'leaderTokens':sum(call['usage']['totalTokens'] for call in known),
            'leaderReportedCost':sum(call['reportedCost'] for call in known),
            'leaderAndRecoverySeconds':sum(call['seconds'] for call in calls),
            'learningTokens':last.get('knownLearningTokens',0),'learningReportedCost':last.get('knownLearningCost',0),
            'unknownUsageAttempts':last.get('interruptedUnknownUsage',0),'unknownWorkerUsageLedgers':last.get('unknownWorkerUsageLedgers',0),'allLearningCostsPriced':last.get('allLearningCostsPriced',False),
            'learningFailedAttempts':last.get('learningFailedAttempts',sum(a.get('outcome')!='completed' for a in last.get('attempts',[]))),
            'learningFailedReplayAttempts':last.get('learningFailedReplayAttempts',sum(a.get('outcome')!='completed' for a in last.get('attempts',[]))),
            'toolBudgetExceededTasks':sum(row['inference'].get('toolBudgetExceeded',False) for row in rows),
            'leaderPricingVerified':False}
        if any(call.get('commandSessionContinuation') or call.get('sessionCaptureError') for call in calls):
            result[arm]['unknownLeaderUsageAttempts']=len(unbound)
            result[arm]['unattributedLeaderReportedTokens']=sum(call['usage']['totalTokens'] for call in unbound)
            result[arm]['unattributedLeaderReportedCost']=sum(call['reportedCost'] for call in unbound)
    return result


def run(args: argparse.Namespace) -> dict:
    unlimited_budget = getattr(args, 'unlimited_budget', False)
    failure_manifest = getattr(args, 'observed_idle_failure', None)
    failure_input = load_observed_idle_source(failure_manifest) if failure_manifest else None
    verified_failure_learning=getattr(args,'verified_failure_learning',False)
    explicit_command_initialization=getattr(args,'explicit_command_initialization',False)
    if explicit_command_initialization and (not failure_input or not unlimited_budget or verified_failure_learning):
        raise RuntimeError('Command initialization requires its separate observed-failure unlimited protocol')
    if verified_failure_learning and (not failure_input or not unlimited_budget):
        raise RuntimeError('Verified failure learning requires the explicit observed-failure unlimited protocol')
    tasks = command_initialization_tasks() if explicit_command_initialization else failure_first_tasks() if failure_input else TASKS
    if failure_input and (not unlimited_budget or failure_input['manifest'].get('sourceCommit') != SOURCE_COMMIT):
        raise RuntimeError('Observed failure requires its explicit source ancestry and unlimited-count protocol')
    paths=[base.PACKAGE/'index.ts',Path(__file__),Path(__file__).with_name('support.py'),Path(__file__).with_name('recovery_integrity.py'),Path(__file__).with_name('continuous_failure_retention.py'),Path(__file__).with_name('continuous-tool-budget.ts'),Path(__file__).with_name('continuous-bash-environment.ts'),Path(__file__).with_name('continuous-task-deadline.ts'),Path(__file__).with_name('continuous-verifier-reference.ts'),Path(__file__).with_name('continuous_project_evidence.py'),Path(__file__).with_name('continuous-dossier-proof.mjs'),Path(__file__).with_name('failure-observation-proof.ts'),Path(__file__).with_name('failure-observation-proof-cli.ts'),Path(__file__).with_name('continuous-memory-audit.ts'),Path(__file__).with_name('continuous-command-proof.ts'),Path(__file__).with_name('docker_experiment.py'),Path(__file__).with_name('jev-http-forward.mjs'),Path(__file__).with_name('jev-https-forward.mjs'),Path(__file__).with_name('live_acceptance_support.py'),Path(__file__).with_name('continuous_project_tasks.py'),Path(base.__file__),
           *base.PACKAGE.joinpath('extensions').glob('*.ts'),*base.PACKAGE.joinpath('prompts').glob('*.md'),
           *base.REPO.joinpath('packages/kit/src').glob('*.ts')]
    if failure_input:paths += [failure_manifest, failure_manifest.with_name('source.tar.gz')]
    evidence=EvidenceRun(args.output,{str(p):p for p in paths})
    print(json.dumps({'outputDir':str(evidence.output)},ensure_ascii=False),flush=True)
    protocol={'project':'p-limit','commit':SOURCE_COMMIT,'tasks':tasks,'arms':['without-learning','with-learning'],
              'sameCodeEachStage':True,'convergence':'first passing candidate, without-learning priority; otherwise without-learning failed source',
              'freshSessions':True,'memorySeeded':False,'harnessSeeded':False,'jev':None,'jevTransport':'host Bun fetch transparent JSON forwarding; original failed Python HTTP cohorts retained',
              'oracle':ORACLE,'types':[TYPES,SIGNAL_TYPES,REASON_TYPES,SYNC_TYPES,MAP_TYPES],
              'invalidLearning':'retained as operational failure; stop dependent stages after any invalid learning',
              'recovery':'one bounded explicit backfill after initial pending, retirement, or actual task verification failure; failures enter source-bound same-session read-only continuation first, no repeat-until-pass',
              'recoveryIntegrity':'complete live hash/mode-bound private/public/project snapshots and new receipt-owned history chains; prior attempts retained; exact feedback slice claimed in the shared output parent before backfill',
              'recoveryFileIdentityVersion':2,
              'costs':'sum leader usage plus cumulative per-job learning ledger plus Jev usage; missing pricing/interrupt usage remain unknown',
              'failureFeedbackAdmission':'feedback task failure remains failure; one complete same-session verifier read plus byte-bound original and pending slice and proven removed-tool rejection can admit independent backfill without a successful parent summary; no extra parent retries; earlier v18/v19 failures retained',
              'verifierReadBoundary':'exact source/session-bound file, no offset or limit, one admitted read; rejected calls retained, at most three rejected boundary attempts before abort; earlier prompt-only cohort retained',
              'verifierReadWireDomain':'same OpenAI-compatible read schema in both arms: path enum is exact bound file, no pagination or additional properties; messages unchanged, no forced call; execution guard and max-one preread proof unchanged; prior broader-schema failures retained',
              'initialSourceBoundary':{'version':1,'enabled':verified_failure_learning,
                  'readPaths':'complete regular public-source inventory captured before either initial arm',
                  'bashCommands':['node observed-idle-failure.mjs','pnpm test'],
                  'enforcement':'same provider schemas and pre-execution native tool guard in both initial arms; attempts retained; later safety gates unchanged'},
              'parentTaskToolBudget':None if unlimited_budget else 18,
              'transportRequestBudget':None if unlimited_budget else 600,
              'mainTaskDeadlineSeconds':900,'cliGuardianSeconds':UNLIMITED_CLI_GUARDIAN_SECONDS if unlimited_budget else 900,
              'resourceProtocol':'unlimited-counts-separated-deadlines' if unlimited_budget else 'bounded-18-tools-600-requests',
              'budgetMechanism':('no ordinary task tool or transport request count cap; exact one-read feedback guard; main900s closes before learning; Memory correction workers use the recorded 600s budget (ADR 0009) with every other worker/service bound unchanged; outer guardian7200s; independent learning workers unchanged' if unlimited_budget else 'identical experimental extension removes active tools after final admitted result and blocks excess in-flight calls; Memory correction workers use the recorded 600s budget (ADR 0009), which can outlast this 900s task guardian, so a guardian interruption stays interrupted and never a pass; other worker/service bounds and independent learning workers unchanged'),
              'priorUnboundedCohorts':'retained separately; this protocol change cannot be compared as an unchanged intervention',
              'commonPrompt':UNLIMITED_COMMON if unlimited_budget else COMMON,
              'versionVerification':'correction and retirement tasks require a unique matching successful standalone npm --version result, not merely an attempted call or a post-learning pure rule probe',
              'limitations':['one project, one sequence, no statistical generalization','task difficulty changes; no within-arm slope claim','source convergence is an intervention','resource protocol is an experimental intervention']}
    protocol['learningAuthorityProtocolVersion']=2 if unlimited_budget else 1
    protocol['publicRequirementMigrationVersion']=1
    protocol['memorySourceSupportProtocolVersion']=1
    protocol['bashLearningCredentialEnvironment']={'version':1,'bothArms':True,
        'scope':'Ordinary native Bash child environments omit TYPESAFE_API_KEY; the parent keeps SDK authentication. Native command, tool schema, session metadata and original observations are unchanged. This is not a filesystem sandbox or a universal secret filter. Sensitive original evidence still blocks learning. Historical cohorts remain unchanged.'}
    protocol['memorySourceSupportIntervention']='Normal rewrite support checks current new claims with complete cited and bound current source. Complete predecessor/history context remains in every counter, permission and preservation window. Source uncertainty, all thresholds and atomic approval remain unchanged; historical cause and benefit are unproved.'
    capture_envelopes=getattr(args,'capture_jev_envelopes',False)
    protocol['jevEnvelopeCapture']={'enabled':capture_envelopes,'scope':'Authorized public-study proxy UTF-8 JSON buffers only; no headers. Known transport credentials and unsafe response shapes are hash-only. Not raw upstream TLS bytes. Capture is bounded independently of wire capacity and writes after quiescence.'}
    protocol['publicRequirementMigration']={
        'task':'repair-and-sync-wrapper','file':'index.test-d.ts',
        'reason':'Replace the obsolete sync-rejection assertion with a positive Promise<string> assertion before both protected snapshots. Update only its stale comment; preserve every unrelated byte.',
        'countsAsLearning':False,'ordinaryTaskMayEditExistingTests':False,
        'historicalCohortsUnchanged':True}
    protocol['learningAuthorityIntervention']='Explicit separate parent maintenance grant; ordinary tool and existing-test restrictions unchanged. Prior actor-ambiguous cohorts remain separate; this is not evidence of a historical semantic cause.' if unlimited_budget else 'Original bounded actor-ambiguous wording retained.'
    protocol['piBaseline']='1.3.0'
    protocol['historicalPiBaseline']='Pi 1.0 and 1.2 cohorts retained separately; not an unchanged runtime comparison'
    protocol['coverageVersion']=3
    protocol['memoryEvidence']='index only; actual successful read with exact retained revision; read exposure alone is not behavioral use or benefit'
    if explicit_command_initialization:
        protocol['explicitCommandInitializationVersion']=1
        protocol['initialSourceArmExecutionVersion']=3
        protocol['initialArmExecutionOrder']=['with-learning','without-learning']
        protocol['initialArmOrderImpact']='The learner runs first. Retain order effects and shared outer-budget exhaustion; an absent control cannot establish a valid pair. All original downstream gates remain.'
        protocol['initialSourceActionGrammarVersion']=3
        protocol['initializationTreatment']={'sourceTaskAutomaticLearning':False,'command':'/memory 整理记忆',
            'sourceClosure':'at most one actual no-op backfill; pending0 and identical physical knowledge required',
            'policyTask':INITIAL_HARNESS_POLICY,'policyTaskBothArms':True,'policyTaskNativeTools':False,
            'policyOwnership':'separate actual automatic current-session receipt and original-user branch; no manual Harness seed',
            'originalTaskFailures':'immutable; safe source and accurate stored knowledge audited separately',
            'costs':'all source, command, closure, policy and failed initialization calls included; no equal-total-compute or plugin-only causal claim',
            'initialArmHolds':'A normally settled public-source-only control hold skips its policy and invalidates the pair. The independent learner retains all its own gates. Hard anomalies stop the whole cohort. All five later tasks remain blocked.'}
        protocol['limitations'].append('Explicit-command initialization and separate policy task are disclosed treatment changes; historical automatic cohorts remain separate.')
    if failure_input:
        protocol['observedFailureProtocolVersion']=3 if explicit_command_initialization else 2 if verified_failure_learning else 1
        protocol['initialFailureLearning']=('Separate read-only source work, actual same-session Memory command and a distinct automatic policy task; original task outcomes stay immutable and each prerequisite is checked before dependent tasks.' if explicit_command_initialization
            else 'Separate original task failure from native-feedback-bound, source-safe, complete-corpus learning. Original task outcomes stay immutable; invalid training still stops dependent tasks.' if verified_failure_learning else 'Original successful-diagnosis and all-arms first-task pass gate.')
        protocol['initialSourceManifest']=failure_input['manifest']
        protocol['initialSourceManifestSha256']=failure_input['manifestSha256']
        protocol['knownPublicCaseIsNotUnseenTransfer']=True
        protocol['failureCorrection']='Require actual meaningful failure knowledge, learner-own repair and owned current-status correction before source convergence; no restored learned state.'
    evidence.write('protocol.json',json.dumps(protocol,ensure_ascii=False,indent=2))
    failure_origins={}
    report={'status':'running','coverageVersion':3,'stages':[],'preflight':{},**({'observedFailureProtocolVersion':protocol['observedFailureProtocolVersion']} if failure_input else {})};containers=[];proxy=None
    try:
        image=base.runtime_image(args.base_image);report['image']=image
        pristine=failure_input['archive'] if failure_input else base.checked(['git','-C',str(args.source),'archive',SOURCE_COMMIT])
        for _ in range(2):
            c=base.container(image);containers.append(c)
            version=base.checked(['docker','exec',c,'node',base.PI,'--version']).decode().strip()
            report.setdefault('piVersions',[]).append(version)
            if version!='1.3.0':raise RuntimeError('Pi 1.3.0 study baseline required')
            if verified_failure_learning:
                runtime=initial_native_validation(c,version)
                if protocol.get('initialSourceRefusalRuntime',runtime)!=runtime:raise RuntimeError('Initial arm validation runtimes differ')
                protocol['initialSourceRefusalRuntime']=runtime
                protocol['initialSourceActionGrammarVersion']=4
            base.shell(c,'mkdir -p /work/p-limit; find /work/p-limit -mindepth 1 -maxdepth 1 ! -name node_modules -exec rm -rf -- {} +; rm -rf /home/node/agent /home/node/results; mkdir -p /home/node/agent/memory /home/node/agent/learning /home/node/results')
            base.checked(['docker','exec','-i',c,'tar','-xzf' if failure_input else '-xf','-','-C','/work/p-limit'],data=pristine)
            base.shell(c,'cd /work/p-limit && git init -q')
            install_memory_audit_runtime(c)
            if json.loads(base.checked(['docker','exec',c,'tsx','/home/node/continuous-memory-audit.mts','--preflight'])).get('ready') is not True:raise RuntimeError('Memory audit runtime unavailable')
            if explicit_command_initialization:
                probe=native_initialization_proof(c,'automaticHarnessPolicyProof',{'owner':{'container':c}},{},{})
                if (probe.get('ready') is not False or probe.get('reason')!='Unknown policy proof'
                        or probe.get('mutationAuthority') is not False or probe.get('learningBenefitEstablished') is not False):
                    raise RuntimeError('Native initialization proof runtime did not reject incomplete evidence')
                report.setdefault('nativeProofRuntime',[]).append({'container':c,'rejectedIncompleteEvidence':True,'externalRequests':0})
            base.put(c,'/home/node/continuous-task-deadline.ts',Path(__file__).with_name('continuous-task-deadline.ts').read_bytes())
            base.put(c,'/home/node/continuous-tool-budget.ts',Path(__file__).with_name('continuous-tool-budget.ts').read_bytes())
            base.put(c,'/home/node/continuous-bash-environment.ts',Path(__file__).with_name('continuous-bash-environment.ts').read_bytes())
            base.put(c,'/home/node/continuous-verifier-reference.ts',Path(__file__).with_name('continuous-verifier-reference.ts').read_bytes())
        with InferenceProxy(Path(os.environ.get('PI_CODING_AGENT_DIR',str(Path.home()/'.pi/agent'))),jev_key=os.environ.get('TYPESAFE_API_KEY'),request_budget=0 if args.preflight_only else (None if unlimited_budget else 600),jev_transport="node-https" if capture_envelopes else "bun-fetch",retain_jev_envelopes=capture_envelopes) as proxy:
            protocol['jev']=proxy.jev_model
            protocol['jevTransport']=proxy.jev_transport
            protocol['priorTransportCohortsRetained']=True
            evidence.write('protocol.json',json.dumps(protocol,ensure_ascii=False,indent=2))
            report['model']={k:proxy.selection[k] for k in ('provider','model')}
            for arm,c in zip(protocol['arms'],containers):
                base.configuration(c,proxy)
                enabled=arm=='with-learning'
                base.put(c,base.AGENT+'/memory/settings.json',json.dumps({'autoMemory':enabled and not explicit_command_initialization,
                    'automaticPhases':{'memory':'apply' if enabled else 'off','harness':'apply' if enabled and not explicit_command_initialization else 'off','agents':'off'}}).encode())
                before=base.protected(c,'p-limit');pre=score(c,1,proxy,evidence.output/('preflight-'+arm),before)
                if failure_input:
                    pre['publicReproducer']=public_failure_check(c,proxy,evidence.output/('preflight-'+arm))
                    captured=capture_failure_candidate(c,proxy,evidence.output/('preflight-'+arm),b'')
                    if ({name:item['sha256'] for name,item in failure_input['files'].items()}!=captured['manifest']['sourceHashes']
                        or pre['behavior']!={'passed':False,'exitCode':1} or pre['publicReproducer']!={'passed':False,'exitCode':1}
                        or pre['types']!={'passed':True,'exitCode':0} or not pre['upstream']['passed'] or not pre['existingChecksPreserved']):
                        raise RuntimeError('Actual failed source / green existing checks preflight failed')
                elif pre['behavior']['passed'] or pre['types']['passed'] or not pre['upstream']['passed']:raise RuntimeError('Original upstream GREEN / feature RED preflight failed')
                pre['emptyHarness']=harness_probe(c,-1,False)
                if not pre['emptyHarness']['passed']:raise RuntimeError('Initial Harness is not empty or probe failed')
                report['preflight'][arm]=pre
            if not args.preflight_only:
                if not proxy.jev_key:raise RuntimeError('Real Jev key unavailable; study must not fall back silently')
                feedback='';valid_learning_so_far=True
                for index,task in enumerate(tasks):
                    evidence.verify_sources()
                    public_migrations=[]
                    if task['id']=='repair-and-sync-wrapper':
                        for arm,c in zip(protocol['arms'],containers):
                            file='/work/p-limit/index.test-d.ts'
                            original=base.checked(['docker','exec',c,'cat',file])
                            changed,migration=migrate_public_sync_type_test(task['id'],original)
                            base.put(c,file,changed)
                            if base.checked(['docker','exec',c,'cat',file])!=changed:
                                raise RuntimeError('Public requirement migration readback failed')
                            public_migrations.append({'arm':arm,**migration})
                        if public_migrations[0]['afterSha256']!=public_migrations[1]['afterSha256']:
                            raise RuntimeError('Paired public requirement migration differs')
                                        # gzip headers can differ; bind expanded regular file bytes instead.
                    hashes=[base.protected(c,'p-limit',include_source=True) for c in containers]
                    filtered=lambda h:{k:v for k,v in h.items() if not k.startswith(('.memory/','.pi/'))}
                    if filtered(hashes[0])!=filtered(hashes[1]):raise RuntimeError('Paired stage source mismatch')
                    stage={'validPairInput':valid_learning_so_far,'id':task['id'],'arms':{},'sameSource':True,'startingSource':filtered(hashes[0])};outputs={}
                    if public_migrations:stage['publicRequirementMigrations']=public_migrations
                    report['stages'].append(stage)
                    starting_sources={name:item['data'].decode('utf-8') for name,item in source_archive_files(source_archive(containers[0])).items()} if failure_input else None
                    for arm_index in ([1,0] if explicit_command_initialization and index==0 else ([0,1] if index%2==0 else [1,0])):
                        arm=protocol['arms'][arm_index];c=containers[arm_index];out=evidence.output/task['id']/arm;outputs[arm]=out
                        if explicit_command_initialization and index==1:
                            enabled=arm=='with-learning'
                            base.put(c,base.AGENT+'/memory/settings.json',json.dumps({'autoMemory':enabled,'automaticPhases':{
                                'memory':'apply' if enabled else 'off','harness':'apply' if enabled else 'off','agents':'off'}}).encode())
                        before=base.protected(c,'p-limit')
                        prompt=task['prompt']+('\nActual preceding verification results:\n'+feedback if index==4 else '')
                        empty_state=artifacts(c,proxy,out/'initial-empty-state') if failure_input and index==0 else None
                        jev_start=len(proxy.jev_usage);requests_start=proxy.requests
                        inference=run_session(c,prompt,proxy,out,'stage-'+str(index),unlimited_budget=unlimited_budget,
                            initial_source_paths=sorted(starting_sources) if verified_failure_learning and index==0 else None)
                        inference['jevUsage']=proxy.jev_usage[jev_start:];inference['allTransportRequests']=proxy.requests-requests_start
                        stage['arms'][arm]={'inference':inference,'passed':False,'validPairInput':valid_learning_so_far}
                        if inference['timedOut'] or inference.get('interrupted') or inference.get('taskDeadlineExceeded') or inference.get('taskDeadlineMissing') or inference.get('modelAborted'):
                            stage['arms'][arm]={'inference':inference,'passed':False};raise RuntimeError('Timed-out candidate stopped; retain failure and stop dependent stages')
                        verification=score(c,1 if failure_input and index==0 else task['level'],proxy,out,before)
                        main_session=None;main_observation=None;candidate=None
                        if failure_input:
                            verification['publicReproducer']=public_failure_check(c,proxy,out)
                            main_session=base.checked(['docker','exec',c,'cat',base.AGENT+'/sessions/continuous/stage-'+str(index)+'.jsonl'])
                            candidate=capture_failure_candidate(c,proxy,out,main_session)
                            verification['sourceRepairPassed']=verification['passed'] and verification['publicReproducer']['passed']
                            if index==0:
                                verification['passed']=(verification['existingChecksPreserved'] and verification['upstream']['passed']
                                    and verification['types']['passed'] and verification['behavior']=={'passed':False,'exitCode':1}
                                    and verification['publicReproducer']=={'passed':False,'exitCode':1})
                                verification['diagnosisTaskPassed']=None
                            else:verification['passed']=verification['sourceRepairPassed']
                        if index in (2,3):
                            verification['versionExecuted']=bool(inference['executedVersionProbes'])
                            verification['passed']=verification['passed'] and verification['versionExecuted']
                        if index==0:
                            verification['readOnlySourcePreserved']=filtered(hashes[arm_index])==filtered(base.protected(c,'p-limit',include_source=True))
                            verification['passed']=verification['passed'] and verification['readOnlySourcePreserved']
                        if failure_input:
                            main_observation=verifier_observation(task['id'],verification,out,base.protected(c,'p-limit',include_source=True),main_session,inference=inference)
                            (out/'main-observation.json').write_text(json.dumps(main_observation,ensure_ascii=False,indent=2))
                        task_audit=None
                        if failure_input:
                            try:
                                task_payload=source_task_audit_input(main_observation,candidate['sources'],main_session,
                                    UNLIMITED_COMMON+prompt,starting_sources,stage['startingSource'])
                                task_audit=run_memory_audit(c,proxy,task_payload,out/'independent-task-audit')
                            except ValueError:
                                task_audit={'passed':False,'reason':'incomplete-or-failed-source-task'}
                            verification['independentTaskAuditPassed']=bool(task_audit.get('passed'))
                            verification['passed']=verification['passed'] and verification['independentTaskAuditPassed']
                            main_observation=verifier_observation(task['id'],verification,out,base.protected(c,'p-limit',include_source=True),main_session,inference=inference)
                            (out/'main-observation-final.json').write_text(json.dumps(main_observation,ensure_ascii=False,indent=2))
                        if explicit_command_initialization and index==0:
                            row=stage['arms'][arm]
                            row.update(verification=verification,independentTaskAudit=task_audit,
                                passed=task_outcome(inference,verification)['passed'],candidateBeforeConvergence=candidate['manifest'])
                            source_state=artifacts(c,proxy,out/'before-command-initialization')
                            row['initialLearning']=source_state;row['learning']=source_state
                            audit_protocol={'initialSourceManifest':failure_input['manifest'],'explicitCommandInitializationVersion':1,
                                'originalPrompt':UNLIMITED_COMMON+tasks[0]['prompt'],'currentPrompt':UNLIMITED_COMMON+tasks[1]['prompt']}
                            if arm=='with-learning':
                                try:
                                    state=run_command_initialization(c,proxy,out/'initialization','stage-0',prior=empty_state,
                                        observation=main_observation,sources=candidate['sources'],original_session=main_session,
                                        protocol=audit_protocol,row=row)
                                except BaseException:
                                    stage['validPairInput']=False
                                    for initial_row in stage['arms'].values():initial_row['validPairInput']=False
                                    raise
                                audit=row['commandInitializationAudit']
                            else:
                                payload=failure_source_safety_audit_input(empty_state,source_state,main_observation,candidate['sources'],main_session,audit_protocol)
                                audit=run_memory_audit(c,proxy,payload,out/'initial-source-safety')
                                state=source_state
                            row['failureMemoryAudit']=audit
                            if audit.get('passed') is not True:
                                row['validLearning']=False
                                row['initializationBlocked']={'phase':'initial-source-or-knowledge-audit','dependentPolicyStarted':False}
                                stage['validPairInput']=False
                                for initial_row in stage['arms'].values():initial_row['validPairInput']=False
                                if arm=='without-learning' and initial_control_hold_allows_independent_learner(
                                        audit,inference,verification,candidate,failure_input['manifest'],main_session):
                                    # The other initial arm owns a separate fresh container.
                                    # Keep this hold and stop the paired downstream gate.
                                    valid_learning_so_far=False
                                    print(json.dumps({'stage':task['id'],'arm':arm,'passed':row['passed'],
                                        'initializationHeld':True,'dependentPolicyStarted':False,
                                        'independentInitialArmPending':'with-learning' not in stage['arms']}),flush=True)
                                    continue
                                raise RuntimeError('Initial source/knowledge audit held; dependent tasks stopped')
                            state=run_initial_policy(c,proxy,out/'initialization',prior=state,row=row,enabled=arm=='with-learning')
                            harness=harness_probe(c,0,arm=='with-learning');row['harness']=harness
                            if not harness['passed']:raise RuntimeError('Initial actual policy rule does not satisfy its probes')
                            row['validLearning']=arm!='with-learning' or (state['pendingLearningJobs']==0 and bool(state['memoryEntries'])
                                and any('limitFunction' in entry['content'] and 'PromiseLike' in entry['content'] for entry in state['memoryEntries'])
                                and state['actualLearningOperations']>0 and row['initialPolicyBridge']['nativePolicyProof']['ready'] is True
                                and not any(state['backlogStatus'].get(key) for key in ('error','malformed','unlearnable','unscoped')))
                            failure_origins[arm]={'state':state,'observation':main_observation,'sources':candidate['sources'],'session':main_session,
                                **({'initializationRecord':row['commandInitializationRecord'],'policyBridge':row['initialPolicyBridge']} if arm=='with-learning' else {})}
                            print(json.dumps({'stage':task['id'],'arm':arm,'passed':row['passed'],'seconds':inference['seconds'],
                                'initializationTreatment':'explicit-command-then-automatic-policy'},ensure_ascii=False),flush=True)
                            continue
                        initial_state=artifacts(c,proxy,out/'before-recovery') if arm=='with-learning' and index==0 else None
                        recovery=None;verifier_feedback=None;feedback_state=None;native_feedback_evidence=None
                        if not task_outcome(inference,verification)['passed']:
                            original_session=base.checked(['docker','exec',c,'cat',base.AGENT+'/sessions/continuous/stage-'+str(index)+'.jsonl'])
                            source_before_feedback=base.protected(c,'p-limit',include_source=True)
                            observation=verifier_observation(task['id'],verification,out,source_before_feedback,original_session,inference=inference)
                            evidence.write(str(Path(task['id'])/arm/'verifier-observation.json'),json.dumps(observation,ensure_ascii=False,indent=2))
                            settings_file=base.AGENT+'/memory/settings.json'
                            old_settings=base.checked(['docker','exec',c,'cat',settings_file])
                            feedback_settings=json.loads(old_settings);feedback_settings['autoMemory']=False
                            base.put(c,settings_file,json.dumps(feedback_settings).encode())
                            try:
                                verifier_feedback=run_session(c,'continue',proxy,out/'verifier-feedback','stage-'+str(index),feedback_observation=observation,unlimited_budget=unlimited_budget)
                                stage['arms'][arm]['verifierFeedback']=verifier_feedback
                            finally:base.put(c,settings_file,old_settings)
                            feedback_state=artifacts(c,proxy,out/'before-failed-backfill')
                            queued=[entry for entry in feedback_state['backlogStatus']['pendingEntries'] if entry['sessionFile'].endswith('/stage-'+str(index)+'.jsonl')]
                            verifier_feedback['queuedFailure']=max(queued,key=lambda entry:entry['to']) if queued else None
                            verifier_feedback['originalEntryIds']=[row.get('id') for row in (json.loads(line) for line in original_session.splitlines()) if row.get('type')=='message' and row.get('message',{}).get('role') in ('user','toolResult') and row.get('id')]

                            stage['arms'][arm]['verifierFeedback']=verifier_feedback
                            verifier_feedback['observation']=observation
                            verifier_feedback['taskSourceUnchanged']=source_before_feedback==base.protected(c,'p-limit',include_source=True)
                            verifier_feedback['taskPassed']=feedback_accepted(verifier_feedback)
                            proof=failure_observation_ready(c,original_session,observation,verifier_feedback,
                                base.protected(c,'p-limit',include_source=True),retain_input=verified_failure_learning and index==0 and arm=='with-learning')
                            native_feedback_evidence=proof.pop('nativeEvidence',None)
                            verifier_feedback['failureObservationProof']=proof
                            if proof.get('ready') is not True:
                                raise RuntimeError('Actual verifier feedback was not preserved and safely observed')
                        if arm=='with-learning' and (index==3 or verifier_feedback is not None or (initial_state and initial_state['pendingLearningJobs']>0)):
                            recovery_before=feedback_state or artifacts(c,proxy,out/'before-explicit-backfill')
                            if verifier_feedback is not None:
                                claim=claim_recovery(args.output.parent/'failed-slice-claims',proof['sessionDigest'],
                                                     verifier_feedback['queuedFailure']['id'],str(out/'explicit-recovery'))
                                verifier_feedback['recoveryClaim']=str(claim)
                            source_before_recovery=base.protected(c,'p-limit',include_source=True)
                            recovery_jev_start=len(proxy.jev_usage);recovery_request_start=proxy.requests
                            recovery_label='stage-'+str(index)
                            recovery_prefix=read_command_session(c,recovery_label)
                            recovery=run_session(c,'/consolidate backfill',proxy,out/'explicit-recovery',recovery_label,
                                command=True,unlimited_budget=unlimited_budget,
                                prior_session_digest=hashlib.sha256(recovery_prefix).hexdigest())
                            recovery['jevUsage']=proxy.jev_usage[recovery_jev_start:];recovery['allTransportRequests']=proxy.requests-recovery_request_start
                            stage['arms'][arm]['explicitRecovery']=recovery
                            if feedback_state is not None:recovery['priorHistoryIds']=[record['id'] for record in feedback_state['history']]
                            if recovery['timedOut'] or recovery.get('interrupted'):raise RuntimeError('Recovery interrupted; dependent stages stopped')
                            # Recovery is a learning call only. Verify it did not
                            # alter real project source or existing check files.
                            recovered=score(c,task['level'],proxy,out/'after-recovery',before)
                            source_after_recovery=base.protected(c,'p-limit',include_source=True)
                            source_filter=lambda data:{k:v for k,v in data.items() if not k.startswith(('.memory/','.pi/'))}
                            recovery['taskSourceUnchanged']=source_filter(source_before_recovery)==source_filter(source_after_recovery)
                            verification['afterRecovery']=recovered
                            verification['passed']=verification['passed'] and recovered['passed'] and recovery['taskSourceUnchanged']
                        state=artifacts(c,proxy,out,source_review=verified_failure_learning and index==0 and arm=='with-learning')
                        if recovery is not None:
                            recovery['historyIntegrity']=verify_recovery_delta(recovery_before,state)
                            if recovery['historyIntegrity'].get('passed') is not True:
                                raise RuntimeError('Recovery history or learned surface integrity failed')
                        harness=harness_probe(c,index,arm=='with-learning')
                        memory_audits=[];memory_audit_inputs=[]
                        if arm=='with-learning' and index==4:
                            original_entries=report['stages'][0]['arms']['with-learning']['learning']['memoryEntries']
                            sources={name:base.checked(['docker','exec',c,'cat','/work/p-limit/'+name]).decode() for name in ('index.js','index.d.ts')}
                            for old in original_entries:
                                if 'limitFunction' not in old['content'] or 'PromiseLike' not in old['content']:continue
                                for new in state['memoryEntries']:
                                    if new['filename']!=old['filename'] or new['revision']==old['revision']:continue
                                    payload={'filename':old['filename'],'priorMemory':old['content'],'currentMemory':new['content'],'sources':sources}
                                    memory_audit_inputs.append(payload)
                                    base.put(c,'/home/node/memory-audit.json',json.dumps(payload).encode())
                                    audit_args=['docker','exec']
                                    for key,value in proxy.jev_environment().items():audit_args+=['-e',key+'='+value]
                                    audit_args += [c,'tsx','/home/node/continuous-memory-audit.mts','/home/node/memory-audit.json']
                                    memory_audits.append(json.loads(base.checked(audit_args)))
                            evidence.write(str(Path(task['id'])/arm/'memory-audit-inputs.json'),json.dumps(memory_audit_inputs,ensure_ascii=False,indent=2))
                            evidence.write(str(Path(task['id'])/arm/'memory-audits.json'),json.dumps(memory_audits,indent=2))
                            base.shell(c,'rm -f /home/node/memory-audit.json')
                        failure_audit=None;failure_payload=None
                        if failure_input and index in (0,1):
                            try:
                                audit_protocol={'initialSourceManifest':failure_input['manifest'],
                                    'originalPrompt':UNLIMITED_COMMON+tasks[0]['prompt'],'currentPrompt':UNLIMITED_COMMON+tasks[1]['prompt']}
                                if verified_failure_learning:audit_protocol['initialSourceRefusalRuntime']=protocol['initialSourceRefusalRuntime']
                                if index==0:
                                    if verified_failure_learning and arm!='with-learning':
                                        payload=failure_source_safety_audit_input(empty_state,state,main_observation,candidate['sources'],main_session,audit_protocol)
                                    elif verified_failure_learning and verifier_feedback is not None:
                                        payload=failure_feedback_audit_input(empty_state,state,main_observation,candidate['sources'],main_session,audit_protocol,verifier_feedback,native_feedback_evidence)
                                    else:payload=failure_record_audit_input(empty_state,state,main_observation,candidate['sources'],main_session,audit_protocol,diagnosis_only=arm!='with-learning')
                                    failure_payload=payload
                                elif arm=='with-learning':
                                    origin=failure_origins[arm]
                                    payload=failure_transition_audit_input(origin['state'],state,origin['observation'],main_observation,
                                        origin['sources'],candidate['sources'],origin['session'],main_session,audit_protocol,
                                        original_feedback_record=origin.get('feedbackRecord'),
                                        original_initialization_record=origin.get('initializationRecord'),initial_policy_bridge=origin.get('policyBridge'),
                                        native_runner=lambda name,evidence,before,after:native_initialization_proof(c,name,evidence,before,after))
                                else:payload=None
                                if payload is not None:failure_audit=run_memory_audit(c,proxy,payload,out/'failure-memory-audit')
                            except (ValueError,KeyError) as error:
                                failure_audit={'passed':False,'reason':'incomplete-bound-failure-evidence','errorType':type(error).__name__}
                                (out/'failure-memory-audit-rejected.json').write_text(json.dumps(failure_audit,indent=2))
                            if index==0:
                                verification['diagnosisTaskPassed']=verification['passed'] and bool(failure_audit and failure_audit.get('passed'))
                                verification['passed']=verification['diagnosisTaskPassed']
                                failure_origins[arm]={'state':state,'observation':main_observation,'sources':candidate['sources'],'session':main_session,
                                    'feedbackRecord':failure_payload if failure_payload and failure_payload['mode']=='observed-failure-feedback-record' else None}
                        failure_processed=verifier_feedback is None or exact_failure_processed(verifier_feedback,state)
                        if verifier_feedback is not None:verifier_feedback['exactFailureProcessed']=failure_processed
                        valid_learning=arm!='with-learning' or (failure_processed and state['pendingLearningJobs']==0 and bool(state['memoryEntries']) and (index!=0 or any('limitFunction' in entry['content'] and 'PromiseLike' in entry['content'] for entry in state['memoryEntries'])) and state['actualLearningOperations']>0 and harness['passed'] and (index!=4 or bool(memory_audits) and all(audit.get('passed') is True for audit in memory_audits)) and not any(state['backlogStatus'].get(k) for k in ('error','malformed','unlearnable','unscoped')))
                        if failure_input and arm=='with-learning' and index in (0,1):valid_learning=valid_learning and bool(failure_audit and failure_audit.get('passed'))
                        stage['arms'][arm]={'independentTaskAudit':task_audit,'failureMemoryAudit':failure_audit,**({'candidateBeforeConvergence':candidate['manifest']} if candidate else {}),'inference':inference,'verification':verification,'learning':state,'initialLearning':initial_state,'explicitRecovery':recovery,'verifierFeedback':verifier_feedback,'harness':harness,'memoryAudits':memory_audits,'validLearning':valid_learning,'validPairInput':valid_learning_so_far,
                                            'passed':task_outcome(inference,verification)['passed']}
                        print(json.dumps({'stage':task['id'],'arm':arm,'passed':stage['arms'][arm]['passed'],'seconds':inference['seconds']},ensure_ascii=False),flush=True)
                        if verified_failure_learning and index==0 and arm=='without-learning' and not (failure_audit and failure_audit.get('passed') is True):
                            row=stage['arms'][arm]
                            row['validLearning']=False
                            row['initializationBlocked']={'phase':'initial-source-safety-audit','dependentPolicyStarted':False}
                            stage['validPairInput']=False
                            for initial_row in stage['arms'].values():initial_row['validPairInput']=False
                            valid_learning_so_far=False
                            if not initial_control_hold_allows_independent_learner(
                                    failure_audit,inference,verification,candidate,failure_input['manifest'],main_session,
                                    native_validation=protocol.get('initialSourceRefusalRuntime')):
                                raise RuntimeError('Initial control safety audit unavailable or unsafe; independent learner and dependent tasks stopped')
                    valid_learning_so_far=valid_learning_so_far and stage['arms']['with-learning']['validLearning']
                    if failure_input and index==0:
                        valid_learning_so_far=valid_learning_so_far and initial_learning_continuation(stage,
                            verified_failure_learning=verified_failure_learning,explicit_command_initialization=explicit_command_initialization)
                    if not valid_learning_so_far:
                        raise RuntimeError('Invalid learning; dependent tasks stopped')
                    chosen=next((i for i,arm in enumerate(protocol['arms']) if stage['arms'][arm]['passed']),0)
                    stage['canonicalCandidate']=protocol['arms'][chosen]
                    canonical=source_archive(containers[chosen])
                    for c in containers:install_source(c,canonical)
                    feedback+=json.dumps({arm:{'result':v['verification'],'logs':{name:(outputs[arm]/(name+'.log')).read_text() for name in ('hidden','types','upstream') if (outputs[arm]/(name+'.log')).exists()}} for arm,v in stage['arms'].items()},ensure_ascii=False)
                    evidence.write('results.json',redact_transport_bytes(json.dumps(report,ensure_ascii=False,indent=2).encode(),proxy).decode() if proxy else json.dumps(report,ensure_ascii=False,indent=2))
            report['transport']={'requests':proxy.requests,'errors':proxy.errors,'jevRequests':proxy.jev_requests,'jevUsage':proxy.jev_usage,'jevObservations':proxy.jev_observations}
            report['status']='preflight-passed' if args.preflight_only else 'completed'
    except (Exception, KeyboardInterrupt) as error:
        report['status']='failed';report['error']=type(error).__name__
    finally:
        report['totals']=totals(report)
        report['coverage']=continuous_coverage(report)
        if report['status']=='completed' and not report['coverage']['coverageComplete']:
            report['executionStatus']='completed';report['status']='incomplete-coverage'
        if proxy is not None:
            report['transport']={'requests':proxy.requests,'errors':proxy.errors,'jevRequests':proxy.jev_requests,'jevUsage':proxy.jev_usage,'jevObservations':proxy.jev_observations}
            if capture_envelopes:
                report['jevEnvelopeCapture']=proxy.write_jev_envelopes(evidence.output/'jev-envelopes')
        # On failure, preserve available raw session artifacts before cleanup.
        # Missing interrupted usage is explicitly unknown, never imputed as zero.
        if report['status']=='failed' and proxy is None:
            # Version/build admission may fail before transport exists. Keep
            # owned containers intact rather than deleting unarchived evidence.
            report['retainedContainers']=list(containers)
            report['retentionIncomplete']=bool(containers)
            report['failureRetentionReason']='transport-not-initialized; containers retained without exporting unredacted data'
        elif report['status']=='failed' and proxy is not None:
            report['interruptedCostsMayBeUnknown']=True
            report['failureRetention']=[]
            report['retainedContainers']=[]
            for index,c in enumerate(containers):
                target=evidence.output/f'interrupted-agent-{index}'
                retained=retain_failure_container(c,target,base.process,lambda data:redact_transport_bytes(data,proxy))
                report['failureRetention'].append(retained)
                if retained['surfaces']['memory']['saved'] and retained['surfaces']['learning']['saved']:
                    try:
                        recovered = retained_learning_costs(target)
                        arm = protocol['arms'][index]
                        report.setdefault('retainedLearningCosts', {})[arm] = recovered
                        total = report['totals'][arm]
                        total['learningTokens'] = max(total['learningTokens'], recovered['knownLearningTokens'])
                        total['learningReportedCost'] = max(total['learningReportedCost'], recovered['knownLearningCost'])
                        total['allLearningCostsPriced'] = False
                        total['interruptedCostReconciled'] = True
                    except Exception as recovery_error:
                        report.setdefault('retainedCostErrors', []).append(type(recovery_error).__name__)
                if not retained['passed']:report['retainedContainers'].append(c)
            report['retentionIncomplete']=bool(report['retainedContainers'])
        else:
            for c in containers:base.process(['docker','rm','-f',c])
        report['sourceUnchanged']=evidence.hashes()==evidence.start_hashes
        if not report['sourceUnchanged']:
            report['status']='failed';report['error']='SourceDrift'
        evidence.write('results.json',redact_transport_bytes(json.dumps(report,ensure_ascii=False,indent=2).encode(),proxy).decode() if proxy else json.dumps(report,ensure_ascii=False,indent=2));evidence.write('manifest.json',redact_transport_bytes(json.dumps({**report,'sourceHashes':evidence.start_hashes,'sourceHashesAfter':evidence.hashes()},ensure_ascii=False,indent=2).encode(),proxy).decode() if proxy else json.dumps({**report,'sourceHashes':evidence.start_hashes,'sourceHashesAfter':evidence.hashes()},ensure_ascii=False,indent=2))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);parser.add_argument('--source',type=Path,default=Path('/tmp/cl-real-project-inputs/p-limit'));parser.add_argument('--base-image',default='cl-real-trained:p-limit-20261011-rebuilt');parser.add_argument('--preflight-only',action='store_true');parser.add_argument('--unlimited-budget',action='store_true');parser.add_argument('--capture-jev-envelopes',action='store_true');parser.add_argument('--observed-idle-failure',type=Path);parser.add_argument('--verified-failure-learning',action='store_true');parser.add_argument('--explicit-command-initialization',action='store_true')
    result=run(parser.parse_args());print(json.dumps({'status':result['status'],'error':result.get('error')},ensure_ascii=False));raise SystemExit(0 if result['status'] in ('completed','preflight-passed') else 1)
