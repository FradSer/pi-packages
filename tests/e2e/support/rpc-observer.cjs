// Test-only preload: observe real child JSONL without changing writes or acks.
// The temporary trace survives parent shutdown so Python can verify/reap children
// even though pi-kit deliberately launches them in separate process groups.
const childProcess = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { syncBuiltinESMExports } = require("node:module");
const { StringDecoder } = require("node:string_decoder");

const trace = path.join(process.env.PI_CODING_AGENT_DIR, "rpc-children.jsonl");
const spawn = childProcess.spawn;
const record = (event) => fs.appendFileSync(trace, `${JSON.stringify(event)}\n`);
childProcess.spawn = function (command, args, options) {
  const child = spawn.call(this, command, args, options);
  if (!args?.includes("rpc")) return child;
  const bindings = {};
  for (const key of ["PI_SUBAGENT_PROJECT_CWD", "PI_SUBAGENT_WORKSPACE_PATH", "PI_SUBAGENT_DEFINITION", "PI_SUBAGENT_SCOPE"]) {
    if (typeof options?.env?.[key] === "string") bindings[key] = options.env[key];
  }
  record({ type: "spawn", pid: child.pid, args, cwd: options?.cwd, bindings });
  const decoder = new StringDecoder("utf8");
  let buffer = "";
  child.stdout?.on("data", (chunk) => {
    buffer += decoder.write(chunk);
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      try {
        const response = JSON.parse(line);
        if (response.type === "response") record({ type: "response", pid: child.pid, response });
      } catch { /* Diagnostics are not protocol responses. */ }
    }
  });
  if (child.stdin) {
    const write = child.stdin.write;
    child.stdin.write = function (chunk, ...rest) {
      try { record({ type: "command", pid: child.pid, command: JSON.parse(String(chunk)) }); }
      catch { /* Preserve the original write, including malformed input. */ }
      return write.call(this, chunk, ...rest);
    };
  }
  child.once("close", (code, signal) => record({ type: "close", pid: child.pid, code, signal }));
  return child;
};
syncBuiltinESMExports();
