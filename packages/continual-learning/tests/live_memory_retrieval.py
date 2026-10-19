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
    fixture = json.loads((tests / 'fixtures/real-memory-retrieval-ranking.json').read_text())
    node = shutil.which('node')
    pi = tests.parents[2] / 'node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js'
    assert node and pi.is_file(), 'Installed workspace Pi CLI required'
    with tempfile.TemporaryDirectory(prefix='cl-native-retrieval-') as directory:
        root = Path(directory).resolve()
        cwd, agent = root / 'project', root / 'agent'
        cwd.mkdir()
        agent.mkdir()
        scope = '--' + str(cwd).lstrip('/').replace('/', '-') + '--'
        memory = agent / 'memory' / scope
        memory.mkdir(parents=True)
        registry = agent / 'memory/scopes'
        registry.mkdir()
        (registry / (scope + '.json')).write_text(json.dumps({'version': 1, 'cwd': str(cwd)}))
        for entry in fixture['entries']:
            assert Path(entry['filename']).name == entry['filename']
            (memory / entry['filename']).write_text(entry['content'])
        (memory / 'MEMORY.md').write_text('\n'.join('- [' + e['filename'] + '](' + e['filename'] + ')' for e in fixture['entries']))
        (agent / 'settings.json').write_text(json.dumps({'packages': [], 'quietStartup': True}))
        (agent / 'memory/settings.json').write_text(json.dumps({'autoMemory': False, 'automaticPhases': {'memory': 'off', 'harness': 'off', 'agents': 'off'}}))
        result = root / 'result.json'
        env = {k: v for k, v in os.environ.items() if k in {'PATH', 'LANG', 'LC_ALL'}}
        env.update(HOME=str(root), PI_CODING_AGENT_DIR=str(agent), PI_OFFLINE='1',
                   PI_RETRIEVAL_FIXTURE_AUTH=secrets.token_hex(16), PI_RETRIEVAL_FIXTURE_RESULT=str(result))
        version = subprocess.check_output([node, str(pi), '--version'], env=env, text=True).strip()
        assert version == '1.3.0', 'Pi compatibility baseline changed'
        command = [node, str(pi), '--no-session', '--offline', '--no-extensions', '--no-skills', '--no-prompt-templates',
                   '--no-context-files', '--no-themes', '--no-approve', '--no-builtin-tools',
                   '--extension', str(tests / 'memory-retrieval-live-fixture.ts'), '--provider', 'memory-retrieval-fixture',
                   '--model', 'deterministic', '--thinking', 'off', '--print', fixture['query']]
        completed = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert result.exists(), 'Actual provider request never reached offline acceptance'
        data = json.loads(result.read_text())
        assert data['status'] == 'passed'
        print(json.dumps({**data, 'piVersion': version,
                          'isolatedMemoryCopiedForOfflineAcceptanceOnly': True, 'realCohortUnchanged': True}))


if __name__ == '__main__':
    main()
