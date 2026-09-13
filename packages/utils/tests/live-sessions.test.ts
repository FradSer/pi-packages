import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, rm, chmod, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { startServer } from '../extensions/live-sessions/server.ts';
import { execute } from '../extensions/live-sessions/client.ts';
import { parseRequest } from '../extensions/live-sessions/protocol.ts';

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
