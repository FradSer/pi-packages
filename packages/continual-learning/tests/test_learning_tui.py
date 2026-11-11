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
    # Each applied Memory is named so the user can identify which records were
    # written; raw frontmatter and receipt metadata stay out of the expansion.
    assert "pnpm-contract.md" in output["expanded"], output["expanded"]
    assert "release-scope.md" in output["expanded"], output["expanded"]
    for marker in ("name: pnpm-contract", "type: project", "--- generated Memory ---"):
        assert marker not in output["expanded"], (marker, output["expanded"])
    # Markdown is rendered by pi-tui, not printed as literal source markers.
    assert "**pnpm**" not in output["expanded"], output["expanded"]
    assert "`pnpm test`" not in output["expanded"], output["expanded"]
    assert output["noisy"] == [], output["noisy"]
    assert output["messages"] == []


def test_learning_result_without_applied_memory_stays_one_unexpandable_line() -> None:
    # Given a legacy message with no expanded content, When rendered collapsed
    # and expanded, Then the row stays one compact line with no expand affordance
    # and no body. Malformed stored shapes must not throw.
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


def test_learning_result_expansion_shows_private_memory_but_never_secrets() -> None:
    # The user owns all their Memory files: private (harness-only) entries are
    # shown in the terminal just like safe ones. Only credential-shaped content
    # stays out, both at construction time and on a forged stored message.
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
    assert "private.md" in output["content"], output["content"]
    assert "A private preference." in output["content"], output["content"]
    assert "secret.md" not in output["content"], output["content"]
    assert "A public project fact." in output["emitted"], output["emitted"]
    # Every applied Memory is named in the expansion regardless of privacy;
    # credential-shaped and forged entries still stay hidden.
    assert "public.md" in output["emitted"], output["emitted"]
    assert "private.md" in output["emitted"], output["emitted"]
    assert "A private preference." in output["emitted"], output["emitted"]
    assert "secret.md" not in output["emitted"], output["emitted"]
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


def test_applied_agents_md_edits_are_named_in_the_expanded_result() -> None:
    # Given a run that applied both a Memory and one AGENTS.md change, When the
    # user expands the result, Then both are identifiable: the Memory by name
    # and description/body, the AGENTS.md edit by its operation and applied unit
    # text. Receipt metadata, byte digests and the whole document stay hidden.
    source = _result_fixture() + r'''
      import { displayableAgentDetails } from './packages/continual-learning/extensions/inject-memory.ts';
      const appliedMemory = [
        { name: 'pi-tasks-waiting.md', content: '---\nname: pi-tasks-waiting\ndescription: pi-tasks emits a waiting row at settlement\ntype: project\n---\nUnfinished tasks keep the waiting reminder.', classification: 'safe' },
      ];
      const agents = displayableAgentDetails([
        { operation: 'addUnit', text: 'Use pnpm for verification before publishing.' },
        { operation: 'removeUnit', text: 'Old duplicated instruction.' },
      ]);
      const content = learningResultContent('Learning result', appliedMemory, agents);
      const emitted = render({ content, details: receipt }, true);
      const collapsed = render({ content, details: receipt }, false);
      console.log(JSON.stringify({ content, emitted, collapsed, agents }));
    '''
    output = run_bun(source)
    assert output["agents"] == [
        {"operation": "addUnit", "text": "Use pnpm for verification before publishing."},
        {"operation": "removeUnit", "text": "Old duplicated instruction."},
    ], output
    assert "pi-tasks-waiting.md" in output["emitted"], output["emitted"]
    assert "Unfinished tasks keep the waiting reminder." in output["emitted"], output["emitted"]
    assert "AGENTS.md" in output["emitted"], output["emitted"]
    assert "addUnit" in output["emitted"] and "removeUnit" in output["emitted"], output["emitted"]
    assert "Use pnpm for verification before publishing." in output["emitted"], output["emitted"]
    assert "to expand" in output["collapsed"], output["collapsed"]
    assert "addUnit" not in output["collapsed"], output["collapsed"]
    for marker in ("--- AGENTS.md changes ---", "bytesBefore", "digestBefore", "planDigest", "usage", "cost"):
        assert marker not in output["emitted"], (marker, output["emitted"])


def test_zero_write_result_expands_to_state_what_was_checked() -> None:
    # Given an in-process organize run with zero writes, When the user expands
    # the result, Then it says nothing was written and names the screened scope,
    # instead of looking like an unfinished run. A legacy message with an empty
    # content still stays one unexpandable line.
    source = _result_fixture() + r'''
      const note = 'No Memory or AGENTS.md changes were written. 66 frozen entries were checked; mirrors, indexes and consistency were verified.';
      const content = learningResultContent('Learning organized in-process', [], [], note);
      const emitted = render({ content, details: receipt }, true);
      const collapsed = render({ content, details: receipt }, false);
      const legacy = render({ content: '', details: receipt }, false);
      console.log(JSON.stringify({ emitted, collapsed, legacy }));
    '''
    output = run_bun(source)
    assert "No Memory or AGENTS.md changes were written" in output["emitted"], output["emitted"]
    assert "66 frozen entries were checked" in output["emitted"], output["emitted"]
    assert "to expand" in output["collapsed"], output["collapsed"]
    assert "No Memory or AGENTS.md changes" not in output["collapsed"], output["collapsed"]
    assert "to expand" not in output["legacy"], output["legacy"]


def test_displayable_memory_details_accept_private_and_refuse_secrets() -> None:
    # The collection gate is shared by the pipeline (plan object) and the
    # renderer (stored array). Both must admit private entries now, while
    # credential-shaped content and incomplete records stay out.
    source = _result_fixture() + r'''
      import { displayableMemoryDetails } from './packages/continual-learning/extensions/inject-memory.ts';
      const plan = { operations: [], newMemories: [
        { name: 'safe.md', content: 'Public fact.', classification: 'safe' },
        { name: 'private.md', content: 'Private note.', classification: 'private' },
        { name: 'secret.md', content: 'api_key: abcdefghijklmnop', classification: 'private' },
        { name: 'empty.md', content: '   ', classification: 'safe' },
        { name: 'public.md', content: 'No label.', classification: 'public' },
      ] };
      const collected = displayableMemoryDetails(plan);
      const rescreened = displayableMemoryDetails(collected);
      console.log(JSON.stringify({ collected, rescreened }));
    '''
    value = run_bun(source)
    assert [item["name"] for item in value["collected"]] == ["safe.md", "private.md"], value["collected"]
    assert [item["classification"] for item in value["collected"]] == ["safe", "private"], value["collected"]
    assert value["rescreened"] == value["collected"], value
