from __future__ import annotations

from support import run_bun


def _result_fixture() -> str:
    return r'''
      import { initTheme } from '@earendil-works/pi-coding-agent';
      import register, { learningResultContent } from './packages/continual-learning/extensions/inject-memory.ts';
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
      const render = (message, expanded) => renderer(message, { expanded }, theme).render(100).join('\n');
    '''


def test_learning_result_expands_to_markdown_descriptions_and_bodies() -> None:
    # Given a run that applied safe Memory entries, When the user expands the
    # one-line final result, Then each entry's description and body render as
    # Markdown. Frontmatter, filenames and receipt details are NOT part of the
    # expansion: they are metadata, not the learned content.
    source = _result_fixture() + r'''
      const appliedMemory = [
        { name: 'pnpm-contract.md', content: '---\nname: pnpm-contract\ndescription: **Builds** use pnpm\ntype: project\n---\nThe project builds with **pnpm** and verifies with `pnpm test`.', classification: 'safe' },
        { name: 'release-scope.md', content: '---\nname: release-scope\ndescription: Release scope\ntype: project\n---\nKeep release checks separate from local builds.', classification: 'safe' },
      ];
      const message = { content: learningResultContent('Learning result', appliedMemory), details: receipt };
      const collapsed = render(message, false);
      const expanded = render(message, true);
      const noisy = ['input 10', 'output 2', 'cost', 'usage', 'mode', 'source', 'calls', 'directions', 'selector:', 'memory #', 'status ·', 'summary ·'];
      console.log(JSON.stringify({ collapsed, expanded,
        noisy: noisy.filter(text => collapsed.includes(text) || expanded.includes(text)), messages }));
    '''
    output = run_bun(source)
    assert "[learning] 2 memories and 1 harness change applied" in output["collapsed"]
    assert "to expand" in output["collapsed"], output["collapsed"]
    assert "pnpm-contract.md" not in output["collapsed"], "collapsed row must stay one line"
    assert "Builds use pnpm" in output["expanded"], output["expanded"]
    assert "**Builds**" not in output["expanded"], "description must render as Markdown"
    assert "Release scope" in output["expanded"], output["expanded"]
    assert "The project builds with" in output["expanded"], output["expanded"]
    assert "Keep release checks separate from local builds." in output["expanded"]
    # No raw frontmatter, filenames or metadata in the expanded body.
    for marker in ("pnpm-contract.md", "release-scope.md", "name: pnpm-contract", "type: project", "--- generated Memory ---", "---\n"):
        assert marker not in output["expanded"], (marker, output["expanded"])
    # Markdown is rendered by pi-tui, not printed as literal source markers.
    assert "**pnpm**" not in output["expanded"], output["expanded"]
    assert "`pnpm test`" not in output["expanded"], output["expanded"]
    assert output["noisy"] == [], output["noisy"]
    assert output["messages"] == []


def test_learning_result_without_applied_memory_stays_one_unexpandable_line() -> None:
    # Given a run with no applied safe Memory (proposed/held/private/failed),
    # When rendered collapsed and expanded, Then the row stays one compact line
    # with no expand affordance and no body.
    source = _result_fixture() + r'''
      const message = { content: '', details: receipt };
      const collapsed = render(message, false);
      const expanded = render(message, true);
      let malformedSafe = true;
      try {
        for (const details of [{ broken: true }, { kind: 'learning-pipeline-receipt', version: 1, attempts: [], totals: {}, operations: 0, costAvailable: false }]) {
          render({ content: 'fallback', details }, false);
          render({ content: 'fallback', details }, true);
        }
        render({ content: 42, details: receipt }, false);
        render({ content: 42, details: receipt }, true);
      } catch { malformedSafe = false; }
      console.log(JSON.stringify({ collapsed, expanded, malformedSafe, messages }));
    '''
    output = run_bun(source)
    assert "[learning] 2 memories and 1 harness change applied" in output["collapsed"]
    assert output["collapsed"] == output["expanded"], output["expanded"]
    assert "to expand" not in output["collapsed"]
    assert output["malformedSafe"] is True
    assert output["messages"] == []


def test_learning_result_expansion_never_renders_private_or_sensitive_entries() -> None:
    # The parent owns privacy: private and credential-shaped entries never enter
    # the emitted content, and a forged credential-shaped entry in stored
    # content is dropped by the renderer as a second line of defence.
    source = _result_fixture() + r'''
      const appliedMemory = [
        { name: 'public.md', content: 'A public project fact.', classification: 'safe' },
        { name: 'private.md', content: 'A private preference.', classification: 'private' },
        { name: 'secret.md', content: 'api_key: abcdefghijklmnop', classification: 'safe' },
      ];
      const content = learningResultContent('Learning result', appliedMemory);
      const emitted = render({ content, details: receipt }, true);
      const forged = render({ content: content + '\n\nforged.md\napi_key: abcdefghijklmnop', details: receipt }, true);
      const collapsed = render({ content, details: receipt }, false);
      console.log(JSON.stringify({ content, emitted, forged, collapsed, messages }));
    '''
    output = run_bun(source)
    assert "private.md" not in output["content"], output["content"]
    assert "A private preference." not in output["content"], output["content"]
    assert "secret.md" not in output["content"], output["content"]
    assert "A public project fact." in output["emitted"], output["emitted"]
    # The expansion shows learned content, not file-identity details.
    assert "public.md" not in output["emitted"], output["emitted"]
    assert "A public project fact." in output["forged"], output["forged"]
    assert "forged.md" not in output["forged"], output["forged"]
    assert "abcdefghijklmnop" not in output["emitted"] and "abcdefghijklmnop" not in output["forged"]
    assert "to expand" in output["collapsed"]


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


def test_started_row_names_the_real_task_topic_not_a_generic_placeholder() -> None:
    # Given a real user entry naming a specific topic, When a learning run
    # starts, Then both the started row and the spinner use that bounded topic,
    # never the generic "learn from this task" or a claim of knowledge learned.
    from pathlib import Path
    from support import run_bun_script

    value = run_bun_script(Path(__file__).with_name("learning-policy-harness.ts"), "manual-constraint")
    subjects = value["startedSubjects"]
    assert subjects, value
    assert value["quote"] == "Never run the retired compiler.", value["quote"]
    assert all("Never run the retired compiler." in subject for subject in subjects), subjects
    assert all("learn from this task" not in subject for subject in subjects), subjects
    assert all("learned" not in subject.lower() for subject in subjects), subjects


def test_started_row_falls_back_when_no_real_user_topic_exists() -> None:
    from pathlib import Path
    from support import run_bun_script

    value = run_bun_script(Path(__file__).with_name("learning-policy-harness.ts"), "empty-full")
    subjects = value["startedSubjects"]
    assert subjects, value
    assert all(subject and "\n" not in subject for subject in subjects), subjects
    assert all(subject == "maintain all knowledge" for subject in subjects), subjects
