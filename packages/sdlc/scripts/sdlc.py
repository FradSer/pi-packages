#!/usr/bin/env python3
"""SDLC artifact, evidence and adapter runner. Python 3.11+, Git; no dependencies."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tempfile
from typing import Any, Iterator
from datetime import datetime, timezone

STAGES = ['intent', 'design', 'plan', 'build', 'test', 'review', 'deploy', 'maintain']
DOCS = ['INTENT.md', 'SPEC.md', 'PLAN.md', 'HANDOFF.md', 'REVIEW.md']
SECTIONS = {
    'INTENT.md': ['Problem', 'Proposed outcome', 'Affected users and systems', 'Constraints', 'Open questions'],
    'SPEC.md': ['Requirements', 'Design', 'Constraint mapping', 'Open questions', 'Areas of concern', 'Policy versions'],
    'PLAN.md': ['Changes', 'Sequence', 'Verification', 'Risks and alternatives', 'Policy versions'],
    'HANDOFF.md': ['Current state', 'Decisions', 'Verification', 'Blockers', 'Next steps'],
}
ASSETS = Path(__file__).resolve().parents[1] / 'templates'


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(message)


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        stat = os.fstat(fd)
        import stat as mode
        require(mode.S_ISREG(stat.st_mode) and stat.st_nlink == 1, f'Unsafe document: {path}')
        with os.fdopen(fd, 'r', encoding='utf-8', closefd=False) as stream:
            return stream.read()
    finally:
        os.close(fd)


def write(path: Path, value: Any) -> None:
    text = value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False) + '\n'
    if path.exists() or path.is_symlink():
        read(path)
    fd, temporary = tempfile.mkstemp(prefix='.sdlc-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run(argv: list[str], cwd: Path, data: Any = None, timeout: int = 120) -> dict[str, Any]:
    require(isinstance(argv, list) and bool(argv) and all(isinstance(v, str) and v for v in argv), 'Commands must be nonempty argv arrays')
    require(isinstance(timeout, int) and 1 <= timeout <= 900, 'Command timeout must be 1..900 seconds')
    # A temporary file bounds memory even when an adapter produces large output.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE, stdout=out, stderr=err, start_new_session=True)
        try:
            process.communicate(json.dumps(data).encode() if data is not None else b'', timeout=timeout)
        except BaseException:
            import signal
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise
        out.seek(0); err.seek(0)
        return {'code': process.returncode, 'stdout': out.read(1_000_000).decode(errors='replace'),
                'stderr': err.read(32_000).decode(errors='replace')}


def git(cwd: Path, *args: str) -> str:
    result = run(['git', *args], cwd)
    require(result['code'] == 0, 'Git command failed: ' + result['stderr'])
    return result['stdout'].strip()


def confined(base: Path, name: str) -> Path:
    relative = Path(name)
    require(not relative.is_absolute() and '..' not in relative.parts, 'Path escapes the workspace')
    current = base
    for part in relative.parts:
        current = current / part
        require(not current.is_symlink(), 'Symbolic link in managed path: ' + str(current))
    require(current.resolve().is_relative_to(base.resolve()), 'Path escapes the workspace')
    return current


def local(cwd: Path) -> Path:
    root = cwd / '.sdlc'
    require(not root.is_symlink(), '.sdlc must not be a symbolic link')
    return root


@contextmanager
def locked(cwd: Path) -> Iterator[None]:
    root = local(cwd)
    root.mkdir(exist_ok=True)
    fd = os.open(root / 'lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        require(os.fstat(fd).st_nlink == 1, 'Unsafe SDLC lock')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def config(cwd: Path) -> dict[str, Any]:
    value = json.loads(read(local(cwd) / 'config.json'))
    require(isinstance(value, dict) and value.get('version') == 1, 'Unsupported SDLC configuration')
    return value


def policy(cwd: Path) -> dict[str, Any]:
    name = os.environ.get('SDLC_POLICY_FILE', '')
    require(bool(name) and Path(name).is_absolute(), 'Configure an external SDLC_POLICY_FILE for approvals and service adapters')
    path = Path(name).resolve()
    require(not path.is_relative_to(cwd), 'Approval policy must be outside the agent workspace')
    value = json.loads(read(path))
    require(value.get('version') == 1, 'Unsupported managed policy')
    return value


def doc(cwd: Path, name: str) -> str:
    text = read(cwd / name)
    # Raw source requests are retained but are not approval-bearing requirements.
    if name == 'INTENT.md':
        text = text.split('<!-- intent:event:', 1)[0].rstrip()
    return text


def valid_doc(cwd: Path, name: str) -> None:
    text = doc(cwd, name)
    sections = re.findall(r'^## (.+)$', text, re.M)
    require(all(s in sections for s in SECTIONS[name]), f'{name}: missing required sections')
    require(not re.search(r'Pending summary|\bTODO\b|\bTBD\b|\[REQUIRED\]', text, re.I), f'{name}: unfinished content')
    for section in SECTIONS[name]:
        body = re.split(r'^## ' + re.escape(section) + r'\s*$', text, flags=re.M)[1].split('\n## ', 1)[0].strip()
        require(bool(body), f'{name}: empty {section}')
    if name == 'INTENT.md':
        require(sections == SECTIONS[name], 'INTENT.md: use the exact five course sections')
        require(re.match(r'# Intent: .+\nAuthor: .+\. Status: .+\.', text), 'INTENT.md: missing title, author or status')
    if name in ('SPEC.md', 'PLAN.md', 'HANDOFF.md'):
        require('[INTENT.md](INTENT.md)' in text, f'{name}: missing relative intent link')
    if name == 'PLAN.md':
        require('[SPEC.md](SPEC.md)' in text, 'PLAN.md: missing specification link')
    if name == 'HANDOFF.md':
        require(len(text.splitlines()) < 200, 'HANDOFF.md: must stay below 200 lines')
        require('No task progress has been recorded' not in text and 'Not assessed.' not in text, 'HANDOFF.md: refresh current evidence and blockers')


def snapshot(cwd: Path) -> dict[str, str]:
    files = git(cwd, 'ls-files', '-co', '--exclude-standard', '-z').split('\0')
    tree = {}
    for name in sorted(set(files)):
        if not name or name.split('/')[0] in ('.sdlc', '.git') or name in DOCS:
            continue
        path = cwd / name
        # Hash link targets as text, never follow them into private files.
        if path.is_symlink():
            tree[name] = digest({'link': os.readlink(path)})
        elif path.is_file():
            with path.open('rb') as stream:
                tree[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
        else:
            tree[name] = 'deleted'
    cfg = config(cwd)
    result = {'code': digest(tree), 'config': digest(cfg)}
    suite = cfg.get('evalSuite')
    result['evalSuite'] = digest(read(Path(suite))) if isinstance(suite, str) and Path(suite).is_file() else 'missing'
    managed = os.environ.get('SDLC_POLICY_FILE')
    result['policy'] = digest(read(Path(managed))) if managed and Path(managed).is_file() else 'missing'
    head = run(['git', 'rev-parse', 'HEAD'], cwd)
    result['head'] = head['stdout'].strip() if head['code'] == 0 else 'unborn'
    for name in ('INTENT.md', 'SPEC.md', 'PLAN.md', 'REVIEW.md'):
        if (cwd / name).exists():
            result[name] = digest(doc(cwd, name))
    return result


def binding(cwd: Path, stage: str) -> str:
    current = snapshot(cwd)
    keys = {'intent': ['INTENT.md'], 'design': ['INTENT.md', 'SPEC.md'],
            'plan': ['INTENT.md', 'SPEC.md', 'PLAN.md', 'config', 'evalSuite']}.get(stage)
    return digest({k: current.get(k) for k in keys}) if keys else digest(current)


def approve(cwd: Path, state: dict[str, Any], stage: str, role: str) -> dict[str, Any]:
    request = {'task': state['task'], 'stage': stage, 'role': role, 'digest': binding(cwd, stage)}
    result = run(policy(cwd).get('approve', []), cwd, request)
    require(result['code'] == 0, 'Approval verifier failed')
    answer = json.loads(result['stdout'])
    require(answer.get('approved') is True and all(answer.get(k) == v for k, v in request.items()), 'Missing approval for this task, role and digest')
    require(bool(answer.get('approver')) and bool(answer.get('reference')), 'Approval must name its approver and reference')
    require(binding(cwd, stage) == request['digest'], 'The workspace changed while approval was checked; retry from current evidence')
    return {**answer, 'at': stamp()}


def current_receipt(cwd: Path, state: dict[str, Any], name: str) -> None:
    receipt = state.get('receipts', {}).get(name, {})
    require(receipt.get('passed') is True and receipt.get('digest') == binding(cwd, 'test'), f'{name}: missing, failed or stale evidence; run it again')


def check_approvals(cwd: Path, state: dict[str, Any]) -> None:
    required = {'intent': 1, 'design': 2, 'plan': 3}
    for stage, index in required.items():
        if STAGES.index(state['stage']) >= index:
            require(state.get('approvals', {}).get(stage, {}).get('digest') == binding(cwd, stage), f'{stage}: approval is stale; rewind and review the changed artifact')


def file_tree(root: Path) -> dict[str, str]:
    """Record final edit boundaries, including ignored files, without following links."""
    entries = {}
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = [name for name in folders if name != '.git']
        for name in files + [name for name in folders if (Path(directory) / name).is_symlink()]:
            path = Path(directory) / name
            if path.name == '.git':
                continue
            relative = str(path.relative_to(root))
            if path.is_symlink():
                entries[relative] = digest({'link': os.readlink(path)})
            elif path.is_file():
                with path.open('rb') as stream:
                    entries[relative] = hashlib.file_digest(stream, 'sha256').hexdigest()
            else:
                entries[relative] = 'special-file'
    return entries


def evaluate(cwd: Path, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Each case runs from its historical ref; the grader stays outside the checkout."""
    suite_path = Path(cfg.get('evalSuite', '')).resolve()
    require(suite_path.is_file() and not suite_path.is_relative_to(cwd), 'evalSuite must be an independent file outside the workspace')
    suite = json.loads(read(suite_path))
    require(isinstance(suite, list) and bool(suite), 'Evaluation suite is empty')
    results = []
    for case in suite:
        require(all(k in case for k in ('name', 'from', 'prompt', 'mayChange', 'runner', 'checks')), 'Invalid evaluation case')
        require(bool(case['checks']) and isinstance(case['mayChange'], list), 'Evaluation checks and allowed paths are required')
        with tempfile.TemporaryDirectory(prefix='sdlc-eval-') as folder:
            checkout = Path(folder) / 'work'
            git(cwd, 'worktree', 'add', '--detach', str(checkout), case['from'])
            try:
                # Copy current agent setup onto the historical source before recording baseline.
                for name in cfg.get('agentFiles', []):
                    require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'Invalid agent setup path')
                    source = confined(cwd, name)
                    if source.exists():
                        target = confined(checkout, name)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        write(target, read(source))
                git(checkout, 'add', '-A')
                git(checkout, '-c', 'user.name=SDLC eval', '-c', 'user.email=eval@localhost', 'commit', '--allow-empty', '-qm', 'Agent setup under test')
                baseline = git(checkout, 'rev-parse', 'HEAD')
                initial_files = file_tree(checkout)
                output = run(case['runner'], checkout, {'prompt': case['prompt'], 'cwd': str(checkout)}, case.get('timeout', 120))
                changed = (git(checkout, 'diff', '--name-only', '-z', baseline) + '\0' + git(checkout, 'ls-files', '-o', '--exclude-standard', '-z')).split('\0')
                final_files = file_tree(checkout)
                changed = set(changed) | {p for p in initial_files.keys() | final_files.keys() if initial_files.get(p) != final_files.get(p)}
                stray = sorted(p for p in changed if p and not any(p == a or p.startswith(a.rstrip('/') + '/') for a in case['mayChange']))
                checks = [run(command, checkout, {'baseline': baseline, 'case': case['name']}) for command in case['checks']]
                results.append({'name': case['name'], 'passed': output['code'] == 0 and not stray and all(c['code'] == 0 for c in checks),
                                'stray': stray, 'runnerExit': output['code'], 'checkExits': [c['code'] for c in checks]})
            finally:
                git(cwd, 'worktree', 'remove', '--force', str(checkout))
    return results


def metric_tier(values: list[float]) -> dict[str, Any]:
    require(isinstance(values, list) and len(values) >= 25 and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values), 'Need at least 25 finite hourly readings')
    baseline = values[-721:-1]
    mean = statistics.mean(baseline)
    sigma = max(statistics.stdev(baseline), 0.01)
    tier = 3 if values[-1] > mean + 3 * sigma else 2 if (values[-1] > mean + 2 * sigma or sum(v > mean + sigma for v in values[-5:]) >= 4 or all(v > mean for v in values[-8:])) else 1 if values[-1] > mean + sigma else 0
    return {'tier': tier, 'mean': mean, 'sigma': sigma, 'latest': values[-1]}


def detect_metric(cwd: Path, args: dict[str, Any]) -> dict[str, Any]:
    root = local(cwd)
    detection = metric_tier(args.get('readings'))
    if detection['tier'] >= 2:
        # The diagnostic adapter is read-only by deployment policy. It returns a proto-spec.
        destination = confined(root, 'inbox')
        destination.mkdir(exist_ok=True)
        event = args.get('event')
        require(isinstance(event, str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', event), 'A stable event id is required for metric deduplication')
        target = destination / (event + '.json')
        if target.exists():
            return json.loads(read(target))
        response = run(policy(cwd).get('diagnose', []), cwd, {**detection, 'event': event, 'route': 'read-only-diagnosis', 'evidence': args.get('evidence')})
        require(response['code'] == 0, 'Metric diagnosis failed')
        finding = json.loads(response['stdout'])
        require(isinstance(finding.get('intent'), str) and finding['intent'].startswith('# Intent:'), 'Diagnostic adapter must return an intent proto-spec')
        record = {**detection, 'event': event, 'intent': finding['intent'], 'at': stamp(), 'route': 'product-owner-triage', 'actionsExecuted': False}
        write(target, record)
        write(destination / (event + '.md'), finding['intent'])
        return record
    return {**detection, 'actionsExecuted': False}


def execute(cwd: Path, action: str, args: dict[str, Any]) -> dict[str, Any]:
    root = local(cwd)
    state_path = root / 'state.json'
    if action == 'init':
        git(cwd, 'rev-parse', '--show-toplevel')
        require(not state_path.exists(), 'An active task exists; archive it before starting another')
        task = args.get('task', datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
        require(isinstance(task, str) and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', task), 'Invalid task id')
        require(not confined(root, 'tasks/' + task).exists(), 'This task id already has an archive')
        state = {'version': 1, 'task': task, 'stage': 'intent', 'created': stamp(), 'approvals': {}, 'receipts': {}}
        for name in ('INTENT.md', 'HANDOFF.md'):
            if not (cwd / name).exists():
                write(cwd / name, read(ASSETS / name))
        if not (root / 'config.json').exists():
            write(root / 'config.json', {'version': 1, 'checks': [], 'agentFiles': [], 'evalSuite': None})
        if not (root / '.gitignore').exists():
            write(root / '.gitignore', '*\n!.gitignore\n!config.json\n')
        write(state_path, state)
        return state
    if action == 'metric':
        return detect_metric(cwd, args)
    state = json.loads(read(state_path))
    require(state.get('version') == 1 and state.get('stage') in STAGES, 'Invalid workflow state')
    cfg = config(cwd)
    if action == 'guard':
        tool = args.get('tool', '')
        data = args.get('input', {})
        require(isinstance(data, dict), 'Invalid tool input')
        if re.search(r'(?:^|__)release$', tool):
            raise ValueError('Use the gated deploy action for release tools')
        paths = []
        if tool in ('write', 'edit', 'Write', 'Edit'):
            paths = [data.get('path', data.get('file_path', ''))]
        elif tool == 'apply_patch':
            paths = re.findall(r'^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (.+)$', data.get('command', data.get('patch', '')), re.M)
        if paths and state['stage'] in ('intent', 'design', 'plan'):
            for name in paths:
                target = (cwd / name).resolve()
                require(target.is_relative_to(cwd), 'Write outside the active worktree is not allowed by the SDLC guard')
                relative = str(target.relative_to(cwd))
                require(relative in DOCS or relative == '.sdlc/config.json', 'Approve the implementation plan before editing source files')
        return {'passed': True}
    if action == 'status':
        return {**state, 'currentDigest': binding(cwd, state['stage'])}
    if action == 'handoff':
        valid_doc(cwd, 'HANDOFF.md')
        return {'passed': True, 'digest': digest(doc(cwd, 'HANDOFF.md'))}
    if action == 'rewind':
        stage = args.get('stage')
        require(stage in STAGES and STAGES.index(stage) < STAGES.index(state['stage']), 'Rewind must name an earlier stage')
        state['stage'] = stage
        state['approvals'] = {k: v for k, v in state['approvals'].items() if STAGES.index(k) < STAGES.index(stage)}
        state['receipts'] = {}
    elif action == 'archive':
        require(state['stage'] == 'maintain', 'Only a task that reached maintain can be archived')
        valid_doc(cwd, 'HANDOFF.md')
        require(isinstance(state.get('task'), str) and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', state['task']), 'Invalid saved task id')
        target = confined(root, 'tasks/' + state['task'])
        target.mkdir(parents=True, exist_ok=False)
        for name in DOCS:
            if (cwd / name).exists():
                write(target / name, read(cwd / name))
        write(target / 'state.json', state)
        # Preserve working documents for human inspection. init never overwrites them.
        state_path.unlink()
        return {'archived': str(target), 'next': 'Use a new worktree or explicitly replace the active artifact summaries before init.'}
    elif action in ('check', 'eval', 'review'):
        require(state['stage'] in ('build', 'test', 'review', 'deploy'), 'Evidence requires an approved implementation plan')
        check_approvals(cwd, state)
        before = binding(cwd, 'test')
        for downstream in {'check': ['review', 'deploy'], 'eval': ['review', 'deploy'], 'review': ['deploy']}[action]:
            state['receipts'].pop(downstream, None)
        state['approvals'].pop('review', None)
        state['approvals'].pop('deploy', None)
        state['receipts'][action] = {'passed': False, 'digest': before, 'at': stamp(), 'reason': 'Run started; result pending'}
        write(state_path, state)
        if action == 'check':
            commands = cfg.get('checks')
            require(isinstance(commands, list) and bool(commands), 'Configure at least one verification command before plan approval')
            results = []
            for command in commands:
                result = run(command['argv'], cwd, timeout=command.get('timeout', 120))
                results.append({'name': command['name'], 'exit': result['code'], 'output': result['stdout'], 'error': result['stderr']})
            passed = all(r['exit'] == 0 for r in results)
        elif action == 'eval':
            results = evaluate(cwd, cfg)
            passed = all(r['passed'] for r in results)
        else:
            current_receipt(cwd, state, 'check')
            current_receipt(cwd, state, 'eval')
            request = {'task': state['task'], 'digest': before, 'passes': ['bugs', 'security', 'compliance'], 'artifacts': ['INTENT.md', 'SPEC.md', 'PLAN.md', 'REVIEW.md']}
            answer = run(policy(cwd).get('review', []), cwd, request)
            results = json.loads(answer['stdout']) if answer['code'] == 0 else {}
            passed = answer['code'] == 0 and results.get('digest') == before and results.get('passes') == request['passes'] and type(results.get('important')) is int and results.get('important') == 0 and isinstance(results.get('findings'), list)
        receipt = {'digest': before, 'passed': passed and before == binding(cwd, 'test'), 'at': stamp(), 'results': results}
        state['receipts'][action] = receipt
    elif action == 'advance':
        stage = state['stage']
        check_approvals(cwd, state)
        valid_doc(cwd, 'HANDOFF.md')
        if stage in ('intent', 'design', 'plan'):
            name = {'intent': 'INTENT.md', 'design': 'SPEC.md', 'plan': 'PLAN.md'}[stage]
            valid_doc(cwd, name)
            if stage == 'plan':
                require(bool(cfg.get('checks')) and bool(cfg.get('evalSuite')), 'Configure checks and independent evalSuite before approving the plan')
            state['approvals'][stage] = approve(cwd, state, stage, 'engineer' if stage == 'plan' else 'product-owner')
        elif stage == 'test':
            current_receipt(cwd, state, 'check'); current_receipt(cwd, state, 'eval')
        elif stage == 'review':
            current_receipt(cwd, state, 'check'); current_receipt(cwd, state, 'eval'); current_receipt(cwd, state, 'review')
            state['approvals']['review'] = approve(cwd, state, stage, 'code-owner')
        elif stage == 'deploy':
            for name in ('check', 'eval', 'review', 'deploy'):
                current_receipt(cwd, state, name)
            require(state['approvals'].get('review', {}).get('digest') == binding(cwd, 'review'), 'Code owner approval is stale')
        require(stage != 'maintain', 'Maintain waits for metrics or archive, not another stage')
        state['stage'] = STAGES[STAGES.index(stage) + 1]
    elif action == 'deploy':
        require(state['stage'] == 'deploy', 'Deployment requires the deploy stage')
        state['receipts']['deploy'] = {'passed': False, 'at': stamp(), 'reason': 'Deployment requested; result pending'}
        write(state_path, state)
        check_approvals(cwd, state)
        for name in ('check', 'eval', 'review'):
            current_receipt(cwd, state, name)
        require(state['approvals'].get('review', {}).get('digest') == binding(cwd, 'review'), 'Code owner approval is stale')
        state['approvals']['review'] = approve(cwd, state, 'review', 'code-owner')
        environment = args.get('environment', 'dev')
        require(environment in ('dev', 'staging', 'production'), 'Invalid deployment environment')
        adapters = policy(cwd).get('environments', {}).get(environment, {})
        require(all(adapters.get(k) for k in ('release', 'status', 'rollback')), 'Configure release, status and rollback adapters')
        if environment != 'dev':
            approval = approve(cwd, state, 'deploy', 'release-manager' if environment == 'production' else 'engineer')
            state['approvals']['deploy'] = approval
        pinned = snapshot(cwd)
        before = digest(pinned)
        for name in ('check', 'eval', 'review'):
            require(state['receipts'][name]['digest'] == before, 'Evidence changed during release approval')
        require(state['approvals']['review']['digest'] == before, 'Code owner approval changed during release approval')
        if environment != 'dev':
            require(state['approvals']['deploy']['digest'] == before, 'Release approval does not match the pinned version')
        request = {'task': state['task'], 'environment': environment, 'digest': before, 'version': pinned['head']}
        require(request['version'] != 'unborn' and not git(cwd, 'status', '--porcelain', '--untracked-files=normal'), 'Deploy only a clean committed revision; commit artifacts and source first')
        require(binding(cwd, 'test') == before, 'Workspace changed before release; rerun verification')
        release, status, rollback = {'code': -1}, {'code': -1}, None
        healthy = False
        failure = None
        try:
            release = run(adapters['release'], cwd, request, adapters.get('timeout', 120))
            if release['code'] == 0:
                status = run(adapters['status'], cwd, request, adapters.get('timeout', 120))
                healthy = status['code'] == 0 and json.loads(status.get('stdout', '{}')).get('healthy') is True
        except (Exception, KeyboardInterrupt) as error:
            failure = type(error).__name__ + ': ' + str(error)
        finally:
            if not healthy:
                try:
                    rollback = run(adapters['rollback'], cwd, request, adapters.get('timeout', 120))
                except (Exception, KeyboardInterrupt) as error:
                    rollback = {'code': -1}
                    failure = (failure or '') + '; rollback: ' + type(error).__name__ + ': ' + str(error)
            state['receipts']['deploy'] = {'passed': healthy and before == binding(cwd, 'test'), 'digest': before, 'at': stamp(), 'environment': environment,
                'releaseExit': release['code'], 'statusExit': status['code'], 'rollbackExit': rollback['code'] if rollback else None, 'failure': failure}
            write(state_path, state)
    else:
        raise ValueError('Unknown action: ' + action)
    state['updated'] = stamp()
    write(state_path, state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'status', 'guard', 'handoff', 'advance', 'rewind', 'archive', 'check', 'eval', 'review', 'deploy', 'metric'])
    parser.add_argument('--cwd', type=Path, default=Path.cwd())
    parser.add_argument('--args', default='{}', help='JSON action arguments; adapter input is sent through stdin')
    options = parser.parse_args()
    import signal
    def interrupted(_signal: int, _frame: Any) -> None:
        raise KeyboardInterrupt('SDLC command interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    try:
        cwd = options.cwd.resolve(strict=True)
        args = json.loads(options.args)
        require(isinstance(args, dict), 'Action arguments must be an object')
        with locked(cwd):
            result = execute(cwd, options.action, args)
        print(json.dumps(result, ensure_ascii=False))
        if options.action in ('check', 'eval', 'review', 'deploy') and result.get('receipts', {}).get(options.action, {}).get('passed') is not True:
            return 1
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({'error': str(error), 'action': options.action}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
