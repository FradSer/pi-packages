import assert from "node:assert/strict";
import {test} from "node:test";
import {spawnSync} from "node:child_process";
import {memoryWorkerEnvironment} from "../extensions/memory-worker-environment.ts";

test("Memory planner keeps its parent's explicitly enabled proxy transport", () => {
  const env = memoryWorkerEnvironment({
    PATH: "/runtime/bin", HOME: "/isolated", PI_CODING_AGENT_DIR: "/isolated/agent",
    HTTPS_PROXY: "http://127.0.0.1:7890", HTTP_PROXY: "http://127.0.0.1:7890",
    NO_PROXY: "localhost,127.0.0.1,::1", NODE_OPTIONS: "--use-env-proxy",
    ANTHROPIC_API_KEY: "test-only-do-not-inherit", TYPESAFE_API_KEY: "test-only-do-not-inherit",
  });
  assert.equal(env.HTTPS_PROXY, "http://127.0.0.1:7890");
  assert.equal(env.HTTP_PROXY, "http://127.0.0.1:7890");
  assert.equal(env.NO_PROXY, "localhost,127.0.0.1,::1");
  assert.equal(env.NODE_OPTIONS, "--use-env-proxy");
  assert.equal(env.ANTHROPIC_API_KEY, undefined);
  assert.equal(env.TYPESAFE_API_KEY, undefined);
});

test("Memory planner does not inherit arbitrary Node startup code or unrelated environment", () => {
  const env = memoryWorkerEnvironment({
    NODE_OPTIONS: "--require /unrelated/preload.cjs", NODE_TLS_REJECT_UNAUTHORIZED: "0",
    SECRET_VALUE: "test-only-do-not-inherit", HTTPS_PROXY: "http://127.0.0.1:7890",
  });
  assert.equal(env.NODE_OPTIONS, undefined);
  assert.equal(env.NODE_TLS_REJECT_UNAUTHORIZED, undefined);
  assert.equal(env.SECRET_VALUE, undefined);
});

test("Memory planner preserves lowercase proxy settings and only the supported Node opt-in", () => {
  assert.deepEqual(memoryWorkerEnvironment({
    http_proxy: "http://127.0.0.1:7890", https_proxy: "http://127.0.0.1:7890",
    no_proxy: "localhost", NODE_OPTIONS: '  "--use-env-proxy"  ', NODE_USE_ENV_PROXY: "1",
  }), {
    http_proxy: "http://127.0.0.1:7890", https_proxy: "http://127.0.0.1:7890",
    no_proxy: "localhost", NODE_OPTIONS: "--use-env-proxy", NODE_USE_ENV_PROXY: "1",
  });
  assert.equal(memoryWorkerEnvironment({NODE_OPTIONS: "--use-env-proxy --require /preload.cjs"}).NODE_OPTIONS, undefined);
  assert.equal(memoryWorkerEnvironment({NODE_USE_ENV_PROXY: "0"}).NODE_USE_ENV_PROXY, undefined);
});

const supportsNodeProxy = spawnSync("node", ["-p", 'process.allowedNodeEnvironmentFlags.has("--use-env-proxy")'], {encoding: "utf8"}).stdout?.trim() === "true";

test("a real Node planner child can fetch through the inherited loopback proxy", {
  timeout: 10_000, skip: supportsNodeProxy ? false : "Installed Node does not support --use-env-proxy",
}, async () => {
  const {createServer} = await import("node:http");
  const {spawn} = await import("node:child_process");
  let proxyRequests = 0;
  const proxy = createServer((request, response) => {
    proxyRequests++;
    assert.equal(request.url, "http://memory-worker.invalid/probe");
    response.end("proxy-ok");
  });
  proxy.on("connect", (request, socket) => {
    assert.equal(request.url, "memory-worker.invalid:80");
    socket.write("HTTP/1.1 200 Connection Established\r\n\r\n");
    socket.once("data", data => {
      assert.match(data.toString(), /^GET \/probe HTTP\/1\.1/);
      proxyRequests++;
      socket.end("HTTP/1.1 200 OK\r\nContent-Length: 8\r\nConnection: close\r\n\r\nproxy-ok");
    });
  });
  await new Promise<void>((resolve, reject) => {
    proxy.once("error", reject);
    proxy.listen(0, "127.0.0.1", resolve);
  });
  const address = proxy.address();
  assert.ok(address && typeof address === "object");
  const child = spawn("node", ["--input-type=module", "-e",
    'const response = await fetch("http://memory-worker.invalid/probe"); process.stdout.write(await response.text());'], {
    env: memoryWorkerEnvironment({PATH: process.env.PATH,
      HTTP_PROXY: `http://127.0.0.1:${address.port}`, NO_PROXY: "", NODE_OPTIONS: "--use-env-proxy"}),
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  child.stdout.setEncoding("utf8").on("data", chunk => {stdout += chunk;});
  child.stderr.resume();
  try {
    const exitCode = await new Promise<number | null>((resolve, reject) => {
      child.once("error", reject);
      child.once("close", resolve);
    });
    assert.equal(exitCode, 0);
    assert.equal(stdout, "proxy-ok");
    assert.equal(proxyRequests, 1);
  } finally {
    child.kill();
    await new Promise<void>(resolve => proxy.close(() => resolve()));
  }
});
