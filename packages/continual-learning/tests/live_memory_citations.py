"""Offline native-Pi request acceptance, not learning-effectiveness evidence."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile


def main() -> None:
    tests = Path(__file__).resolve().parent
    fixture = json.loads((tests / 'fixtures/real-long-verifier-line.json').read_text())
    node = shutil.which('node')
    pi = tests.parents[2] / 'node_modules/@earendil-works/pi-coding-agent/dist/cli.js'
    assert node and pi.is_file(), 'Installed workspace Pi CLI required'
    with tempfile.TemporaryDirectory(prefix='cl-native-retrieval-') as directory:
        root = Path(directory).resolve()
        cwd, agent = root / 'project', root / 'agent'
        cwd.mkdir()
        agent.mkdir()
        evidence_file = cwd / 'frozen-evidence.json'
        evidence_file.write_text(json.dumps({'entries': [fixture['entry'], {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 'old-memory', 'name': 'read', 'arguments': {'path': '.memory/deployment.md'}}]}, {'role': 'toolResult', 'toolCallId': 'old-memory', 'toolName': 'read', 'isError': False, 'content': 'Old Memory deployment claim'}]}, ensure_ascii=False))
        (agent / 'settings.json').write_text(json.dumps({'packages': [], 'quietStartup': True}))
        result = root / 'result.json'
        env = {k: v for k, v in os.environ.items() if k in {'PATH', 'LANG', 'LC_ALL'}}
        env.update(HOME=str(root), PI_CODING_AGENT_DIR=str(agent), PI_OFFLINE='1',
                   PI_CITATION_FIXTURE_AUTH=secrets.token_hex(16), PI_CITATION_FIXTURE_RESULT=str(result), PI_CITATION_FIXTURE_FILE=str(evidence_file))
        version = subprocess.check_output([node, str(pi), '--version'], env=env, text=True).strip()
        assert version == '1.0.0', 'Pi compatibility baseline changed'
        command = [node, str(pi), '--no-session', '--offline', '--no-extensions', '--no-skills', '--no-prompt-templates',
                   '--no-context-files', '--no-themes', '--no-approve', '--no-builtin-tools',
                   '--extension', str(tests / 'memory-citation-live-fixture.ts'), '--provider', 'memory-citation-fixture',
                   '--model', 'deterministic', '--thinking', 'off', '--print', 'Read the scoped frozen evidence once.']
        completed = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert result.exists(), 'Actual provider request never reached offline acceptance'
        data = json.loads(result.read_text())
        assert data['status'] == 'passed'
        print(json.dumps({**data, 'piVersion': version,
                          'deterministicReaderOnly': True, 'realCohortUnchanged': True}))


if __name__ == '__main__':
    main()
