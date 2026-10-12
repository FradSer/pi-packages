"""One real, read-only repair of a retained v30 failure; never learning-benefit proof."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
from pathlib import Path
import shutil
import subprocess
import tarfile
import time

from docker_experiment import InferenceProxy, redact_transport_bytes

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parents[2]
RUN = 'run_mv50z5p1_6908d7a47a5c083a'
DOSSIER_RUN = 'run_mv50xmnf_bfa8bf32dead98cc'


def frozen_validation_context(prompt: str) -> dict:
    surface = json.loads(prompt.split('- Current harness surface summary:\n', 1)[1].split('\n- Target layer', 1)[0])
    # This diagnostic supports exactly the initial empty custom-layer failure.
    # Effective summaries cannot reconstruct shadowed custom declarations.
    if (any(rule.get('source') != 'built-in defaults' for rule in surface['rules'])
            or any(surface.get(key) for key in ('invalidRules', 'learnedRules', 'errors', 'reservedLegacyNames'))):
        raise ValueError('Frozen ownership context cannot be reconstructed; do not relax the parent gate')
    return {'layers': [], 'learnedRules': {}, 'targetSource': 'project', 'availableSkills': surface['availableSkills']}


def complete_reads(frozen: Path, observations: list[dict]) -> bool:
    for name in ('snapshot.json', 'dossier.json'):
        file = frozen / name
        data = file.read_bytes()
        lines = data.decode().split('\n')
        covered: set[int] = set()
        for read in observations:
            if read.get('path') != str(file) or read.get('sha256') != hashlib.sha256(data).hexdigest() or read.get('error'):
                continue
            offset, limit = read.get('offset'), read.get('limit')
            if type(offset) is not int or type(limit) is not int or offset < 1 or limit < 1:
                continue
            selected = '\n'.join(lines[offset - 1:offset - 1 + limit])
            footer = f'\n[lines {offset}-{min(len(lines), offset + limit - 1)} of {len(lines)}]'
            if read.get('result') == selected + footer:
                covered.update(range(offset - 1, min(len(lines), offset - 1 + limit)))
        if covered != set(range(len(lines))):
            return False
    return True


def require_authorized_destination(proxy: InferenceProxy) -> None:
    if (proxy.upstream.geturl().rstrip('/') != 'http://10.10.0.195:8317/v1'
            or proxy.selection.get('model') != 'bailian/qwen3.8-flash'):
        raise ValueError('Configured destination/model differs from explicitly authorized diagnostic')


def repair_continuity(original: dict, repaired: dict, observations: dict | None = None) -> bool:
    old, new = original.get('operations'), repaired.get('operations')
    if not isinstance(old, list) or not isinstance(new, list) or len(old) != len(new) or repaired.get('evidence') != original.get('evidence'):
        return False
    for before, after in zip(old, new):
        if not isinstance(after, dict) or not isinstance(after.get('rule'), dict):
            return False
        if (after.get('op') != before['op'] or after['rule'].get('id') != before['rule']['id']
                or after['rule'].get('action') != before['rule'].get('action') or after['rule'].get('enabled') is False):
            return False
        for kind in ('positive', 'negative'):
            cases = after.get('cases', {}).get(kind, [])
            for case in before['cases'][kind]:
                observed = next((row for row in (observations or {}).get('cases', [])
                                 if row.get('command') == case.get('bash')), None)
                if observed is None:
                    if case not in cases:
                        return False
                    continue
                target = 'positive' if observed['firstRecordedExecutable'] == 'npm' else 'negative'
                expected = {**case, 'expected': 'block'} if target == 'positive' else {k: v for k, v in case.items() if k != 'expected'}
                if expected not in after.get('cases', {}).get(target, []):
                    return False
                if any(row.get('bash') == case.get('bash') for row in after.get('cases', {}).get('negative' if target == 'positive' else 'positive', [])):
                    return False
    return True


def prepare(archive: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    frozen = output / 'frozen'
    frozen.mkdir(exist_ok=True)
    members = {
        'repair.md': f'./runs/--work-p-limit--/{RUN}/harness-repair.md',
        'snapshot.json': f'./runs/--work-p-limit--/{RUN}/snapshot.json',
        'manifest.json': f'./runs/--work-p-limit--/{RUN}/manifest.json',
        'dossier.json': f'./runs/--work-p-limit--/{DOSSIER_RUN}/incremental-learning-dossier.json',
    }
    with tarfile.open(archive) as source:
        for name, member in members.items():
            entry = source.getmember(member)
            if not entry.isfile() or entry.size > 32 * 1024 * 1024:
                raise ValueError('Unsupported frozen evidence member')
            data = source.extractfile(entry).read()
            target = frozen / name
            if target.exists() and target.read_bytes() != data:
                raise ValueError('Frozen evidence changed')
            target.write_bytes(data)
            target.chmod(0o600)
    context = frozen_validation_context((frozen / 'repair.md').read_text())
    (frozen / 'validation-context.json').write_text(json.dumps(context))
    members['validation-context.json'] = 'derived from full original harnessSurfaceSummary; custom layers must be empty'
    sources = [Path(__file__), *sorted((TESTS.parent / 'extensions').glob('*.ts')),
               *sorted((TESTS.parent / 'prompts').glob('*.md')), *sorted((REPO / 'packages/kit/src').rglob('*.ts'))]
    return {'archive': str(archive), 'archiveSha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            'members': members, 'frozenHashes': {name: hashlib.sha256((frozen / name).read_bytes()).hexdigest() for name in members},
            'sourceHashes': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            'intervention': 'Original full repair prompt and frozen source evidence unchanged. Read paths relocated explicitly; current read-only case preview added.',
            'requestBudget': 10, 'timeoutSeconds': 240, 'retryBudget': 0,
            'semanticReview': False, 'mutationAuthorized': False, 'benefitEstablished': False}


def run(archive: Path, output: Path, real: bool, observation_file: Path | None = None) -> dict:
    report = prepare(archive.resolve(), output.resolve())
    output = output.resolve()
    observations = None
    if observation_file is not None:
        data = observation_file.read_bytes()
        observations = json.loads(data)
        if not isinstance(observations.get('cases'), list) or not observations['cases']:
            raise ValueError('Missing actual shell observations')
        target = output / 'frozen' / 'shell-observations.json'
        if target.exists() and target.read_bytes() != data:
            raise ValueError('Frozen shell observations changed')
        target.write_bytes(data); target.chmod(0o600)
        report['frozenHashes']['shell-observations.json'] = hashlib.sha256(data).hexdigest()
        report['intervention'] += ' Independently observed Bash results supplied; preserve every original command, correct only observed classifications. Original failures remain failures.'
    if not real:
        report['status'] = 'preflight-only'
        (output / 'preflight.json').write_text(json.dumps(report, indent=2))
        return report
    # A consumed marker survives all failures and interruptions. Never auto-retry.
    with (output / 'single-attempt.json').open('x') as marker:
        json.dump(report, marker, indent=2)
    report['status'] = 'failed'
    started = time.monotonic()
    agent, home, cwd = (output / name for name in ('agent', 'home', 'project'))
    for directory in (home, cwd):
        directory.mkdir(mode=0o700)
    frozen = output / 'frozen'
    read_module = TESTS.parent / 'extensions/planner-read-scope.ts'
    preview_module = TESTS.parent / 'extensions/harness-planner-preview.ts'
    extension = output / 'diagnostic.mjs'
    scope = {'cwd': str(cwd), 'files': [str(frozen / name) for name in ('snapshot.json', 'dossier.json')], 'roots': []}
    extension.write_text(f'import fs from "node:fs/promises";\nimport {{registerPlannerRead}} from {json.dumps(str(read_module))};\n'
                         f'import {{registerHarnessPlannerPreview}} from {json.dumps(str(preview_module))};\n'
                         f'export default pi=>{{registerPlannerRead(pi,{json.dumps(scope)},async read=>fs.appendFile({json.dumps(str(output / "reads.jsonl"))},JSON.stringify(read)+"\\n"));registerHarnessPlannerPreview(pi);}};\n')
    task = output / 'task.md'
    task.write_text((frozen / 'repair.md').read_text() + '\n\n## Diagnostic transport relocation\n'
                    f'The complete frozen snapshot is now at {json.dumps(str(frozen / "snapshot.json"))}.\n'
                    f'The complete frozen dossier is now at {json.dumps(str(frozen / "dossier.json"))}.\n'
                    'Read those exact files with learning_read; old absolute paths are historical identities. No repository exploration is available. '
                    'Check proposed rules and their exact cases with harness_check_cases and correct evaluator mismatches before final JSON. '
                    'Passing cases grant no semantic, ownership or mutation approval. Preserve the original evidence and authorization boundaries.\n')
    if observations is not None:
        with task.open('a') as stream:
            stream.write('\n## Independent actual Bash observations (diagnostic intervention)\n'
                         'The original plan contains incorrect case labels. Preserve every original command string and evidence quote. '
                         'For commands below, classify by the observed first executable (npm means positive/block; other or missing means negative). '
                         'Do not change unobserved classifications. These facts grant no write authorization or learning credit.\n'
                         + json.dumps(observations, ensure_ascii=True) + '\n')
    proxy = None
    stdout = b''
    child = None
    spool, errors = output / 'output.partial', output / 'stderr.partial'
    try:
        config = Path(os.environ.get('PI_CODING_AGENT_DIR', Path.home() / '.pi/agent'))
        proxy = InferenceProxy(config, request_budget=report['requestBudget'])
        require_authorized_destination(proxy)
        with proxy:
            proxy.write_agent_config(agent)
            models = json.loads((agent / 'models.json').read_text())
            provider = models['providers'][proxy.selection['provider']]
            provider['baseUrl'] = provider['baseUrl'].replace('host.docker.internal', '127.0.0.1')
            (agent / 'models.json').write_text(json.dumps(models))
            env = {k: v for k, v in os.environ.items() if k in {'PATH', 'LANG', 'LC_ALL'}}
            env.update(HOME=str(home), PI_CODING_AGENT_DIR=str(agent), PI_OFFLINE='1')
            pi = REPO / 'node_modules/@earendil-works/pi-coding-agent/dist/cli.js'
            report['piVersion'] = subprocess.check_output([shutil.which('node'), str(pi), '--version'], env=env, text=True).strip()
            if report['piVersion'] != '1.0.0':
                raise ValueError('Pi compatibility baseline changed')
            command = [shutil.which('node'), str(pi), '--offline', '--no-extensions', '--no-context-files',
                       '--no-skills', '--no-prompt-templates', '--no-themes', '--no-session', '--print', '--mode', 'json',
                       '--tools', 'learning_read,harness_check_cases', '-e', str(extension),
                       '--system-prompt', (TESTS.parent / 'prompts/planner-system.md').read_text(),
                       '--provider', proxy.selection['provider'], '--model', proxy.selection['model'], '--thinking', 'off', f'@{task}']
            with os.fdopen(os.open(spool, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as out, os.fdopen(os.open(errors, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as err:
                child = subprocess.Popen(command, cwd=cwd, env=env, stdout=out, stderr=err, start_new_session=True)
                returncode = child.wait(timeout=report['timeoutSeconds'])
            stdout = spool.read_bytes()
            (output / 'output.jsonl').write_bytes(redact_transport_bytes(stdout, proxy))
            (output / 'stderr.txt').write_bytes(redact_transport_bytes(errors.read_bytes(), proxy))
            report.update(returncode=returncode, model=proxy.selection)
            rows = [json.loads(line) for line in stdout.decode().splitlines() if line.strip()]
            assistants = [r['message'] for r in rows if r.get('type') == 'message_end' and r.get('message', {}).get('role') == 'assistant']
            report['usage'] = [m.get('usage') for m in assistants]
            report['previewCalls'] = sum(p.get('name') == 'harness_check_cases' for m in assistants for p in m.get('content', []))
            if returncode != 0 or not assistants:
                raise ValueError('Planner did not complete successfully')
            final = ''.join(p.get('text', '') for p in assistants[-1].get('content', []) if p.get('type') == 'text')
            plan = json.loads(final)
            (output / 'plan.json').write_text(json.dumps(plan, indent=2))
            rejected = json.loads((frozen / 'repair.md').read_text().splitlines()[-1])['rejectedPlan']
            report['repairContinuity'] = repair_continuity(rejected, plan, observations)
            validate = '''import fs from 'node:fs';import {validateHarnessPlan} from MODULE;
const [planFile,snapshotFile,manifestFile,contextFile]=process.argv.slice(2);const plan=JSON.parse(fs.readFileSync(planFile,'utf8'));
const text=fs.readFileSync(snapshotFile,'utf8'),manifest=JSON.parse(fs.readFileSync(manifestFile,'utf8'));
const context=JSON.parse(fs.readFileSync(contextFile,'utf8'));
const errors=validateHarnessPlan(plan,{...context,snapshot:JSON.parse(text),snapshotText:text,automatic:true,requireEvidence:true,requireCases:true});
for(const [key,value] of Object.entries({runId:manifest.runId,scopeDigest:manifest.scopeDigest,artifactHash:manifest.snapshotDigest}))if(plan[key]!==value)errors.push('Bound identity mismatch: '+key);
console.log(JSON.stringify({errors,operations:plan.operations?.length??0}));'''.replace('MODULE', json.dumps(str(TESTS.parent / 'extensions/harness-consolidation.ts')))
            validator = output / 'validate.mts'; validator.write_text(validate)
            check = subprocess.run(['bun', str(validator), str(output / 'plan.json'), str(frozen / 'snapshot.json'), str(frozen / 'manifest.json'), str(frozen / 'validation-context.json')], cwd=REPO, env=env, capture_output=True, text=True, check=True)
            report['parentValidation'] = json.loads(check.stdout)
            reads = output / 'reads.jsonl'
            report['completeEvidenceRead'] = complete_reads(frozen, [json.loads(line) for line in reads.read_text().splitlines()] if reads.exists() else [])
            if report['parentValidation']['errors'] or not report['parentValidation']['operations'] or not report['previewCalls'] or not report['completeEvidenceRead'] or not report['repairContinuity']:
                raise ValueError('Read-only correction acceptance failed; no-op is not a correction')
            report['status'] = 'structural-repair-passed'
    except subprocess.TimeoutExpired as error:
        report.update(error='Planner deadline exceeded', interruptedUsageUnknown=True)
    except KeyboardInterrupt:
        report.update(error='Planner interrupted', interruptedUsageUnknown=True)
    except Exception as error:
        report.update(errorType=type(error).__name__, error=str(error)[:1000])
    finally:
        if child and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)
        if spool.exists():
            stdout = spool.read_bytes()
            (output / 'output.jsonl').write_bytes(redact_transport_bytes(stdout, proxy) if proxy else stdout)
            spool.unlink()
        if errors.exists():
            (output / 'stderr.txt').write_bytes(redact_transport_bytes(errors.read_bytes(), proxy) if proxy else errors.read_bytes())
            errors.unlink()
        # Keep usage even when final JSON, validation or the deadline fails.
        usage = []
        for line in stdout.decode(errors='replace').splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get('type') == 'message_end' and row.get('message', {}).get('role') == 'assistant':
                usage.append(row['message'].get('usage'))
        report['usage'] = usage
        report['unknownCosts'] = not usage or any(not isinstance(u, dict) or not isinstance(u.get('cost'), dict) or not isinstance(u['cost'].get('total'), (int, float)) for u in usage) or report.get('interruptedUsageUnknown', False) or bool(proxy and (proxy.errors or proxy.requests > len(usage)))
        report['knownReportedCostUsd'] = sum(u['cost']['total'] for u in usage if isinstance(u, dict) and isinstance(u.get('cost'), dict) and isinstance(u['cost'].get('total'), (int, float)))
        for name in ('models.json', 'models-store.json', 'auth.json'):
            (agent / name).unlink(missing_ok=True)
        report.update(seconds=round(time.monotonic() - started, 2), requests=proxy.requests if proxy else 0,
                      transportErrors=proxy.errors if proxy else 0, billingVerified=False,
                      sourceUnchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest for p, digest in report['sourceHashes'].items()),
                      frozenUnchanged=all(hashlib.sha256((frozen / p).read_bytes()).hexdigest() == digest for p, digest in report['frozenHashes'].items()),
                      projectFiles=[str(p.relative_to(cwd)) for p in cwd.rglob('*') if p.is_file()])
        if not report['sourceUnchanged'] or not report['frozenUnchanged'] or report['projectFiles']:
            report['status'] = 'failed-integrity'
        (output / 'result.json').write_text(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    def interrupted(_signal: int, _frame: object) -> None:
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--real-model', action='store_true')
    parser.add_argument('--shell-observations', type=Path)
    args = parser.parse_args()
    result = run(args.archive, args.output, args.real_model, args.shell_observations)
    print(json.dumps({k: result[k] for k in ('status', 'requests', 'seconds', 'parentValidation', 'error') if k in result}))
    raise SystemExit(0 if result['status'] in ('preflight-only', 'structural-repair-passed') else 1)
