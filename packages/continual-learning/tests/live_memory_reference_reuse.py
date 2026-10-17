"""Actual offline Pi sessions: compact index reuse, refresh, removal, and restart."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from docker_experiment import model_prompt_observation
from live_learning_loop import API_KEY, MODEL, PROVIDER, message_text, pi_version, run_pi, stream_response


class Provider(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, *_args: object) -> None:
        pass

    def do_POST(self) -> None:
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.requests.append(payload)
        stream_response(self, 'DONE')


def run(parent: Path) -> dict:
    Provider.requests = []
    package = Path(__file__).resolve().parents[1]
    sources = [package / 'index.ts', package / 'extensions/inject-memory.ts', package / 'extensions/memory-files.ts', Path(__file__)]
    def source_hashes() -> dict[str, str]:
        return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    initial_hashes = source_hashes()
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='memory-reference-', dir=parent))
    project, agent = root / 'project', root / 'agent'
    project.mkdir(); agent.mkdir(mode=0o700)
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    public = project / '.memory'; public.mkdir()
    (public / 'fact.md').write_text('---\nname: fact\ndescription: initial description\ntype: project\n---\nBODY_MUST_NOT_BE_INJECTED\n')
    (agent / 'memory').mkdir()
    (agent / 'memory/settings.json').write_text(json.dumps({'autoMemory': False, 'agentsMd': {'disabled': True}}))
    (agent / 'settings.json').write_text(json.dumps({'packages': []}))
    (agent / 'continual-learning.json').write_text(json.dumps({'jev': False}))
    (agent / 'memory.json').write_text(json.dumps({'provider': PROVIDER, 'model': MODEL}))
    server = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    (agent / 'models.json').write_text(json.dumps({'providers': {PROVIDER: {
        'baseUrl': f'http://127.0.0.1:{server.server_port}/v1', 'api': 'openai-completions', 'apiKey': API_KEY,
        'models': [{'id': MODEL, 'reasoning': False, 'input': ['text'], 'contextWindow': 200000, 'maxTokens': 4096,
                    'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0}}],
    }}}))
    report = {'status': 'failed', 'outputDir': str(root), 'pi': pi_version(), 'remoteCalls': 0, 'cost': 0}
    try:
        session = root / 'session.jsonl'
        for i in range(5):
            if i == 2:
                (public / 'fact.md').write_text('---\nname: fact\ndescription: corrected description\ntype: project\n---\nNEW_BODY_MUST_NOT_BE_INJECTED\n')
            if i == 3:
                (public / 'fact.md').unlink()
            if i == 4:
                (public / 'fact.md').write_text('---\nname: fact\ndescription: restored description\ntype: project\n---\nBODY_MUST_NOT_BE_INJECTED\n')
                session = root / 'fresh-session.jsonl'
            result = run_pi(project, agent, session, f'User turn {i}: reply DONE.', server.server_port)
            (root / f'turn-{i}.jsonl').write_text(result.stdout)
            (root / f'turn-{i}.stderr').write_text(result.stderr)
            assert result.returncode == 0, result.stderr[-1000:]
            text = message_text(Provider.requests[-1])
            wire_observation = model_prompt_observation(Provider.requests[-1])
            assert wire_observation['memoryProtocolOnWire']
            assert wire_observation['memoryDiscoveryOnWire'] is (i != 3)
            assert 'use the read tool to inspect relevant indexed Memory entries' in text, 'Relevant Memory use protocol was not delivered'
            assert "Respect the task's write scope" in text, 'Read-only task boundary was not delivered'
            assert 'BODY_MUST_NOT_BE_INJECTED' not in text
            assert '(harness)' not in text and '(public)' not in text
            assert text.count('# Project memories') == (0 if i == 3 else 1)
            if i == 2:
                assert 'initial description' not in text and 'corrected description' in text
            if i < 2:
                entries = [json.loads(line) for line in session.read_text().splitlines()]
                references = [entry for entry in entries if entry.get('type') == 'custom_message' and entry.get('customType') == 'continual-learning-memory-reference']
                assert len(references) == 0, f'legacy discovery messages appended again: {len(references)}'
        assert source_hashes() == initial_hashes, 'Sources changed during verification'
        report.update(status='passed', providerRequests=len(Provider.requests), unchangedReferenceCount=0, structuredDiscoveryPerPayload=1,
                      changedReferenceReplaced=True, deletedReferenceRemoved=True, freshSessionRestored=True,
                      bodyInjected=False, modelWireMetadata=[model_prompt_observation(payload) for payload in Provider.requests], evidence='actual Pi CLI with deterministic loopback provider; no model learning claim')
        return report
    except BaseException as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        report.update(sourceHashes=initial_hashes, sourceHashesAfter=source_hashes(), sourceUnchanged=source_hashes() == initial_hashes)
        (root / 'requests.json').write_text(json.dumps(Provider.requests, indent=2))
        (root / 'manifest.json').write_text(json.dumps(report, indent=2))
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    run(Path(sys.argv[1]))
