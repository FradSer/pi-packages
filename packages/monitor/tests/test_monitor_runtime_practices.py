from __future__ import annotations

from test_monitor_runtime_safety import run


def test_elapsed_is_independent_of_wall_clock() -> None:
    run(r'''const wallClock = Date.now;
try {
  for (const offset of [-60000, 60000]) for (const outcome of ['timeout', 'success', 'stopped']) {
    const m = manager.start({command: outcome === 'success' ? "sleep 0.1; printf 'DONE\\n'" : 'sleep 2', description:'clock', resultPattern:'^DONE$',timeoutMs:outcome === 'timeout' ? 150 : 1500});
    Date.now = () => wallClock() + offset;
    if (outcome === 'stopped') { await new Promise(resolve => setTimeout(resolve, 50)); manager.stop(m.id); }
    const {result} = await manager.waitForTerminal(m.id);
    assert.equal(result.status, outcome);
    assert.ok(result.elapsedMs >= 0 && result.elapsedMs < 1500, String(result.elapsedMs));
    Date.now = wallClock;
  }
} finally { Date.now = wallClock; }''')


def test_worker_constructor_failure_reclaims_monitor() -> None:
    run(r'''const { createRequire, syncBuiltinESMExports } = await import('node:module');
const require = createRequire(import.meta.url);
const workerModule = require('node:worker_threads');
const originalWorker = workerModule.Worker;
try {
  workerModule.Worker = class { constructor() { throw new Error('simulated matcher startup failure'); } };
  syncBuiltinESMExports();
  const m = manager.start({command:'sleep 2',description:'startup',resultPattern:'DONE',timeoutMs:200});
  const {result} = await manager.waitForTerminal(m.id);
  assert.equal(result.status, 'failure');
  assert.match(result.reason, /^matcher_error: simulated matcher startup failure$/);
  assert.equal(manager.list().length, 0);
} finally { workerModule.Worker = originalWorker; syncBuiltinESMExports(); }''')


def test_short_line_burst_uses_backpressure() -> None:
    run(r'''for (const ending of ['DONE\\n', 'DONE']) {
const code = `process.stdout.write("x\\n".repeat(30000));process.stderr.write("progress\\n".repeat(10000));process.stdout.write("${ending}")`;
const m = manager.start({command:`node -e '${code}'`,description:'burst',resultPattern:'^DONE$',timeoutMs:4000});
const {result} = await manager.waitForTerminal(m.id);
assert.equal(result.status,'success', JSON.stringify(result));
assert.equal(manager.list().length, 0);
}''')
