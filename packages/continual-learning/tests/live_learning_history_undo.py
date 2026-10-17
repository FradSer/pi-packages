"""Real Pi learning -> native history -> confirmed undo -> exact restoration.

Explicit live acceptance, with a deterministic loopback provider and real parent
validation/writes. Default loopback mode uses no credentials or external services.
Explicit --real-model uses private temporary auth and incurs remote model usage.
Images reconstruct PTY
bytes, not OS screenshots. Run with uv --with pyte --with pillow.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
from http.server import ThreadingHTTPServer

from live_learning_loop import LoopbackProvider, PACKAGE, REPO, PROVIDER, MODEL, API_KEY
from live_manual_memory import NativeTui
from live_acceptance_support import EvidenceRun, isolated_environment, preflight, dialog_result, private_provider_copy, archive_terminal, workspace_pi


def snapshot_surfaces(roots: dict[str, Path]) -> dict:
    result = {}
    for label, root in roots.items():
        if root.is_symlink():
            raise AssertionError('Learned surface is a symlink')
        files = sorted(root.rglob('*')) if root.is_dir() else [root]
        for file in files:
            if file.is_symlink():
                raise AssertionError('Learned file is a symlink')
            if not file.is_file():
                continue
            key = label + ('/' + str(file.relative_to(root)) if root.is_dir() else '')
            data = file.read_bytes()
            result[key] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': data.hex(), 'mode': file.stat().st_mode & 0o777}
    return result


def assert_restored(before: dict, after: dict) -> None:
    assert before == after, f'Predecessor mismatch: {set(before) ^ set(after)}; changed={[key for key in before.keys() & after.keys() if before[key] != after[key]]}'


def cancel_observed(events: list[dict], start: int) -> bool:
    return any(row.get('kind') == 'confirmed' and row.get('value') is False for row in events[start:])


def expected_subject(receipt: dict) -> str:
    counts = {phase: sum(row.get('operations', 0) for row in receipt['attempts'] if row['phase'] == phase and row['outcome'] == 'applied') for phase in ('memory', 'harness')}
    parts = []
    if counts['memory']:
        parts.append(f"{counts['memory']} {'memory' if counts['memory'] == 1 else 'memories'}")
    if counts['harness']:
        parts.append(f"{counts['harness']} harness {'change' if counts['harness'] == 1 else 'changes'}")
    return ' and '.join(parts) + ' applied'


def validate_learning_result(receipt: dict, records: list[dict], learned: dict, visible: str, *, real_model: bool = False) -> None:
    import base64
    attempts = receipt['attempts']
    counts = {phase: sum(row.get('operations', 0) for row in attempts if row['phase'] == phase and row['outcome'] == 'applied') for phase in ('memory', 'harness')}
    if real_model:
        assert counts['memory'] > 0 and counts['harness'] == 0, counts
    else:
        assert counts == {'memory': 1, 'harness': 1}, counts
    last = {row['phase']: row['outcome'] for row in attempts}
    assert all(last.get(phase) == 'applied' for phase in (('memory',) if real_model else ('memory', 'harness')))
    assert not any(outcome in {'failed', 'rejected', 'cancelled'} for outcome in last.values()), 'Terminal learning failure'
    assert expected_subject(receipt) in visible, 'Native result disagrees with applied receipt'
    assert {row['phase'] for row in records} == ({'memory'} if real_model else {'memory', 'harness'}), 'History phases disagree with receipt'
    assert all(row['status'] == 'applied' for row in records)
    assert any(change['target']['name'].endswith('.md') and change['target']['name'] != 'MEMORY.md' for row in records if row['phase'] == 'memory' for change in row['changes'])
    assert real_model or any(change['target'] == {'root': 'project', 'name': '.pi/harness.json'} for row in records if row['phase'] == 'harness' for change in row['changes'])
    seen = set()
    # History is newest first: older index bootstrap states are predecessors.
    for row in records:
        for change in row['changes']:
            target = change['target']
            key = target['root'] + '/' + target['name'] if target['root'] != 'project' else {'.pi/harness.json': 'harness', 'AGENTS.md': 'agents'}[target['name']]
            if key in seen:
                continue
            seen.add(key)
            state = change['after']
            if state is None:
                assert key not in learned
            else:
                data = base64.b64decode(state['bytes'])
                assert learned[key] == {'sha256': state['digest'], 'bytes': data.hex(), 'mode': state['mode']}, key
                assert hashlib.sha256(data).hexdigest() == state['digest'], key


def run(output: Path, *, real_model: bool = False, raw_memory_json: bool = False) -> dict:
    if real_model and raw_memory_json:
        raise ValueError("Raw JSON fixture is offline only")
    LoopbackProvider.raw_memory_json = raw_memory_json
    files = [PACKAGE / 'index.ts', PACKAGE / 'package.json', REPO / 'packages/kit/package.json',
             *sorted(file for folder in ('extensions', 'prompts', 'scripts') for file in (PACKAGE / folder).rglob('*')
                     if file.is_file() and file.suffix in {'.ts', '.py', '.md', '.json', '.mjs', '.sh'}),
             *sorted((REPO / 'packages/kit/src').rglob('*.ts')),
             *sorted(Path(__file__).parent.glob('live_*.py')), Path(__file__).with_name('support.py')]
    evidence = EvidenceRun(output, {str(file.relative_to(REPO)): file for file in files})
    report = {'status': 'running', 'outputDir': str(evidence.output),
              'revision': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO, capture_output=True, text=True).stdout.strip(),
              'localChanges': subprocess.run(['git', 'status', '--short'], cwd=REPO, capture_output=True, text=True).stdout.splitlines()}
    evidence.write('manifest.json', json.dumps(report, indent=2))
    try:
        _run(evidence, report, real_model=real_model, raw_memory_json=raw_memory_json)
    except Exception as error:
        report.update({'status': 'failed', 'errorType': type(error).__name__, 'error': str(error)})
        raise
    finally:
        evidence.finish(report)
        evidence.write('run.log', json.dumps({key: report.get(key) for key in ('status', 'errorType', 'outputDir', 'cliExitCode', 'sourceUnchanged')}, indent=2))
    assert report['status'] == 'passed', 'Acceptance failed; inspect the run manifest'
    return report


def _run(evidence: EvidenceRun, report: dict, *, real_model: bool, raw_memory_json: bool = False) -> None:
    output = evidence.output
    import fcntl
    import struct
    import termios
    import pyte
    from PIL import Image, ImageDraw, ImageFont

    output.mkdir(parents=True, exist_ok=True)
    LoopbackProvider.requests = []
    LoopbackProvider.responses = []
    server = ThreadingHTTPServer(('127.0.0.1', 0), LoopbackProvider)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    report.update({'source': 'real Pi CLI, native menus, real validated writes; ' + ('configured real model, Memory only' if real_model else 'deterministic loopback Memory and Harness plans'), 'providerCondition': ('configured remote model; Jev disabled' if real_model else 'loopback only; Jev disabled; inherited service environment removed; not a packet capture'), 'captures': [], 'interactions': []})
    secrets = []
    def safe(data: bytes) -> bytes:
        assert not any(value in data for value in secrets), 'Credential in terminal evidence; capture refused'
        return data
    try:
        with tempfile.TemporaryDirectory(prefix='cl-history-undo-') as raw:
            base = Path(raw).resolve()
            project, agent = base / 'project', base / 'agent'
            project.mkdir(); agent.mkdir(mode=0o700); (agent / 'memory').mkdir()
            (project / '.pi').mkdir()
            (project / '.pi/harness.json').write_text('{"rules":[]}\n')
            (project / 'AGENTS.md').write_bytes(b'# Existing project\r\n\r\nPreserve this file.\r\n')
            (project / 'unrelated.txt').write_bytes(b'unrelated predecessor\x00\r\n')
            (agent / 'settings.json').write_text(json.dumps({'quietStartup': True, 'packages': []}))
            (agent / 'continual-learning.json').write_text(json.dumps({'jev': False}))
            (agent / 'memory.json').write_text(json.dumps({'provider': PROVIDER, 'model': MODEL}))
            (agent / 'models.json').write_text(json.dumps({'providers': {PROVIDER: {
                'baseUrl': f'http://127.0.0.1:{server.server_port}/v1', 'api': 'openai-completions', 'apiKey': API_KEY,
                'models': [{'id': MODEL, 'reasoning': False, 'input': ['text'], 'contextWindow': 200000, 'maxTokens': 4096,
                            'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0}}]}}}))
            settings = agent / 'memory/settings.json'
            settings.write_text(json.dumps({'autoMemory': True, 'automaticPhases': {'memory': 'apply', 'harness': 'apply', 'agents': 'off'}, 'agentsMd': {'disabled': True}}))
            provider, model = PROVIDER, MODEL
            if real_model:
                # Explicit opt-in: copy auth privately, never into retained evidence.
                source = Path(os.environ.get('PI_CODING_AGENT_DIR', str(Path.home() / '.pi/agent')))
                configured = json.loads((source / 'memory.json').read_text())
                provider, model = configured['provider'], configured['model']
                (agent / 'memory.json').write_text(json.dumps({'provider': provider, 'model': model}))
                (agent / 'models.json').unlink()
                secrets = private_provider_copy(source, agent, provider)
                settings.write_text(json.dumps({'autoMemory': True, 'automaticPhases': {'memory': 'apply', 'harness': 'off', 'agents': 'off'}, 'agentsMd': {'disabled': True}}))
            subprocess.run(['git', 'init', '-q', str(project)], check=True)
            events = base / 'events.jsonl'
            probe = base / 'probe.ts'
            probe.write_text("import fs from 'node:fs'; export default function(pi) {" +
                f"const emit=(x)=>fs.appendFileSync({json.dumps(str(events))},JSON.stringify(x)+'\\n');" +
                "pi.on('session_start',(_e,ctx)=>{const notify=ctx.ui.notify.bind(ctx.ui);ctx.ui.notify=(message,level)=>{emit({kind:'notify',message,level});return notify(message,level)};" +
                "const select=ctx.ui.select.bind(ctx.ui);ctx.ui.select=async(title,options)=>{emit({kind:'select',title,options});const value=await select(title,options);emit({kind:'selected',title,value});return value};" +
                "let dialogId=0;const confirm=ctx.ui.confirm.bind(ctx.ui);ctx.ui.confirm=async(title,body)=>{const id=++dialogId;emit({kind:'confirm',dialogId:id,title,body});const value=await confirm(title,body);emit({kind:'confirmed',dialogId:id,value});return value};emit({kind:'ready'})});}")
            env = isolated_environment(base, agent)
            report['preflight'] = preflight(base, project, agent, env, real_model=real_model)
            evidence.write('preflight.json', json.dumps(report['preflight'], indent=2))
            evidence.verify_sources()
            report['piVersion'] = subprocess.run([workspace_pi(REPO), '--version'], cwd=project, env=env, capture_output=True, text=True, check=True).stdout.strip()
            report['piPath'] = workspace_pi(REPO)
            command = [report['piPath'], '--offline', '--no-extensions', '-e', str(PACKAGE / 'index.ts'), '-e', str(probe),
                       '--no-skills', '--no-prompt-templates', '--no-themes', '--no-context-files', '--no-approve',
                       '--session', str(base / 'session.jsonl'), '--model', f'{provider}/{model}', '--no-builtin-tools', '--thinking', 'off']
            tui = NativeTui(command, project, env)
            screen = pyte.Screen(120, 40); stream = pyte.Stream(screen); consumed = 0
            fcntl.ioctl(tui.master, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 120, 0, 0))
            def display():
                nonlocal consumed
                stream.feed(bytes(tui.transcript[consumed:]).decode('utf8', errors='replace')); consumed = len(tui.transcript)
                return '\n'.join(screen.display)
            def rows():
                return [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
            def send(data: bytes, description: str):
                evidence.verify_sources()
                report['interactions'].append({'sequence': len(report['interactions']) + 1, 'action': description, 'bytesHex': data.hex(), 'terminalOffset': len(tui.transcript)}); os.write(tui.master, data)
            def wait_text(text: str):
                tui.wait_until(lambda: text in display(), 40, 'Missing native screen: ' + text)
            def resize(width: int, height: int):
                previous = len(tui.transcript)
                screen.resize(lines=height, columns=width)
                fcntl.ioctl(tui.master, termios.TIOCSWINSZ, struct.pack('HHHH', height, width, 0, 0))
                tui.process.send_signal(signal.SIGWINCH)
                tui.wait_until(lambda: len(tui.transcript) > previous, 20, 'No native repaint after live resize')
            def capture(name: str):
                # Drain the native renderer after the observable state transition.
                import select
                while select.select([tui.master], [], [], .15)[0]: tui._pump()
                safe(bytes(tui.transcript))
                assert not (output / f'{name}.png').exists(), 'Duplicate capture name'
                text = display(); (output / f'{name}.txt').write_text(text)
                (output / f'{name}.ansi').write_bytes(tui.transcript)
                image = Image.new('RGB', (screen.columns * 13 + 32, screen.lines * 26 + 32), '#161616'); draw = ImageDraw.Draw(image)
                font = ImageFont.truetype('/System/Library/Fonts/Menlo.ttc', 20)
                colors = {'default': '#dadada', 'red': '#cc5555', 'green': '#55aa55', 'brown': '#c4a000', 'blue': '#5555cc', 'magenta': '#aa55aa', 'cyan': '#55aaaa', 'white': '#dadada', 'black': '#000000', 'brightblack': '#777777'}
                def color(value, background=False):
                    if value == 'default' and background: return '#161616'
                    return colors.get(value, '#' + value if len(value) == 6 else '#dadada')
                for y in range(screen.lines):
                    for x in range(screen.columns):
                        cell = screen.buffer[y][x]; fg, bg = color(cell.fg), color(cell.bg, True)
                        if cell.reverse: fg, bg = bg, fg
                        draw.rectangle((16+x*13, 16+y*26, 29+x*13, 41+y*26), fill=bg)
                        draw.text((16+x*13,16+y*26),cell.data,font=font,fill=fg)
                image.save(output / f'{name}.png')
                report['captures'].append({'name': name, 'columns': screen.columns, 'rows': screen.lines, 'provenance': 'PTY reconstruction', 'terminalOffset': len(tui.transcript)})
            def history():
                result = subprocess.run(['bun', '-e', f'import {{listLearningHistory}} from {json.dumps(str(PACKAGE / "extensions/learning-history.ts"))};console.log(JSON.stringify(await listLearningHistory({json.dumps(str(project))})));'], cwd=REPO, env=env, capture_output=True, text=True, check=True)
                return json.loads(result.stdout.strip().splitlines()[-1])
            try:
                tui.wait_until(lambda: any(row.get('kind') == 'ready' for row in rows()), 40, 'Pi did not start')
                roots = {'public': project / '.memory', 'harness': project / '.pi/harness.json', 'agents': project / 'AGENTS.md', 'unrelated': project / 'unrelated.txt'}
                # Resolve the actual canonical private scope before learning.
                result = subprocess.run(['bun', '-e', f'import {{resolveMemoryPaths}} from {json.dumps(str(PACKAGE / "extensions/memory-paths.ts"))};console.log(JSON.stringify(resolveMemoryPaths({json.dumps(str(project))})));'], cwd=REPO, env=env, capture_output=True, text=True, check=True)
                roots['private'] = Path(json.loads(result.stdout.strip().splitlines()[-1])['harnessDir'])
                before = snapshot_surfaces(roots)
                evidence.write('snapshots.json', json.dumps({'before': before, 'learned': None, 'after': None}, indent=2))
                prompt = ('Settled project knowledge: CL_REAL_ISOLATED_FACT means this disposable project uses `printf CL_REAL_ISOLATED_OK` as its local verification command. Remember this durable shared project fact for future tasks. Reply only acknowledged.' if real_model else 'LOOPBACK_MEMORY_FACT: This project uses printf CL_OFFLINE_SAFE as its settled local verification command. LOOPBACK_HARNESS_RULE: Never run printf CL_OFFLINE_BLOCKED; that marker is prohibited in this project. Reply only LOOPBACK_TASK_DONE.')
                send(prompt.encode() + b'\r', 'Learn durable project facts')
                receipt_files = lambda: list((agent / 'memory/runs').glob('**/learning-pipeline-receipt.json'))
                tui.wait_until(lambda: bool(receipt_files()), 480 if real_model else 180, 'Learning did not produce a final receipt')
                receipt_file = receipt_files()[0]; receipt_bytes = receipt_file.read_bytes(); receipt = json.loads(receipt_bytes)
                (output / 'receipt.json').write_bytes(receipt_bytes)
                if raw_memory_json:
                    conversions = []
                    for conversion_file in sorted((agent / 'memory/runs').glob('**/generation-json-whitespace.json')):
                        original_file = conversion_file.with_name('generation-original-output.json')
                        original = json.loads(original_file.read_text())
                        conversion = json.loads(conversion_file.read_text())
                        assert original['originalTransportRetained'] and not original['sensitive']
                        assert hashlib.sha256(original['stdout'].encode()).hexdigest() == original['originalTransportSha256']
                        assert conversion['counts']['newline'] > 0 and conversion['semanticAcceptance'] is False
                        (output / "generation-recovery" / conversion_file.parent.name).mkdir(parents=True, exist_ok=True)
                        for file in (conversion_file, original_file):
                            evidence.write('generation-recovery/' + conversion_file.parent.name + '/' + file.name, safe(file.read_bytes()).decode())
                        conversions.append({'runId': conversion['runId'], 'counts': conversion['counts'],
                                            'originalTransportSha256': original['originalTransportSha256']})
                    assert conversions, 'Raw fixture did not exercise initial-generation recovery'
                    assert 'memory-plan-repair' not in LoopbackProvider.responses, 'Lossless recovery spent an extra repair call'
                    report['generationSerializationRecovery'] = {'conversions': conversions, 'originalTransportRetained': True,
                                                                  'additionalRepairCalls': 0, 'semanticAcceptanceProven': False}
                wait_text('[learning]')
                capture('01-learning-result')
                assert ({('memory', 'applied')} if real_model else {('memory', 'applied'), ('harness', 'applied')}) <= {(row['phase'], row['outcome']) for row in receipt['attempts']}, receipt
                wait_text(expected_subject(receipt))
                learned = snapshot_surfaces(roots)
                evidence.write('snapshots.json', json.dumps({'before': before, 'learned': learned, 'after': None}, indent=2))
                assert learned != before
                if real_model:
                    assert any(b'CL_REAL_ISOLATED_FACT' in bytes.fromhex(state['bytes']) and b'printf CL_REAL_ISOLATED_OK' in bytes.fromhex(state['bytes']) for key, state in learned.items() if key.startswith('private/')), 'Real model did not retain the supplied fact'
                original_history = history(); assert len(original_history) >= 1 and all(row['status'] == 'applied' for row in original_history)
                validate_learning_result(receipt, original_history, learned, display(), real_model=real_model)
                assert len({row.get('batchId') for row in original_history}) == 1 and original_history[0].get('batchId'), 'Pipeline history lacks exact batch identity'
                (output / 'receipt.json').write_bytes(receipt_bytes)
                (output / 'history-applied.json').write_text(json.dumps(original_history, indent=2))
                # No additional learning should occur during verification and navigation.
                settings.write_text(json.dumps({'autoMemory': False, 'agentsMd': {'disabled': True}}))
                for index, record in enumerate(original_history):
                    send(b'/memory\r', 'Open Memory menu'); wait_text('Recent learning')
                    send(b'\x1b[A' * 5 + b'\x1b[B\x1b[B\r', 'Open Recent learning'); wait_text('Recent learning')
                    if record.get('batchId'):
                        wait_text('Learning batches')
                        if index == 0:
                            capture('02-batches-applied')
                            resize(48, 24); capture('02-batches-applied-narrow')
                            assert 'applied' in next(line for line in display().splitlines() if '#1 ' in line)
                            resize(120, 40)
                        send(b'\r', 'Open exact learning batch')
                    wait_text('#1 ')
                    capture(f'02-history-{index}')
                    if index == 0:
                        resize(48, 24); capture('02-history-narrow')
                        selected = next(line for line in display().splitlines() if '#1 ' in line)
                        assert 'applied' in selected, 'Narrow history hides the result'
                        resize(120, 40)
                    send(b'\x1b[B' * index + b'\r', 'Inspect applied change'); wait_text('Learning change')
                    wait_text(record['id'])
                    capture(f'03-detail-{index}')
                    send(b'\x1b[C\r', 'Choose Undo this change'); wait_text("Restore this learning change")
                    capture(f'04-confirm-{index}')
                    state = snapshot_surfaces(roots)
                    cancel_start = len(rows())
                    cancel_id = next(row['dialogId'] for row in reversed(rows()) if row.get('kind') == 'confirm')
                    send(b'\x1b', 'Cancel undo confirmation')
                    tui.wait_until(lambda: dialog_result(rows(), cancel_start, cancel_id, False), 20, 'Cancel was not observed')
                    assert_restored(state, snapshot_surfaces(roots))
                    assert next(row for row in history() if row['id'] == record['id'])['status'] == 'applied'
                    wait_text('Recent learning')
                    send(b'\x1b[A' * 5 + b'\x1b[B\x1b[B\r', 'Reopen history after cancel')
                    if record.get('batchId'):
                        wait_text('Learning batches'); send(b'\r', 'Reopen exact learning batch')
                    wait_text('#1 ')
                    send(b'\x1b[B' * index + b'\r', 'Reopen applied detail'); wait_text('Learning change')
                    send(b'\x1b[C\r', 'Request undo again'); wait_text("Restore this learning change")
                    confirmed_start = len(rows())
                    confirmed_id = next(row['dialogId'] for row in reversed(rows()) if row.get('kind') == 'confirm')
                    assert_restored(state, snapshot_surfaces(roots))
                    send(b'\r', 'Confirm restoration')
                    tui.wait_until(lambda: dialog_result(rows(), confirmed_start, confirmed_id, True), 20, 'Current confirmation was not observed')
                    tui.wait_until(lambda: next(row for row in history() if row['id'] == record['id'])['status'] == 'undone', 30, 'Undo did not persist')
                    capture(f'05-undone-{index}')
                    send(b'\x1b', 'Close root menu'); wait_text('Undone ')
                final_history = history(); assert all(row['status'] == 'undone' for row in final_history)
                after = snapshot_surfaces(roots)
                evidence.write('snapshots.json', json.dumps({'before': before, 'learned': learned, 'after': after}, indent=2))
                assert_restored(before, after)
                assert receipt_file.read_bytes() == receipt_bytes, 'Undo rewrote original receipt'
                send(b'/memory\r', 'Inspect retained undone history'); wait_text('Recent learning')
                send(b'\x1b[A' * 5 + b'\x1b[B\x1b[B\r', 'Open final history')
                if final_history[0].get('batchId'):
                    wait_text('Learning batches'); capture('06-batches-undone'); send(b'\r', 'Open retained learning batch')
                wait_text('undone'); capture('06-history-undone')
                resize(48, 24); capture('06-history-undone-narrow')
                assert 'undone' in next(line for line in display().splitlines() if '#1 ' in line)
                resize(120, 40)
                send(b'\r', 'Inspect undone read-only record'); wait_text('Learning change'); capture('07-undone-detail')
                assert 'Undo this change' not in display()
                send(b'\x1b', 'Close read-only detail'); wait_text('#1 ')
                send(b'\x1b', 'Leave change list')
                if final_history[0].get('batchId'):
                    wait_text('Learning batches'); send(b'\x1b', 'Return to Memory root')
                wait_text('Browse memories')
                release_start = len(rows())
                send(b'\x1b', 'Release menu input')
                tui.wait_until(lambda: any(row.get('kind') == 'selected' and 'value' not in row for row in rows()[release_start:]), 20, 'Root menu did not release input')
                send(b'/quit\r', 'Exit real Pi CLI')
                tui.wait_until(lambda: tui.process.poll() is not None, 30, 'Pi did not exit cleanly')
                assert tui.process.returncode == 0
                report['cliExitCode'] = 0
                report['status'] = 'passed'
                report.update({'providerResponses': LoopbackProvider.responses, 'receiptMatchesHistory': True, 'cancelPreservesFiles': True, 'allChangesUndone': True, 'exactRestoration': True, 'receiptPreserved': True})
                for name, value in [('snapshots', {'before': before, 'learned': learned, 'after': after}), ('history-undone', final_history)]:
                    (output / f'{name}.json').write_text(json.dumps(value, indent=2))
            finally:
                archive_terminal(bytes(tui.transcript), events, output, safe, tui.close)
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        raise
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)



if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='Parent directory; each invocation creates a new run directory')
    parser.add_argument('--raw-memory-json', action='store_true', help='Offline initial-generation raw string whitespace regression')
    parser.add_argument('--real-model', action='store_true', help='Use configured real provider; incurs model usage')
    args = parser.parse_args()
    result = run(args.output.resolve(), real_model=args.real_model, raw_memory_json=args.raw_memory_json)
    print(json.dumps({key: result[key] for key in ('status', 'outputDir', 'cliExitCode', 'sourceUnchanged')}, indent=2))
