"""Explicit real-Pi AGENTS reliability probe, retaining child transport failures."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import signal
import tempfile
from live_acceptance_support import EvidenceRun, isolated_environment, private_provider_copy, workspace_pi

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
PROMPT = ('Our AGENTS.md instruction is wrong: the progress reporting workflow is instead '
          'one short status line, not a paragraph. This is a durable requirement for future tasks. '
          'Update the project guidance through automatic learning. Reply only: acknowledged.')

FULL_PROMPT = ('For my personal replies, I prefer the sign-off marker PRIVATE_PREF_QUARTZ; this is private preference data and must never become a project Memory entry. Also record this project fact as settled shared knowledge: PROJECT_FACT_CALDERA is the release marker for this project. The existing project_smoke_build_command.md Memory entry is stale: update it from `bun run check` to `bun run verify`, and use the updated command in future tasks. Also, never run retired-smoke-compiler through bash: it is prohibited in this project. Our AGENTS.md instruction is wrong: the progress reporting workflow is instead one short status line, not a paragraph. All of these are durable requirements for future tasks. Reply only: acknowledged.')


def terminate_recorded_groups(registry: Path | None) -> None:
    """The Pi child helper detaches planners; the CLI group alone cannot stop them."""
    if registry is None or not registry.exists():
        return
    active: set[int] = set()
    for line in registry.read_text().splitlines():
        row = json.loads(line)
        if row.get('event') == 'started': active.add(row['pid'])
        else: active.discard(row['pid'])
    for pid in active:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pid, sig)
            except ProcessLookupError:
                break


def communicate_bounded(child: subprocess.Popen, timeout: float, registry: Path | None = None) -> tuple[int, bytes, bytes, bool]:
    """Stop the entire disposable CLI group and retain its terminal failure bytes."""
    try:
        stdout, stderr = child.communicate(timeout=timeout)
        return child.returncode, stdout, stderr, False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        terminate_recorded_groups(registry)
        try:
            stdout, stderr = child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = child.communicate()
        terminate_recorded_groups(registry)
        return 124, stdout, stderr, True


def trial(number: int, output: Path, source: Path, model: dict, full_pipeline: bool = False) -> dict:
    target=output/f'trial-{number}';target.mkdir()
    with tempfile.TemporaryDirectory(prefix='cl-agents-reliability-') as temporary:
        base=Path(temporary).resolve(); project=base/'project';project.mkdir();agent=base/'agent';agent.mkdir(mode=0o700)
        secrets=private_provider_copy(source,agent,model['provider'])
        def archive(name: str, data: bytes) -> None:
            if any(secret in data for secret in secrets): raise RuntimeError('Credential evidence refused')
            dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        (agent/'memory').mkdir();(agent/'memory.json').write_text(json.dumps(model));(agent/'settings.json').write_text('{"packages":[]}')
        (agent/'continual-learning.json').write_text('{"jev":false}')
        (agent/'memory/settings.json').write_text(json.dumps({'autoMemory':True,'automaticPhases':{'memory':'off','harness':'off','agents':'apply'},'agentsMd':{'disabled':False}}))
        (project/'AGENTS.md').write_text('# Project instructions\n\n## Progress reporting\n\nReport progress as a paragraph describing what changed and why.\n')
        subprocess.run(['git','init','-q',str(project)],check=True)
        if full_pipeline:
            (agent/'memory/settings.json').write_text(json.dumps({'autoMemory':True,'agentsMd':{'disabled':False}}))
            scope='--'+str(project).lstrip('/').replace('/','-')+'--'
            registry=agent/'memory/scopes';registry.mkdir();(registry/(scope+'.json')).write_text(json.dumps({'version':1,'cwd':str(project)}))
            root=agent/'memory'/scope;root.mkdir()
            entries={'project_smoke_build_command.md':'The settled build and verification command for this project is `bun run check`.','feedback_smoke_progress_line.md':'Progress updates in this project are reported as one short status line.'}
            for name,body in entries.items():(root/name).write_text('---\nname: '+name[:-3]+'\ndescription: '+body+'\ntype: project\n---\n\n'+body+'\n')
            (root/'MEMORY.md').write_text('# Memory\n\n'+''.join('- ['+name+']('+name+')\n' for name in entries))
        before=(project/'AGENTS.md').read_bytes()
        capture=base/'capture';capture.mkdir()
        probe=base/'capture.ts'
        probe.write_text("import cp from 'node:child_process';import fs from 'node:fs';import {syncBuiltinESMExports} from 'node:module';const original=cp.spawn;cp.spawn=function(command,args,options){const child=original.call(this,command,args,options);if(options?.detached&&child.pid){const record=event=>fs.appendFileSync("+json.dumps(str(capture/'children.jsonl'))+",JSON.stringify({pid:child.pid,event})+'\\n');record('started');child.once('exit',()=>record('exited'));}if(Array.isArray(args)&&args.some(a=>typeof a==='string'&&a.includes('agents-task.md'))){child.stdout?.on('data',b=>fs.appendFileSync("+json.dumps(str(capture/'agents-stdout.jsonl'))+",b));child.stderr?.on('data',b=>fs.appendFileSync("+json.dumps(str(capture/'agents-stderr.txt'))+",b));}return child;};syncBuiltinESMExports();export default function(){};")
        session=base/'session.jsonl'
        proc=subprocess.Popen([workspace_pi(REPO),'--offline','--no-extensions','-e',str(probe),'-e',str(PACKAGE/'index.ts'),'--no-skills','--no-prompt-templates','--no-themes','--no-context-files','--no-builtin-tools','--no-approve','--thinking','off','--model',model['provider']+'/'+model['model'],'--session',str(session),'--print','--mode','json',FULL_PROMPT if full_pipeline else PROMPT],cwd=project,env=isolated_environment(base,agent),stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        code,stdout,stderr,timed_out=communicate_bounded(proc,300,capture/'children.jsonl')
        archive('main-stdout.jsonl',stdout);archive('main-stderr.txt',stderr)
        if session.exists():archive('session.jsonl',session.read_bytes())
        for f in capture.iterdir():archive(f.name,f.read_bytes())
        for f in (agent/'memory/runs').rglob('*'):
            if f.is_file() and f.suffix in {'.json','.jsonl','.txt','.md'}:archive(str(Path('runs')/f.relative_to(agent/'memory/runs')),f.read_bytes())
        archive('before-AGENTS.md',before);archive('after-AGENTS.md',(project/'AGENTS.md').read_bytes())
        receipts=[json.loads(f.read_text()) for f in target.glob('runs/**/learning-pipeline-receipt.json')]
        phases=[a for r in receipts for a in r.get('attempts',[]) if a.get('phase')=='agents']
        result={'trial':number,'exitCode':code,'timedOut':timed_out,'agentsAttempts':phases,'changed':before!=(project/'AGENTS.md').read_bytes(),'childTransportCaptured':(target/'agents-stdout.jsonl').exists()}
        archive('result.json',json.dumps(result,indent=2).encode());return result


def run(parent: Path, trials: int, full_pipeline: bool = False) -> dict:
    source=Path(os.environ.get('PI_CODING_AGENT_DIR',str(Path.home()/'.pi/agent')));cfg=json.loads((source/'memory.json').read_text());model={k:cfg[k] for k in ('provider','model')}
    sources=[*PACKAGE.glob('index.ts'),*(PACKAGE/'extensions').glob('*.ts'),*(PACKAGE/'prompts').glob('*.md'),Path(__file__)]
    e=EvidenceRun(parent,{str(f.relative_to(REPO)):f for f in sources});e.write('prompt.txt',FULL_PROMPT if full_pipeline else PROMPT)
    report={'status':'running','model':model,'trials':[]};e.write('manifest.json',json.dumps(report,indent=2));print(json.dumps({'started':str(e.output)}),flush=True)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            for row in pool.map(lambda n:trial(n,e.output,source,model,full_pipeline),range(trials)):
                report['trials'].append(row);print(json.dumps(row),flush=True)
        e.verify_sources();report.update({'status':'completed','sourceUnchanged':True,'passed':all(r['exitCode']==0 and r['changed'] and r['childTransportCaptured'] and any(a.get('outcome')=='applied' for a in r['agentsAttempts']) and not any(a.get('outcome') in {'failed','rejected','cancelled'} for a in r['agentsAttempts']) for r in report['trials'])})
    except Exception as error:
        report.update({'status':'failed','passed':False,'errorCategory':type(error).__name__})
        raise
    finally:
        report['sourceHashes']=e.start_hashes;report['sourceHashesAfter']=e.hashes();e.write('manifest.json',json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);parser.add_argument('--trials',type=int,default=4);parser.add_argument('--full-pipeline',action='store_true');args=parser.parse_args();run(args.output,args.trials,args.full_pipeline)
