"""Explicit real-model paired downstream task study; never collected as a live pytest.

Usage: uv run --no-project .../live_memory_task_quality.py OUTPUT_PARENT --split development
No model-generated judge or fabricated Memory is used. Each case learns through
actual Pi, then runs two fresh sessions with identical task/files and same cwd.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from live_acceptance_support import EvidenceRun, isolated_environment, preflight, private_provider_copy, workspace_pi
from memory_task_quality_cases import cases

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]


def score(artifact: object, case: dict) -> dict:
    valid = isinstance(artifact, dict) and set(artifact) == {'value'} and isinstance(artifact['value'], str)
    actual = artifact['value'] if valid else None
    return {'correct': valid and actual == case['expected'], 'actual': actual,
            'expected': case['expected'], 'obsoleteUsed': actual == case['obsolete'], 'unsupportedAnswer': valid and actual not in {case['expected'],'unknown'}, 'artifactValid': valid}


def task_snapshot(project: Path) -> dict[str, str]:
    result = {}
    for p in project.rglob('*'):
        if p.is_symlink(): raise RuntimeError('Task mutated project into symlink')
        if p.is_file() and p != project/'answer.json':
            result[str(p.relative_to(project))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def assert_task_unchanged(project: Path, before: dict[str, str]) -> None:
    if task_snapshot(project) != before:
        raise RuntimeError('Task mutated frozen project evidence or left cross-arm files')


def learning_receipts(messages: list[dict]) -> list[dict]:
    messages = [r.get('message',r) for r in messages]
    return [m['details'] for m in messages if m.get('customType') == 'continual-learning-result'
            and isinstance(m.get('details'),dict) and m['details'].get('kind') == 'learning-pipeline-receipt']


def training_ok(row: dict) -> bool:
    for task in row.get('training',[]):
        if task.get('exitCode') != 0 or task.get('errors') or task.get('error'):
            return False
        if not task.get('receipts'): return False
        for receipt in task.get('receipts',[]):
            if not isinstance(receipt,dict): return False
            last = {a.get('phase'):a.get('outcome') for a in receipt.get('attempts',[])}
            if any(v in {'failed','rejected','cancelled'} for v in last.values()): return False
    return True


def summarize(rows: list[dict]) -> dict:
    invalid = [r['id'] for r in rows if r.get('error') or any(r[arm].get('error') or r[arm].get('errors')
               or r[arm].get('exitCode',0) != 0 for arm in ('baseline','memory'))]
    valid = [r for r in rows if r['id'] not in invalid]
    improvements = [r['id'] for r in valid if r['memory']['correct'] and not r['baseline']['correct']]
    regressions = [r['id'] for r in valid if r['baseline']['correct'] and not r['memory']['correct']]
    groups = {c: {arm: sum(r[arm]['correct'] for r in valid if r['category'] == c) for arm in ('baseline', 'memory')}
              | {'cases': sum(r['category'] == c for r in valid)} for c in sorted({r['category'] for r in rows})}
    training_failures = [r['id'] for r in rows if not training_ok(r)]
    return {'trainingFailures': training_failures, 'invalidPairs':invalid, 'pairs': len(rows), 'validPairs':len(valid),
            'baselineCorrect': sum(r['baseline']['correct'] for r in valid),
            'memoryCorrect': sum(r['memory']['correct'] for r in valid), 'improvements': improvements,
            'regressions': regressions, 'harmfulMemoryAnswers':[r['id'] for r in valid if r['memory'].get('unsupportedAnswer')],
            'newHarm':[r['id'] for r in valid if r['memory'].get('unsupportedAnswer') and not r['baseline'].get('unsupportedAnswer')], 'categories': groups,
            'acceptance': bool(rows) and bool(improvements) and not regressions and not invalid and not training_failures
                          and all(r['memory']['correct'] for r in rows),
            'limits': ['Small authored synthetic corpus; not statistical proof or general capability.',
                       'Same provider/model; temperature is provider default, no seed guarantee.',
                       'Jev disabled explicitly; does not establish Jev-on behavior.',
                       'Training is real automatic learning; fresh task sessions have no training transcript.',
                       'Scores use exact written artifacts, not learning success or a model judge.']}


def run_case(case: dict, evidence: EvidenceRun, source: Path, model: dict, order: list[str]) -> dict:
    directory = evidence.output / case['id']; directory.mkdir()
    secrets: list[bytes] = []
    def archive(name: str, data: str) -> None:
        raw = data.encode()
        if any(secret in raw for secret in secrets):
            raise RuntimeError('Credential in evidence; capture refused')
        (directory / name).write_bytes(raw)
    with tempfile.TemporaryDirectory(prefix='cl-quality-') as raw:
        base = Path(raw).resolve(); project = base / 'project'; project.mkdir()
        subprocess.run(['git', 'init', '-q', str(project)], check=True)
        agents = {}
        for arm in ('memory', 'baseline'):
            agent = base / arm; agent.mkdir(mode=0o700); (agent / 'memory').mkdir()
            agents[arm] = agent
            secrets.extend(private_provider_copy(source, agent, model['provider']))
            (agent / 'settings.json').write_text(json.dumps({'packages': [], 'quietStartup': True}))
            (agent / 'continual-learning.json').write_text('{"jev":false}')
            (agent / 'memory.json').write_text(json.dumps(model))
            (agent / 'memory/settings.json').write_text(json.dumps({'autoMemory': arm == 'memory',
                'automaticPhases': {'memory': 'apply', 'harness': 'off', 'agents': 'off'}, 'agentsMd': {'disabled': True}}))
            preflight(base, project, agent, isolated_environment(base, agent), real_model=True)
        probe = base/'probe.ts'
        notify = base/'notifications.jsonl'
        probe.write_text("import fs from 'node:fs';export default function(pi){pi.on('session_start',(_e,ctx)=>{const old=ctx.ui.notify.bind(ctx.ui);ctx.ui.notify=(message,level)=>{fs.appendFileSync("+json.dumps(str(notify))+",JSON.stringify({message,level})+'\\n');return old(message,level)}})}")
        def invoke(agent: Path, prompt: str, name: str, learning: bool) -> dict:
            evidence.verify_sources()
            session = base / (name + '.jsonl')
            cmd = [workspace_pi(REPO), '--offline', '--no-extensions', '-e', str(PACKAGE/'index.ts'),
                   '-e', str(probe), '--no-skills', '--no-prompt-templates', '--no-themes', '--no-context-files',
                   '--no-approve', '--thinking', 'off', '--session', str(session), '--print', '--mode', 'json',
                   '--model', model['provider']+'/'+model['model']]
            cmd += ['--no-builtin-tools'] if learning else ['--tools', 'read,write']
            before_receipts = {(str(p),p.stat().st_mtime_ns,p.stat().st_ino) for p in (agent/'memory/runs').glob('**/learning-pipeline-receipt.json')}
            started = time.monotonic()
            try:
                proc = subprocess.run([*cmd, prompt], cwd=project, env=isolated_environment(base,agent),
                                      capture_output=True, text=True, timeout=600 if learning else 180)
            except subprocess.TimeoutExpired as error:
                archive(name+'.partial.stdout.jsonl', (error.stdout or b'').decode(errors='replace') if isinstance(error.stdout,bytes) else error.stdout or '')
                archive(name+'.partial.stderr.txt', (error.stderr or b'').decode(errors='replace') if isinstance(error.stderr,bytes) else error.stderr or '')
                if session.exists(): archive(name+'.partial.session.jsonl',session.read_text())
                return {'error': 'process-timeout', 'seconds': round(time.monotonic()-started,2)}
            archive(name+'.stdout.jsonl', proc.stdout)
            archive(name+'.stderr.txt', proc.stderr)
            records = [json.loads(line) for line in session.read_text().splitlines()] if session.exists() else []
            archive(name+'.session.jsonl', '\n'.join(json.dumps(r) for r in records))
            messages = [r['message'] for r in records if r.get('type') == 'message']
            errors = [m.get('errorMessage','model-error') for m in messages if m.get('stopReason') == 'error']
            receipts = learning_receipts(records)
            current_receipts = [json.loads(p.read_text()) for p in (agent/'memory/runs').glob('**/learning-pipeline-receipt.json')
                                if (str(p),p.stat().st_mtime_ns,p.stat().st_ino) not in before_receipts]
            if current_receipts: receipts = current_receipts
            archive(name+'-receipts.json', json.dumps(receipts,indent=2))
            tools = [{'name':b.get('name'), 'arguments':b.get('arguments')} for m in messages if m.get('role') == 'assistant'
                     for b in m.get('content',[]) if b.get('type') == 'toolCall']
            return {'exitCode': proc.returncode, 'errors': errors, 'receipts': receipts, 'tools':tools,
                    'seconds': round(time.monotonic()-started,2), 'contextIsFresh': True}
        training = []
        for i, prompt in enumerate(case['training']):
            result = invoke(agents['memory'], prompt + '\nFor this acknowledgement task, reply only "acknowledged".', f'train-{i}', True)
            training.append(result)
            if notify.exists(): archive(f'train-{i}-notifications.jsonl',notify.read_text())
            for artifact in (agents['memory']/'memory/runs').rglob('*'):
                if artifact.is_file() and artifact.suffix in {'.json','.jsonl','.md','.txt'}:
                    target = directory/f'train-{i}-artifacts'/artifact.relative_to(agents['memory']/'memory/runs')
                    target.parent.mkdir(parents=True,exist_ok=True)
                    archive(str(target.relative_to(directory)),artifact.read_text())
            archive(f'train-{i}-memory.json', json.dumps({str(p.relative_to(agents['memory']/'memory')):p.read_text()
                    for p in (agents['memory']/'memory').glob('--*--/*.md')},indent=2))
        # Freeze learned entries before either task. No manual seeding/repair.
        learned = {str(p.relative_to(agents['memory']/'memory')):p.read_text()
                   for p in (agents['memory']/'memory').glob('--*--/*.md')}
        archive('learned-memory.json', json.dumps(learned, indent=2))
        for name, contents in case['files'].items():
            (project/name).write_text(json.dumps(contents))
        settings = agents['memory']/'memory/settings.json'
        value = json.loads(settings.read_text()); value['autoMemory'] = False; settings.write_text(json.dumps(value))
        row = {'id':case['id'], 'category':case['category'], 'training':training, 'armOrder':order,
               'learnedEntries':len([p for p in learned if not p.endswith('/MEMORY.md')])}
        for arm in order:
            answer = project/'answer.json'
            answer.unlink(missing_ok=True)
            public = project/'.memory'; stash = base/'public-stash'
            if arm == 'baseline' and public.exists(): shutil.move(str(public), stash)
            before_task = task_snapshot(project)
            try:
                result = invoke(agents[arm], case['task'] + '\nProject working directory: ' + str(project) + '\nCurrent input files: ' + (', '.join(case['files']) or 'none') + '\nThis file inventory is complete; do not search for nonexistent project files. Only current input files and retrieved established Memory can supply project facts. Write exactly ' + str(answer) + '.', arm, False)
                assert_task_unchanged(project,before_task)
                try: artifact = json.loads(answer.read_text())
                except (OSError, ValueError): artifact = None
                archive(arm+'-answer.json',json.dumps(artifact))
                scored = score(artifact,case)
                if result.get('exitCode') != 0 or result.get('errors') or result.get('error'):
                    scored['correct'] = False
                row[arm] = {**scored, **result}
            finally:
                if arm == 'baseline' and stash.exists(): shutil.move(str(stash),public)
        after = {str(p.relative_to(agents['memory']/'memory')):p.read_text()
                 for p in (agents['memory']/'memory').glob('--*--/*.md')}
        if after != learned: raise RuntimeError('Follow-up task mutated learned Memory')
        archive('result.json',json.dumps(row,indent=2))
        return row


def run(parent: Path, split: str, workers: int = 2, only: list[str] | None = None, task_type: str = 'recall') -> dict:
    sources = [*PACKAGE.glob('index.ts'), *sorted((PACKAGE/'extensions').rglob('*.ts')),
               *sorted((PACKAGE/'prompts').glob('*.md')), *sorted((PACKAGE/'scripts').glob('*.py')),
               *sorted((REPO/'packages/kit/src').rglob('*.ts')),
               *[Path(__file__),Path(__file__).with_name('memory_task_quality_cases.py'),Path(__file__).with_name('live_acceptance_support.py')]]
    evidence = EvidenceRun(parent,{str(p.relative_to(REPO)):p for p in sources})
    corpus = cases(split,task_type)
    if only:
        if set(only) - {c['id'] for c in corpus}: raise ValueError('Unknown selected case')
        corpus = [c for c in corpus if c['id'] in only]
    evidence.write('corpus.json',json.dumps(corpus,indent=2))
    source = Path(os.environ.get('PI_CODING_AGENT_DIR',str(Path.home()/'.pi/agent')))
    config = json.loads((source/'memory.json').read_text())
    model = {key:config[key] for key in ('provider','model')}
    report = {'status':'running','split':split,'taskType':task_type,'providerModel':model,'outputDir':str(evidence.output),
              'piVersion':subprocess.run([workspace_pi(REPO),'--version'],capture_output=True,text=True,check=True).stdout.strip(),
              'revision':subprocess.run(['git','rev-parse','HEAD'],cwd=REPO,capture_output=True,text=True,check=True).stdout.strip(),
              'localChanges':subprocess.run(['git','status','--short'],cwd=REPO,capture_output=True,text=True,check=True).stdout.splitlines(),
              'corpusSha256':hashlib.sha256((evidence.output/'corpus.json').read_bytes()).hexdigest(),
              'sourceHashes':evidence.start_hashes,'rows':[], 'jev':False}
    evidence.write('manifest.json',json.dumps(report,indent=2))
    print(json.dumps({'started':str(evidence.output),'split':split}),flush=True)
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(run_case,c,evidence,source,model,['baseline','memory'] if i%2==0 else ['memory','baseline']):c for i,c in enumerate(corpus)}
            for future in as_completed(futures):
                case = futures[future]
                try: row = future.result()
                except Exception as error:
                    row = {'id':case['id'],'category':case['category'],'error':type(error).__name__,'diagnostic':str(error) if isinstance(error,RuntimeError) else 'Run failed; inspect retained evidence',
                           'baseline':{'correct':False},'memory':{'correct':False}}
                report['rows'].append(row)
                evidence.write('checkpoint.json',json.dumps(report,indent=2))
                print(json.dumps({'case':row['id'],'baseline':row['baseline']['correct'],'memory':row['memory']['correct'],'error':row.get('error')}),flush=True)
        evidence.verify_sources()
        report.update({'status':'completed','sourceUnchanged':True,'summary':summarize(report['rows'])})
    finally:
        report['sourceHashesAfter']=evidence.hashes()
        if report['sourceHashesAfter'] != report['sourceHashes']:
            report.update({'status':'invalid-source-drift','sourceUnchanged':False})
        evidence.write('manifest.json',json.dumps(report,indent=2))
        write_report(evidence.output,report)
    return report


def write_report(output: Path, report: dict) -> None:
    rows = sorted(report['rows'],key=lambda r:r['id'])
    lines=['# 真实模型有无记忆对照评测','',f"状态：{report['status']}；Pi {report['piVersion']}；分组：{report['split']}。",
           '', '两组使用相同任务、当前文件和同一模型；各自使用全新 session。训练和自动学习仅发生在有记忆组；后续两组都关闭自动学习。',
           '', '| 样本 | 无记忆正确 | 有记忆正确 | 无记忆答案 | 有记忆答案 |', '|---|---|---|---|---|']
    for r in rows:
        lines.append(f"| {r['id']} | {r['baseline']['correct']} | {r['memory']['correct']} | {r['baseline'].get('actual')} | {r['memory'].get('actual')} |")
    lines += ['', '```json', json.dumps(report.get('summary',{}),ensure_ascii=False,indent=2),'```','',
              '这是小规模人工编写的合成任务，不构成统计显著性或普遍能力证明。模型错误、学习拒绝与实际任务错误均保留，不以流程成功代替任务正确。',
              f'[完整记录]({output}/manifest.json) · [运行前固定语料与答案]({output}/corpus.json)']
    (output/'report.zh-CN.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=Path);parser.add_argument('--split',choices=['development','heldout'],required=True)
    parser.add_argument('--workers',type=int,choices=[1,2],default=2)
    parser.add_argument('--task-type',choices=['recall','resolve'],default='recall')
    parser.add_argument('--case-id',action='append')
    args=parser.parse_args()
    result=run(args.output,args.split,args.workers,args.case_id,args.task_type)
    print(json.dumps({'outputDir':result['outputDir'],'status':result['status'],'summary':result.get('summary')}),flush=True)
