from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def run_bun(source: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="automatic-learning-test-") as temporary:
        result = subprocess.run(
            ["bun", "-e", source], cwd=REPO, text=True, capture_output=True,
            env={**os.environ, "TMPDIR": temporary}, timeout=30,
        )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


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
      const snapshots = [], notices = [];
      const kit = await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts', () => ({
        ...kit,
        resolvePiCli: () => ({ command: process.execPath, args: [] }),
        spawnPiChild: (_command, args, options) => {
          const taskFile = args.find(arg => arg.startsWith('@')).slice(1);
          const task = fs.readFileSync(taskFile, 'utf8');
          const runDir = path.dirname(taskFile);
          const manifest = JSON.parse(fs.readFileSync(path.join(runDir, 'manifest.json'), 'utf8'));
          const snapshot = JSON.parse(fs.readFileSync(manifest.snapshotPath, 'utf8'));
          snapshots.push(snapshot.entries[0].message.content);
          live[0].message.content = 'Later unrelated user task.';
          const memory = task.startsWith('Task: produce a read-only structured consolidation plan');
          const plan = {
            kind: memory ? 'memory-consolidation-plan' : 'harness-consolidation-plan',
            version: 1, schemaVersion: 1,
            runId: manifest.runId, scopeKey: manifest.scopeKey,
            scopeDigest: manifest.scopeDigest, artifactHash: manifest.snapshotDigest,
            snapshotDigest: manifest.snapshotDigest, selected: [], operations: [],
            inventory: [], clusters: [], staleness: [], grounding: [], report: [],
            ...(memory ? { newMemories: [{
              name: 'preference.md', kind: 'preference',
              content: '---\nname: concise-updates\ndescription: Concise updates\ntype: feedback\n---\nPrefer concise updates.\n',
              evidence: [{ index: 0, quote: 'Prefer concise updates.' }],
            }] } : {}),
          };
          const event = { type: 'message_end', message: { role: 'assistant', content: [{ type: 'text', text: JSON.stringify(plan) }] } };
          const worker = 'const fs=require("node:fs"); fs.writeSync(1,' + JSON.stringify(JSON.stringify(event) + '\n') + '); fs.closeSync(1); fs.closeSync(2); setTimeout(() => process.exit(0), 200);';
          return spawn('node', ['-e', worker], { cwd: options.cwd, stdio: ['ignore', 'pipe', 'pipe'] });
        },
      }));
      const { default: register } = await import('./packages/continual-learning/extensions/inject-memory.ts');
      const hooks = new Map();
      const pi = {
        on: (name, handler) => hooks.set(name, [...(hooks.get(name) ?? []), handler]),
        registerCommand: () => {}, getCommands: () => [],
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
      const lockFiles = fs.existsSync(path.join(agent, 'memory')) ? fs.readdirSync(path.join(agent, 'memory')).filter(name => name.endsWith('.lock')) : [];
      const { resolveMemoryPaths } = await import('./packages/continual-learning/extensions/memory-paths.ts');
      const memoryPaths = resolveMemoryPaths(cwd);
      const created = fs.existsSync(path.join(memoryPaths.harnessDir, 'preference.md'));
      const leaked = fs.existsSync(path.join(cwd, '.memory', 'preference.md'));
      await emit('session_shutdown', {});
      fs.rmSync(temp, { recursive: true, force: true });
      console.log(JSON.stringify({ snapshots, lockFiles, created, leaked, completed: notices.some(text => text.includes('memory consolidated')), failures: notices.filter(text => /failed|rejected|blocked|without verified/i.test(text)) }));
    ''')
    assert result["failures"] == []
    assert result["snapshots"] == ["Prefer concise updates.", "Prefer concise updates."]
    assert result["lockFiles"] == []
    assert result["completed"]
    assert result["created"] and not result["leaked"]


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
  kind: memory ? 'memory-consolidation-plan' : 'harness-consolidation-plan',
  version: 1, schemaVersion: 1, runId: manifest.runId, scopeKey: manifest.scopeKey,
  scopeDigest: manifest.scopeDigest, artifactHash: manifest.snapshotDigest,
  snapshotDigest: manifest.snapshotDigest, selected: [], operations: [],
  inventory: [], clusters: [], staleness: [], grounding: [], report: [], newMemories: [],
};
fs.writeSync(1, JSON.stringify({type:'message_end',message:{role:'assistant',content:[{type:'text',text:JSON.stringify(plan)}]}})+'\n');
fs.closeSync(1); fs.closeSync(2);
setTimeout(() => process.exit(0), 300);
''')
        source = r'''
import fs from 'node:fs';
import path from 'node:path';
import register from './packages/continual-learning/extensions/inject-memory.ts';
const base = process.env.LEARNING_TEST_DIR;
process.argv[1] = path.join(base, 'worker.cjs');
const cwd = path.join(base, 'project'); fs.mkdirSync(cwd);
const hooks = new Map(), notices = [];
register({on:(name,handler)=>hooks.set(name,[...(hooks.get(name)??[]),handler]),registerCommand:()=>{},getCommands:()=>[]});
const ctx = {cwd,mode:'json',hasUI:false,ui:{notify:text=>notices.push(text),setWidget:()=>{}},sessionManager:{getBranch:()=>[],buildContextEntries:()=>[]}};
for (const [name,event] of [['session_start',{}],['input',{source:'interactive'}],['agent_settled',{}],['session_shutdown',{}]]) {
  for (const handler of hooks.get(name)??[]) await handler(event,ctx);
}
console.log(JSON.stringify({completed:true,notices}));
'''
        result = subprocess.run(
            ["node", "--import", "tsx", "--input-type=module", "-e", source],
            cwd=REPO, capture_output=True, text=True, timeout=20,
            env={**os.environ, "LEARNING_TEST_DIR": temporary,
                 "PI_CODING_AGENT_DIR": str(base / "agent")},
        )
        assert result.returncode == 0, result.stderr
        outcome = json.loads(result.stdout.strip().splitlines()[-1])
        assert outcome["completed"]
        assert any("memory consolidated" in notice for notice in outcome["notices"]), outcome
