import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, rm, chmod, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawn } from 'node:child_process';
import { startServer } from '../src/server.ts';
import { execute } from '../src/client.ts';
import { parseRequest } from '../src/protocol.ts';

const request = (command: string, extra = {}) => ({ version: 1, requestId: 'test', command, ...extra });
test('protocol rejects array and object commands without coercion', () => {
  for (const command of [['send'], ['status'], ['list'], { toString: () => 'send' }, {}]) {
    assert.throws(() => parseRequest({ version: 1, requestId: 'review', command, sessionId: 'live' }));
  }
});
test('live discovery, delivery, deduplication, stale target and private transport', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'psc-'));
  const deliveries: string[] = [];
  let state = 'idle';
  const server = await startServer(directory, 'session-a', () => ({ sessionId: 'session-a', cwd: '/work', pid: process.pid, state }), (text) => deliveries.push(text));
  try {
    assert.equal((await stat(server.path)).mode & 0o777, 0o600);
    const listed = await execute(request('list'), directory);
    assert.equal(listed.sessions?.length, 1);
    const cli = spawn(process.execPath, ['packages/session-control/bin/pi-session-control.mjs'], { env: { ...process.env, PI_SESSION_CONTROL_DIR: directory } });
    let stdout = '';
    cli.stdout.on('data', (chunk) => { stdout += chunk; });
    cli.stdin.end(JSON.stringify(request('list')) + '\n');
    await new Promise<void>((resolve, reject) => { cli.once('error', reject); cli.once('close', (code) => code === 0 ? resolve() : reject(new Error(`CLI exited ${code}`))); });
    assert.equal(JSON.parse(stdout).sessions.length, 1);
    const oversized = spawn(process.execPath, ['packages/session-control/bin/pi-session-control.mjs']);
    let errors = '';
    oversized.stdout.on('data', (chunk) => { errors += chunk; });
    oversized.stdin.end('x'.repeat(70000));
    await new Promise<void>((resolve, reject) => { oversized.once('error', reject); oversized.once('close', () => resolve()); });
    assert.equal(errors.trim().split('\n').length, 1);
    assert.equal(JSON.parse(errors).error.code, 'frame_too_large');
    const send = request('send', { sessionId: 'session-a', text: 'hello' });
    assert.equal((await execute(send, directory)).status, 'accepted');
    assert.equal((await execute(send, directory)).status, 'accepted');
    assert.deepEqual(deliveries, ['hello']);
    assert.equal((await execute({ ...send, text: 'different' }, directory)).error?.code, 'request_conflict');
    state = 'running';
    assert.equal((await execute({ ...send, requestId: 'two' }, directory)).status, 'queued');
    assert.equal((await execute(request('send', { sessionId: '../wrong', text: 'hello' }), directory)).ok, false);
    assert.equal((await execute({ ...send, requestId: 'large', text: 'x'.repeat(70000) }, directory)).ok, false);
    await server.close();
    assert.equal((await execute(send, directory)).error?.code, 'not_found');
    await chmod(directory, 0o755);
    assert.equal((await execute(request('list'), directory)).error?.code, 'unsafe_directory');
  } finally {
    await server.close();
    await rm(directory, { recursive: true, force: true });
  }
});
