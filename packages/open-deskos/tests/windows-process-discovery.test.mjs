import assert from "node:assert/strict";
import test from "node:test";

test("Windows process snapshots identify quoted Pi launchers and exclude mentions and invalid times", async () => {
  const { parseWindowsPiProcesses } = await import("../src/processes.ts");
  assert.equal(typeof parseWindowsPiProcesses, "function");
  const now = 20000;
  const row = (ProcessId, CommandLine, startedAtMs = 10000, Name = "node.exe") => ({ ProcessId, Name, CommandLine, startedAtMs });
  const script = "C:\\Program Files\\Pi\\node_modules\\@earendil-works\\pi-coding-agent\\dist\\cli.js";
  const payload = JSON.stringify([
    row(1, `"C:\\Program Files\\nodejs\\node.exe" "${script}"`),
    row(2, "node.exe app.js pi"),
    row(3, `powershell.exe -Command echo "${script}"`, 10000, "powershell.exe"),
    row(4, `node.exe "${script}"`, 0),
    row(5, `node.exe "${script}"`, 30000),
    row(6, `node.exe "${script}"`, "10000"),
    row(0x80000000, `node.exe "${script}"`),
    row(7, "pi.exe", 10000, "pi.exe"),
  ]);
  assert.deepEqual(parseWindowsPiProcesses(payload, now), [{ pid: 1, startedAt: 10000 }, { pid: 7, startedAt: 10000 }]);
  assert.deepEqual(parseWindowsPiProcesses(JSON.stringify(row(8, `node.exe "${script}"`)), now), [{ pid: 8, startedAt: 10000 }]);
  for (const invalid of ["{", "null", JSON.stringify([null, [], { ProcessId: "1" }]), " ".repeat(1024 * 1024 + 1)]) assert.deepEqual(parseWindowsPiProcesses(invalid, now), []);
});

test("win32 inventory queries one bounded read-only PowerShell snapshot rather than ps", async () => {
  const { listPiProcesses } = await import("../src/processes.ts");
  const calls = [];
  const processes = await listPiProcesses({ platform: "win32", now: () => 20000, readSnapshot: async (command, args) => {
    calls.push({ command, args });
    return JSON.stringify({ ProcessId: 42, Name: "pi.exe", CommandLine: "pi.exe", startedAtMs: 10000 });
  } });
  assert.deepEqual(processes, [{ pid: 42, startedAt: 10000 }]);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].command, "powershell.exe");
  assert.ok(calls[0].args.includes("-NonInteractive"));
  assert.match(calls[0].args.at(-1), /Get-CimInstance Win32_Process/);
});

test("a stuck process snapshot releases handles and rejects at its own deadline", async () => {
  const { readProcessSnapshot } = await import("../src/processes.ts");
  assert.equal(typeof readProcessSnapshot, "function");
  const calls = [];
  const keepAlive = setTimeout(() => {}, 1000);
  try {
    await assert.rejects(readProcessSnapshot("fixture-command", [], { timeoutMs: 10, execute() {
      return { kill(signal) { calls.push(signal); }, unref() { calls.push("unref"); }, stdout: { destroy() { calls.push("stdout"); } }, stderr: { destroy() { calls.push("stderr"); } } };
    } }), /deadline|timeout/);
    assert.deepEqual(calls, ["SIGKILL", "stdout", "stderr", "unref"]);
  } finally { clearTimeout(keepAlive); }
});
