import assert from "node:assert/strict";
import { appendFileSync } from "node:fs";
import { MonitorManager } from "../src/monitor.ts";

type Case = { name: string; code: string; status: string; pattern?: string; failure?: string; matched?: string; payload?: unknown; parseError?: boolean; truncated?: boolean; reason?: string; timeout?: number; action?: "stop" | "shutdown"; limit?: string };
const cases: Case[] = [];
const add = (name: string, text: string, status = "success", options: Partial<Case> = {}) => cases.push({ name, code: `process.stdout.write(${JSON.stringify(text)})`, status, ...options });
for (const stream of ["stdout", "stderr"]) for (const ending of ["\n", "\r\n", ""]) {
  for (const [token, status] of [["DONE", "success"], ["FAIL", "failure"]]) {
    add(`${stream}-${status}-${JSON.stringify(ending)}`, token + ending, status, { code: `process.${stream}.write(${JSON.stringify(token + ending)})`, failure: "^FAIL$", matched: token });
  }
}
for (const near of ["NOT_DONE", "DONEISH", "almost DONE", "DONE 10%", "DONE failed", "undone", "DONE_", " DONE", "DONE ", "done", "Done", "progress: success", "0 errors", "100%", "\u001b[32mDONE\u001b[0m"]) add(`near-${JSON.stringify(near)}`, near + "\n", "result_missing");
add("empty-zero-exit", "", "result_missing");
add("nonzero-no-result", "diagnostic\n", "failure", { code: 'process.stdout.write("diagnostic\\n");process.exitCode=7', reason: "process_exit" });
add("success-precedes-nonzero", "DONE\n", "success", { code: 'process.stdout.write("DONE\\n");process.exitCode=7', matched: "DONE", limit: "A matched terminal contract takes precedence over the shell exit code; a sentinel must represent the intended outcome." });
add("failure-precedes-zero", "FAIL\n", "failure", { failure: "^FAIL$", matched: "FAIL" });
add("same-line-failure-wins", "DONE FAIL\n", "failure", { pattern: "DONE", failure: "FAIL", matched: "FAIL" });
add("first-success-line-wins", "DONE\nFAIL\n", "success", { failure: "^FAIL$", matched: "DONE", limit: "The first matching physical line wins; later failure lines do not revoke an earlier success." });
add("first-failure-line-wins", "FAIL\nDONE\n", "failure", { failure: "^FAIL$", matched: "FAIL" });
add("unicode-capture", "完成:界𐐀\n", "success", { pattern: "^完成:(?<value>.+)$", matched: "完成:界𐐀" });
add("ansi-explicit-contract", "\u001b[32mDONE\u001b[0m\n", "success", { pattern: "^\\x1b\\[32mDONE\\x1b\\[0m$" });
for (const delay of [1, 10, 45, 90]) add(`split-sentinel-${delay}`, "", "success", { code: `process.stdout.write("DO");setTimeout(()=>process.stdout.write("NE\\n"),${delay})`, matched: "DONE" });
for (const delay of [1, 10, 45, 90]) add(`split-invalidating-suffix-${delay}`, "", "result_missing", { code: `process.stdout.write("DONE");setTimeout(()=>process.stdout.write("ISH\\n"),${delay})` });
add("idle-prefix-design-limit", "", "success", { code: 'process.stdout.write("DONE");setTimeout(()=>process.stdout.write("ISH\\n"),600)', limit: "An unterminated prefix idle for more than 150 ms may match before its suffix arrives.", matched: "DONE" });
for (const payload of [{ ok: true, count: 3 }, [1, "界"], "hello", 0, false, null]) add(`json-${JSON.stringify(payload)}`, `RESULT ${JSON.stringify(payload)}\n`, "success", { pattern: "^RESULT (?<json>.*)$", payload });
for (const text of ["", "{", "undefined", "{bad:true}", "[1,]", "NaN"]) add(`invalid-json-${JSON.stringify(text)}`, `RESULT ${text}\n`, "success", { pattern: "^RESULT (?<json>.*)$", parseError: true });
add("json-value-clipping", `RESULT ${JSON.stringify({ text: "a".repeat(35000) })}\n`, "success", { pattern: "^RESULT (?<json>.*)$", parseError: true, truncated: true });
add("capture-aggregate", "a".repeat(4096) + "\n", "success", { pattern: "^" + Array.from({ length: 100 }, (_, i) => `(?<g${i}>`).join("") + "a+" + ")".repeat(100) + "$", truncated: true });
add("physical-line-over-budget", "x".repeat(65537) + "DONE\n", "failure", { reason: "matcher_line_limit" });
add("physical-line-over-budget-unicode", "界".repeat(23000) + "DONE\n", "failure", { reason: "matcher_line_limit" });
for (const ending of ["\n", ""]) add(`burst-${JSON.stringify(ending)}`, "", "success", { code: `process.stdout.write("progress\\n".repeat(20000));process.stderr.write("noise\\n".repeat(10000));process.stdout.write(${JSON.stringify("DONE" + ending)})`, matched: "DONE", timeout: 6000 });
add("timeout-diagnostic-tail", "", "timeout", { code: 'process.stderr.write("exact fatal detail");setTimeout(()=>{},3000)', timeout: 200 });
add("redos-timeout", "", "timeout", { code: 'process.stdout.write("a".repeat(35)+"!\\n");setTimeout(()=>{},3000)', pattern: "(a+)+$", timeout: 250 });
for (const action of ["stop", "shutdown"] as const) add(`${action}-diagnostic-tail`, "", "stopped", { code: 'process.stderr.write("owned diagnostic");setTimeout(()=>{},3000)', action });
let seed = 0x617c4;
for (let repeat = 0; repeat < 16; repeat++) {
  seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
  const delay = seed % 40;
  const first = repeat % 2 === 0 ? "DONE" : "FAIL";
  const second = first === "DONE" ? "FAIL" : "DONE";
  add(`seeded-first-match-${repeat}`, "", first === "DONE" ? "success" : "failure", { code: `process.stdout.write(${JSON.stringify(first + "\n")});setTimeout(()=>process.stdout.write(${JSON.stringify(second + "\n")}),${delay})`, failure: "^FAIL$", matched: first });
}

type Observation = { name: string; passed: boolean; expected: string; actual?: string; limit?: string; error?: string };
const observed: Observation[] = [];
const identities = new Set<string>();
const keepAlive = setInterval(() => {}, 100);
async function execute(test: Case) {
  const events: { id: string; result: unknown }[] = [];
  const manager = new MonitorManager({ onTerminal(monitor, result) { events.push({ id: monitor.id, result }); } });
  let monitor;
  try {
    const encoded = Buffer.from(test.code).toString("base64");
    monitor = manager.start({ command: `node -e 'eval(Buffer.from("${encoded}","base64").toString())'`, description: test.name, resultPattern: test.pattern ?? "^DONE$", failurePattern: test.failure, timeoutMs: test.timeout ?? 4000 });
    assert.ok(!identities.has(monitor.id), "monitor identities must be unique across managers");
    identities.add(monitor.id);
    const pid = (manager as unknown as { active: Map<string, { child: { pid?: number } }> }).active.get(monitor.id)?.child?.pid;
    if (pid && process.env.MONITOR_MATRIX_PID_FILE) appendFileSync(process.env.MONITOR_MATRIX_PID_FILE, `${pid}\n`);
    const waiting = manager.waitForTerminal(monitor.id);
    if (test.action) {
      await new Promise(resolve => setTimeout(resolve, 250));
      if (test.action === "stop") assert.deepEqual(manager.stop(monitor.id).stopped, [monitor.id]);
      else await manager.stopAllOnShutdown();
    }
    const terminal = await waiting;
    assert.equal(terminal.monitor.id, monitor.id);
    assert.equal(terminal.result.status, test.status, JSON.stringify(terminal.result));
    assert.equal(terminal.monitor.status, test.status);
    assert.ok(terminal.result.elapsedMs >= 0);
    if (test.matched) assert.equal(terminal.result.matched, test.matched);
    if (Object.hasOwn(test, "payload")) assert.deepEqual(terminal.result.result, test.payload);
    if (test.parseError) { assert.ok(terminal.result.resultParseError); assert.equal(terminal.result.result, undefined); }
    if (test.truncated) assert.equal(terminal.result.capturesTruncated, true);
    if (test.reason) assert.equal(terminal.result.reason, test.reason);
    if (terminal.result.captures) assert.ok(Buffer.byteLength(JSON.stringify(terminal.result.captures)) <= 32768);
    assert.ok(Buffer.byteLength((terminal.result.output ?? []).join("\n")) <= 32768);
    assert.equal(manager.list().length, 0);
    assert.equal(events.length, test.action ? 0 : 1);
    if (events.length) { assert.equal(events[0].id, monitor.id); assert.deepEqual(events[0].result, terminal.result); }
    if (test.name === "unicode-capture") assert.equal(terminal.result.captures?.value, "界𐐀");
    if (test.name === "timeout-diagnostic-tail") assert.ok(terminal.result.output?.some(line => line.includes("exact fatal detail")), JSON.stringify(terminal.result));
    observed.push({ name: test.name, passed: true, expected: test.status, actual: terminal.result.status, limit: test.limit });
  } catch (error) {
    observed.push({ name: test.name, passed: false, expected: test.status, error: String(error) });
  } finally { await manager.stopAllOnShutdown(); }
}
async function sharedManagerBatch(batch: number) {
  const events = new Map<string, number>();
  const manager = new MonitorManager({ onTerminal(monitor) { events.set(monitor.id, (events.get(monitor.id) ?? 0) + 1); } });
  try {
    const pending = Array.from({ length: 8 }, (_, index) => {
      const status = index === 0 ? "stopped" : index % 2 ? "success" : "failure";
      const token = status === "failure" ? "FAIL" : "DONE";
      const payload = `${batch}:${index}`;
      const code = `setTimeout(()=>process.stdout.write(${JSON.stringify(`${token} ${payload}\n`)}),${index === 0 ? 1000 : index * 20 + 70})`;
      const encoded = Buffer.from(code).toString("base64");
      const monitor = manager.start({ command: `node -e 'eval(Buffer.from("${encoded}","base64").toString())'`, description: payload, resultPattern: "^DONE (?<identity>.+)$", failurePattern: "^FAIL (?<identity>.+)$", timeoutMs: 4000 });
      assert.ok(!identities.has(monitor.id));
      identities.add(monitor.id);
      const pid = (manager as unknown as { active: Map<string, { child: { pid?: number } }> }).active.get(monitor.id)?.child?.pid;
      if (pid && process.env.MONITOR_MATRIX_PID_FILE) appendFileSync(process.env.MONITOR_MATRIX_PID_FILE, `${pid}\n`);
      return { monitor, status, payload, terminal: manager.waitForTerminal(monitor.id) };
    });
    assert.deepEqual(manager.stop(pending[0].monitor.id).stopped, [pending[0].monitor.id]);
    assert.equal(manager.list().length, 7, "stopping one monitor must preserve its seven siblings");
    for (const entry of pending) {
      const name = `shared-manager-${batch}-${entry.payload}`;
      try {
        const terminal = await entry.terminal;
        assert.equal(terminal.monitor.id, entry.monitor.id);
        assert.equal(terminal.result.status, entry.status);
        if (entry.status !== "stopped") assert.equal(terminal.result.captures?.identity, entry.payload);
        assert.equal(events.get(entry.monitor.id) ?? 0, entry.status === "stopped" ? 0 : 1);
        observed.push({ name, passed: true, expected: entry.status, actual: terminal.result.status });
      } catch (error) { observed.push({ name, passed: false, expected: entry.status, error: String(error) }); }
    }
    assert.equal(manager.list().length, 0);
    assert.deepEqual(manager.stop("missing").stopped, []);
  } finally { await manager.stopAllOnShutdown(); }
}
try {
  for (let offset = 0; offset < cases.length; offset += 4) await Promise.all(cases.slice(offset, offset + 4).map(execute));
  for (let batch = 0; batch < 3; batch++) await sharedManagerBatch(batch);
} finally { clearInterval(keepAlive); }
console.log(JSON.stringify({ suite: "real-process accuracy matrix", cases: observed.length, singleMonitorCases: cases.length, sharedManagerCases: 24, seededRepeatCases: 16, uniqueMonitorIds: identities.size, observed }));
process.exitCode = observed.some(row => !row.passed) ? 1 : 0;
