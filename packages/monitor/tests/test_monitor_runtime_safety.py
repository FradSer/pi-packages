from __future__ import annotations

import subprocess
import json
import os
import signal
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def run(script: str) -> None:
    with tempfile.TemporaryDirectory(prefix='monitor-watchdog-') as scratch:
        harness = """import assert from 'node:assert/strict';
import { writeFileSync } from 'node:fs';
import { MonitorManager } from './packages/monitor/src/monitor.ts';
const manager = new MonitorManager({onTerminal() {}});
const pids = [];
const originalStart = manager.start.bind(manager);
manager.start = args => {
  const monitor = originalStart(args);
  const pid = manager.active.get(monitor.id)?.child?.pid;
  if (pid) { pids.push(pid); writeFileSync(PID_FILE, JSON.stringify(pids)); }
  return monitor;
};
const keepAlive = setInterval(() => {}, 100);
try {\n""".replace('PID_FILE', json.dumps(str(Path(scratch) / 'pids')))
        try:
            result = subprocess.run(
                ['node', '--import', 'tsx', '--input-type=module'], cwd=REPO,
                input=harness + script + "\n} finally { await manager.stopAllOnShutdown(); clearInterval(keepAlive); }",
                text=True, capture_output=True, timeout=12,
            )
            assert result.returncode == 0, result.stderr
        finally:
            pid_file = Path(scratch) / 'pids'
            if pid_file.exists():
                for pid in json.loads(pid_file.read_text()):
                    try:
                        os.killpg(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass


def test_regex_deadline_is_interruptible() -> None:
    run('''const m = manager.start({command: "printf 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa!\\\\n'; sleep 2", description:'regex', resultPattern:'(a+)+$', timeoutMs:300});
const {result} = await manager.waitForTerminal(m.id);
assert.equal(result.status, 'timeout'); assert.ok(result.elapsedMs < 1500);''')


def test_monitor_identities_are_unique_across_manager_instances() -> None:
    run('''const first = manager.start({command:'exit 1', description:'verify', resultPattern:'DONE'});
await manager.waitForTerminal(first.id);
const reloaded = new MonitorManager({onTerminal() {}});
try {
  const second = reloaded.start({command:'printf DONE', description:'verify', resultPattern:'DONE'});
  await reloaded.waitForTerminal(second.id);
  assert.notEqual(first.id, second.id, 'extension reload must not reuse a monitor identity');
} finally { await reloaded.stopAllOnShutdown(); }''')


def test_stream_idle_is_independent() -> None:
    run('''const m = manager.start({command: "printf READY; while true; do echo progress >&2; sleep 0.03; done", description:'idle', resultPattern:'^READY$', timeoutMs:700});
assert.equal((await manager.waitForTerminal(m.id)).result.status, 'success');''')


def test_timeout_retains_unterminated_tail() -> None:
    run('''const m = manager.start({command: "printf 'FATAL exact cause'; sleep 2", description:'tail', resultPattern:'NEVER', timeoutMs:300});
const {result} = await manager.waitForTerminal(m.id);
assert.ok(result.output.some(line => line.includes('FATAL exact cause')));''')


def test_unicode_byte_budget_and_truncation() -> None:
    run('''const m = manager.start({command: "node -e \\\"console.log('界'.repeat(30000)); setTimeout(()=>{},2000)\\\"", description:'unicode', resultPattern:'NEVER', timeoutMs:500});
const {result} = await manager.waitForTerminal(m.id);
assert.ok(result.outputTruncated); assert.ok(Buffer.byteLength(result.output.join('\\n')) <= 32768);
assert.ok(result.output.every(line => Buffer.byteLength(line) <= 10240 + 10));''')


def test_shutdown_reclaims_stopped_and_naturally_closed_groups() -> None:
    run(r'''const { mkdtempSync, readFileSync, existsSync, rmSync } = await import('node:fs');
const { tmpdir } = await import('node:os');
const { execFileSync } = await import('node:child_process');
for (const natural of [false, true]) {
  const dir = mkdtempSync(tmpdir() + '/monitor-group-');
  let pid;
  try {
    const childCode = 'process.on("SIGTERM",()=>{});require("fs").writeFileSync("pid",String(process.pid));setInterval(()=>{},1000)';
    const command = `node -e '${childCode}' >/dev/null 2>&1 & ${natural ? 'while [ ! -f pid ]; do sleep 0.02; done; printf "READY\\n"' : 'wait'}`;
    const m = manager.start({command, cwd:dir, description:'group', resultPattern:'READY', timeoutMs:3000});
    while (!existsSync(dir + '/pid')) await new Promise(resolve => setTimeout(resolve,20));
    pid = Number(readFileSync(dir + '/pid','utf8'));
    if (natural) assert.equal((await manager.waitForTerminal(m.id)).result.status,'success');
    else manager.stop(m.id);
    const start = Date.now();
    await manager.stopAllOnShutdown();
    assert.ok(Date.now()-start >= 700, 'shutdown must await already pending escalation');
    let state = '';
    try { state = execFileSync('ps',['-o','stat=','-p',String(pid)], {encoding:'utf8'}).trim(); } catch {}
    assert.ok(!state || state.startsWith('Z'), `descendant still running: ${state}`);
  } finally {
    if (pid) { try { process.kill(pid,'SIGKILL'); } catch {} }
    rmSync(dir,{recursive:true,force:true});
  }
}''')


def test_manual_stop_retains_unterminated_tail() -> None:
    run('''const m = manager.start({command: "printf 'FATAL stopped cause'; sleep 2", description:'tail', resultPattern:'NEVER', timeoutMs:3000});
await new Promise(resolve => setTimeout(resolve,200)); manager.stop(m.id);
const {result} = await manager.waitForTerminal(m.id);
assert.equal(result.status,'stopped');
assert.ok(result.output.some(line => line.includes('FATAL stopped cause')));''')
