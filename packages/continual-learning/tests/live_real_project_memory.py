"""Explicit Jev-on, paired complex coding study on pinned public source.

No host mounts; credentials stay in the host transport proxy. Oracles are copied
only after the model exits. A failed candidate remains a scored failure.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import time
import uuid

from docker_experiment import InferenceProxy, redact_transport_bytes
from live_acceptance_support import EvidenceRun
from real_project_tasks import COMMON, PROJECTS, P_LIMIT_ORACLE, PLUGGY_ORACLE, P_LIMIT_TYPES

PACKAGE=Path(__file__).resolve().parents[1]
REPO=PACKAGE.parents[1]
AGENT='/home/node/agent'
RESULTS='/home/node/results'
PI='/opt/experiment/node_modules/@earendil-works/pi-coding-agent/dist/cli.js'


def process(args: list[str], *, timeout: int = 900, data: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args,input=data,capture_output=True,timeout=timeout)


def checked(args: list[str], *, timeout: int = 900, data: bytes | None = None) -> bytes:
    p=process(args,timeout=timeout,data=data)
    if p.returncode: raise RuntimeError(f'{args[0]} operation failed with exit {p.returncode}')
    return p.stdout


def shell(container: str, script: str, *, timeout: int = 900) -> bytes:
    return checked(['docker','exec',container,'bash','-lc',script],timeout=timeout)


def put(container: str, destination: str, data: bytes) -> None:
    checked(['docker','exec','-i',container,'python3','-c',
             'import pathlib,sys;p=pathlib.Path(sys.argv[1]);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(sys.stdin.buffer.read())',destination],data=data)


def get(container: str, filename: str) -> bytes:
    return checked(['docker','exec',container,'cat',filename])


def runtime_image(base_image: str = "cl-real-project-runtime:20261010-base") -> str:
    # Only runtime source is transferred. Evaluation code/oracles are never in it.
    with tempfile.TemporaryDirectory(prefix='cl-real-runtime-') as temp:
        context=Path(temp)
        for package in ('kit','continual-learning'):
            src=REPO/'packages'/package; dst=context/'packages'/package;dst.mkdir(parents=True)
            for item in src.iterdir():
                if item.name in {'tests','node_modules','features','.pytest_cache','__pycache__'}: continue
                if item.is_dir(): shutil.copytree(item,dst/item.name)
                elif item.suffix in {'.ts','.json','.md'}: shutil.copy2(item,dst/item.name)
        (context/'Dockerfile').write_text('FROM '+base_image+'\nUSER root\nCOPY packages /opt/experiment/packages\nRUN chown -R node:node /home/node/.cache /home/node/.local\nUSER node\nWORKDIR /work\n')
        tag='cl-real-runtime:'+uuid.uuid4().hex[:12]
        checked(['docker','build','-q','-t',tag,str(context)])
        return tag


def container(image: str) -> str:
    return checked(['docker','run','-d','--cap-drop=ALL','--security-opt=no-new-privileges',
                    '--pids-limit','256',image,'sleep','infinity']).decode().strip()


def configuration(c: str, proxy: InferenceProxy) -> None:
    with tempfile.TemporaryDirectory(prefix='cl-proxy-config-') as temp:
        root=Path(temp)/'agent';proxy.write_agent_config(root)
        for f in root.iterdir(): put(c,AGENT+'/'+f.name,f.read_bytes())
    # Only public source is present. Malformed-plan recovery stores private by default;
    # explicitly allow its Jev review in this isolated study, never in user settings.
    put(c,AGENT+'/continual-learning.json',b'{"jev":{"model":"jev-1.13.0","allowPrivateMemory":true}}')


def policy(c: str, learn: bool) -> None:
    put(c,AGENT+'/memory/settings.json',json.dumps({'autoMemory':learn,
        'automaticPhases':{'memory':'apply' if learn else 'off','agents':'off','harness':'off'}}).encode())


def model_prompt_arguments(prompt: str, *, continuation: bool = False) -> list[str]:
    # A substantive new user prompt would discard old tool evidence from the
    # product's currentTaskSlice. Keep the existing continuation contract.
    return ['--append-system-prompt',COMMON+prompt,'continue'] if continuation else [COMMON+prompt]


def run_model(c: str, project: str, prompt: str, proxy: InferenceProxy, output: Path, label: str, *, continuation: bool = False) -> dict:
    args=['docker','exec','-w','/work/'+project,'-e','PI_CODING_AGENT_DIR='+AGENT,'-e','PI_OFFLINE=1']
    for key,value in proxy.jev_environment().items(): args+=['-e',key+'='+value]
    args += [c,'node',PI,'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates',
             '--no-themes','--no-approve','--model',proxy.selection['provider']+'/'+proxy.selection['model'],
             '--thinking','off',*(['--no-tools'] if continuation else ['--tools','read,bash,edit,write']),'-e','/opt/experiment/packages/continual-learning/index.ts',
             '--session',RESULTS+'/'+label+'-session.jsonl','--print','--mode','json',*model_prompt_arguments(prompt,continuation=continuation)]
    start=time.monotonic()
    try:
        p=process(args,timeout=1500); code=p.returncode; stdout=p.stdout;stderr=p.stderr; timed_out=False
    except subprocess.TimeoutExpired as error:
        # Stopping the disposable container also stops any model tool children.
        checked(['docker','stop',c]); code=124;stdout=error.stdout or b'';stderr=error.stderr or b'';timed_out=True
    output.mkdir(parents=True,exist_ok=True)
    (output/'stdout.jsonl').write_bytes(redact_transport_bytes(stdout,proxy));(output/'stderr.txt').write_bytes(redact_transport_bytes(stderr,proxy))
    messages=[]
    if not timed_out:
        session=get(c,RESULTS+'/'+label+'-session.jsonl');(output/'session.jsonl').write_bytes(redact_transport_bytes(session,proxy))
        for line in session.splitlines():
            row=json.loads(line)
            if row.get('type')=='message': messages.append(row['message'])
    errors=sum(m.get('stopReason')=='error' for m in messages)
    usage=[m.get('usage',{}) for m in messages if m.get('role')=='assistant']
    return {'exitCode':code,'timedOut':timed_out,'modelErrors':errors,'seconds':round(time.monotonic()-start,2),
            'usage':{k:sum(u.get(k,0) for u in usage) for k in ('input','output','cacheRead','cacheWrite','totalTokens')}}


def export_tree(c: str, root: str, output: Path, proxy: InferenceProxy) -> None:
    data=checked(['docker','exec',c,'tar','--exclude=node_modules','--exclude=.venv','--exclude=.git','--exclude=__pycache__','--exclude=.pytest_cache','-czf','-','-C',root,'.'])
    # Scan file bodies, not compressed bytes, before retaining any archive.
    sanitized=io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as src,tarfile.open(fileobj=sanitized,mode='w:gz') as dst:
        for item in src:
            if item.isfile():
                content=redact_transport_bytes(src.extractfile(item).read(),proxy);item.size=len(content);dst.addfile(item,io.BytesIO(content))
            else: dst.addfile(item)
    output.write_bytes(sanitized.getvalue())


def protected(c: str, project: str, *, include_source: bool = False) -> dict:
    script='scope_all='+str(include_source)+'\n'+'''import hashlib,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); result={}; configs=[]
for f in p.rglob('*'):
 if not f.is_file() or any(x in f.parts for x in ('.git','.venv','node_modules','__pycache__','.pytest_cache')): continue
 r=str(f.relative_to(p))
 if f.name=='conftest.py' or (f.parent==p and (f.name.endswith(('.ini','.cfg','.json','.yaml','.yml')) or 'config' in f.name or f.name.startswith('.'))): configs.append(r)
 if scope_all or r.startswith(('testing/','test/','tests/')) or f.name=='conftest.py' or (f.parent==p and f.name not in ('index.js','index.d.ts','memory-study.test-d.ts') and (f.suffix.lower() not in ('.md','.rst') or f.name in ('AGENTS.md','CLAUDE.md'))):
  result[r]=hashlib.sha256(f.read_bytes()).hexdigest()
result['__configuration_paths__']=sorted(configs)
print(json.dumps(result))'''
    return json.loads(checked(['docker','exec',c,'python3','-c',script,'/work/'+project]))


def verify(c: str, project: str, proxy: InferenceProxy, output: Path, before: dict) -> dict:
    root='/work/'+project
    # Hidden probes appear only now, after all model execution has ended.
    put(c,'/home/node/oracle/'+('oracle.mjs' if project=='p-limit' else 'test_oracle.py'),
        (P_LIMIT_ORACLE if project=='p-limit' else PLUGGY_ORACLE).encode())
    args=(['node','--test','/home/node/oracle/oracle.mjs'] if project=='p-limit' else
          [root+'/.venv/bin/python','-m','pytest','-q','-c','/dev/null','--confcutdir=/home/node/oracle','/home/node/oracle/test_oracle.py'])
    def check(label: str, command: list[str], seconds: int = 180) -> dict:
        try:
            p=process(['docker','exec','-w',root,*(['-e','PYTEST_DISABLE_PLUGIN_AUTOLOAD=1'] if label=='hidden' else []),c,*command],timeout=seconds)
            (output/(label+'.log')).write_bytes(redact_transport_bytes(p.stdout+p.stderr,proxy))
            return {'exitCode':p.returncode,'passed':p.returncode==0}
        except subprocess.TimeoutExpired:
            return {'exitCode':124,'passed':False,'timedOut':True}
    behavior=check('hidden',args)
    regression=check('upstream',PROJECTS[project]['check'],300)
    types=None
    if project=='p-limit':
        put(c,root+'/memory-study.test-d.ts',P_LIMIT_TYPES.encode())
        types=check('types',['pnpm','exec','tsd','--files','memory-study.test-d.ts'])
    after=protected(c,project); integrity=all(after.get(k)==v for k,v in before.items())
    return {'behavior':behavior,'upstream':regression,'types':types,'existingChecksPreserved':integrity,
            'passed':behavior['passed'] and regression['passed'] and integrity and (types is None or types['passed'])}


def resume_training(root: Path, selection: dict[str, str]) -> dict[str, dict]:
    """Reuse only a verified, matching source-orientation trajectory, never answers."""
    manifest=json.loads((root/'manifest.json').read_text())
    protocol=json.loads((root/'protocol.json').read_text())
    if manifest.get('sourceUnchanged') is not True:
        raise ValueError('Prior source hashes were not preserved')
    if protocol.get('projects') != PROJECTS:
        raise ValueError('Prior project protocol does not match')
    result={}
    for project in PROJECTS:
        target=root/project
        preparation=json.loads((target/'preparation.json').read_text())
        training=preparation.get('training',{})
        if (training.get('exitCode') != 0 or training.get('modelErrors') != 0 or training.get('timedOut') is not False
            or preparation.get('existingChecksPreserved') is not True or preparation.get('trainingUpstreamPassed') is not True):
            raise ValueError('Prior source orientation checks did not pass')
        path=target/'training/session.jsonl';data=path.read_bytes()
        rows=[json.loads(line) for line in data.splitlines()]
        users=[row['message'] for row in rows if row.get('type')=='message' and row.get('message',{}).get('role')=='user']
        text=lambda message: message.get('content') if isinstance(message.get('content'),str) else ''.join(c.get('text','') for c in message.get('content',[]) if c.get('type')=='text')
        models=[row for row in rows if row.get('type')=='model_change']
        if (not rows or rows[0].get('type')!='session' or rows[0].get('cwd')!='/work/'+project
            or len(users)!=1 or text(users[0])!=COMMON+PROJECTS[project]['training'] or not models
            or any(row.get('provider')!=selection['provider'] or row.get('modelId')!=selection['model'] for row in models)):
            raise ValueError('Prior source orientation session or model does not match')
        result[project]={'session':data,'digest':hashlib.sha256(data).hexdigest(),'source':str(path.resolve())}
    return result


def original_observations_preserved(session: bytes, dossiers: list[dict]) -> bool:
    rows=[json.loads(line) for line in session.splitlines()]
    original=[row for row in rows if row.get('type')=='message' and row.get('message',{}).get('role') in {'user','toolResult'}]
    if not any(row['message']['role']=='toolResult' for row in original): return False
    canonical=lambda row: json.dumps(row,sort_keys=True,ensure_ascii=False)
    # A single parent-bound dossier must retain the entire original observation
    # set. Combining unrelated or incomplete runs cannot satisfy this gate.
    return any(set(map(canonical,original)) <= set(map(canonical,dossier.get('taskSlice',{}).get('entries',[]))) for dossier in dossiers)


def prepare(project: str, image: str, proxy: InferenceProxy, sources: Path, output: Path, *, preflight_only: bool = False, resumed: dict | None = None) -> dict:
    c=container(image); target=output/project;target.mkdir()
    try:
        archive=checked(['git','-C',str(sources/project),'archive',PROJECTS[project]['commit']])
        checked(['docker','exec',c,'mkdir','-p','/work/'+project])
        checked(['docker','exec','-i',c,'tar','-xf','-','-C','/work/'+project],data=archive)
        shell(c,'cd /work/'+project+' && git init -q')
        configuration(c,proxy);policy(c,True)
        install=('pnpm install --ignore-scripts' if project=='p-limit' else 'SETUPTOOLS_SCM_PRETEND_VERSION_FOR_PLUGGY=1.7.0 uv sync --python 3.13 --group testing --no-group dev')
        install_result=process(['docker','exec','-w','/work/'+project,c,'bash','-lc',install],timeout=600)
        (target/'install.log').write_bytes(redact_transport_bytes(install_result.stdout+install_result.stderr,proxy))
        if install_result.returncode: raise RuntimeError('Project dependency preparation failed')
        baseline=verify(c,project,proxy,target,protected(c,project))
        if baseline['behavior']['passed'] or not baseline['upstream']['passed']: raise RuntimeError('Oracle RED or upstream baseline gate failed')
        if preflight_only:
            return {'project':project,'baseline':baseline,'preflightPassed':True}
        shell(c,'rm -rf /home/node/oracle; rm -f /work/'+project+'/memory-study.test-d.ts')
        initial=protected(c,project,include_source=True)
        jev_start=len(proxy.jev_usage)
        training_prompt=PROJECTS[project]['training']
        if resumed:
            put(c,RESULTS+'/training-session.jsonl',resumed['session'])
            (target/'training-source-session.jsonl').write_bytes(resumed['session'])
            (target/'training-resume.json').write_text(json.dumps({k:v for k,v in resumed.items() if k!='session'},indent=2))
            training_prompt='The prior read-only source orientation is complete. Use only the existing session original tool observations to give a concise final summary now. Do not make any more tool calls or file changes. Automatic learning decides what to retain; no future feature is requested.'
        training=run_model(c,project,training_prompt,proxy,target/'training','training',continuation=bool(resumed))
        observations_preserved=None
        if resumed:
            training['usageScope']='entire resumed session, including prior source orientation'
            dossiers=json.loads(checked(['docker','exec',c,'python3','-c',
                "import pathlib,json; print(json.dumps([json.loads(p.read_text()) for p in pathlib.Path('/home/node/agent/memory/runs').glob('**/incremental-learning-dossier.json')]))"]))
            observations_preserved=original_observations_preserved(resumed['session'],dossiers)


        export_tree(c,AGENT+'/memory',target/'learned-memory.tar.gz',proxy)
        export_tree(c,'/work/'+project,target/'trained-source.tar.gz',proxy)
        receipt_bytes=checked(['docker','exec',c,'python3','-c',
            "import json,pathlib; print(json.dumps([json.loads(p.read_text()) for p in sorted(pathlib.Path('/home/node/agent/memory/runs').glob('**/learning-pipeline-receipt.json'))]))"])
        receipts=json.loads(receipt_bytes)
        (target/'receipts.json').write_bytes(redact_transport_bytes(json.dumps(receipts,indent=2).encode(),proxy))
        attempts=[a for r in receipts for a in r.get('attempts',[]) if a.get('phase')=='memory']
        applied=any(a.get('outcome')=='applied' and a.get('operations',0)>0 for a in attempts)
        jev=any(a.get('outcome')=='applied' and a.get('operations',0)>0 and a.get('jev',{}).get('status')=='decided' and a.get('jev',{}).get('reason')=='supported' and a.get('jev',{}).get('model')=='jev-1.13.0' and type(a.get('jev',{}).get('inputTokens')) is int for a in attempts) and len(proxy.jev_usage)>jev_start
        training_check=process(['docker','exec','-w','/work/'+project,c,*PROJECTS[project]['check']],timeout=300)
        (target/'training-upstream.log').write_bytes(redact_transport_bytes(training_check.stdout+training_check.stderr,proxy))
        unchanged=all(protected(c,project,include_source=True).get(k)==v for k,v in initial.items())
        valid=training['exitCode']==0 and not training['modelErrors'] and training_check.returncode==0 and unchanged and applied and jev and (not resumed or observations_preserved is True)
        # Freeze the exact same post-training source/dependencies for both arms.
        # Remove all transcripts, snapshots, history and run traces before cloning.
        shell(c,"python3 - <<'PY'\nfrom pathlib import Path\nimport shutil\np=Path('/home/node/agent/memory')\nfor f in p.iterdir():\n if f.name.startswith('--') or f.name=='scopes': continue\n if f.is_dir(): shutil.rmtree(f)\n else: f.unlink()\nshutil.rmtree('/home/node/results');Path('/home/node/results').mkdir()\nPY")
        policy(c,False)
        frozen='cl-real-trained:'+project+'-'+uuid.uuid4().hex[:10]
        checked(['docker','commit',c,frozen])
        result={'project':project,'image':frozen,'training':training,'valid':valid,'memoryApplied':applied,'realJevDecided':jev,
                'originalObservationsPreserved':observations_preserved,'jevResponsesWithUsage':len(proxy.jev_usage)-jev_start,'trainingUpstreamPassed':training_check.returncode==0,'existingChecksPreserved':unchanged,'baseline':baseline}
        (target/'preparation.json').write_text(json.dumps(result,indent=2));return result
    finally: checked(['docker','rm','-f',c])


def candidate(prepared: dict, arm: str, repeat: int, proxy: InferenceProxy, output: Path) -> dict:
    project=prepared['project'];c=container(prepared['image']);target=output/project/f'{repeat}-{arm}';target.mkdir()
    try:
        if arm=='without-memory':
            shell(c,'rm -rf /home/node/agent/memory /work/'+project+'/.memory');policy(c,False)
        initial=protected(c,project)
        model=run_model(c,project,PROJECTS[project]['task'],proxy,target,'task')
        if model['timedOut']:
            result={'project':project,'arm':arm,'repeat':repeat,'model':model,'passed':False,'validPairInput':prepared['valid']}
        else:
            export_tree(c,'/work/'+project,target/'candidate-source.tar.gz',proxy)
            checks=verify(c,project,proxy,target,initial)
            result={'project':project,'arm':arm,'repeat':repeat,'model':model,'checks':checks,
                    'passed':prepared['valid'] and model['exitCode']==0 and not model['modelErrors'] and checks['passed'],'validPairInput':prepared['valid']}
        (target/'result.json').write_text(json.dumps(result,indent=2));return result
    finally: checked(['docker','rm','-f',c])


def run(parent: Path, sources: Path, repeats: int, preflight_only: bool = False, resume_from: Path | None = None) -> dict:
    paths=[*PACKAGE.glob('index.ts'),*(PACKAGE/'extensions').glob('*.ts'),*(PACKAGE/'prompts').glob('*.md'),
           *(REPO/'packages/kit/src').glob('*.ts'),Path(__file__),Path(__file__).with_name('real_project_tasks.py')]
    source_paths={str(p.relative_to(REPO)):p for p in paths}
    if resume_from:
        for project in PROJECTS:
            for name in ('preparation.json','training/session.jsonl'):
                source_paths['resume/'+project+'/'+name]=resume_from/project/name
        for name in ('manifest.json','protocol.json'): source_paths['resume/'+name]=resume_from/name
    e=EvidenceRun(parent,source_paths);print(json.dumps({'started':str(e.output)}),flush=True)
    protocol={'projects':PROJECTS,'repeats':repeats,'order':'alternating arms by repeat','jev':'on for learning',
              'scope':'new authored complex feature tasks on real pinned source; projects previously used in experiments',
              'scoring':'all hidden behavior, public types, full upstream checks and existing-check integrity must pass',
              'noSuccessRequirement':'ties and regressions remain results; technical/training failures invalidate inference',
              'resumeFrom':str(resume_from.resolve()) if resume_from else None}
    e.write('protocol.json',json.dumps(protocol,indent=2));e.write('oracles.json',json.dumps({'p-limit':P_LIMIT_ORACLE,'pluggy':PLUGGY_ORACLE,'types':P_LIMIT_TYPES},indent=2))
    key=os.environ.get('TYPESAFE_API_KEY')
    if not key: raise RuntimeError('Jev credential unavailable')
    report={'status':'running','preparations':[],'candidates':[]}
    try:
        image=runtime_image();report['runtimeImage']=checked(['docker','image','inspect','--format={{.Id}}',image]).decode().strip()
        config=Path(os.environ.get('PI_CODING_AGENT_DIR',str(Path.home()/'.pi/agent')))
        with InferenceProxy(config,jev_key=key,request_budget=1500) as proxy:
            resumed=resume_training(resume_from,proxy.selection) if resume_from else {}
            report['model']={k:proxy.selection[k] for k in ('provider','model')}
            for name in PROJECTS:
                row=prepare(name,image,proxy,sources,e.output,preflight_only=preflight_only,**({'resumed':resumed[name]} if name in resumed else {}));report['preparations'].append(row);print(json.dumps(row),flush=True)
                e.write('manifest.json',json.dumps(report,indent=2))
                if not preflight_only and not row['valid']:
                    raise RuntimeError('Training gate failed; later paid work was not started')
            if not preflight_only and not all(row['valid'] for row in report['preparations']):
                raise RuntimeError('Training gate failed; paired model tasks were not started')
            jobs=[]
            for repeat in range(0 if preflight_only else repeats):
                for row in report['preparations']:
                    for arm in (('without-memory','with-memory') if repeat%2==0 else ('with-memory','without-memory')):
                        jobs.append((row,arm,repeat))
            with ThreadPoolExecutor(max_workers=2) as pool:
                for row in pool.map(lambda j:candidate(*j,proxy,e.output),jobs):
                    report['candidates'].append(row);print(json.dumps(row),flush=True);e.write('manifest.json',json.dumps(report,indent=2))
            report.update({'proxyRequests':proxy.requests,'proxyErrors':proxy.errors,'jevRequests':proxy.jev_requests,'jevUsage':proxy.jev_usage})
        e.verify_sources();report['status']='completed'
    except Exception as error:
        # Never serialize subprocess args/environment or arbitrary transport errors.
        report.update({'status':'failed','errorCategory':type(error).__name__});raise
    finally:
        report.update({'sourceHashes':e.start_hashes,'sourceHashesAfter':e.hashes(),'sourceUnchanged':e.hashes()==e.start_hashes})
        e.write('manifest.json',json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--sources',type=Path,default=Path('/tmp/cl-real-project-inputs'));p.add_argument('--repeats',type=int,default=2);p.add_argument('--preflight-only',action='store_true')
    p.add_argument('--resume-from',type=Path)
    a=p.parse_args();run(a.output,a.sources,a.repeats,a.preflight_only,a.resume_from)
