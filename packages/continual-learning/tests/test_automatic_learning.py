from __future__ import annotations

import json
import tempfile
from functools import partial
from pathlib import Path

import pytest

from support import REPO, run_bun as _run_bun

run_bun = partial(_run_bun, timeout=30, temp_dirs=("TMPDIR",))


def test_automatic_pipeline_does_not_request_routine_result_rows() -> None:
    source = (REPO / 'packages/continual-learning/extensions/inject-memory.ts').read_text(encoding='utf-8')
    assert 'mode: "automatic",\n        reportResult: false' in source
    assert 'registerMessageRenderer(LEARNING_RESULT_MESSAGE' in source
    assert 'eventToolLifecycle("learning", subject' in source


def test_memory_management_reports_shipped_incremental_planner() -> None:
    result = run_bun(r'''
      import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path';
      const root = fs.mkdtempSync(path.join(os.tmpdir(), 'memory-procedure-'));
      process.env.PI_CODING_AGENT_DIR = path.join(root, 'agent');
      const { default: register } = await import('./packages/continual-learning/extensions/inject-memory.ts');
      const commands = new Map(), notices = [];
      register({ on() {}, registerCommand: (name, command) => commands.set(name, command), getCommands: () => [], registerEntryRenderer: () => {}, appendEntry: () => {} });
      await commands.get('memory').handler('', { cwd: root, hasUI: false, ui: { notify: text => notices.push(text) }, getSystemPromptOptions: () => ({ contextFiles: [] }) });
      const file = /Consolidate procedure: (.+)/.exec(notices.join('\n'))[1];
      console.log(JSON.stringify({ file, exists: fs.existsSync(file) }));
      fs.rmSync(root, { recursive: true, force: true });
    ''')
    assert result['exists'] is True
    assert result['file'].endswith('/prompts/incremental-memory-consolidator.md')


def test_incremental_planner_prompt_declares_the_exact_new_memory_kind_enum() -> None:
    prompt = (REPO / "packages/continual-learning/prompts/incremental-memory-consolidator.md").read_text(encoding="utf-8")
    assert '"preference" | "project"' in prompt
    assert '"project-fact"' in prompt and "invalid plan kinds" in prompt
    assert '"kind":"project"' in prompt
    assert "type: project" in prompt


@pytest.mark.parametrize("has_ui", [False, True])
def test_memory_open_reports_invalid_model_configuration(tmp_path: Path, has_ui: bool) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "memory.json").write_text("{", encoding="utf-8")
    result = run_bun(r'''
      const { default: register } = await import('./packages/continual-learning/extensions/inject-memory.ts');
      const commands = new Map(), labels = [];
      register({ on() {}, registerCommand: (name, command) => commands.set(name, command), getCommands: () => [], registerEntryRenderer: () => {}, appendEntry: () => {} });
      await commands.get('memory').handler('', { cwd: process.env.TEST_CWD, hasUI: process.env.TEST_HAS_UI === 'true', ui: {
        notify: text => labels.push(text), select: async title => { labels.push(title); return undefined; },
      } });
      console.log(JSON.stringify({labels}));
    ''', {"PI_CODING_AGENT_DIR": str(agent), "TEST_CWD": str(tmp_path), "TEST_HAS_UI": str(has_ui).lower()})
    assert any("configuration invalid" in label for label in result["labels"]), result


def test_learning_deduplicates_and_ignores_extension_inputs() -> None:
    result = run_bun("""
      import { createAutomaticLearning } from './packages/continual-learning/extensions/automatic-learning.ts';
      const runs = [];
      const learning = createAutomaticLearning(async value => { runs.push(value); }, error => { throw error; });
      learning.input('extension');
      await learning.settle('extension', true);
      learning.input('interactive');
      await learning.settle('user', true);
      await learning.settle('duplicate', true);
      learning.input('rpc');
      await learning.settle('rpc', true);
      console.log(JSON.stringify({ runs }));
    """)
    assert result == {"runs": ["user", "rpc"]}


def test_disabled_settle_reports_the_frozen_snapshot_and_real_user_revision_once() -> None:
    result = run_bun("""
      import { createAutomaticLearning } from './packages/continual-learning/extensions/automatic-learning.ts';
      const skipped = [], runs = [];
      const learning = createAutomaticLearning(
        async value => { runs.push(value); },
        error => { throw error; },
        { onSkipped: (context, revision, reason) => skipped.push({ context, revision, reason }) },
      );
      learning.input('interactive');
      await learning.settle({ task: 'frozen' }, false);
      await learning.settle({ task: 'duplicate' }, false);
      learning.input('extension');
      await learning.settle({ task: 'extension-only' }, false);
      console.log(JSON.stringify({ skipped, runs }));
    """)
    assert result == {
        "skipped": [{"context": {"task": "frozen"}, "revision": 1, "reason": "auto-memory-off"}],
        "runs": [],
    }


def test_disabled_settle_does_not_report_after_shutdown() -> None:
    result = run_bun("""
      import { createAutomaticLearning } from './packages/continual-learning/extensions/automatic-learning.ts';
      const skipped = [];
      const learning = createAutomaticLearning(async () => {}, error => { throw error; }, {
        onSkipped: (context, revision, reason) => skipped.push({ context, revision, reason }),
      });
      learning.stop();
      await learning.settle({ task: 'shutdown' }, false);
      console.log(JSON.stringify(skipped));
    """)
    assert result == []


def test_learning_coalesces_settled_contexts_without_overlap() -> None:
    result = run_bun("""
      import { createAutomaticLearning } from './packages/continual-learning/extensions/automatic-learning.ts';
      const runs = [];
      let release;
      const gate = new Promise(resolve => { release = resolve; });
      const learning = createAutomaticLearning(async value => { runs.push(value); if (value === 1) await gate; }, error => { throw error; });
      learning.input('interactive');
      const first = learning.settle(1, true);
      learning.input('interactive');
      const second = learning.settle(2, true);
      learning.input('interactive');
      const third = learning.settle(3, true);
      const during = [...runs];
      release();
      await Promise.all([first, second, third]);
      console.log(JSON.stringify({ during, runs }));
    """)
    assert result == {"during": [1], "runs": [1, 3]}


def test_disabled_and_shutdown_work_is_not_replayed() -> None:
    result = run_bun("""
      import { createAutomaticLearning } from './packages/continual-learning/extensions/automatic-learning.ts';
      const runs = [];
      let release;
      const gate = new Promise(resolve => { release = resolve; });
      const learning = createAutomaticLearning(async value => { runs.push(value); await gate; }, error => { throw error; });
      learning.input('interactive');
      await learning.settle('disabled', false);
      await learning.settle('reenabled', true);
      learning.input('interactive');
      const pending = learning.settle('active', true);
      learning.input('interactive');
      learning.settle('queued', true);
      learning.stop();
      release();
      await pending;
      learning.input('interactive');
      await learning.settle('after-stop', true);
      console.log(JSON.stringify({ runs }));
    """)
    assert result == {"runs": ["active"]}


def test_failed_learning_reports_once_and_allows_later_tasks() -> None:
    result = run_bun("""
      import { createAutomaticLearning } from './packages/continual-learning/extensions/automatic-learning.ts';
      const runs = [], errors = [];
      const learning = createAutomaticLearning(async value => { runs.push(value); if (value === 1) throw new Error('planner failed'); }, error => errors.push(error.message));
      learning.input('interactive');
      await learning.settle(1, true);
      await learning.settle(1, true);
      learning.input('interactive');
      await learning.settle(2, true);
      console.log(JSON.stringify({ runs, errors }));
    """)
    assert result == {"runs": [1, 2], "errors": ["planner failed"]}


def test_settled_hook_waits_in_headless_mode_and_freezes_queued_context() -> None:
    result = run_bun("""
      import { registerAutomaticLearning } from './packages/continual-learning/extensions/automatic-learning.ts';
      const hooks = new Map();
      const pi = { on: (name, fn) => hooks.set(name, fn) };
      const runs = [], errors = [];
      let release;
      const gate = new Promise(resolve => { release = resolve; });
      registerAutomaticLearning(pi, {
        enabled: async () => true,
        snapshot: ctx => ({ ...ctx }),
        run: async ctx => { runs.push(ctx.value); await gate; },
        reportError: error => errors.push(String(error)),
      });
      const ctx = { value: 'original', hasUI: false };
      hooks.get('input')({ source: 'interactive' }, ctx);
      let settled = false;
      const pending = hooks.get('agent_settled')({}, ctx).then(() => { settled = true; });
      await new Promise(resolve => setTimeout(resolve, 0));
      const beforeRelease = settled;
      ctx.value = 'changed';
      release();
      await pending;
      console.log(JSON.stringify({ runs, errors, beforeRelease, settled }));
    """)
    assert result == {"runs": ["original"], "errors": [], "beforeRelease": False, "settled": True}


def test_settings_read_does_not_consume_a_later_user_task() -> None:
    result = run_bun("""
      import { registerAutomaticLearning } from './packages/continual-learning/extensions/automatic-learning.ts';
      const hooks = new Map(), runs = [];
      let release;
      const gate = new Promise(resolve => { release = resolve; });
      registerAutomaticLearning({ on: (name, fn) => hooks.set(name, fn) }, {
        enabled: async () => { await gate; return true; },
        snapshot: ctx => ({ ...ctx }),
        run: async ctx => { runs.push(ctx.value); },
        reportError: error => { throw error; },
      });
      const ctx = { value: 'first', hasUI: false };
      hooks.get('input')({ source: 'interactive' });
      const first = hooks.get('agent_settled')({}, ctx);
      ctx.value = 'second';
      hooks.get('input')({ source: 'interactive' });
      release();
      await first;
      await hooks.get('agent_settled')({}, ctx);
      console.log(JSON.stringify({ runs }));
    """)
    assert result == {"runs": ["first", "second"]}


def test_headless_pipeline_freezes_context_and_finishes_all_phases() -> None:
    result = run_bun(r'''
      import { mock } from 'bun:test';
      import fs from 'node:fs';
      import os from 'node:os';
      import path from 'node:path';
      import { spawn, execFileSync } from 'node:child_process';
      const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'learning-pipeline-'));
      const cwd = path.join(temp, 'project');
      const agent = path.join(temp, 'agent');
      fs.mkdirSync(cwd); fs.mkdirSync(agent);
      execFileSync('git', ['init', '-q', cwd]);
      process.env.PI_CODING_AGENT_DIR = agent;
      const live = [{ type: 'message', id: 'user-1', message: { role: 'user', content: 'Prefer concise updates.' } }];
      const snapshots = [], notices = [], selectorPrompts = [], plannerTasks = [];
      const kit = await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts', () => ({
        ...kit,
        resolvePiCli: () => ({ command: process.execPath, args: [] }),
        runPiWorker: async ({ prompt, tools }) => {
          selectorPrompts.push({ prompt, tools });
          const contextDigest = /Context digest: ([a-f0-9]+)/.exec(prompt)[1];
          return {
            text: JSON.stringify({
              kind: 'incremental-memory-selection', version: 1, contextDigest,
              selected: [], memory: true, harness: false, agents: false, reason: 'durable preference',
            }),
            exitCode: 0, stderr: '', usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: 0 },
          };
        },
        spawnPiChild: (_command, args, options) => {
          const taskFile = args.find(arg => arg.startsWith('@')).slice(1);
          const task = fs.readFileSync(taskFile, 'utf8');
          plannerTasks.push(task);
          const runDir = path.dirname(taskFile);
          const manifest = JSON.parse(fs.readFileSync(path.join(runDir, 'manifest.json'), 'utf8'));
          const snapshot = JSON.parse(fs.readFileSync(manifest.snapshotPath, 'utf8'));
          snapshots.push(snapshot.entries[0].message.content);
          live[0].message.content = 'Later unrelated user task.';
          const workerExitMarker = path.join(temp, 'memory-worker-exited');
          const plan = {
            kind: 'incremental-memory-plan', version: 1, schemaVersion: 1,
            runId: manifest.runId, scopeKey: manifest.scopeKey,
            scopeDigest: manifest.scopeDigest, artifactHash: manifest.snapshotDigest,
            snapshotDigest: manifest.snapshotDigest, operations: [],
            newMemories: [{
              name: 'preference.md', kind: 'preference',
              content: '---\nname: concise-updates\ndescription: Concise updates\ntype: feedback\n---\nPrefer concise updates.\n',
              evidence: [{ index: 0, quote: 'Prefer concise updates.' }],
            }],
          };
          const event = { type: 'message_end', message: { role: 'assistant', content: [{ type: 'text', text: JSON.stringify(plan) }] } };
          const worker = 'const fs=require("node:fs"); fs.writeSync(1,' + JSON.stringify(JSON.stringify(event) + '\n') + '); fs.closeSync(1); fs.closeSync(2); setTimeout(() => { fs.writeFileSync(' + JSON.stringify(workerExitMarker) + ', "exited\\n"); process.exit(0); }, 200);';
          return spawn('node', ['-e', worker], { cwd: options.cwd, stdio: ['ignore', 'pipe', 'pipe'] });
        },
      }));
      const { default: register } = await import('./packages/continual-learning/extensions/inject-memory.ts');
      const hooks = new Map();
      const pi = {
        on: (name, handler) => hooks.set(name, [...(hooks.get(name) ?? []), handler]),
        registerCommand: () => {}, getCommands: () => [],
        registerEntryRenderer: () => {}, appendEntry: () => {}
      };
      const ctx = {
        cwd, mode: 'json', hasUI: false,
        ui: { notify: (text) => notices.push(text), setWidget: () => {} },
        sessionManager: { getBranch: () => live, buildContextEntries: () => live },
      };
      register(pi);
      const emit = async (name, event) => { for (const handler of hooks.get(name) ?? []) await handler(event, ctx); };
      await emit('session_start', {});
      await emit('input', { source: 'interactive' });
      await emit('agent_settled', {});
      const lockFiles = fs.existsSync(path.join(agent, 'memory', 'locks')) ? fs.readdirSync(path.join(agent, 'memory', 'locks')).filter(name => name.endsWith('.lock')) : [];
      const { resolveMemoryPaths } = await import('./packages/continual-learning/extensions/memory-paths.ts');
      const memoryPaths = resolveMemoryPaths(cwd);
      const created = fs.existsSync(path.join(memoryPaths.harnessDir, 'preference.md'));
      const leaked = fs.existsSync(path.join(cwd, '.memory', 'preference.md'));
      const learningReceipt = JSON.parse(fs.readFileSync(path.join(memoryPaths.runsDir, 'learning-pipeline-receipt.json'), 'utf8'));
      await emit('session_shutdown', {});
      const exitMarkers = ['memory-worker-exited'].filter(name => fs.existsSync(path.join(temp, name)));
      const incrementalAgent = plannerTasks.every(task => task.includes('"kind": "incremental-memory-plan"') || task.includes('"kind":"incremental-memory-plan"'));
      const dossierOnly = plannerTasks.every(task => task.includes('`dossierPath`:') && task.includes('Learning Dossier'));
      fs.rmSync(temp, { recursive: true, force: true });
      console.log(JSON.stringify({ snapshots, lockFiles, created, leaked, exitMarkers, selectorPrompts, incrementalAgent, dossierOnly, receiptAttempts: learningReceipt.attempts, receiptOperations: learningReceipt.operations, failures: notices.filter(text => /failed|rejected|blocked|without verified/i.test(text)) }));
    ''')
    assert result["failures"] == []
    assert result["snapshots"] == ["Prefer concise updates."]
    assert result["lockFiles"] == []
    assert "memory-worker-exited" in result["exitMarkers"]
    assert result["receiptOperations"] == 1
    assert [(attempt["phase"], attempt["outcome"], attempt["operations"]) for attempt in result["receiptAttempts"]] == [("selector", "applied", 0), ("memory", "applied", 1)]
    assert result["selectorPrompts"] == []
    assert result["receiptAttempts"][0]["diagnostic"] == "empty Memory index; parent-routed explicit evidence"
    assert result["receiptAttempts"][0].get("usage") is None
    assert result["incrementalAgent"] and result["dossierOnly"]
    assert result["created"] and not result["leaked"]


def test_selector_cannot_suppress_parent_detected_memory_phase() -> None:
    source = (REPO / 'packages/continual-learning/extensions/inject-memory.ts').read_text(encoding='utf-8')
    assert 'screen.memory = screen.memory || incrementalSelection.selection.memory' in source
    assert 'screen.harness = screen.harness || incrementalSelection.selection.harness' in source


def test_shutdown_cancels_and_awaits_all_later_planner_children() -> None:
    result = run_bun(r'''
      import { EventEmitter } from 'node:events';
      import { cancelLaterPlannerChildren } from './packages/continual-learning/extensions/inject-memory.ts';
      const createChild = (label, delay) => {
        const child = new EventEmitter();
        child.exitCode = null; child.signalCode = null; child.pid = undefined;
        child.kill = () => { setTimeout(() => { child.signalCode = 'SIGTERM'; child.emit('close', null, 'SIGTERM'); }, delay); return true; };
        child.label = label;
        return child;
      };
      const first = createChild('harness', 20), second = createChild('agents', 35);
      const states = [
        { cancelled: false, generation: 1, child: first },
        { cancelled: false, generation: 1, child: second },
      ];
      const closed = [];
      first.on('close', () => closed.push('harness'));
      second.on('close', () => closed.push('agents'));
      const started = Date.now();
      await cancelLaterPlannerChildren(states);
      console.log(JSON.stringify({ closed: closed.sort(), cancelled: states.every(state => state.cancelled), generations: states.map(state => state.generation), elapsed: Date.now() - started }));
    ''')
    assert result["closed"] == ["agents", "harness"]
    assert result["cancelled"] is True
    assert result["generations"] == [2, 2]
    assert result["elapsed"] >= 35


def test_harness_only_evidence_runs_without_memory_mutation_and_records_receipt() -> None:
    with tempfile.TemporaryDirectory(prefix="harness-only-learning-test-") as temporary:
        result = run_bun(r'''
      import { mock } from 'bun:test';
      import fs from 'node:fs';
      import os from 'node:os';
      import path from 'node:path';
      import { EventEmitter } from 'node:events';
      import { execFileSync } from 'node:child_process';
      const temp = process.env.HARNESS_ONLY_TEST_DIR;
      const cwd = path.join(temp, 'project'), agent = process.env.PI_CODING_AGENT_DIR;
      fs.mkdirSync(cwd); fs.mkdirSync(agent); execFileSync('git', ['init', '-q', cwd]);
      const { resolveMemoryPaths } = await import('./packages/continual-learning/extensions/memory-paths.ts');
      const configuredPaths = resolveMemoryPaths(cwd);
      fs.mkdirSync(path.dirname(configuredPaths.settingsFile), { recursive: true });
      fs.writeFileSync(configuredPaths.settingsFile, JSON.stringify({ autoMemory: true, agentsMd: { disabled: true } }));
      const workerKinds = [];
      const kit = await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts', () => ({
        ...kit,
        resolvePiCli: () => ({ command: process.execPath, args: [] }),
        runPiWorker: async ({ prompt, tools }) => ({
          text: JSON.stringify({ kind: 'incremental-memory-selection', version: 1, contextDigest: /Context digest: ([a-f0-9]+)/.exec(prompt)[1], selected: [], memory: false, harness: true, agents: false, reason: 'grounded harness event' }),
          exitCode: 0, stderr: '', usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: 0 },
        }),
        spawnPiChild: (_command, args) => {
          const taskFile = args.find(arg => arg.startsWith('@')).slice(1);
          const task = fs.readFileSync(taskFile, 'utf8');
          workerKinds.push(task.startsWith('Task: produce a read-only structured consolidation plan') ? 'memory' : 'harness');
          const runDir = path.dirname(taskFile);
          const manifest = JSON.parse(fs.readFileSync(path.join(runDir, 'manifest.json'), 'utf8'));
          const plan = { kind: 'harness-consolidation-plan', version: 1, schemaVersion: 1, runId: manifest.runId, scopeDigest: manifest.scopeDigest, artifactHash: manifest.snapshotDigest, operations: [], evidence: [], report: [] };
          const child = new EventEmitter(); child.stdout = new EventEmitter(); child.stderr = new EventEmitter(); child.killed = false; child.exitCode = null; child.signalCode = null;
          queueMicrotask(() => { child.stdout.emit('data', Buffer.from(JSON.stringify({ type: 'message_end', message: { role: 'assistant', content: [{ type: 'text', text: JSON.stringify(plan) }] } }) + '\n')); child.exitCode = 0; child.emit('close', 0); });
          return child;
        },
      }));
      const { default: register } = await import('./packages/continual-learning/extensions/inject-memory.ts');
      const hooks = new Map(), notices = [];
      register({ on: (name, handler) => hooks.set(name, [...(hooks.get(name) ?? []), handler]), registerCommand: () => {}, getCommands: () => [], registerEntryRenderer: () => {}, appendEntry: () => {} });
      const entries = [
        { message: { role: 'user', content: [{ type: 'text', text: 'Please finish the current task.' }] } },
        { message: { role: 'toolResult', content: [{ type: 'text', text: 'Harness policy blocked a generated write.' }] } },
        // Words in tool output are not evidence; the guardrail entry is.
        { type: 'custom', customType: 'harness-event', data: { kind: 'policy-matched', action: 'block', tool: 'write' } },
      ];
      const ctx = { cwd, mode: 'json', hasUI: false, ui: { notify: text => notices.push(text), setWidget: () => {} }, sessionManager: { getBranch: () => entries, buildContextEntries: () => entries } };
      for (const handler of hooks.get('session_start') ?? []) await handler({}, ctx);
      for (const handler of hooks.get('input') ?? []) await handler({ source: 'interactive' }, ctx);
      const settledHandlers = hooks.get('agent_settled') ?? [];
      for (const handler of settledHandlers) await handler({}, ctx);
      const paths = resolveMemoryPaths(cwd);
      const receipts = [];
      if (fs.existsSync(paths.runsDir)) for (const run of fs.readdirSync(paths.runsDir)) {
        const receipt = path.join(paths.runsDir, run, 'learning-pipeline-receipt.json');
        if (fs.existsSync(receipt)) receipts.push(JSON.parse(fs.readFileSync(receipt, 'utf8')));
      }
      const memoryFiles = fs.existsSync(paths.harnessDir) ? fs.readdirSync(paths.harnessDir).filter(name => name.endsWith('.md') && name !== 'MEMORY.md') : [];
      await Promise.all((hooks.get('session_shutdown') ?? []).map(handler => handler({}, ctx)));
      fs.rmSync(temp, { recursive: true, force: true });
      console.log(JSON.stringify({ workerKinds, attempts: receipts[0]?.attempts, memoryFiles, notices, failures: notices.filter(text => /failed/i.test(text)) }));
    ''', {
            "HARNESS_ONLY_TEST_DIR": temporary,
            "PI_CODING_AGENT_DIR": str(Path(temporary) / "agent"),
        })
    assert result["workerKinds"] == ["harness"]
    assert result["memoryFiles"] == []
    assert [(attempt["phase"], attempt["outcome"]) for attempt in result["attempts"]] == [("selector", "applied"), ("harness", "noop")]
    assert result["failures"] == []


def test_failed_memory_gate_persists_receipt_and_skips_later_phases() -> None:
    result = run_bun(r'''
      import { mock } from 'bun:test';
      import fs from 'node:fs';
      import os from 'node:os';
      import path from 'node:path';
      import { EventEmitter } from 'node:events';
      import { execFileSync } from 'node:child_process';
      const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'failed-memory-receipt-'));
      const cwd = path.join(temp, 'project'), agent = path.join(temp, 'agent');
      fs.mkdirSync(cwd); fs.mkdirSync(agent); execFileSync('git', ['init', '-q', cwd]);
      process.env.PI_CODING_AGENT_DIR = agent;
      const workerKinds = [], selectorCalls = [];
      const kit = await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts', () => ({
        ...kit,
        resolvePiCli: () => ({ command: process.execPath, args: [] }),
        runPiWorker: async ({ prompt }) => {
          selectorCalls.push('selector');
          return {
            text: JSON.stringify({ kind: 'incremental-memory-selection', version: 1, contextDigest: /Context digest: ([a-f0-9]+)/.exec(prompt)[1], selected: [], memory: true, harness: true, agents: false, reason: 'durable constraint' }),
            exitCode: 0, stderr: '', usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: 0 },
          };
        },
        spawnPiChild: (_command, args) => {
          const taskFile = args.find(arg => arg.startsWith('@')).slice(1);
          const task = fs.readFileSync(taskFile, 'utf8');
          workerKinds.push(task.startsWith('Task: produce a read-only structured consolidation plan') ? 'memory' : 'later');
          const child = new EventEmitter();
          child.stdout = new EventEmitter(); child.stderr = new EventEmitter();
          child.killed = false; child.exitCode = null; child.signalCode = null;
          queueMicrotask(() => {
            child.stdout.emit('data', Buffer.from(JSON.stringify({
              type: 'message_end',
              message: { role: 'assistant', content: [], stopReason: 'error', errorMessage: 'planner provider unavailable' },
            }) + '\n'));
            child.exitCode = 0;
            child.emit('close', 0);
          });
          return child;
        },
      }));
      const { default: register, resolveMemoryPaths } = await import('./packages/continual-learning/extensions/inject-memory.ts');
      const hooks = new Map(), notices = [];
      register({
        on: (name, handler) => hooks.set(name, [...(hooks.get(name) ?? []), handler]),
        registerCommand: () => {},
        getCommands: () => [],
        registerEntryRenderer: () => {}, appendEntry: () => {},
      });
      const entries = [{ message: { role: 'user', content: [{ type: 'text', text: 'Never use npm in this project; use pnpm instead.' }] } }];
      const ctx = {
        cwd, mode: 'json', hasUI: false,
        ui: { notify: text => notices.push(text), setWidget: () => {} },
        sessionManager: { getBranch: () => entries, buildContextEntries: () => entries },
      };
      for (const handler of hooks.get('session_start') ?? []) await handler({}, ctx);
      for (const handler of hooks.get('input') ?? []) await handler({ source: 'interactive' }, ctx);
      for (const handler of hooks.get('agent_settled') ?? []) await handler({}, ctx);
      const receiptPath = path.join(resolveMemoryPaths(cwd).runsDir, 'learning-pipeline-receipt.json');
      const receipt = fs.existsSync(receiptPath) ? JSON.parse(fs.readFileSync(receiptPath, 'utf8')) : null;
      for (const handler of hooks.get('session_shutdown') ?? []) await handler({}, ctx);
      fs.rmSync(temp, { recursive: true, force: true });
      console.log(JSON.stringify({ workerKinds, selectorCalls, receipt, notices }));
    ''')
    assert result["workerKinds"] == ["memory"]
    assert result["selectorCalls"] == []
    assert result["receipt"]["screen"]["harness"] is True
    assert [(attempt["phase"], attempt["outcome"], attempt["operations"]) for attempt in result["receipt"]["attempts"]] == [("selector", "applied", 0), ("memory", "failed", 0)]
    assert any("planner provider unavailable" in notice for notice in result["notices"])


def test_consolidate_full_skips_selector_and_uses_exhaustive_planner() -> None:
    result = run_bun(r'''
      import { mock } from 'bun:test';
      import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path';
      import { EventEmitter } from 'node:events'; import { execFileSync } from 'node:child_process';
      const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'full-consolidation-'));
      const cwd = path.join(temp, 'project'), agent = path.join(temp, 'agent');
      fs.mkdirSync(cwd); fs.mkdirSync(agent); execFileSync('git', ['init', '-q', cwd]); process.env.PI_CODING_AGENT_DIR = agent;
      let selectorCalls = 0; const plannerTasks = []; const memoryIdentityCounts = [];
      const kit = await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts', () => ({
        ...kit,
        resolvePiCli: () => ({ command: process.execPath, args: [] }),
        runPiWorker: async () => { selectorCalls += 1; throw new Error('full mode must not select'); },
        spawnPiChild: (_command, args) => {
          const taskFile = args.find(arg => arg.startsWith('@')).slice(1);
          const task = fs.readFileSync(taskFile, 'utf8'); plannerTasks.push(task);
          const manifest = JSON.parse(fs.readFileSync(path.join(path.dirname(taskFile), 'manifest.json'), 'utf8'));
          const harness = task.startsWith('Task: produce a read-only structured harness consolidation plan');
          if (!harness) memoryIdentityCounts.push((task.match(/(?:- Run ID:|- `runId`:)/g) ?? []).length);
          const plan = harness
            ? { kind: 'harness-consolidation-plan', version: 1, schemaVersion: 1, runId: manifest.runId, scopeDigest: manifest.scopeDigest, artifactHash: manifest.snapshotDigest, operations: [], evidence: [], report: [] }
            : { kind: 'memory-consolidation-plan', version: 1, schemaVersion: 1, runId: manifest.runId, scopeKey: manifest.scopeKey, scopeDigest: manifest.scopeDigest, artifactHash: manifest.snapshotDigest, snapshotDigest: manifest.snapshotDigest, selected: [], operations: [], newMemories: [], inventory: [], clusters: [], staleness: [], grounding: [], report: [] };
          const child = new EventEmitter(); child.stdout = new EventEmitter(); child.stderr = new EventEmitter(); child.exitCode = null; child.signalCode = null;
          queueMicrotask(() => { child.stdout.emit('data', Buffer.from(JSON.stringify({ type: 'message_end', message: { role: 'assistant', content: [{ type: 'text', text: JSON.stringify(plan) }] } }) + '\n')); child.exitCode = 0; child.emit('close', 0); });
          return child;
        },
      }));
      const { default: register } = await import('./packages/continual-learning/extensions/inject-memory.ts');
      const hooks = new Map(), commands = new Map(), notices = [];
      register({ on: (name, handler) => hooks.set(name, [...(hooks.get(name) ?? []), handler]), registerCommand: (name, command) => commands.set(name, command), getCommands: () => [], registerEntryRenderer: () => {}, appendEntry: () => {} });
      const entries = [{ message: { role: 'user', content: 'Earlier task' } }, { message: { role: 'assistant', content: 'Earlier answer' } }, { message: { role: 'user', content: 'Current task' } }];
      const ctx = { cwd, mode: 'json', hasUI: false, ui: { notify: text => notices.push(text), setWidget() {} }, sessionManager: { getBranch: () => entries, buildContextEntries: () => entries } };
      for (const handler of hooks.get('session_start') ?? []) await handler({}, ctx);
      await commands.get('consolidate').handler('full', ctx);
      const memoryTask = plannerTasks.find(task => task.startsWith('Task: produce a read-only structured consolidation plan'));
      await Promise.all((hooks.get('session_shutdown') ?? []).map(handler => handler({}, ctx)));
      fs.rmSync(temp, { recursive: true, force: true });
      console.log(JSON.stringify({ selectorCalls, fullAgent: memoryTask.includes('# Memory consolidation child planner'), incrementalAgent: memoryTask.includes('# Incremental Memory consolidation child planner'), fullSnapshot: memoryTask.includes('snapshotPath'), memoryIdentityCounts }));
    ''')
    assert result["selectorCalls"] == 0
    assert result["fullAgent"] is True and result["incrementalAgent"] is False
    assert result["fullSnapshot"] is True
    assert result["memoryIdentityCounts"] and set(result["memoryIdentityCounts"]) == {1}


def test_incremental_memory_repair_prompt_contains_only_rejected_delta_errors_scope_and_identity() -> None:
    result = run_bun(r'''
      import { mock } from 'bun:test';
      const prompts = [];
      const kit = await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts', () => ({
        ...kit,
        runPiWorker: async options => {
          prompts.push(options);
          return {
            text: JSON.stringify({
              kind: 'incremental-memory-plan', version: 1, schemaVersion: 1,
              runId: 'run_repair', scopeKey: 'scope-key', scopeDigest: 'scope-digest',
              artifactHash: 'snapshot-digest', snapshotDigest: 'snapshot-digest',
              operations: [], newMemories: [],
            }),
            exitCode: 0, stderr: '', usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: 0 },
          };
        },
      }));
      const { repairIncrementalMemoryPlan } = await import('./packages/continual-learning/extensions/inject-memory.ts');
      const outcome = await repairIncrementalMemoryPlan({
        rejectedPlan: { kind: 'incremental-memory-plan', operations: 'bad' },
        errors: ['operations must be an array'],
        selectedNames: ['chosen.md'],
        identity: { runId: 'run_repair', scopeKey: 'scope-key', scopeDigest: 'scope-digest', artifactHash: 'snapshot-digest', snapshotDigest: 'snapshot-digest' },
        cwd: process.cwd(),
      });
      console.log(JSON.stringify({ outcome: outcome.outcome, tools: prompts[0].tools, prompt: prompts[0].prompt }));
    ''')
    assert result["outcome"] == "repaired"
    assert result["tools"] == []
    assert "operations must be an array" in result["prompt"]
    assert "chosen.md" in result["prompt"] and "run_repair" in result["prompt"]
    assert "incremental-memory-plan" in result["prompt"]
    assert 'newMemories[].kind must be exactly "preference" or "project"' in result["prompt"]
    assert "project-fact" in result["prompt"]
    assert '"evidence"' in result["prompt"]
    assert "Retain every recognizable original selected operation and new proposal by its exact name" in result["prompt"]
    assert "preserve an original rewrite as rewrite and an original delete as delete" in result["prompt"]
    for forbidden in ("snapshotPath", "dossierPath", "harnessDir", "publicDir", "repoRoot"):
        assert forbidden not in result["prompt"]


def test_incremental_memory_repair_retains_recognizable_intents() -> None:
    result = run_bun(r'''
      import { mock } from 'bun:test';
      let candidate;
      const kit = await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts', () => ({
        ...kit,
        runPiWorker: async () => ({
          text: JSON.stringify(candidate), exitCode: 0, stderr: '',
          usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: 0 },
        }),
      }));
      const { repairIncrementalMemoryPlan } = await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity = { runId: 'run_retention', scopeKey: 'scope-key', scopeDigest: 'scope-digest', artifactHash: 'snapshot-digest', snapshotDigest: 'snapshot-digest' };
      const base = { kind: 'incremental-memory-plan', version: 1, schemaVersion: 1, ...identity, operations: [], newMemories: [] };
      const proposalIntent = {
        ...base,
        newMemories: [
          { name: 'private.md', kind: 'preference', content: 'private', evidence: [{ index: 0, quote: 'private' }] },
          { name: 'project_fact.md', kind: 'project-fact', content: 'project', evidence: [{ index: 0, quote: 'project' }] },
        ],
      };
      const proposalFixed = {
        ...base,
        newMemories: [
          { name: 'private.md', kind: 'preference', content: 'private fixed', evidence: [{ index: 0, quote: 'private' }] },
          { name: 'project_fact.md', kind: 'project', content: 'project fixed', evidence: [{ index: 0, quote: 'project' }] },
        ],
      };
      const proposalRenamed = {
        ...base,
        newMemories: [
          { name: 'private.md', kind: 'preference', content: 'private fixed', evidence: [{ index: 0, quote: 'private' }] },
          { name: 'project-Fact.md', kind: 'project', content: 'project fixed', evidence: [{ index: 0, quote: 'project' }] },
        ],
      };
      const proposalEmpty = { ...base };
      const rewrite = { ...base, operations: [{ name: 'existing.md', kind: 'rewrite', classification: 'safe', content: 'old' }] };
      const deleteReplacement = { ...base, operations: [{ name: 'existing.md', kind: 'delete', classification: 'safe', verdict: 'SUPERSEDED', preservedIn: ['kept.md'] }] };
      const invalidOperations = { ...base, operations: 'not-an-array' };
      const run = async (rejectedPlan, repairedPlan) => {
        candidate = repairedPlan;
        const value = await repairIncrementalMemoryPlan({ rejectedPlan, errors: ['bounded validator error'], selectedNames: ['existing.md'], identity });
        return value.outcome;
      };
      console.log(JSON.stringify({
        retained: await run(proposalIntent, proposalFixed),
        emptyRejected: await run(proposalIntent, proposalEmpty),
        renamedRejected: await run(proposalIntent, proposalRenamed),
        rewriteDeleteRejected: await run(rewrite, deleteReplacement),
        invalidOriginalMayBeEmpty: await run(invalidOperations, proposalEmpty),
      }));
    ''')
    assert result == {
        "retained": "repaired",
        "emptyRejected": "failed",
        "renamedRejected": "failed",
        "rewriteDeleteRejected": "failed",
        "invalidOriginalMayBeEmpty": "repaired",
    }


@pytest.mark.parametrize("memory_policy", ["apply", "off"])
@pytest.mark.parametrize("trigger", ["automatic", "manual", "full", "request"])
def test_invalid_memory_config_blocks_every_worker_before_normalization(memory_policy: str, trigger: str) -> None:
    with tempfile.TemporaryDirectory(prefix="learning-invalid-config-") as temporary:
        result = run_bun(r'''
          import { mock } from 'bun:test';
          import fs from 'node:fs'; import path from 'node:path';
          const base = process.env.INVALID_CONFIG_TEST_DIR;
          const agent = process.env.PI_CODING_AGENT_DIR;
          const cwd = path.join(base, 'project'); fs.mkdirSync(cwd); fs.mkdirSync(agent);
          fs.mkdirSync(path.join(agent, 'memory'), { recursive: true });
          fs.writeFileSync(path.join(agent, 'memory.json'), JSON.stringify({ provider: 'only-provider' }));
          fs.writeFileSync(path.join(agent, 'memory', 'settings.json'), JSON.stringify({ autoMemory: true, automaticPhases: {memory: process.env.TEST_MEMORY_POLICY} }));
          const { resolveMemoryPaths } = await import('./packages/continual-learning/extensions/memory-paths.ts');
          const paths = resolveMemoryPaths(cwd);
          fs.mkdirSync(paths.harnessDir, { recursive: true });
          const body = path.join(paths.harnessDir, 'fact.md');
          const index = path.join(paths.harnessDir, 'MEMORY.md');
          fs.writeFileSync(body, '---\nname: Fact\ndescription: Verified project fact\ntype: project\n---\nverified fact\n');
          fs.writeFileSync(index, '- [fact.md](fact.md) stale annotation\n');
          const before = {body: fs.readFileSync(body, 'utf8'), index: fs.readFileSync(index, 'utf8')};
          let modelCalls = 0;
          const kit = await import('./packages/kit/src/index.ts');
          mock.module('./packages/kit/src/index.ts', () => ({
            ...kit,
            spawnPiChild: () => { modelCalls += 1; throw new Error('Fixture forbids actual child process'); },
            runPiWorker: async ({ prompt }) => { modelCalls += 1; return ({
              text: JSON.stringify({ kind: 'incremental-memory-selection', version: 1, contextDigest: /Context digest: ([a-f0-9]+)/.exec(prompt)[1], selected: [], memory: true, harness: true, agents: false, reason: 'durable rule' }),
              exitCode: 0, stderr: '',
            }); },
          }));
          const { default: register } = await import('./packages/continual-learning/extensions/inject-memory.ts');
          const hooks = new Map(), commands = new Map(), notices = [];
          register({ on: (name, handler) => hooks.set(name, [...(hooks.get(name) ?? []), handler]), registerCommand: (name, command) => commands.set(name, command), getCommands: () => [], registerEntryRenderer: () => {}, appendEntry: () => {} });
          const entries = [{ message: { role: 'user', content: [{ type: 'text', text: 'Never publish without approval. Always preserve this durable rule.' }] } }];
          const ctx = { cwd, mode: 'json', hasUI: false, ui: { notify: text => notices.push(text), setWidget: () => {} }, sessionManager: { getBranch: () => entries, buildContextEntries: () => entries } };
          for (const [name, event] of [['session_start', {}], ['input', { source: 'interactive' }]]) for (const handler of hooks.get(name) ?? []) await handler(event, ctx);
          const trigger = process.env.TEST_TRIGGER;
          if (trigger === 'automatic') for (const handler of hooks.get('agent_settled') ?? []) await handler({}, ctx);
          else if (trigger === 'request') await commands.get('memory').handler('Remember the verified fixture fact.', ctx);
          else await commands.get('consolidate').handler(trigger === 'full' ? 'full' : '', ctx);
          const receiptPath = path.join(paths.runsDir, 'learning-pipeline-receipt.json');
          const receipt = fs.existsSync(receiptPath) ? JSON.parse(fs.readFileSync(receiptPath, 'utf8')) : {attempts: []};
          console.log(JSON.stringify({ attempts: receipt.attempts, notices, modelCalls, preserved: before.body === fs.readFileSync(body, 'utf8') && before.index === fs.readFileSync(index, 'utf8') }));
        ''', {
            "INVALID_CONFIG_TEST_DIR": temporary,
            "TEST_MEMORY_POLICY": memory_policy,
            "TEST_TRIGGER": trigger,
            "PI_CODING_AGENT_DIR": str(Path(temporary) / "agent"),
        })
    phases = [(attempt["phase"], attempt["outcome"], attempt["operations"]) for attempt in result["attempts"]]
    assert result["modelCalls"] == 0
    assert result["preserved"] is True
    assert phases == [("memory" if trigger == "full" else "selector", "failed", 0)]
    assert any("Learning is blocked" in notice for notice in result["notices"])


def test_node_parent_waits_for_worker_exit_after_output_pipes_close() -> None:
    with tempfile.TemporaryDirectory(prefix="learning-node-exit-") as temporary:
        base = Path(temporary)
        worker = base / "worker.cjs"
        (base / "package.json").write_text(json.dumps({"name": "@earendil-works/pi-coding-agent"}))
        worker.write_text(r'''
const fs = require('node:fs'), path = require('node:path');
const task = process.argv.find(arg => arg.startsWith('@')).slice(1);
const manifest = JSON.parse(fs.readFileSync(path.join(path.dirname(task), 'manifest.json'), 'utf8'));
const memory = fs.readFileSync(task, 'utf8').startsWith('Task: produce a read-only structured consolidation plan');
const plan = {
  kind: 'incremental-memory-plan', version: 1, schemaVersion: 1,
  runId: manifest.runId, scopeKey: manifest.scopeKey,
  scopeDigest: manifest.scopeDigest, artifactHash: manifest.snapshotDigest,
  snapshotDigest: manifest.snapshotDigest, operations: [],
  newMemories: [{name:'durable-rule.md',kind:'preference',classification:'private',content:'---\ndescription: durable rule\n---\nAlways preserve this durable project rule.\n',evidence:[{index:0,quote:'Always preserve this durable project rule.'}]}],
};
fs.writeSync(1, JSON.stringify({type:'message_end',message:{role:'assistant',content:[{type:'text',text:JSON.stringify(plan)}]}})+'\n');
fs.closeSync(1); fs.closeSync(2);
setTimeout(() => {
  fs.writeFileSync(path.join(path.dirname(manifest.cwd), 'worker-exited.txt'), 'exited\n');
  process.exit(0);
}, 300);
''')
        source = r'''
import fs from 'node:fs';
import path from 'node:path';
import { mock } from 'bun:test';
const base = process.env.LEARNING_TEST_DIR;
process.argv[1] = path.join(base, 'worker.cjs');
const kit = await import('./packages/kit/src/index.ts');
mock.module('./packages/kit/src/index.ts', () => ({
  ...kit,
  runPiWorker: async ({ prompt }) => ({
    text: JSON.stringify({ kind: 'incremental-memory-selection', version: 1, contextDigest: /Context digest: ([a-f0-9]+)/.exec(prompt)[1], selected: [], memory: true, harness: false, agents: false, reason: 'durable rule' }),
    exitCode: 0, stderr: '',
  }),
}));
const { default: register } = await import('./packages/continual-learning/extensions/inject-memory.ts');
const cwd = path.join(base, 'project'); fs.mkdirSync(cwd);
const hooks = new Map(), notices = [];
register({on:(name,handler)=>hooks.set(name,[...(hooks.get(name)??[]),handler]),registerCommand:()=>{},getCommands:()=>[],registerEntryRenderer: () => {}, appendEntry: () => {}});
const evidence = [{message:{role:'user',content:[{type:'text',text:'Always preserve this durable project rule.'}]}}];
const ctx = {cwd,mode:'json',hasUI:false,ui:{notify:text=>notices.push(text),setWidget:()=>{}},sessionManager:{getBranch:()=>evidence,buildContextEntries:()=>evidence}};
for (const [name,event] of [['session_start',{}],['input',{source:'interactive'}],['agent_settled',{}]]) {
  for (const handler of hooks.get(name)??[]) await handler(event,ctx);
}
const workerExited = fs.existsSync(path.join(base, 'worker-exited.txt'));
for (const handler of hooks.get('session_shutdown')??[]) await handler({},ctx);
console.log(JSON.stringify({workerExited,notices}));
'''
        outcome = run_bun(
            source,
            {"LEARNING_TEST_DIR": temporary, "PI_CODING_AGENT_DIR": str(base / "agent")},
            timeout=20,
        )
        assert outcome["workerExited"], outcome
        assert outcome["notices"] == []


def test_incremental_prompt_covers_affirmed_terminology_without_invented_process() -> None:
    # The real sparse EN trial routed Memory but emitted an empty first delta.
    # Keep the durable-fact contract visible to the read-only generation stage.
    prompt = (REPO / 'packages/continual-learning/prompts/incremental-memory-consolidator.md').read_text()
    assert 'Project terminology' in prompt and 'alias' in prompt
    assert 'does not require' in prompt and 'remember' in prompt
    assert 'maintains a glossary' in prompt and 'verified' in prompt


def test_harness_repair_does_not_preserve_unauthorized_generated_positive_cases() -> None:
    prompt = (REPO / 'packages/continual-learning/prompts/harness-consolidator.md').read_text()
    assert 'Generated positive cases are not authorization' in prompt
    assert 'extra arguments must be negative' in prompt
    assert 'while retaining\nthe required positives' not in prompt
