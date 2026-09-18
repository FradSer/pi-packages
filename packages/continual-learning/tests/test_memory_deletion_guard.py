from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_builtin_blocks_bulk_memory_deletion_but_allows_unrelated_cleanup() -> None:
    source = """
      import { DEFAULT_RULES, evaluateBash, mergeLayers } from './packages/continual-learning/extensions/guardrail-engine.ts';
      const config = mergeLayers([{ source: 'defaults', rules: DEFAULT_RULES }]);
      const decide = command => evaluateBash(config, command);
      console.log(JSON.stringify({
        directory: decide('rm -rf .memory'),
        glob: decide('git rm .memory/*.md'),
        find: decide('find .memory -type f -delete'),
        unlink: decide('unlink .memory/MEMORY.md'),
        script: decide(`python -c "import shutil; shutil.rmtree('.memory')"`),
        privateRoot: decide('rm -rf ~/.pi/agent/memory/project-scope'),
        unrelated: decide('rm -rf dist').decision === 'execute',
      }));
    """
    result = subprocess.run(["bun", "-e", source], cwd=REPO, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    for key in ['directory', 'glob', 'find', 'unlink', 'script', 'privateRoot']:
        assert payload[key]['decision'] == 'block'
    assert payload["unrelated"] is True
