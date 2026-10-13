"""Explicit real-project /memory maintenance reproduction in a disposable copy.

Preflight is offline. Real execution uses actual configured models and Jev,
actual old Memory, current project bytes and the native slash command. No future
answer or synthetic fact is seeded; source/Memory writes outside the copy are
forbidden by the product worker scopes. Failures and partial costs are retained.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from docker_experiment import InferenceProxy, redact_transport_bytes
from live_manual_memory import NativeTui
from support import REPO

TESTS = Path(__file__).resolve().parent
FORBIDDEN = re.compile(r'^(?:\.git|node_modules|\.memory|\.pi|\.env(?:\..*)?|\.dev\.vars(?:\..*)?|auth\.json|credentials(?:\..*)?|id_(?:rsa|ed25519)|.*\.(?:pem|key|p12|pfx))$', re.I)


def digest(file: Path) -> str:
    return hashlib.sha256(file.read_bytes()).hexdigest()


def prepare_learning_settings(agent: Path) -> None:
    file = agent / 'memory/settings.json'
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps({'autoMemory': False}))
    file.chmod(0o600)


def scoped_paths(cwd: Path, env: dict[str, str]) -> dict:
    code = 'import {resolveMemoryPaths} from ' + json.dumps(str(TESTS.parent / 'extensions/memory-paths.ts')) + '; console.log(JSON.stringify(resolveMemoryPaths(process.argv[1])));'
    return json.loads(subprocess.check_output(['bun', '-e', code, str(cwd)], env=env, cwd=REPO, text=True))


def private_review_config(planner_json_output: bool, planner_structured_output: bool = False) -> dict:
    # Explicit experiment opt-in for the already wire-verified gateway only.
    return {'jev': {'model': 'jev-1.13.0'}, **({'plannerJsonOutput': True} if planner_json_output else {}),
            **({'plannerStructuredOutput': True} if planner_structured_output else {})}


def inference_request_counts(proxy: InferenceProxy) -> dict[str, int]:
    """The proxy total includes Jev; do not charge those requests twice."""
    return {'transportRequests': proxy.requests, 'modelRequests': proxy.requests - proxy.jev_requests,
            'jevRequests': proxy.jev_requests}


def run(output: Path, project: Path, *, preflight_only: bool, snapshot: Path | None = None,
        approve_private_review: bool = False, request_budget: int = 100, planner_json_output: bool = False, planner_structured_output: bool = False) -> dict:
    if not 1 <= request_budget <= 100:
        raise ValueError('Private replay request budget must be between 1 and 100')
    output.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='memory-maintenance-', dir=output)).resolve()
    root.chmod(0o700)
    report = {'status': 'running', 'outputDir': str(root), 'request': '/memory 整理记忆',
              'preflightOnly': preflight_only, 'efficacyEstablished': False, 'projectServiceRequests': 0}
    report['requestBudget'] = request_budget
    report['plannerJsonOutput'] = planner_json_output
    report['plannerStructuredOutput'] = planner_structured_output
    started = time.monotonic()
    proxy = tui = None
    old_hashes: dict[str, str] = {}
    code_hashes = {str(p): digest(p) for folder in ('extensions', 'prompts', 'scripts') for p in (TESTS.parent / folder).rglob('*') if p.is_file()}
    code_hashes.update({str(p): digest(p) for p in [Path(__file__), TESTS / 'memory-maintenance-live-fixture.ts',
        TESTS / 'live_manual_memory.py', TESTS / 'docker_experiment.py']})
    def retain_partial_usage() -> None:
        # Ledger IDs prevent treating repeated snapshots as additional calls.
        # Do not add per-worker ledgers to final receipt totals: they overlap.
        ledgers = {}
        for file in (root / 'agent/memory').rglob('*.json'):
            if 'usage' not in file.name and file.name != 'receipt.json':
                continue
            try:
                value = json.loads(file.read_text())
                if 'knownUsage' in value or 'usage' in value:
                    ledgers[str(file.relative_to(root))] = value
            except (OSError, ValueError):
                pass
        (root / 'partial-worker-usage.json').write_text(json.dumps({'ledgers': ledgers,
            'overlapsFinalReceipt': True, 'completeCostAccounting': False,
            'unrecordedOrInterruptedUsage': 'unknown; never zero'}))
    try:
        project = project.resolve(strict=True)
        if not (project / '.git').exists():
            raise AssertionError('Reproduction requires the actual Git project')
        config = Path(os.environ.get('PI_CODING_AGENT_DIR', Path.home() / '.pi/agent'))
        source_paths = scoped_paths(project, dict(os.environ))
        memory_source = Path(source_paths['harnessDir'])
        old_hashes.update({str(p): digest(p) for p in memory_source.glob('*.md') if p.is_file() and not p.is_symlink()})
        if not old_hashes:
            raise AssertionError('No actual existing Memory; never seed replacements')
        cwd, agent, home = root / 'project', root / 'agent', root / 'home'
        cwd.mkdir(); agent.mkdir(mode=0o700); home.mkdir()
        names = subprocess.check_output(['git', 'ls-files', '-co', '--exclude-standard', '-z'], cwd=project).decode().split('\0')
        project_hashes, omitted = {}, []
        for name in sorted(set(names) - {''}):
            relative = Path(name)
            if relative.is_absolute() or '..' in relative.parts or any(FORBIDDEN.match(part) for part in relative.parts):
                omitted.append(name); continue
            file = project / relative
            if file.is_symlink() or not file.is_file():
                omitted.append(name); continue
            project_hashes[name] = digest(file)
        # Credential detection happens before copying or making any model call.
        candidates = [str(project / name) for name in project_hashes] + list(old_hashes)
        if snapshot:
            candidates.append(str(snapshot))
        scan = 'import {containsSensitiveMemoryMaterial} from ' + json.dumps(str(TESTS.parent / 'extensions/consolidation-run.ts')) + '; const files=JSON.parse(await Bun.stdin.text()); const rejected=[]; for(const f of files){const b=await Bun.file(f).text(); if(containsSensitiveMemoryMaterial(b))rejected.push(f)} console.log(JSON.stringify(rejected));'
        rejected = set(json.loads(subprocess.check_output(['bun', '-e', scan], input=json.dumps(candidates).encode(), cwd=REPO)))
        if rejected.intersection(old_hashes):
            raise AssertionError('Existing Memory contains sensitive material; source is unchanged')
        if snapshot and str(snapshot) in rejected:
            raise AssertionError('Frozen task evidence contains sensitive material; no remote review')
        for name in list(project_hashes):
            file = project / name
            if str(file) in rejected:
                omitted.append(name); del project_hashes[name]; continue
            target = cwd / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target)
        subprocess.run(['git', 'init', '-q', str(cwd)], check=True)
        env = {k: v for k, v in os.environ.items() if k in {'PATH', 'LANG', 'LC_ALL'}}
        env.update(HOME=str(home), PI_CODING_AGENT_DIR=str(agent), PI_OFFLINE='1', TERM='xterm-256color',
                   PI_MAINTENANCE_READY=str(root / 'ready'), PI_MAINTENANCE_EVENTS=str(root / 'events.jsonl'))
        if snapshot:
            manifest = json.loads((snapshot.parent / 'manifest.json').read_text())
            if digest(snapshot) != manifest['snapshotDigest'] or Path(manifest['cwd']) != project:
                raise AssertionError('Frozen evidence is not bound to this project')
            frozen = root / 'original-snapshot.json'
            shutil.copy2(snapshot, frozen); frozen.chmod(0o600)
            env.update(PI_MAINTENANCE_SNAPSHOT=str(frozen), PI_MAINTENANCE_SNAPSHOT_SHA256=digest(frozen))
            report['frozenEvidence'] = {'sha256': digest(frozen), 'entries': len(json.loads(frozen.read_text())['entries']),
                                        'originalRunId': manifest['runId'], 'remapped': False}
        target_paths = scoped_paths(cwd, env)
        target_memory = Path(target_paths['harnessDir'])
        target_memory.mkdir(parents=True, mode=0o700)
        for file in old_hashes:
            shutil.copy2(file, target_memory / Path(file).name)
        public_source = Path(source_paths['publicDir']) if source_paths.get('publicDir') else None
        public_target = Path(target_paths['publicDir']) if target_paths.get('publicDir') else None
        if public_source and public_target:
            public_target.mkdir(parents=True, exist_ok=True)
            for file in public_source.glob('*.md'):
                if file.is_symlink() or not file.is_file() or file.name not in {Path(f).name for f in old_hashes}:
                    continue
                if file.read_bytes() == (memory_source / file.name).read_bytes():
                    shutil.copy2(file, public_target / file.name)
        prepare_learning_settings(agent)
        settings_code = 'import {readLearningSettings} from ' + json.dumps(str(TESTS.parent / 'extensions/learning-settings.ts')) + ';console.log(JSON.stringify(await readLearningSettings(process.argv[1])));'
        settings = json.loads(subprocess.check_output(['bun', '-e', settings_code, str(cwd)], env=env, cwd=REPO, text=True))
        if settings != {'autoMemory': False}:
            raise AssertionError('Disposable learning settings failed product preflight')
        report.update(projectSource=str(project), originalMemoryHashes=old_hashes, originalProjectHashes=project_hashes,
                      omittedSourcePaths=omitted, sourceHashes=code_hashes, originalMemoryPreserved=True)
        (root / 'provenance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        if preflight_only:
            report.update(status='preflight-passed', modelRequests=0, jevRequests=0)
            return report
        jev_config = json.loads((config / 'continual-learning.json').read_text()) if (config / 'continual-learning.json').exists() else {}
        jev_key = os.environ.get('TYPESAFE_API_KEY') or jev_config.get('jev', {}).get('apiKey')
        if not jev_key:
            raise AssertionError('Actual Jev is required; never silently disable it')
        proxy = InferenceProxy(config, jev_key=jev_key, request_budget=request_budget, jev_transport='bun-fetch')
        with proxy:
            # The empty directory was created for offline preflight; provider helper owns creation.
            provider_dir = root / 'provider-config'
            proxy.write_agent_config(provider_dir)
            for file in provider_dir.iterdir():
                shutil.copy2(file, agent / file.name)
            shutil.rmtree(provider_dir)
            # Exercise the production per-run dialog, rather than pre-authorizing config.
            (agent / 'continual-learning.json').write_text(json.dumps(private_review_config(planner_json_output, planner_structured_output)))
            models = json.loads((agent / 'models.json').read_text())
            provider = models['providers'][proxy.selection['provider']]
            provider['baseUrl'] = provider['baseUrl'].replace('host.docker.internal', '127.0.0.1')
            (agent / 'models.json').write_text(json.dumps(models))
            (agent / 'settings.json').write_text(json.dumps({'packages': [], 'quietStartup': True, 'defaultThinkingLevel': 'off'}))
            env.update({k: v.replace('host.docker.internal', '127.0.0.1') for k, v in proxy.jev_environment().items()})
            pi = REPO / 'node_modules/@earendil-works/pi-coding-agent/dist/cli.js'
            node = shutil.which('node')
            version = subprocess.check_output([node, str(pi), '--version'], env=env, text=True).strip()
            if version != '1.0.0':
                raise AssertionError('Pi compatibility baseline changed')
            report['piVersion'] = version
            command = [node, str(pi), '--offline', '--no-extensions', '--no-skills', '--no-prompt-templates',
                       '--no-context-files', '--no-themes', '--no-approve', '--extension',
                       str(TESTS / 'memory-maintenance-live-fixture.ts'), '--provider', proxy.selection['provider'],
                       '--model', proxy.selection['model'], '--thinking', 'off', '--session', str(root / 'session.jsonl'), '--no-tools']
            tui = NativeTui(command, cwd, env)
            tui.wait_until((root / 'ready').exists, 30, 'Pi did not become ready')
            receipt_file = Path(target_paths['runsDir']) / 'learning-pipeline-receipt.json'
            tui.send('/memory 整理记忆')
            events = root / 'events.jsonl'
            tui.wait_until(lambda: receipt_file.exists() or events.exists(), 30, 'No command receipt or consent dialog')
            if events.exists():
                rows = [json.loads(line) for line in events.read_text().splitlines()]
                if rows != [{'kind': 'confirm', 'title': 'Allow private Memory review?'}]:
                    raise AssertionError('Unexpected consent dialog')
                if not approve_private_review:
                    os.write(tui.master, b'\x1b')
                    raise AssertionError('Real private review requires explicit authorization flag')
                tui.send('')  # Native selector's first option is Yes.
                tui.wait_until(lambda: '"accepted":true' in events.read_text().replace(' ', ''), 10,
                               'Native private review consent was not accepted')
                report['privateReviewConsent'] = 'explicit-user-authorization-native-Yes'
            last_retained = 0.0
            def completed() -> bool:
                nonlocal last_retained
                if time.monotonic() - last_retained < 1 and not receipt_file.exists():
                    return False
                last_retained = time.monotonic()
                retain_partial_usage()
                (root / 'transport-progress.json').write_text(json.dumps({'requests': proxy.requests,
                    'jevRequests': proxy.jev_requests, 'errors': proxy.errors, 'jevUsage': proxy.jev_usage,
                    'modelWireMetadata': proxy.model_observations,
                    'incomplete': not receipt_file.exists()}))
                return receipt_file.exists()
            tui.wait_until(completed, 1800, 'Memory maintenance did not finish')
            receipt = json.loads(receipt_file.read_text())
            (root / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
            report['receipt'] = str(root / 'receipt.json')
            report['operations'] = receipt['operations']
            report['reportedModelCostUsd'] = receipt['totals']['cost']
            report['usageAvailable'] = receipt.get('usageAvailable', False)
            changed = [name for file, old in old_hashes.items() if (name := Path(file).name) != 'MEMORY.md'
                       and (target_memory / name).is_file() and digest(target_memory / name) != old]
            report['changedExistingMemory'] = changed
            if not changed or receipt['operations'] == 0:
                raise AssertionError('No validated correction of actual existing knowledge')
            if any(row['outcome'] in {'failed', 'rejected', 'cancelled'} for row in receipt['attempts']):
                raise AssertionError('Retained learning failure; changed files alone do not establish completion')
            history_code = 'import {listLearningHistory} from ' + json.dumps(str(TESTS.parent / 'extensions/learning-history.ts')) + ';console.log(JSON.stringify(await listLearningHistory(process.argv[1])));'
            history = json.loads(subprocess.check_output(['bun', '-e', history_code, str(cwd)], env=env, cwd=REPO, text=True))
            (root / 'history.json').write_text(json.dumps(history, ensure_ascii=False, indent=2))
            if not any(row.get('status') == 'applied' and row.get('phase') == 'memory' for row in history):
                raise AssertionError('No parent-applied Memory history')
            report.update(status='passed-correction-mechanics', efficacyEstablished=False)
    except Exception as error:
        report.update(status='failed', error=str(error))
    finally:
        if tui:
            tui.close()
            (root / 'terminal.ansi').write_bytes(redact_transport_bytes(bytes(tui.transcript), proxy) if proxy else bytes(tui.transcript))
        if proxy:
            retain_partial_usage()
            report.update(**inference_request_counts(proxy), transportErrors=proxy.errors,
                          jevUsage=proxy.jev_usage, jevObservations=proxy.jev_observations,
                          modelWireMetadata=proxy.model_observations)
            report['partialWorkerUsage'] = str(root / 'partial-worker-usage.json')
            report['unaccountedInterruptedModelCost'] = 'unknown' if 'receipt' not in report else 'see receipt usage availability'
        report.update(seconds=round(time.monotonic() - started, 2), implementationUnchanged=all(p.is_file() and digest(p) == h for file, h in code_hashes.items() if (p := Path(file))),
                      originalMemoryPreserved=all(Path(file).is_file() and digest(Path(file)) == h for file, h in old_hashes.items()))
        if not report['implementationUnchanged'] or not report['originalMemoryPreserved']:
            report.update(status='failed', error='Source or actual Memory changed during reproduction')
        for file in [root / 'agent/models.json', root / 'agent/continual-learning.json']:
            file.unlink(missing_ok=True)
        (root / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps({k: report.get(k) for k in ('status', 'outputDir', 'operations', 'changedExistingMemory', 'modelRequests', 'jevRequests', 'reportedModelCostUsd', 'error')}, ensure_ascii=False))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--approve-private-review', action='store_true')
    parser.add_argument('--planner-json-output', action='store_true', help='Explicit isolated opt-in for a wire-verified compatible gateway; does not alter user settings')
    parser.add_argument('--planner-structured-output', action='store_true', help='Independent isolated opt-in for wire-verified strict schemas; does not grant private review')
    parser.add_argument('--request-budget', type=int, default=100)
    args = parser.parse_args()
    result = run(args.output, args.project, preflight_only=args.preflight_only,
                 snapshot=args.snapshot, approve_private_review=args.approve_private_review, request_budget=args.request_budget, planner_json_output=args.planner_json_output, planner_structured_output=args.planner_structured_output)
    raise SystemExit(0 if result['status'] in {'preflight-passed', 'passed-correction-mechanics'} else 1)
