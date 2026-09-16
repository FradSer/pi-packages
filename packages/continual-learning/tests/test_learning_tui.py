from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_learning_renderer_and_explicit_delivery_are_compact_and_single() -> None:
    source = r'''
      import { initTheme } from '@earendil-works/pi-coding-agent';
      import register from './packages/continual-learning/extensions/inject-memory.ts';
      initTheme('dark');
      const renderers = new Map(), commands = new Map(), messages = [], hooks = new Map();
      const pi = {
        on: (name, handler) => hooks.set(name, [...(hooks.get(name) ?? []), handler]),
        registerCommand: (name, command) => commands.set(name, command),
        registerMessageRenderer: (name, renderer) => renderers.set(name, renderer),
        sendMessage: (message, options) => messages.push({ message, options }),
        getCommands: () => [],
      };
      register(pi);
      const receipt = {
        kind: 'learning-pipeline-receipt', version: 1, mode: 'manual',
        screen: { memory: true, harness: false, agents: false, reasons: [] },
        attempts: [
          { phase: 'selector', attempt: 0, outcome: 'applied', durationMs: 5, operations: 0 },
          { phase: 'memory', attempt: 0, outcome: 'applied', durationMs: 10, operations: 2 },
          { phase: 'harness', attempt: 0, outcome: 'applied', durationMs: 8, operations: 1 },
        ],
        totals: { input: 10, output: 2, cacheRead: 3, cacheWrite: 0, totalTokens: 15, cost: 0 },
        costAvailable: false, operations: 3, retries: 0,
      };
      const renderer = renderers.get('continual-learning-result');
      const theme = { fg: (_c, text) => text, bg: (_c, text) => text, bold: text => text };
      const collapsed = renderer({ content: '', details: receipt }, { expanded: false }, theme).render(100).join('\n');
      const expanded = renderer({ content: '', details: receipt }, { expanded: true }, theme).render(100).join('\n');
      let malformedSafe = true;
      try {
        renderer({ content: 'fallback', details: { broken: true } }, { expanded: false }, theme).render(100);
        renderer({ content: 'fallback', details: { kind: 'learning-pipeline-receipt', version: 1, attempts: [], totals: {}, operations: 0, costAvailable: false } }, { expanded: false }, theme).render(100);
        renderer({ content: 'fallback', details: { ...receipt, mode: 'bad', retries: 'x', attempts: [{ phase: 'selector', outcome: 'applied' }] } }, { expanded: false }, theme).render(100);
      } catch { malformedSafe = false; }
      console.log(JSON.stringify({ collapsed, expanded, malformedSafe, messages }));
    '''
    result = subprocess.run(["bun", "-e", source], cwd=REPO, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout.strip().splitlines()[-1])
    assert "[learning] event · 2 memories and 1 harness change applied" in output["collapsed"]
    assert "input 10" not in output["collapsed"]
    assert "usage · input 10" in output["expanded"]
    assert output["malformedSafe"] is True
    assert output["messages"] == []
