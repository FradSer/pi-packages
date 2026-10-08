/** Observe the real Python native-probe cleanup against an isolated process. */
import { spawnSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { observedAssert as assert, observeScenario, observedScenarios } from "../../../tests/e2e/support/assertion-observer.ts";

const python = `
import json, os, signal, subprocess, sys, time
sys.path.insert(0, "packages/goal/tests")
from goal_native_tui import terminate_fixture
child = subprocess.Popen([sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready',flush=True); time.sleep(60)"], stdout=subprocess.PIPE, text=True, start_new_session=True)
try:
    ready = child.stdout.readline().strip()
    start = time.monotonic()
    terminate_fixture(child, grace_seconds=0.1)
    elapsed = time.monotonic() - start
    signals = []
    original = os.killpg
    os.killpg = lambda pid, sig: signals.append([pid, sig])
    try: terminate_fixture(child, grace_seconds=0.1)
    finally: os.killpg = original
    print(json.dumps({"ready":ready,"returncode":child.returncode,"reaped":child.poll() is not None,"elapsed":elapsed,"lateSignals":signals}))
finally:
    if child.poll() is None:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=3)
    child.stdout.close()
`;
const results: string[] = [];
try {
  await observeScenario("cleanup kills and reaps a resistant fixture without late signals", () => {
    const child = spawnSync("python3", ["-c", python], { encoding: "utf8", timeout: 10000 });
    assert.equal(child.status, 0, child.stderr);
    const observed = JSON.parse(child.stdout) as { ready: string; returncode: number; reaped: boolean; elapsed: number; lateSignals: unknown[] };
    assert.equal(observed.ready, "ready");
    assert.equal(observed.returncode, -9);
    assert.equal(observed.reaped, true);
    assert.ok(observed.elapsed < 3);
    assert.deepEqual(observed.lateSignals, []);
  });
  results.push("ok cleanup kills and reaps a resistant fixture without late signals");
} catch (error) { results.push(`FAIL cleanup: ${String(error)}`); process.exitCode = 1; }
console.log(JSON.stringify(results));
if (process.env.PI_E2E_ASSERTION_PATH) writeFileSync(process.env.PI_E2E_ASSERTION_PATH, JSON.stringify(observedScenarios()));
