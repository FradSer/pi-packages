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


def scoped_paths(cwd: Path, env: dict[str, str]) -> dict:
    code = 'import {resolveMemoryPaths} from ' + json.dumps(str(TESTS.parent / 'extensions/memory-paths.ts')) + '; console.log(JSON.stringify(resolveMemoryPaths(process.argv[1])));'
    return json.loads(subprocess.check_output(['bun', '-e', code, str(cwd)], env=env, cwd=REPO, text=True))


def run(output: Path, project: Path, *, preflight_only: bool) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='memory-maintenance-', dir=output)).resolve()
    root.chmod(0o700)
    report = {'status': 'running', 'outputDir': str(root), 'request': '/memory 整理记忆',
              'preflightOnly': preflight_only, 'efficacyEstablished': False, 'projectServiceRequests': 0}
    started = time.monotonic()
    proxy = tui = None
    old_hashes: dict[str, str] = {}
    code_hashes = {str(p): digest(p) for folder in ('extensions', 'prompts', 'scripts') for p in (TESTS.parent / folder).rglob('*') if p.is_file()}
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
        scan = 'import {containsSensitiveMemoryMaterial} from ' + json.dumps(str(TESTS.parent / 'extensions/consolidation-run.ts')) + '; const files=JSON.parse(await Bun.stdin.text()); const rejected=[]; for(const f of files){const b=await Bun.file(f).text(); if(containsSensitiveMemoryMaterial(b))rejected.push(f)} console.log(JSON.stringify(rejected));'
        rejected = set(json.loads(subprocess.check_output(['bun', '-e', scan], input=json.dumps(candidates).encode(), cwd=REPO)))
        if rejected.intersection(old_hashes):
            raise AssertionError('Existing Memory contains sensitive material; source is unchanged')
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
                   PI_MAINTENANCE_READY=str(root / 'ready'))
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
        proxy = InferenceProxy(config, jev_key=jev_key, request_budget=100, jev_transport='bun-fetch')
        with proxy:
            # The empty directory was created for offline preflight; provider helper owns creation.
            provider_dir = root / 'provider-config'
            proxy.write_agent_config(provider_dir)
            for file in provider_dir.iterdir():
                shutil.copy2(file, agent / file.name)
            shutil.rmtree(provider_dir)
            models = json.loads((agent / 'models.json').read_text())
            provider = models['providers'][proxy.selection['provider']]
            provider['baseUrl'] = provider['baseUrl'].replace('host.docker.internal', '127.0.0.1')
            (agent / 'models.json').write_text(json.dumps(models))
            (agent / 'settings.json').write_text(json.dumps({'packages': [], 'quietStartup': True, 'defaultThinkingLevel': 'off'}))
            (agent / 'memory').mkdir(exist_ok=True)
            (agent / 'memory/settings.json').write_text(json.dumps({'version': 1, 'autoMemory': False}))
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
            tui.wait_until(receipt_file.exists, 900, 'Memory maintenance did not finish')
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
            report.update(modelRequests=proxy.requests, transportErrors=proxy.errors, jevRequests=proxy.jev_requests,
                          jevUsage=proxy.jev_usage, jevObservations=proxy.jev_observations)
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
    args = parser.parse_args()
    result = run(args.output, args.project, preflight_only=args.preflight_only)
    raise SystemExit(0 if result['status'] in {'preflight-passed', 'passed-correction-mechanics'} else 1)
