"""Small stage controller: isolated source snapshots, durable events, reserved handoff."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import hashlib
import json
import os
import selectors
import subprocess
import tempfile
import time
import uuid
from proxy import InferenceProxy, redact_transport_credentials
from budget import MAX_REQUESTS

HERE = Path(__file__).resolve().parent
ROOT = HERE / 'runs/controlled-20261010'
IMAGE = 'pi-e2e-quality-runtime:20261010'
MODEL = {'provider': 'cli-proxy', 'model': 'opencode/deepseek-v4.1-flash'}
NETWORK = 'quality-pilot-controlled-internal'
RELAY = 'quality-pilot-controlled-relay'


def cmd(args: list[str], check: bool = True, timeout: int = 60) -> str:
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError(f'{args[:2]} failed: {p.stderr[-1000:]}')
    return p.stdout


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def messages(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e['message'] for e in events if e.get('type') == 'message_end'
            and e.get('message', {}).get('role') == 'assistant']


def completed(events: list[dict[str, Any]], code: int) -> bool:
    replies = messages(events)
    return code == 0 and bool(replies) and replies[-1].get('stopReason') == 'stop'


def packet(arm: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    if arm == 'e2e':
        return {'source': 'native E2E results', 'results': [e['result'] for e in events
                if e.get('type') == 'tool_execution_end' and e.get('toolName') == 'e2e_verify']}
    return {'source': 'same DeepSeek model review', 'messages': messages(events),
            'observations': [e.get('result') for e in events if e.get('type') == 'tool_execution_end']}


def setup_transport(proxy: InferenceProxy) -> None:
    cmd(['docker', 'network', 'create', '--internal', NETWORK])
    cmd(['docker', 'run', '-d', '--name', RELAY, '--network', 'bridge', '--memory', '256m',
         '--cpus', '0.5', '--pids-limit', '64', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
         '-e', f'PILOT_PROXY_PORT={proxy.server.server_address[1]}', '-v', f'{HERE}/relay.mjs:/relay.mjs:ro',
         IMAGE, 'node', '/relay.mjs'])
    cmd(['docker', 'network', 'connect', '--alias', 'model-proxy', NETWORK, RELAY])


def close_transport() -> None:
    cmd(['docker', 'rm', '-f', RELAY], check=False)
    cmd(['docker', 'network', 'rm', NETWORK], check=False)


def isolated_proxy_args() -> list[str]:
    """Override inherited image proxies so inference uses only the internal relay."""
    values = [name + '=' for name in ('http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY')]
    bypass = 'model-proxy,host.docker.internal,127.0.0.1,localhost'
    values += ['no_proxy=' + bypass, 'NO_PROXY=' + bypass]
    return [part for value in values for part in ('-e', value)]


def stage(proxy: InferenceProxy, public: Path, source: Path, folder: Path,
          prompt: str, *, tools: str, plugin: bool = False, allowance: int = 8) -> dict[str, Any]:
    """A fresh container per phase means killing a stage cannot leave tool children."""
    folder.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    before, jev_before, errors_before = proxy.requests, proxy.jev_requests, proxy.errors
    jev_usage_before = len(proxy.jev_usage)
    proxy.request_budget = min(MAX_REQUESTS, before + allowance)
    cap = proxy.request_budget
    name = 'quality-pilot-stage-' + uuid.uuid4().hex[:10]
    save(folder / 'owner.json', {'container': name, 'phaseRequestCap': cap, 'requestsBefore': before})
    events: list[dict[str, Any]] = []
    code = 1
    reason = None
    initial_hash = digest(source)
    with tempfile.TemporaryDirectory(prefix='quality-pilot-config-') as temp:
        config = Path(temp) / 'agent'
        proxy.write_agent_config(config)
        model_config = json.loads((config / 'models.json').read_text())
        model_config['providers'][MODEL['provider']]['baseUrl'] = 'http://model-proxy:8080/v1'
        (config / 'models.json').write_text(json.dumps(model_config))
        work = Path(temp) / 'workspace'
        work.mkdir()
        (work / 'solution.mjs').write_bytes(source.read_bytes())
        (work / 'TASK.md').write_bytes((public / 'TASK.md').read_bytes())
        (work / 'acceptance.feature').write_bytes((public / 'acceptance.feature').read_bytes())
        (work / '.e2e').mkdir()
        runner = {'executable': '/usr/local/bin/node', 'args': ['/adapter.mjs'],
                  'adapterFiles': ['/adapter.mjs', '/pilot/probe.mjs', '/pilot/profile.json', '/pilot/TASK.md'],
                  'timeoutMs': 15000}
        runner_text = json.dumps(runner)
        (work / '.e2e/runner.json').write_text(runner_text)
        run_args = ['docker', 'run', '-d', '--name', name, '--network', NETWORK, '--memory', '1g',
                    '--cpus', '1', '--pids-limit', '128', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                    '-v', f'{work}:/workspace', '-v', f'{config}:/agent', '-v', f'{public}:/pilot:ro',
                    '-v', f'{HERE}/adapter.mjs:/adapter.mjs:ro',
                    '-v', f'{HERE}/transport.mjs:/transport.mjs:ro',
                    '-e', 'PI_CODING_AGENT_DIR=/agent', '-e', 'PI_SKIP_VERSION_CHECK=1',
                    '-e', 'PI_TELEMETRY=0', *isolated_proxy_args(), '-e', f'TYPESAFE_API_KEY={proxy.token}', IMAGE]
        try:
            cmd(run_args)
            cli = ['docker', 'exec', '-w', '/workspace', name, 'node', '--import', '/transport.mjs',
                   '/opt/pilot-runtime/node_modules/@earendil-works/pi-coding-agent/dist/cli.js',
                   '--print', '--mode', 'json', '--no-session', '--no-extensions', '--no-skills',
                   '--no-context-files', '--no-prompt-templates', '--no-mcp', '--provider', MODEL['provider'],
                   '--model', MODEL['model'], '--thinking', 'high']
            cli += ['--tools', tools] if tools else ['--no-tools']
            if plugin:
                cli += ['-e', '/opt/pilot-runtime/node_modules/@fradser/pi-e2e/index.ts']
            prompt += (f'\nYou have {allowance} model/semantic requests in this phase. Work efficiently and finish with a concise report. '
                       'Only solution.mjs is delivered; use no dependencies. TASK.md, acceptance.feature, .e2e/runner.json and /pilot are frozen public inputs; do not edit them. '
                       'The public probe command available to BOTH strategies is: node /pilot/probe.mjs /workspace/solution.mjs. '
                       'No hidden grader or reference code exists here.\nPublic request:\n' + (public / 'TASK.md').read_text())
            process = subprocess.Popen(cli + [prompt], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            selector = selectors.DefaultSelector()
            assert process.stdout and process.stderr
            selector.register(process.stdout, selectors.EVENT_READ, 'stdout')
            selector.register(process.stderr, selectors.EVENT_READ, 'stderr')
            buffers = {'stdout': b'', 'stderr': b''}
            drain_deadline = float('inf')
            with (folder / 'events.jsonl').open('w') as output, (folder / 'stderr.log').open('w') as error:
                while selector.get_map():
                    if reason is None and time.monotonic() - start >= 1200:
                        reason = 'phase_safety_deadline'
                        cmd(['docker', 'stop', '-t', '1', name], check=False)
                        drain_deadline = time.monotonic() + 5
                    if time.monotonic() > drain_deadline:
                        break
                    for key, _ in selector.select(0.2):
                        block = key.fileobj.read1(65536)
                        if not block:
                            selector.unregister(key.fileobj)
                            continue
                        channel = key.data
                        buffers[channel] += block
                        while b'\n' in buffers[channel]:
                            raw, buffers[channel] = buffers[channel].split(b'\n', 1)
                            text = redact_transport_credentials(raw.decode(errors='replace'), proxy)
                            target = output if channel == 'stdout' else error
                            target.write(text + '\n'); target.flush()
                            if channel != 'stdout':
                                continue
                            try:
                                event = json.loads(text)
                            except ValueError:
                                continue
                            events.append(event)
                            if reason is None and proxy.requests >= cap and event.get('type') == 'tool_execution_end':
                                reason = 'request_allowance_handoff'
                                cmd(['docker', 'stop', '-t', '1', name], check=False)
                                drain_deadline = time.monotonic() + 5
                    save(folder / 'progress.json', {'requests': proxy.requests - before, 'jevRequests': proxy.jev_requests - jev_before,
                                                    'elapsedSeconds': round(time.monotonic() - start, 2)})
                selector.close()
                for channel, buffer in buffers.items():
                    if buffer:
                        (output if channel == 'stdout' else error).write(redact_transport_credentials(buffer.decode(errors='replace'), proxy))
            try:
                code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); code = process.wait(timeout=5)
            process.stdout.close(); process.stderr.close()
            source.write_bytes((work / 'solution.mjs').read_bytes())
            fixed = ((work / 'TASK.md').read_bytes() == (public / 'TASK.md').read_bytes()
                     and (work / 'acceptance.feature').read_bytes() == (public / 'acceptance.feature').read_bytes()
                     and (work / '.e2e/runner.json').read_text() == runner_text)
        finally:
            cmd(['docker', 'rm', '-f', name], check=False)
    result = {'events': events, 'exitCode': code, 'reason': reason, 'reportCompleted': completed(events, code),
              'requests': proxy.requests - before, 'jevRequests': proxy.jev_requests - jev_before,
              'transportErrors': proxy.errors - errors_before, 'elapsedSeconds': round(time.monotonic() - start, 2),
              'sourceBefore': initial_hash, 'sourceAfter': digest(source), 'fixedInputsIntact': fixed,
              'costEstimatedUsd': sum(m.get('usage', {}).get('cost', {}).get('total', 0) for m in messages(events)),
              'usage': [m.get('usage', {}) for m in messages(events)], 'billingVerified': False}
    result['jevUsage'] = proxy.jev_usage[jev_usage_before:]
    result['jevEstimatedUsd'] = sum(u['input_tokens'] for u in result['jevUsage']) * .042 / 1e6
    if plugin:
        calls = [e.get('args', {}) for e in events if e.get('type') == 'tool_execution_start' and e.get('toolName') == 'e2e_verify']
        expected_runner = {key: runner[key] for key in ['executable', 'args', 'timeoutMs']}
        result['nativeArgumentsValid'] = bool(calls) and all(
            c.get('feature') in ['acceptance.feature', '/workspace/acceptance.feature']
            and c.get('runner') == expected_runner and c.get('offline') is False
            and not any(k in c for k in ['clauseGate', 'verdictGate', 'minConfidence', 'evidence']) for c in calls)
    save(folder / 'result.json', {k: v for k, v in result.items() if k != 'events'})
    return result


def handoff(proxy: InferenceProxy, public: Path, source: Path, folder: Path,
            stage_result: dict[str, Any], arm: str) -> dict[str, Any]:
    """This cannot suppress the later fix stage, even if summarization itself fails."""
    if stage_result['reportCompleted']:
        return stage_result
    context = json.dumps(packet(arm, stage_result['events']), ensure_ascii=False)
    summary = stage(proxy, public, source, folder, 'Summarize this incomplete phase using only recorded evidence below. '
                    'No further tools or investigation. Distinguish findings, unknowns, and unfinished work.\n' + context[-24000:],
                    tools='', allowance=1)
    return {**stage_result, 'handoff': summary, 'events': stage_result['events'] + summary['events']}
