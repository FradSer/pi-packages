import { expect, test } from "bun:test";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { debugDirectory } from "../extensions/debug.ts";

const repo = path.resolve(import.meta.dir, "../../..");

test("实际 Pi print 记录门禁和工具结果，关闭 debug 后不再落盘", async () => {
  const root = realpathSync(mkdtempSync(path.join(os.tmpdir(), "cl-debug-native-")));
  const project = path.join(root, "project"), agent = path.join(root, "agent");
  mkdirSync(project); mkdirSync(agent, { mode: 0o700 }); mkdirSync(path.join(project, ".pi"));
  writeFileSync(path.join(project, ".pi/harness.json"), JSON.stringify({ rules: [{ id: "fixture", bash: "^debug-forbidden$", action: "block", message: "Controlled debug denial." }] }));
  writeFileSync(path.join(agent, "settings.json"), JSON.stringify({ packages: [], retry: { enabled: false } }));
  writeFileSync(path.join(agent, "continual-learning.json"), JSON.stringify({ autoSettledLearning: false, autoContinualLearning: false, jev: false }));
  let calls = 0, organize = false, organizeCalls = 0;
  const server = Bun.serve({ hostname: "127.0.0.1", port: 0, async fetch(request) {
    await request.json();
    const call = ++calls;
    const useTool = organize ? ++organizeCalls === 1 : call <= 2;
    const delta = useTool ? { tool_calls: [{ index: 0, id: `call-${call}`, type: "function", function: {
      name: organize ? "learn" : "bash", arguments: JSON.stringify(organize ? {} : { command: call === 1 ? "debug-forbidden" : "printf debug-native-success" }),
    } }] } : { content: "Controlled debug probe complete." };
    const frames = [{ id: "fixture", object: "chat.completion.chunk", model: "fixed", choices: [{ index: 0, delta, finish_reason: null }] },
      { id: "fixture", object: "chat.completion.chunk", model: "fixed", choices: [{ index: 0, delta: {}, finish_reason: useTool ? "tool_calls" : "stop" }], usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 } }];
    return new Response(frames.map(frame => "data: " + JSON.stringify(frame) + "\n\n").join("") + "data: [DONE]\n\n", { headers: { "content-type": "text/event-stream" } });
  } });
  writeFileSync(path.join(agent, "models.json"), JSON.stringify({ providers: { fixture: {
    baseUrl: `http://127.0.0.1:${server.port}/v1`, api: "openai-completions", apiKey: "public-loopback-fixture",
    models: [{ id: "fixed", reasoning: false, input: ["text"], contextWindow: 100000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
  } } }));
  const cli = path.join(repo, "node_modules/.bin/pi"), session = path.join(root, "session.jsonl");
  const run = async (prompt: string, tools = "bash") => {
    const child = Bun.spawn([cli, "--offline", "--no-extensions", "--no-context-files", "--no-skills", "--no-prompt-templates", "--no-themes", "--no-approve", "--thinking", "off", "--tools", tools,
      "-e", path.join(repo, "packages/continual-learning/index.ts"), "--model", "fixture/fixed", "--session", session, "--print", "--mode", "json", prompt],
    { cwd: project, env: { PATH: process.env.PATH, HOME: root, PI_CODING_AGENT_DIR: agent, PI_OFFLINE: "1", PI_TELEMETRY: "0" }, stdout: "pipe", stderr: "pipe" });
    const timeout = setTimeout(() => child.kill(), 20000);
    try {
      const [code, stdout, stderr] = await Promise.all([child.exited, new Response(child.stdout).text(), new Response(child.stderr).text()]);
      expect(code, stderr + "\n" + stdout.slice(-2000)).toBe(0);
      return { stdout, stderr };
    } finally { clearTimeout(timeout); }
  };
  try {
    await run("Run the controlled debug probe.");
    expect(calls).toBe(3);
    const directory = debugDirectory(project, agent);
    const logs = () => readdirSync(directory).filter(name => name.endsWith(".jsonl")).flatMap(name => readFileSync(path.join(directory, name), "utf8").trim().split("\n").map(line => JSON.parse(line)));
    const rows = logs();
    expect(rows.some(row => row.event === "event:tool_call" && row.outcome === "blocked")).toBe(true);
    expect(JSON.stringify(rows)).toContain("debug-native-success");
    expect(rows.some(row => row.event === "appendEntry" && row.data[0] === "harness-behavior-observation")).toBe(true);
    expect(rows.some(row => row.source === "extensions/harness-guidance.ts")).toBe(true);
    expect(rows.some(row => row.source === "extensions/output-checks.ts")).toBe(true);
    const snapshots = rows.filter(row => row.event === "context:snapshot");
    expect(snapshots.length).toBeGreaterThan(0);
    expect(rows.every(row => row.context.projectId === path.basename(directory))).toBe(true);
    expect(rows.filter(row => !["process:exit", "context:snapshot", "lifecycle:batch"].includes(row.event) && !row.event.startsWith("event:"))
      .every(row => typeof row.context.sessionId === "string")).toBe(true);
    expect(rows.some(row => typeof row.context.sessionId === "string" && row.data.context?.sessionFile === session)).toBe(true);
    if (existsSync(path.join(agent, "auth.json"))) expect(JSON.parse(readFileSync(path.join(agent, "auth.json"), "utf8"))).toEqual({});
    writeFileSync(path.join(agent, "continual-learning.json"), JSON.stringify({ autoSettledLearning: false, autoContinualLearning: true, jev: false }));
    organize = true;
    await run("整理记忆", "bash,learn");
    expect(organizeCalls).toBe(2);
    const learning = logs();
    const receipt = learning.find(row => row.event === "receipt:written" && row.data.receipt.screen.routing?.includes("organized-in-process"));
    expect(receipt?.data.receipt.operations, JSON.stringify(learning.filter(row => /^(?:tool:learn|receipt:|pipeline:)/.test(row.event)))).toBe(0);
    expect(learning.some(row => row.event === "pipeline:started" && row.data.batchId === receipt?.data.receipt.batchId)).toBe(true);
    expect(learning.some(row => row.event === "pipeline:closed" && row.data.batchId === receipt?.data.receipt.batchId)).toBe(true);
    expect(learning.some(row => row.event === "tool:learn" && row.phase === "completed" && row.data.result.details.status === "organized")).toBe(true);
    organize = false;
    await run("/learning debug off");
    expect(JSON.parse(readFileSync(path.join(agent, "continual-learning.json"), "utf8")).debug).toBe(false);
    const before = JSON.stringify(logs());
    await run("Observe the completed local probe.");
    expect(JSON.stringify(logs())).toBe(before);
    expect(calls).toBe(6);
  } finally { server.stop(true); rmSync(root, { recursive: true, force: true }); }
}, 60000);
