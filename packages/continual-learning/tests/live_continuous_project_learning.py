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
from continuous_failure_retention import retain_failure_container
import tarfile
import time

import live_real_project_memory as base
from continuous_project_tasks import COMMON, TASKS, SOURCE_COMMIT, ORACLE, TYPES, SIGNAL_TYPES, REASON_TYPES, SYNC_TYPES, MAP_TYPES
from docker_experiment import InferenceProxy, redact_transport_bytes
from live_acceptance_support import EvidenceRun
from continuous_project_evidence import continuous_coverage, verifier_observation, task_outcome, feedback_accepted, exact_failure_processed


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


def run_session(c: str, prompt: str, proxy: InferenceProxy, output: Path, label: str, *, command: bool = False, feedback_observation: dict | None = None) -> dict:
    session=base.AGENT+'/sessions/continuous/'+label+'.jsonl'
    base.shell(c,'mkdir -p '+base.AGENT+'/sessions/continuous')
    prior_bytes=b'';prior_count=0;feedback_text='';feedback_file='/home/node/project-verification.json'
    if feedback_observation is not None:
        prior_bytes=base.checked(['docker','exec',c,'cat',session])
        if hashlib.sha256(prior_bytes).hexdigest()!=feedback_observation['sessionDigest']:raise RuntimeError('Original verifier session changed')
        prior_count=len(prior_bytes.splitlines())
        feedback_text=json.dumps(feedback_observation,ensure_ascii=False,indent=2)
        base.put(c,feedback_file,feedback_text.encode())
    args=['docker','exec','-w','/work/p-limit','-e','PI_CODING_AGENT_DIR='+base.AGENT,'-e','PI_OFFLINE=1']
    for key,value in proxy.jev_environment().items():args+=['-e',key+'='+value]
    if feedback_observation is not None:args+=['-e','PI_STUDY_VERIFIER_FILE='+feedback_file,'-e','PI_STUDY_TASK_TOOL_LIMIT=1']
    args += [c,'node',base.PI,'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-approve',
             '--model',proxy.selection['provider']+'/'+proxy.selection['model'],'--thinking','off','--tools','read' if feedback_observation is not None else 'read,bash,edit,write',
             *([] if command else ['-e','/home/node/continuous-tool-budget.ts']),
             *(['-e','/home/node/continuous-verifier-reference.ts'] if feedback_observation is not None else []),
             '-e','/opt/experiment/packages/continual-learning/index.ts','--session',session,'--print','--mode','json',prompt if command or feedback_observation is not None else COMMON+prompt]
    started=time.monotonic();output.mkdir(parents=True,exist_ok=True);interrupted=False
    try:
        p=base.process(args,timeout=900);stdout=p.stdout;stderr=p.stderr;code=p.returncode;timed_out=False
    except KeyboardInterrupt:
        base.checked(['docker','stop',c]);stdout=b'';stderr=b'Operator interrupted; partial session retained';code=130;timed_out=False;interrupted=True
    except subprocess.TimeoutExpired as error:
        base.checked(['docker','stop',c]);stdout=error.stdout or b'';stderr=error.stderr or b'';code=124;timed_out=True
    (output/'stdout.jsonl').write_bytes(redact_transport_bytes(stdout,proxy));(output/'stderr.txt').write_bytes(redact_transport_bytes(stderr,proxy))
    # docker cp can still retrieve evidence from a stopped disposable container.
    copied=base.process(['docker','cp',c+':'+session,str(output/'session.jsonl')])
    messages=[];references=[];rows=[];malformed_rows=0;original_preserved=not prior_bytes
    if copied.returncode==0:
        captured=(output/'session.jsonl').read_bytes()
        original_preserved=not prior_bytes or captured.startswith(prior_bytes)
        raw=redact_transport_bytes(captured,proxy);(output/'session.jsonl').write_bytes(raw)
        for line in raw.splitlines():
            try:
                row=json.loads(line)
                if not isinstance(row,dict):raise ValueError('Non-object session record')
                rows.append(row)
            except ValueError:malformed_rows+=1
        rows=rows[prior_count:]
        messages=[r['message'] for r in rows if r.get('type')=='message']
        references=[r for r in rows if r.get('customType')=='continual-learning-memory-reference']
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
            'temporaryInstructionLeaked':label not in ('stage-1',) and any('TEMPORARY_IDLE_REVIEW' in str(part.get('text','')) for m in messages[-1:] for part in (m.get('content',[]) if isinstance(m.get('content'),list) else []) if isinstance(part,dict)),
            'modelErrors':sum(m.get('stopReason')=='error' for m in messages),'malformedSessionRows':malformed_rows,
            'toolCalls':sum(len([part for part in m.get('content',[]) if isinstance(part,dict) and part.get('type')=='toolCall']) for m in messages if isinstance(m.get('content'),list)),
            'usage':{k:sum(u.get(k,0) for u in usage) for k in ('input','output','cacheRead','cacheWrite','totalTokens')},
            'reportedCost':sum(u.get('cost',{}).get('total',0) for u in usage),
            'exposedMemoryReferences':len(references),
            'deliveredMemoryEntries':[item for row in references for item in row.get('details',{}).get('retrieved',[])],
            'toolBudgetEvents':[r.get('data') for r in rows if r.get('customType')=='continuous-study-tool-budget'],
            'toolBudgetExceeded':any(r.get('customType')=='continuous-study-tool-budget' and r.get('data',{}).get('outcome') in ('blocked','summary-tool-loop-stopped') for r in rows),
            'harnessEvents':[r for r in rows if str(r.get('customType','')).startswith('harness-')],
            'attemptedVersionProbeCalls':[part for m in messages if isinstance(m.get('content'),list) for part in m['content'] if isinstance(part,dict) and part.get('type')=='toolCall' and part.get('name')=='bash' and 'npm --version' in str(part.get('arguments',{}))],
            'executedVersionProbes':executed_version_probes(messages)}




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


def failure_observation_ready(c: str, original_session: bytes, observation: dict, feedback: dict, source_after: dict) -> dict:
    """Prove failed feedback evidence, without accepting the failed task itself."""
    queued=feedback.get('queuedFailure')
    if not queued:return {'ready':False,'reason':'no-pending-failure'}
    proof_cli=install_failure_observation_proof(c)
    input_file='/home/node/failure-observation-proof-input.json'
    value={'originalSession':original_session.decode(),'currentSession':'',
           'verifierText':json.dumps(observation,ensure_ascii=False,indent=2),
           'verifierPath':'/home/node/project-verification.json',
           'sourceBefore':observation['sourceHashes'],'sourceAfter':source_after,
           'queued':queued,'explicitBackfills':0}
    base.put(c,input_file,json.dumps(value,ensure_ascii=False).encode())
    try:
        return json.loads(base.checked(['docker','exec',c,'tsx',
            proof_cli,input_file]))
    finally:base.shell(c,'rm -f '+input_file)


def artifacts(c: str, proxy: InferenceProxy, output: Path) -> dict:
    output.mkdir(parents=True,exist_ok=True)
    base.export_tree(c,base.AGENT+'/memory',output/'memory.tar.gz',proxy)
    base.export_tree(c,base.AGENT+'/learning',output/'backlog.tar.gz',proxy)
    base.export_tree(c,'/work/p-limit',output/'source.tar.gz',proxy)
    probe="import {backlogStatus,readBacklog,backlogIdentity} from '/opt/experiment/packages/continual-learning/extensions/learning-backlog.ts';const read=readBacklog('/work/p-limit','/home/node/agent');console.log(JSON.stringify({...backlogStatus('/work/p-limit','/home/node/agent'),pendingEntries:read.pendingEntries.map(({entry})=>({...entry,id:backlogIdentity('--work-p-limit--',entry)}))}));"
    base.put(c,'/home/node/backlog-probe.mts',probe.encode())
    backlog=json.loads(base.checked(['docker','exec',c,'tsx','/home/node/backlog-probe.mts']))
    base.shell(c,'rm -f /home/node/backlog-probe.mts')
    receipts=[];states=[];memory_entries=[];history=[];dossiers=[];completed_backlog={}
    for filename in ('memory.tar.gz','backlog.tar.gz'):
        with tarfile.open(output/filename) as archive:
            for item in archive:
                if not item.isfile():continue
                if filename=='memory.tar.gz' and Path(item.name).parent.name=='--work-p-limit--' and item.name.endswith('.md') and Path(item.name).name!='MEMORY.md':
                    data=archive.extractfile(item).read();memory_entries.append({'filename':Path(item.name).name,'revision':hashlib.sha256(data).hexdigest(),'content':data.decode()})
                if not item.name.endswith('.json'):continue
                try: value=json.loads(archive.extractfile(item).read())
                except (ValueError,UnicodeError):continue
                if not isinstance(value,dict):continue
                if value.get('kind')=='learning-pipeline-receipt':receipts.append(value)
                if value.get('version')==1 and isinstance(value.get('changes'),list) and value.get('phase') in ('memory','harness','agents'):history.append(value)
                if Path(item.name).name=='backlog-completed.json':completed_backlog.update(value)
                if value.get('kind')=='incremental-learning-dossier':
                    task=value.get('taskSlice',{});observations=[]
                    for entry in task.get('entries',[]):
                        message=entry.get('message',entry)
                        if message.get('role')!='toolResult' or message.get('toolName')!='read' or message.get('isError') is not False:continue
                        try:observation=json.loads(''.join(part.get('text','') for part in message.get('content',[]) if isinstance(part,dict)))
                        except ValueError:continue
                        if isinstance(observation,dict) and observation.get('kind')=='actual-project-verification':observations.append(observation)
                    dossiers.append({'taskSliceDigest':hashlib.sha256(json.dumps(task,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),
                                     'entryIds':[entry.get('id') for entry in task.get('entries',[]) if entry.get('id')], 'observations':observations})
                if Path(item.name).name.startswith('replay-'):states.append(value)
    # Per-job ledger preserves repeated and failed attempts; receipts elsewhere
    # can duplicate these and are retained separately rather than added twice.
    attempts=[a for state in states for a in state.get('attempts',[])]
    # Use the same JavaScript serialization as the production acknowledgment.
    base.put(c,'/home/node/study-receipts.json',json.dumps([a.get('receipt') for a in attempts]).encode())
    digest_script="const fs=require('node:fs'),crypto=require('node:crypto');console.log(JSON.stringify(JSON.parse(fs.readFileSync('/home/node/study-receipts.json','utf8')).map(r=>r?crypto.createHash('sha256').update(JSON.stringify(r)).digest('hex'):null)));"
    digests=json.loads(base.checked(['docker','exec',c,'node','-e',digest_script]))
    base.shell(c,'rm -f /home/node/study-receipts.json')
    for attempt,digest in zip(attempts,digests):attempt['receiptDigest']=digest
    known=[a['receipt'] for a in attempts if a.get('receipt')]
    return {'memoryEntries':memory_entries,'history':history,'dossiers':dossiers,'completedBacklog':completed_backlog,'receipts':receipts,'attempts':attempts,'knownLearningTokens':sum(r['totals']['totalTokens'] for r in known),
            'knownLearningCost':sum(r['totals']['cost'] for r in known),'interruptedUnknownUsage':sum(not a.get('receipt') or a['receipt'].get('usageAvailable') is not True for a in attempts),
            'pendingLearningJobs':backlog['pending'],'backlogStatus':backlog,
            'actualLearningOperations':sum(r.get('operations',0) for r in known),
            'allLearningCostsPriced':all(r.get('costAvailable') is True for r in known)}


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
        calls=[call for row in rows for call in (row['inference'],row.get('verifierFeedback'),row.get('explicitRecovery')) if call]
        last=next((row['learning'] for row in reversed(rows) if row.get('learning')), {})
        result[arm]={'taskPasses':sum(row.get('passed',False) for row in rows),'tasks':len(rows),
            'validAttributableTasks':sum(row.get('validPairInput',False) for row in rows),
            'leaderTokens':sum(call['usage']['totalTokens'] for call in calls),
            'leaderReportedCost':sum(call['reportedCost'] for call in calls),
            'leaderAndRecoverySeconds':sum(call['seconds'] for call in calls),
            'learningTokens':last.get('knownLearningTokens',0),'learningReportedCost':last.get('knownLearningCost',0),
            'unknownUsageAttempts':last.get('interruptedUnknownUsage',0),'allLearningCostsPriced':last.get('allLearningCostsPriced',False),
            'learningFailedAttempts':sum(a.get('outcome')!='completed' for a in last.get('attempts',[])),
            'toolBudgetExceededTasks':sum(row['inference'].get('toolBudgetExceeded',False) for row in rows),
            'leaderPricingVerified':False}
    return result


def run(args: argparse.Namespace) -> dict:
    paths=[base.PACKAGE/'index.ts',Path(__file__),Path(__file__).with_name('continuous_failure_retention.py'),Path(__file__).with_name('continuous-tool-budget.ts'),Path(__file__).with_name('continuous-verifier-reference.ts'),Path(__file__).with_name('continuous_project_evidence.py'),Path(__file__).with_name('failure-observation-proof.ts'),Path(__file__).with_name('failure-observation-proof-cli.ts'),Path(__file__).with_name('continuous-memory-audit.ts'),Path(__file__).with_name('docker_experiment.py'),Path(__file__).with_name('jev-http-forward.mjs'),Path(__file__).with_name('live_acceptance_support.py'),Path(__file__).with_name('continuous_project_tasks.py'),Path(base.__file__),
           *base.PACKAGE.joinpath('extensions').glob('*.ts'),*base.PACKAGE.joinpath('prompts').glob('*.md'),
           *base.REPO.joinpath('packages/kit/src').glob('*.ts')]
    evidence=EvidenceRun(args.output,{str(p):p for p in paths})
    print(json.dumps({'outputDir':str(evidence.output)},ensure_ascii=False),flush=True)
    protocol={'project':'p-limit','commit':SOURCE_COMMIT,'tasks':TASKS,'arms':['without-learning','with-learning'],
              'sameCodeEachStage':True,'convergence':'first passing candidate, without-learning priority; otherwise without-learning failed source',
              'freshSessions':True,'memorySeeded':False,'harnessSeeded':False,'jev':'1.13.0 isolated configuration only','jevTransport':'host Bun fetch transparent JSON forwarding; original failed Python HTTP cohorts retained',
              'oracle':ORACLE,'types':[TYPES,SIGNAL_TYPES,REASON_TYPES,SYNC_TYPES,MAP_TYPES],
              'invalidLearning':'retained as operational failure; stop dependent stages after any invalid learning',
              'recovery':'one bounded explicit backfill after initial pending, retirement, or actual task verification failure; failures enter source-bound same-session read-only continuation first, no repeat-until-pass',
              'costs':'sum leader usage plus cumulative per-job learning ledger plus Jev usage; missing pricing/interrupt usage remain unknown',
              'failureFeedbackAdmission':'feedback task failure remains failure; one complete same-session verifier read plus byte-bound original and pending slice and proven removed-tool rejection can admit independent backfill without a successful parent summary; no extra parent retries; earlier v18/v19 failures retained',
              'verifierReadBoundary':'exact source/session-bound file, no offset or limit, one admitted read; rejected calls retained, at most three rejected boundary attempts before abort; earlier prompt-only cohort retained',
              'parentTaskToolBudget':18,'budgetMechanism':'identical experimental extension removes active tools after final admitted result and blocks excess in-flight calls; independent learning workers unchanged',
              'priorUnboundedCohorts':'retained separately; this protocol change cannot be compared as an unchanged intervention',
              'commonPrompt':COMMON,
              'versionVerification':'correction and retirement tasks require a unique matching successful standalone npm --version result, not merely an attempted call or a post-learning pure rule probe',
              'limitations':['one project, one sequence, no statistical generalization','task difficulty changes; no within-arm slope claim','source convergence is an intervention','parent resource cap is an experimental intervention']}
    protocol['coverageVersion']=2
    evidence.write('protocol.json',json.dumps(protocol,ensure_ascii=False,indent=2))
    report={'status':'running','stages':[],'preflight':{}};containers=[];proxy=None
    try:
        image=base.runtime_image(args.base_image);report['image']=image
        pristine=base.checked(['git','-C',str(args.source),'archive',SOURCE_COMMIT])
        for _ in range(2):
            c=base.container(image);containers.append(c)
            base.shell(c,'mkdir -p /work/p-limit; find /work/p-limit -mindepth 1 -maxdepth 1 ! -name node_modules -exec rm -rf -- {} +; rm -rf /home/node/agent /home/node/results; mkdir -p /home/node/agent/memory /home/node/agent/learning /home/node/results')
            base.checked(['docker','exec','-i',c,'tar','-xf','-','-C','/work/p-limit'],data=pristine)
            base.shell(c,'cd /work/p-limit && git init -q')
            base.put(c,'/home/node/continuous-memory-audit.mts',Path(__file__).with_name('continuous-memory-audit.ts').read_text().replace('../extensions/jev-sdk','/opt/experiment/packages/continual-learning/extensions/jev-sdk.ts').encode())
            if json.loads(base.checked(['docker','exec',c,'tsx','/home/node/continuous-memory-audit.mts','--preflight'])).get('ready') is not True:raise RuntimeError('Memory audit runtime unavailable')
            base.put(c,'/home/node/continuous-tool-budget.ts',Path(__file__).with_name('continuous-tool-budget.ts').read_bytes())
            base.put(c,'/home/node/continuous-verifier-reference.ts',Path(__file__).with_name('continuous-verifier-reference.ts').read_bytes())
        with InferenceProxy(Path(os.environ.get('PI_CODING_AGENT_DIR',str(Path.home()/'.pi/agent'))),jev_key=os.environ.get('TYPESAFE_API_KEY'),request_budget=600,jev_transport="bun-fetch") as proxy:
            report['model']={k:proxy.selection[k] for k in ('provider','model')}
            for arm,c in zip(protocol['arms'],containers):
                base.configuration(c,proxy)
                enabled=arm=='with-learning'
                base.put(c,base.AGENT+'/memory/settings.json',json.dumps({'autoMemory':enabled,'automaticPhases':{'memory':'apply' if enabled else 'off','harness':'apply' if enabled else 'off','agents':'off'}}).encode())
                before=base.protected(c,'p-limit');pre=score(c,1,proxy,evidence.output/('preflight-'+arm),before)
                if pre['behavior']['passed'] or pre['types']['passed'] or not pre['upstream']['passed']:raise RuntimeError('Original upstream GREEN / feature RED preflight failed')
                pre['emptyHarness']=harness_probe(c,-1,False)
                if not pre['emptyHarness']['passed']:raise RuntimeError('Initial Harness is not empty or probe failed')
                report['preflight'][arm]=pre
            if not args.preflight_only:
                if not proxy.jev_key:raise RuntimeError('Real Jev key unavailable; study must not fall back silently')
                feedback='';valid_learning_so_far=True
                for index,task in enumerate(TASKS):
                    evidence.verify_sources()
                                        # gzip headers can differ; bind expanded regular file bytes instead.
                    hashes=[base.protected(c,'p-limit',include_source=True) for c in containers]
                    filtered=lambda h:{k:v for k,v in h.items() if not k.startswith(('.memory/','.pi/'))}
                    if filtered(hashes[0])!=filtered(hashes[1]):raise RuntimeError('Paired stage source mismatch')
                    stage={'validPairInput':valid_learning_so_far,'id':task['id'],'arms':{},'sameSource':True,'startingSource':filtered(hashes[0])};outputs={}
                    report['stages'].append(stage)
                    for arm_index in ([0,1] if index%2==0 else [1,0]):
                        arm=protocol['arms'][arm_index];c=containers[arm_index];out=evidence.output/task['id']/arm;outputs[arm]=out
                        before=base.protected(c,'p-limit')
                        prompt=task['prompt']+('\nActual preceding verification results:\n'+feedback if index==4 else '')
                        jev_start=len(proxy.jev_usage);requests_start=proxy.requests
                        inference=run_session(c,prompt,proxy,out,'stage-'+str(index))
                        inference['jevUsage']=proxy.jev_usage[jev_start:];inference['allTransportRequests']=proxy.requests-requests_start
                        stage['arms'][arm]={'inference':inference,'passed':False,'validPairInput':valid_learning_so_far}
                        if inference['timedOut'] or inference.get('interrupted'):
                            stage['arms'][arm]={'inference':inference,'passed':False};raise RuntimeError('Timed-out candidate stopped; retain failure and stop dependent stages')
                        verification=score(c,task['level'],proxy,out,before)
                        if index in (2,3):
                            verification['versionExecuted']=bool(inference['executedVersionProbes'])
                            verification['passed']=verification['passed'] and verification['versionExecuted']
                        if index==0:
                            verification['readOnlySourcePreserved']=filtered(hashes[arm_index])==filtered(base.protected(c,'p-limit',include_source=True))
                            verification['passed']=verification['passed'] and verification['readOnlySourcePreserved']
                        initial_state=artifacts(c,proxy,out/'before-recovery') if arm=='with-learning' and index==0 else None
                        recovery=None;verifier_feedback=None;feedback_state=None
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
                                verifier_feedback=run_session(c,'continue',proxy,out/'verifier-feedback','stage-'+str(index),feedback_observation=observation)
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
                            if not verifier_feedback['taskPassed']:
                                proof=failure_observation_ready(c,original_session,observation,verifier_feedback,
                                    base.protected(c,'p-limit',include_source=True))
                                verifier_feedback['failureObservationProof']=proof
                                if proof.get('ready') is not True:
                                    raise RuntimeError('Actual verifier feedback was not preserved and safely observed')
                        if arm=='with-learning' and (index==3 or verifier_feedback is not None or (initial_state and initial_state['pendingLearningJobs']>0)):
                            source_before_recovery=base.protected(c,'p-limit',include_source=True)
                            recovery_jev_start=len(proxy.jev_usage);recovery_request_start=proxy.requests
                            recovery=run_session(c,'/consolidate backfill',proxy,out/'explicit-recovery','recovery-'+str(index),command=True)
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
                        state=artifacts(c,proxy,out)
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
                        failure_processed=verifier_feedback is None or exact_failure_processed(verifier_feedback,state)
                        if verifier_feedback is not None:verifier_feedback['exactFailureProcessed']=failure_processed
                        valid_learning=arm!='with-learning' or (failure_processed and state['pendingLearningJobs']==0 and bool(state['memoryEntries']) and (index!=0 or any('limitFunction' in entry['content'] and 'PromiseLike' in entry['content'] for entry in state['memoryEntries'])) and state['actualLearningOperations']>0 and harness['passed'] and (index!=4 or bool(memory_audits) and all(audit.get('passed') is True for audit in memory_audits)) and not any(state['backlogStatus'].get(k) for k in ('error','malformed','unlearnable','unscoped')))
                        stage['arms'][arm]={'inference':inference,'verification':verification,'learning':state,'initialLearning':initial_state,'explicitRecovery':recovery,'verifierFeedback':verifier_feedback,'harness':harness,'memoryAudits':memory_audits,'validLearning':valid_learning,'validPairInput':valid_learning_so_far,
                                            'passed':task_outcome(inference,verification)['passed']}
                        print(json.dumps({'stage':task['id'],'arm':arm,'passed':stage['arms'][arm]['passed'],'seconds':inference['seconds']},ensure_ascii=False),flush=True)
                    valid_learning_so_far=valid_learning_so_far and stage['arms']['with-learning']['validLearning']
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
        # On failure, preserve available raw session artifacts before cleanup.
        # Missing interrupted usage is explicitly unknown, never imputed as zero.
        if report['status']=='failed' and proxy is not None:
            report['interruptedCostsMayBeUnknown']=True
            report['failureRetention']=[]
            report['retainedContainers']=[]
            for index,c in enumerate(containers):
                target=evidence.output/f'interrupted-agent-{index}'
                retained=retain_failure_container(c,target,base.process,lambda data:redact_transport_bytes(data,proxy))
                report['failureRetention'].append(retained)
                if not retained['passed']:report['retainedContainers'].append(c)
            report['retentionIncomplete']=bool(report['retainedContainers'])
        else:
            for c in containers:base.process(['docker','rm','-f',c])
        report['sourceUnchanged']=evidence.hashes()==evidence.start_hashes
        if not report['sourceUnchanged']:
            report['status']='failed';report['error']='SourceDrift'
        evidence.write('results.json',redact_transport_bytes(json.dumps(report,ensure_ascii=False,indent=2).encode(),proxy).decode() if proxy else json.dumps(report,ensure_ascii=False,indent=2));evidence.write('manifest.json',redact_transport_bytes(json.dumps({**report,'sourceHashes':evidence.start_hashes,'sourceHashesAfter':evidence.hashes()},ensure_ascii=False,indent=2).encode(),proxy).decode() if proxy else json.dumps(report,ensure_ascii=False,indent=2))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);parser.add_argument('--source',type=Path,default=Path('/tmp/cl-real-project-inputs/p-limit'));parser.add_argument('--base-image',default='cl-real-trained:p-limit-445efcaf51');parser.add_argument('--preflight-only',action='store_true')
    result=run(parser.parse_args());print(json.dumps({'status':result['status'],'error':result.get('error')},ensure_ascii=False));raise SystemExit(0 if result['status'] in ('completed','preflight-passed') else 1)
