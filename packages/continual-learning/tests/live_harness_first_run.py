"""Actual Pi slash-command first creation; offline mechanics or bounded real model.

No D0 traffic is generated. Real mode uses a host proxy and retains usage/failures.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import nullcontext

from live_manual_memory import NativeTui
from docker_experiment import InferenceProxy, redact_transport_bytes

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parents[2]
REQUEST = '/harness 避免后续 D0 的流量被打爆'


def current_guidance_delivered(records: list[dict], authored: dict, expected: list[dict]) -> bool:
    """Require both current-revision bookkeeping and actual run-start context."""
    delivered = [entry for row in records
                 if row.get('type') == 'custom' and row.get('customType') == 'harness-guidance-delivery'
                 for entry in row.get('data', {}).get('entries', [])]
    sections = [row.get('message', {}).get('sections', {}).get('harness_guidance', '')
                for row in records if row.get('type') == 'message' and row.get('message', {}).get('role') == 'system']
    return any(entry.get('id') == wanted['id'] and entry.get('revision') == wanted['revision']
               and entry.get('status') in ('active', 'update')
               and any(rule.get('id') == wanted['id'] and isinstance(rule.get('instructions'), str)
                       and any(f"[harness:{wanted['id']}]" in section and rule['instructions'] in section for section in sections)
                       for rule in authored.get('rules', []))
               for wanted in expected for entry in delivered)


def verify(output: Path, real: bool = False) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='harness-first-', dir=output)).resolve()
    run.chmod(0o700)
    sources = [TESTS / 'harness-first-run-fixture.ts', TESTS / 'live_harness_first_run.py',
               *[p for p in sorted((TESTS.parent / 'extensions').glob('*.ts'))],
               *sorted((REPO / 'packages/kit/src').rglob('*.ts'))]
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    report: dict[str, object] = {'status': 'running', 'request': REQUEST, 'realModel': real, 'outputDir': str(run),
                                'sourceHashes': hashes, 'd0ServiceRequests': 0, 'efficacyEstablished': False}
    proxy = None
    tui = None
    started = time.monotonic()
    try:
        if real:
            source = Path(os.environ.get('PI_CODING_AGENT_DIR', Path.home() / '.pi/agent'))
            proxy = InferenceProxy(source, request_budget=16)
        with proxy if proxy else nullcontext():
            cwd, agent, home = run / 'project', run / 'agent', run / 'home'
            cwd.mkdir(); home.mkdir()
            if proxy:
                proxy.write_agent_config(agent)
                models = json.loads((agent / 'models.json').read_text())
                provider = models['providers'][proxy.selection['provider']]
                provider['baseUrl'] = provider['baseUrl'].replace('host.docker.internal', '127.0.0.1')
                (agent / 'models.json').write_text(json.dumps(models))
                model = proxy.selection
            else:
                agent.mkdir(mode=0o700)
                model = {'provider': 'harness-first-fixture', 'model': 'deterministic'}
            (agent / 'settings.json').write_text(json.dumps({'packages': [], 'quietStartup': True, 'defaultThinkingLevel': 'off'}))
            env = {k: v for k, v in os.environ.items() if k in {'PATH', 'LANG', 'LC_ALL'}}
            ready, ended = run / 'ready', run / 'ended'
            env.update(HOME=str(home), PI_CODING_AGENT_DIR=str(agent), PI_OFFLINE='1', TERM='xterm-256color',
                       PI_HARNESS_READY=str(ready), PI_HARNESS_ENDED=str(ended), PI_HARNESS_REAL='1' if real else '0')
            node = shutil.which('node')
            pi = REPO / 'node_modules/@earendil-works/pi-coding-agent/dist/cli.js'
            sdk = pi.resolve().parents[1]
            schema_docs = [sdk / 'README.md', *sorted((sdk / 'docs').rglob('*.md'))]
            assert all(p.resolve().is_relative_to(sdk) for p in schema_docs)
            documentation_paths = [*schema_docs, sdk / 'docs/harness.md', sdk / 'docs/index.md']
            assert all(p.is_file() for p in schema_docs)
            env['PI_HARNESS_SCHEMA_DOCS'] = json.dumps([str(p.resolve()) for p in documentation_paths])
            report['publicSchemaDocs'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in schema_docs}
            version = subprocess.check_output([node, str(pi), '--version'], env=env, text=True).strip()
            assert version == '1.2.0', 'Pi baseline changed'
            report['piVersion'] = version
            session = run / 'session.jsonl'
            command = [node, str(pi), '--offline', '--no-extensions', '--no-skills', '--no-prompt-templates',
                       '--no-context-files', '--no-themes', '--no-approve', '--extension',
                       str(TESTS / 'harness-first-run-fixture.ts'), '--provider', model['provider'], '--model',
                       model['model'], '--thinking', 'off', '--session', str(session), '--tools', 'read,write,harness_preview']
            tui = NativeTui(command, cwd, env)
            tui.wait_until(ready.exists, 30, 'Native Pi did not start')
            assert not (cwd / '.pi').exists()
            tui.send(REQUEST)
            tui.wait_until(lambda: ended.exists(), 240, 'Authoring turn did not finish')
            target = cwd / '.pi/harness.json'
            assert target.is_file(), 'First /harness request did not create a supported rule'
            authored_bytes = target.read_bytes()
            authored = json.loads(authored_bytes)
            assert isinstance(authored.get('rules'), list) and authored['rules']
            # Confirm actual product validation, not just parseable final bytes.
            validation = subprocess.run(['bun', '-e',
                "import {validateHarnessWrite} from " + json.dumps(str(TESTS.parent / 'extensions/guardrails.ts')) +
                "; console.log(JSON.stringify(validateHarnessWrite({content:await Bun.file(process.argv[1]).text()},new Set())));", str(target)],
                cwd=REPO, capture_output=True, text=True, check=True)
            assert json.loads(validation.stdout) == [], validation.stdout
            selector_probe = subprocess.run(['bun', '-e',
                "import {mergeLayers,evaluateText} from " + json.dumps(str(TESTS.parent / 'extensions/guardrail-engine.ts')) +
                ";const v=await Bun.file(process.argv[1]).json();const c=mergeLayers([{...v,source:'project'}],new Set());" +
                "console.log(JSON.stringify(['避免后续 D0 的流量被打爆','接下来要维护 D0，先说明适用的流量保护指引和仍需确认的信息，不执行服务请求。','为本地 UI 调整颜色，不访问任何网络服务。','避免后续 D1 的流量被打爆','避免后续 D0x 的流量被打爆'].map(text=>({text,...evaluateText(c,[text])}))));", str(target)],
                cwd=REPO, capture_output=True, text=True, check=True)
            probes = json.loads(selector_probe.stdout)
            (run / 'selector-probes.json').write_text(json.dumps(probes, ensure_ascii=False, indent=2))
            assert all(not p['incomplete'] for p in probes)
            assert all(p['matches'] for p in probes[:2]), 'Selector failed a plain relevant text without authoring history'
            assert all(not probe['matches'] for probe in probes[2:]), 'Resource-specific guidance matched another resource or unrelated local work'
            report['plainSelectorPositiveNegativeVerified'] = True
            tui.close()
            data = bytes(tui.transcript)
            (run / 'authoring-terminal.ansi').write_bytes(redact_transport_bytes(data, proxy) if proxy else data)
            tui = None
            followup_session = run / 'followup-session.jsonl'
            followup_command = [str(followup_session) if value == str(session) else value for value in command]
            tool_index = followup_command.index('--tools')
            followup_command[tool_index:tool_index + 2] = ['--no-tools']
            ready.unlink(); ended.unlink()
            env['PI_HARNESS_FOLLOWUP'] = '1'
            tui = NativeTui(followup_command, cwd, env)
            tui.wait_until(ready.exists, 30, 'Fresh follow-up Pi did not start')
            tui.send('接下来要维护 D0，先说明适用的流量保护指引和仍需确认的信息，不执行服务请求。')
            tui.wait_until(ended.exists, 240, 'Fresh follow-up turn did not finish')
            records = [json.loads(line) for line in session.read_text().splitlines() if line.strip()]
            assert not any(r.get('customType') == 'harness-first-boundary' for r in records), 'Rejected tool boundary calls remain an acceptance failure'
            messages = [r['message'] for r in records if isinstance(r.get('message'), dict)]
            calls = [(i, b) for i, m in enumerate(messages) for b in m.get('content', []) if isinstance(b, dict) and b.get('type') == 'toolCall']
            def target_call(block: dict) -> bool:
                raw = block.get('arguments', {}).get('path')
                return isinstance(raw, str) and (cwd / raw).resolve() == target.resolve()
            writes = [(i, b) for i, b in calls if b.get('name') == 'write']
            assert len(writes) == 1 and target_call(writes[0][1])
            results = {m.get('toolCallId'): (i, m) for i, m in enumerate(messages) if m.get('role') == 'toolResult'}
            wi, write = writes[0]
            previews = [(i, b) for i, b in calls if b.get('name') == 'harness_preview' and b['id'] in results and not results[b['id']][1].get('isError')]
            assert any(i < results[b['id']][0] < wi and b.get('arguments', {}).get('content') == write['arguments']['content'] for i, b in previews), 'Exact candidate not previewed before write'
            report['parentPreviewBeforeWrite'] = True
            assert results[write['id']][0] > wi and results[write['id']][1].get('toolName') == 'write'
            assert results[write['id']][1].get('isError') is False
            assert json.loads(write['arguments']['content']) == authored
            assert any(i < wi and b.get('name') == 'read' and target_call(b) and b['id'] in results
                       and i < results[b['id']][0] < wi and results[b['id']][1].get('toolName') == 'read'
                       and results[b['id']][1].get('isError') is True and 'ENOENT' in json.dumps(results[b['id']][1]) for i, b in calls)
            def complete_read(result: dict) -> bool:
                text = '\n'.join(b.get('text', '') for b in result.get('content', []) if isinstance(b, dict) and b.get('type') == 'text')
                try:
                    return json.loads(text) == authored
                except (ValueError, TypeError):
                    return False
            assert any(i > wi and b.get('name') == 'read' and target_call(b) and b['id'] in results
                       and results[b['id']][0] > i and results[b['id']][1].get('toolName') == 'read'
                       and results[b['id']][1].get('isError') is False and complete_read(results[b['id']][1]) for i, b in calls)
            revisions = subprocess.run(['bun', '-e',
                "import {hashRuleRevision} from " + json.dumps(str(TESTS.parent / 'extensions/harness-guidance-planner.ts')) +
                "; const v=await Bun.file(process.argv[1]).json();console.log(JSON.stringify(v.rules.filter(r=>'text' in r).map(r=>({id:r.id,revision:hashRuleRevision(r)}))));", str(target)],
                cwd=REPO, capture_output=True, text=True, check=True)
            expected = json.loads(revisions.stdout)
            assert expected and all('text' in rule for rule in authored['rules']), 'This broad operational goal has no observed or quoted command; do not invent a command gate'
            assert target.read_bytes() == authored_bytes, 'Fresh follow-up mutated saved rule'
            followup_records = [json.loads(line) for line in followup_session.read_text().splitlines() if line.strip()]
            assert not any(r.get('customType') == 'harness-first-boundary' for r in followup_records)
            assert current_guidance_delivered(followup_records, authored, expected), 'Current authored revision and instructions not delivered in next run-start context'
            assert not (agent / 'harness.json').exists() and not (cwd / '.pi/harness.local.json').exists()
            report.update(status='passed', absentTargetRead=True, completeWrites=1, readBack=True,
                          nextTaskGuidanceDelivered=True, freshSession=True, followupReadOnly=True, rules=authored['rules'], otherLayersUnchanged=True)
    except Exception as error:
        report.update(status='failed', error=str(error))
    finally:
        if tui:
            tui.close()
            data = bytes(tui.transcript)
            (run / 'terminal.ansi').write_bytes(redact_transport_bytes(data, proxy) if proxy else data)
        if proxy:
            report.update(model=proxy.selection, requests=proxy.requests, transportErrors=proxy.errors, jevRequests=proxy.jev_requests)
            # Disposable proxy tokens are not retained after the run.
            (run / 'agent/models.json').unlink(missing_ok=True)
        else:
            report.update(requests=0, transportErrors=0, jevRequests=0)
        usage = []
        for session_name in ('session.jsonl', 'followup-session.jsonl'):
            session = run / session_name
            if not session.exists(): continue
            if proxy: session.write_bytes(redact_transport_bytes(session.read_bytes(), proxy))
            usage.extend(r['message'].get('usage') for line in session.read_text().splitlines() if line.strip()
                         for r in [json.loads(line)] if isinstance(r.get('message'), dict) and r['message'].get('role') == 'assistant')
        report['knownTokens'] = sum(u.get('totalTokens', 0) for u in usage if isinstance(u, dict))
        report['reportedCostUsd'] = sum(u.get('cost', {}).get('total', 0) for u in usage if isinstance(u, dict))
        report['unaccountedRequests'] = max(0, (proxy.requests if proxy else len(usage)) - len([u for u in usage if isinstance(u, dict)]))
        report['usageMissing'] = any(u is None for u in usage) or report['unaccountedRequests'] > 0 or bool(proxy and proxy.errors)
        report['billingVerified'] = False
        report['seconds'] = round(time.monotonic() - started, 2)
        report['sourceUnchanged'] = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in hashes.items())
        if not report['sourceUnchanged']: report['status'] = 'failed'
        (run / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--real-model', action='store_true')
    args = parser.parse_args()
    result = verify(args.output, args.real_model)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result['status'] == 'passed' else 1)
