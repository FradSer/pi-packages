// Test-only preload: observe real child RPC, and reject outbound sockets before
// DNS or connection setup. NODE_OPTIONS propagates this to native Pi children.
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const tls = require('node:tls');
const http = require('node:http');
const https = require('node:https');
const dgram = require('node:dgram');
const childProcess = require('node:child_process');
const { syncBuiltinESMExports } = require('node:module');

const log = (file, event) => fs.appendFileSync(path.join(__dirname, file), JSON.stringify(event) + '\n');
const refuse = () => {
  log('network-attempts.jsonl', { pid: process.pid, blocked: true, stack: new Error().stack });
  throw new Error('Install wiring fixture forbids non-loopback network access');
};
const checkHost = (host) => {
  if (host !== undefined && !['127.0.0.1', '::1', '[::1]'].includes(String(host))) refuse();
};
const checkLocalSocket = (socketPath) => {
  const temporary = path.resolve(process.env.TMPDIR);
  if (!path.resolve(socketPath).startsWith(temporary + path.sep)) refuse();
};
const checkSocket = (args) => {
  const first = Array.isArray(args[0]) ? args[0][0] : args[0];
  if (typeof first === 'object' && first !== null) {
    if (first.path) return checkLocalSocket(first.path);
    checkHost(first.host ?? first.hostname);
  } else if (typeof first === 'string' && !/^\d+$/.test(first)) {
    checkLocalSocket(first); // tsx uses IPC only beneath this test's TMPDIR.
  } else {
    checkHost(args[1]);
  }
};
const connect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function (...args) {
  checkSocket(args);
  return connect.apply(this, args);
};
const tlsConnect = tls.connect;
tls.connect = function (...args) {
  checkSocket(args);
  return tlsConnect.apply(this, args);
};
for (const module of [http, https]) {
  for (const name of ['request', 'get']) {
    const original = module[name];
    module[name] = function (...args) {
      const first = args[0];
      if (typeof first === 'string' || first instanceof URL) {
        checkHost(new URL(first).hostname);
      } else {
        checkHost(first?.hostname ?? first?.host);
        if (first?.socketPath) refuse();
      }
      return original.apply(this, args);
    };
  }
}
dgram.Socket.prototype.send = refuse;
const fetch = globalThis.fetch;
globalThis.fetch = function (input, ...args) {
  checkHost(new URL(typeof input === 'string' || input instanceof URL ? input : input.url).hostname);
  return fetch.call(this, input, ...args);
};

// No RPC is invented or replaced. These listeners only record actual correlated
// requests/responses before the tool can report startup success.
const spawn = childProcess.spawn;
childProcess.spawn = function (...args) {
  const child = spawn.apply(this, args);
  const argv = args[1];
  if (!Array.isArray(argv) || !argv.includes('rpc')) return child;
  log('rpc.jsonl', { kind: 'spawn', pid: child.pid });
  const requests = new Map();
  const write = child.stdin.write;
  child.stdin.write = function (chunk, ...rest) {
    for (const line of String(chunk).split('\n').filter(Boolean)) {
      try {
        const request = JSON.parse(line);
        if (request.id) requests.set(request.id, request.type);
      } catch { /* Not an RPC record. */ }
    }
    return write.call(this, chunk, ...rest);
  };
  let buffer = '';
  child.stdout.on('data', (chunk) => {
    buffer += String(chunk);
    const lines = buffer.split('\n');
    buffer = lines.pop();
    for (const line of lines) {
      try {
        const response = JSON.parse(line);
        const command = requests.get(response.id);
        if (response.type === 'response' && command) {
          log('rpc.jsonl', {
            kind: 'response', pid: child.pid, command, success: response.success,
            ...(command === 'get_state' ? { isStreaming: response.data?.isStreaming } : {}),
            ...(command === 'prompt' ? { disposition: response.data?.disposition } : {}),
          });
        }
      } catch { /* Not an RPC record. */ }
    }
  });
  child.once('close', () => log('rpc.jsonl', { kind: 'close', pid: child.pid }));
  return child;
};
syncBuiltinESMExports();
