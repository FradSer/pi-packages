#!/usr/bin/env node
import { tsImport } from 'tsx/esm/api';
const { execute } = await tsImport('../src/client.ts', import.meta.url);
const { MAX_BYTES, failure } = await tsImport('../src/protocol.ts', import.meta.url);
let buffer = Buffer.alloc(0);
let timer;
const write = (reply) => process.stdout.write(JSON.stringify(reply) + '\n');
function armTimeout() {
  clearTimeout(timer);
  timer = setTimeout(() => {
    write(failure(null, 'timeout', 'No complete stdin request within 5 seconds'));
    process.stdin.destroy();
  }, 5000);
}
process.stdout.on('error', () => { process.stdin.destroy(); clearTimeout(timer); process.exitCode = 1; });
armTimeout();
try {
  for await (const chunk of process.stdin) {
    buffer = Buffer.concat([buffer, chunk]);
    let end;
    while ((end = buffer.indexOf(10)) !== -1) {
      clearTimeout(timer);
      const line = buffer.subarray(0, end);
      buffer = buffer.subarray(end + 1);
      if (line.length > MAX_BYTES) write(failure(null, 'frame_too_large', 'Maximum input is 65536 bytes'));
      else {
        try { write(await execute(JSON.parse(line.toString('utf8')))); }
        catch { write(failure(null, 'invalid_request', 'Expected one JSON object per line')); }
      }
      armTimeout();
    }
    if (buffer.length > MAX_BYTES) {
      write(failure(null, 'frame_too_large', 'Maximum input is 65536 bytes'));
      buffer = Buffer.alloc(0);
      process.stdin.destroy();
      break;
    }
  }
  if (buffer.length) write(failure(null, 'incomplete_frame', 'Each request must end with a newline'));
} catch { process.exitCode = 1; }
finally { clearTimeout(timer); }
