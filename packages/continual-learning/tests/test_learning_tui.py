from __future__ import annotations

from support import run_bun


def test_learning_result_is_one_final_unexpandable_line() -> None:
    # Given a completed receipt with usage, cost and several phase attempts,
    # When the user renders or expands the result, Then only the final outcome
    # is visible. The complete receipt stays in message details for the model.
    source = r'''
      import { initTheme } from '@earendil-works/pi-coding-agent';
      import register from './packages/continual-learning/extensions/inject-memory.ts';
      initTheme('dark');
      const renderers = new Map(), commands = new Map(), messages = [], hooks = new Map();
      const pi = {
        on: (name, handler) => hooks.set(name, [...(hooks.get(name) ?? []), handler]),
        registerCommand: (name, command) => commands.set(name, command),
        registerMessageRenderer: (name, renderer) => renderers.set(name, renderer),
        registerEntryRenderer: () => {},
        appendEntry: () => {},
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
      const render = (expanded) => renderer({ content: '', details: receipt }, { expanded }, theme).render(100).join('\n');
      const collapsed = render(false);
      const expanded = render(true);
      const noisy = ['input 10', 'output 2', 'cost', 'usage', 'mode', 'source', 'calls', 'directions', 'selector:', 'memory #', 'status ·', 'summary ·', 'to expand'];
      let malformedSafe = true;
      try {
        for (const details of [{ broken: true }, { kind: 'learning-pipeline-receipt', version: 1, attempts: [], totals: {}, operations: 0, costAvailable: false }]) {
          renderer({ content: 'fallback', details }, { expanded: false }, theme).render(100);
          renderer({ content: 'fallback', details }, { expanded: true }, theme).render(100);
        }
      } catch { malformedSafe = false; }
      console.log(JSON.stringify({ collapsed, expanded, noisy: noisy.filter(text => collapsed.includes(text) || expanded.includes(text)), malformedSafe, messages }));
    '''
    output = run_bun(source)
    assert "[learning] 2 memories and 1 harness change applied" in output["collapsed"]
    assert output["collapsed"] == output["expanded"], output["expanded"]
    assert output["noisy"] == [], output["noisy"]
    assert output["malformedSafe"] is True
    assert output["messages"] == []


def test_learning_start_is_one_user_transcript_row() -> None:
    # Given a learning run, When it starts, Then the user sees one compact
    # started row and the model keeps the full procedure in message content.
    source = r'''
      import { initTheme } from '@earendil-works/pi-coding-agent';
      import register from './packages/continual-learning/extensions/inject-memory.ts';
      initTheme('dark');
      const renderers = new Map(), messages = [];
      const pi = {
        on: () => {},
        registerCommand: () => {},
        registerMessageRenderer: (name, renderer) => renderers.set(name, renderer),
        registerEntryRenderer: () => {},
        appendEntry: () => {},
        sendMessage: (message, options) => messages.push({ message, options }),
        getCommands: () => [],
      };
      register(pi);
      const renderer = renderers.get('learning-procedure');
      const theme = { fg: (_c, text) => text, bg: (_c, text) => text, bold: text => text };
      const render = (expanded) => renderer(
        { content: 'Complete procedure for the model.', details: { subject: 'remember this request' } },
        { expanded }, theme).render(100).join('\n');
      console.log(JSON.stringify({ collapsed: render(false), expanded: render(true), registered: [...renderers.keys()] }));
    '''
    output = run_bun(source)
    assert "[learning] started" in output["collapsed"]
    assert "remember this request" in output["collapsed"]
    assert output["collapsed"] == output["expanded"], output["expanded"]
    assert "to expand" not in output["collapsed"]
    assert "Complete procedure" not in output["collapsed"]
    assert "learning-procedure" in output["registered"]
