"""Explicit same-original-input native Docker repair study; never collected by CI."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any
from docker_experiment import InferenceProxy, command, redact_transport_bytes, source_digest

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parents[2]
PREPARATION = TESTS / 'jev-harness-bindings-original-input-preparation.json'


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ResearchPreconditionError(ValueError):
    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


def require(condition: object, category: str) -> None:
    if not condition:
        raise ResearchPreconditionError(category)


def require_paid_permission(value: object) -> None:
    if value is not True:
        raise PermissionError('Paid prerequisite not satisfied')


def project_records(root: Path) -> dict[str, dict[str, int | str]]:
    records: dict[str, dict[str, int | str]] = {}
    for p in [root, *sorted(root.rglob('*'))]:
        require(not p.is_symlink(), 'Unexpected original project symlink')
        relative = str(p.relative_to(root))
        entry: dict[str, int | str] = {'type':'directory' if p.is_dir() else 'file','mode':p.stat().st_mode & 0o777}
        if p.is_file():
            entry['sha256'] = digest(p)
        records[relative] = entry
    return records


def records_digest(records: dict[str, dict[str, int | str]]) -> str:
    return hashlib.sha256(json.dumps(records,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def run_recorded(command_args: list[str], *, timeout: int, prefix: Path, proxy: InferenceProxy) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(command_args,capture_output=True,timeout=timeout)
        stdout,stderr,code,outcome = result.stdout,result.stderr,result.returncode,'completed'
    except subprocess.TimeoutExpired as error:
        stdout,stderr,code,outcome = error.stdout or b'',error.stderr or b'',None,'timeout'
    for suffix,data in [('stdout.jsonl',stdout),('stderr.txt',stderr)]:
        encoded = data.encode() if isinstance(data,str) else data
        path = prefix.with_name(prefix.name+'-'+suffix)
        descriptor = os.open(path,os.O_WRONLY | os.O_CREAT | os.O_EXCL,0o600)
        with os.fdopen(descriptor,'wb') as f:
            f.write(redact_transport_bytes(encoded,proxy))
    return {'exitCode':code,'outcome':outcome,'durationSeconds':round(time.monotonic()-started,3)}


def stop_owned_containers(containers: list[str]) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for index,cid in enumerate(containers):
        outcome: dict[str, Any] = {'containerIndex':index,'removalExitCode':None,'observedState':'unknown','childStoppedConfirmed':False}
        try:
            result=subprocess.run(['docker','rm','--force',cid],capture_output=True,timeout=30)
            outcome['removalExitCode']=result.returncode
        except (OSError,subprocess.TimeoutExpired):
            pass
        try:
            present=subprocess.run(['docker','ps','--all','--filter','id='+cid,'--format','{{.ID}}'],capture_output=True,timeout=10)
            if present.returncode==0 and not present.stdout.strip():
                outcome.update({'observedState':'removed','childStoppedConfirmed':True})
            elif present.returncode==0:
                state=subprocess.run(['docker','inspect','--format','{{.State.Running}}',cid],capture_output=True,timeout=10)
                if state.returncode==0 and state.stdout.strip() in (b'true',b'false'):
                    stopped=state.stdout.strip()==b'false'
                    outcome.update({'observedState':'present-stopped' if stopped else 'present-running','childStoppedConfirmed':stopped})
        except (OSError,subprocess.TimeoutExpired):
            pass
        outcomes.append(outcome)
    return outcomes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    if args.live == args.preflight_only:
        raise SystemExit('Choose explicit research mode')
    m: dict[str, Any] = json.loads(PREPARATION.read_text())
    r16: dict[str, Any] = json.loads((TESTS / 'jev-harness-bindings-r16-final-results.json').read_text())
    require(digest(TESTS / 'jev-harness-bindings-r16-final-results.json') == m['r16TerminalReportSha256'], 'Frozen research prerequisite failed')
    require(source_digest() == r16['sourceDigest'] and r16['sourceMatches'], 'Frozen research prerequisite failed')
    # Original workflows are terminal; this guard cannot be enabled by a lock alone.
    require(not command(['docker', 'ps', '--filter', 'ancestor=' + r16['image'], '--format', '{{.ID}}']).strip(), 'Frozen research prerequisite failed')
    if args.live:
        require_paid_permission(m['paidExecutionAllowedNow'])
    run = Path(m['originalRunDirectory'])
    require(digest(run / 'manifest.json') == m['originalManifestSha256'], 'Frozen research prerequisite failed')
    require(digest(run / 'snapshot.json') == m['snapshotSha256'], 'Frozen research prerequisite failed')
    require(digest(run / 'harness-repair.md') == m['originalTaskSha256'], 'Frozen research prerequisite failed')
    require(all((digest(Path(v['path'])) == v['sha256'] for v in m['tasks'].values())), 'Frozen research prerequisite failed')
    original = json.loads((run / 'manifest.json').read_text())
    require(original['runDir'].startswith('/home/node/agent/memory/runs/') and original['cwd'] == '/work/p-limit', 'Frozen research prerequisite failed')
    project = run.parents[3] / 'project'
    frozen_project = project_records(project)
    require(records_digest(frozen_project)==m['originalProjectTreeSha256'],'Original project tree changed')
    image = r16['image']
    require(command(['docker','image','inspect',image,'--format','{{.Id}}']).strip()==r16['imageId'],'Frozen image changed')
    mode = 'real-results' if args.live else 'preflight'
    output = TESTS / f'jev-harness-binding-original-{mode}.json'
    reservation = output.with_suffix(output.suffix+'.reservation')
    with reservation.open('x') as f:
        json.dump({'preparationSha256':digest(PREPARATION),'plannedArms':2,'requestBudget':120}, f)
    cache = Path(m['tasks']['before']['path']).parent / mode
    cache.mkdir(mode=0o700)
    containers: list[str] = []
    rows: list[dict[str, Any]] = []
    key = os.environ.get('TYPESAFE_API_KEY') if args.live else None
    if args.live and not key:
        raise SystemExit('Real Jev credential unavailable')
    code_hashes = {p.name:digest(p) for p in (Path(__file__), TESTS / 'evaluate_harness_binding_repair.ts', TESTS / 'harness-binding-repair-research.ts')}
    with InferenceProxy(Path(os.environ.get('PI_CODING_AGENT_DIR',Path.home()/'.pi/agent')), jev_key=key, request_budget=120) as proxy:
        require(proxy.selection == m['mainModel'], 'Frozen research prerequisite failed')
        try:
            for arm in ['before','after']:
                cid = command(['docker','run','--detach','--memory','4g','--cpus','2','--pids-limit','256','--cap-drop','ALL','--security-opt','no-new-privileges',image]).strip()
                containers.append(cid)
                command(['docker','exec',cid,'mkdir','-p','/home/node/agent/memory/runs/--work-p-limit--','/home/node/replay'])
                run_files = {p.name:p.read_text() for p in run.iterdir() if p.is_file()}
                writer = "import pathlib,json,sys;r=pathlib.Path(sys.argv[1]);r.mkdir(parents=True);[(r/n).write_text(v) for n,v in json.load(sys.stdin).items()];[p.chmod(0o600) for p in r.iterdir() if p.is_file()]"
                copied = subprocess.run(['docker','exec','-i',cid,'python3','-c',writer,original['runDir']],input=json.dumps(run_files),text=True,capture_output=True,timeout=30)
                require(copied.returncode == 0, 'Node-owned original run restore failed')
                require(project_records(project)==frozen_project,'Project changed between arms')
                require(project.is_dir(), 'Frozen research prerequisite failed')
                command(['docker','exec',cid,'mkdir','-p','/work/p-limit'])
                with tempfile.TemporaryFile() as errors:
                    archive = subprocess.Popen(['tar','-cf','-','-C',str(project),'.'],stdout=subprocess.PIPE,stderr=errors,env={**os.environ,'COPYFILE_DISABLE':'1'})
                    try:
                        restored = subprocess.run(['docker','exec','-i',cid,'tar','--no-same-owner','--same-permissions','-xf','-','-C','/work/p-limit'],stdin=archive.stdout,capture_output=True,timeout=120)
                        require(restored.returncode == 0, 'Read-only project restore failed')
                        if archive.stdout: archive.stdout.close()
                        archive.wait(timeout=30)
                    finally:
                        if archive.stdout: archive.stdout.close()
                        if archive.poll() is None: archive.terminate()
                        archive.wait(timeout=30)
                    require(archive.returncode == 0, 'Original project archive failed')
                for name in ['evaluate_harness_binding_repair.ts','harness-binding-repair-research.ts']:
                    command(['docker','cp',str(TESTS/name),cid+':/opt/experiment/packages/continual-learning/tests/'+name])
                with tempfile.TemporaryDirectory(prefix='cl-repair-config-') as temp:
                    config = Path(temp)/'agent'; proxy.write_agent_config(config)
                    contents = {p.name:p.read_text() for p in config.iterdir()}
                    contents['continual-learning.json'] = json.dumps({'jev':{'model':'jev-1.13.0','allowPrivateMemory':True}})
                    writer="import pathlib,json,sys;r=pathlib.Path('/home/node/agent');[(r/n).write_text(v) for n,v in json.load(sys.stdin).items()];[p.chmod(0o600) for p in r.iterdir() if p.is_file()]"
                    p=subprocess.run(['docker','exec','-i',cid,'python3','-c',writer],input=json.dumps(contents),text=True,capture_output=True,timeout=30)
                    require(p.returncode == 0, 'Isolated configuration initialization failed')
                tasks={name+'.md':Path(m['tasks'][name]['path']).read_text() for name in ['before','after']}
                writer="import pathlib,json,sys;r=pathlib.Path('/home/node/replay');[(r/n).write_text(v) for n,v in json.load(sys.stdin).items()];[p.chmod(0o600) for p in r.iterdir() if p.is_file()]"
                restored=subprocess.run(['docker','exec','-i',cid,'python3','-c',writer],input=json.dumps(tasks),text=True,capture_output=True,timeout=30)
                require(restored.returncode == 0, 'Node-owned task restore failed')
                files = {original['runDir']+'/'+p.name:digest(p) for p in run.iterdir() if p.is_file()}
                files.update({'/home/node/replay/'+name+'.md':m['tasks'][name]['sha256'] for name in ['before','after']})
                inputs = {'paidAllowed':args.live,'files':files,'runDirectory':original['runDir'],'beforeTask':'/home/node/replay/before.md','afterTask':'/home/node/replay/after.md','stdout':'/home/node/replay/stdout.jsonl','output':'/home/node/replay/evaluation.json','projectRoot':original['cwd'],'projectRecords':frozen_project}
                writer="import pathlib,sys;pathlib.Path('/home/node/replay/input.json').write_text(sys.stdin.read())"
                p=subprocess.run(['docker','exec','-i',cid,'python3','-c',writer],input=json.dumps(inputs),text=True,capture_output=True,timeout=30)
                require(p.returncode == 0, 'Frozen research prerequisite failed')
                check=subprocess.run(['docker','exec','--env','PI_CODING_AGENT_DIR=/home/node/agent',cid,'tsx','/opt/experiment/packages/continual-learning/tests/evaluate_harness_binding_repair.ts','--preflight-only','/home/node/replay/input.json'],capture_output=True,timeout=120)
                if check.returncode != 0:
                    known_reasons=['Frozen original input changed','Frozen project path or permissions changed','Frozen project content changed','Frozen project entry missing','Prepared prompt differs from exact production additions','Production guidance changed','Original parent identity mismatch','Original plan not parent valid','Original project configuration unreadable']
                    message=check.stderr.decode(errors='replace')
                    reason=next((v for v in known_reasons if ('Error: '+v) in message),'unknown-container-preflight')
                    (cache/(arm+'-preflight-failure.json')).write_text(json.dumps({'category':reason,'stderrSha256':hashlib.sha256(check.stderr).hexdigest(),'externalRequests':proxy.requests})+'\n')
                    raise ResearchPreconditionError(reason)
                command(['docker','cp',cid+':/home/node/replay/evaluation.json',str(cache/(arm+'-preflight.json'))])
            require(proxy.requests == 0, 'Unexpected preflight inference')
            if args.live:
                for arm,cid in zip(['before','after'],containers,strict=True):
                    print(json.dumps({'stage':'native-repair','arm':arm}),flush=True)
                    system=(TESTS.parent/'prompts/planner-system.md').read_text()
                    cli=['docker','exec','--env','PI_CODING_AGENT_DIR=/home/node/agent','--workdir',original['cwd'],cid,'pi','--print','--mode','json','--no-session','-ne','-ns','-np','-nc','--no-themes','--tools','read,grep,find,ls','--append-system-prompt',system,'--model',m['mainModel']['provider']+'/'+m['mainModel']['model'],'@/home/node/replay/'+arm+'.md']
                    recorded=run_recorded(cli,timeout=900,prefix=cache/(arm+'-native'),proxy=proxy)
                    stdout=cache/(arm+'-native-stdout.jsonl')
                    row={'arm':arm,'nativeExitCode':recorded['exitCode'],'nativeOutcome':recorded['outcome'],'nativeSeconds':recorded['durationSeconds']}
                    rows.append(row)
                    checkpoint=output.with_suffix(output.suffix+'.checkpoint')
                    checkpoint.write_text(json.dumps({'rows':rows,'requests':proxy.requests,'jevRequests':proxy.jev_requests,'jevUsage':proxy.jev_usage},indent=2)+'\n')
                    if recorded['exitCode']==0:
                        writer="import pathlib,sys;p=pathlib.Path('/home/node/replay/stdout.jsonl');p.write_bytes(sys.stdin.buffer.read());p.chmod(0o600)"
                        restored=subprocess.run(['docker','exec','-i',cid,'python3','-c',writer],input=stdout.read_bytes(),capture_output=True,timeout=30)
                        require(restored.returncode==0,'Node-owned generator output restore failed')
                        env_args=[v for k,value in proxy.jev_environment().items() for v in ['--env',k+'='+value]]
                        judged=run_recorded(['docker','exec','--env','PI_CODING_AGENT_DIR=/home/node/agent',*env_args,cid,'tsx','/opt/experiment/packages/continual-learning/tests/evaluate_harness_binding_repair.ts','--live','/home/node/replay/input.json'],timeout=120,prefix=cache/(arm+'-evaluation'),proxy=proxy)
                        row['evaluationExitCode']=judged['exitCode']
                        row['evaluationOutcome']=judged['outcome']
                        if judged['exitCode']==0:
                            target=cache/(arm+'-evaluation.json');command(['docker','cp',cid+':/home/node/replay/evaluation.json',str(target)]);row['evaluation']=json.loads(target.read_text())
                    checkpoint.write_text(json.dumps({'rows':rows,'requests':proxy.requests,'jevRequests':proxy.jev_requests,'jevUsage':proxy.jev_usage},indent=2)+'\n')
                    print(json.dumps({k:row[k] for k in ['arm','nativeExitCode','nativeOutcome','nativeSeconds','evaluationExitCode','evaluationOutcome'] if k in row}),flush=True)
                    if recorded['outcome']=='timeout' or row.get('evaluationOutcome')=='timeout':
                        # Stop the actual container child before ending this incomplete pair.
                        row['timeoutCleanup']=stop_owned_containers([cid])
                        checkpoint.write_text(json.dumps({'rows':rows,'requests':proxy.requests,'jevRequests':proxy.jev_requests,'jevUsage':proxy.jev_usage},indent=2)+'\n')
                        require(row['timeoutCleanup'][0]['childStoppedConfirmed'],'Timed-out native child stop unconfirmed')
                        break
            require(project_records(project)==frozen_project,'Original project changed during study')
            require(source_digest() == r16['sourceDigest'], 'Frozen research prerequisite failed')
            require(code_hashes == {name: digest(TESTS / name) for name in code_hashes}, 'Frozen research prerequisite failed')
            report={'evidence':'real-native-original-repair-before-after' if args.live else 'offline-container-original-repair-preflight','preparationSha256':digest(PREPARATION),'codeHashes':code_hashes,'image':image,'rows':rows,'originalProjectTreeSha256':m['originalProjectTreeSha256'],'plannedArms':2,'allArmsEvaluated':len(rows)==2 and all(r.get('evaluationExitCode')==0 for r in rows),'totalRequests':proxy.requests,'jevRequests':proxy.jev_requests,'providerErrors':proxy.errors,'jevUsage':proxy.jev_usage,'productionWrites':0,'goalComplete':False,'limits':['One known historical input; no heldout/full-workflow quality claim.','Independent retention contract check precedes real Jev; no mutation queue/apply.','Original outputs preserved; no retries, output selection or changed source.']}
        finally:
            # Stop every owned child first: audit I/O failures must not skip cleanup.
            cleanup=stop_owned_containers(containers)
            audit={'plannedArms':2,'recordedArms':len(rows),'rows':rows,'requests':proxy.requests,'jevRequests':proxy.jev_requests,'providerErrors':proxy.errors,'jevUsage':proxy.jev_usage,'accountBillingVerified':False,'limits':['Known usage only; failed or interrupted calls have unknown missing cost.'],'productionWrites':0,'cleanup':cleanup}
            print(json.dumps({'stage':'cleanup','removed':sum(v['observedState']=='removed' for v in cleanup),'unknownOrPresent':sum(v['observedState']!='removed' for v in cleanup)}),flush=True)
            (cache/'execution-final-state.json').write_text(json.dumps(audit,indent=2)+'\n')
            require(all(v['observedState']=='removed' for v in cleanup),'Task-owned container cleanup unconfirmed')
        report['cleanup']=cleanup
        with output.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
        print(json.dumps({'stage':'finished','live':args.live,'totalRequests':proxy.requests,'arms':len(rows)}),flush=True)


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        # Never expose subprocess arguments containing ephemeral transport tokens.
        print(json.dumps({'stage':'failed','category':error.category if isinstance(error,ResearchPreconditionError) else type(error).__name__}),flush=True)
        raise SystemExit(1)
