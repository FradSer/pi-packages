import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, rm } from 'node:fs/promises';
import { join } from 'node:path';
import type { ExtensionAPI, ExtensionContext } from '@earendil-works/pi-coding-agent';
import sessionControl from '../index.ts';
import { execute } from '../src/client.ts';

test('extension opens no factory resource and rotates targets across session lifecycle', async () => {
  const directory = await mkdtemp(join('/tmp', 'psc-'));
  const previous = process.env.PI_SESSION_CONTROL_DIR;
  process.env.PI_SESSION_CONTROL_DIR = directory;
  const hooks = new Map<string, (event: unknown, ctx: ExtensionContext) => Promise<void>>();
  const deliveries: unknown[] = [];
  const pi = {
    on: (event: string, handler: (event: unknown, ctx: ExtensionContext) => Promise<void>) => hooks.set(event, handler),
    getSessionName: () => 'test',
    sendUserMessage: (...args: unknown[]) => deliveries.push(args),
  } as unknown as ExtensionAPI;
  let durableId = 'durable-a';
  const ctx = { cwd: '/work', isIdle: () => false, sessionManager: { getSessionId: () => durableId } } as unknown as ExtensionContext;
  const list = () => execute({ version: 1, requestId: 'list', command: 'list' }, directory);
  try {
    sessionControl(pi);
    assert.deepEqual((await list()).sessions, []);
    await hooks.get('session_start')!({}, ctx);
    const first = (await list()).sessions![0];
    const request = { version: 1, requestId: 'submit', command: 'send', sessionId: first.sessionId, text: '/literal prompt' };
    assert.equal((await execute(request, directory)).status, 'queued');
    assert.deepEqual(deliveries, [['/literal prompt', { deliverAs: 'followUp' }]]);
    durableId = 'durable-b';
    assert.equal((await execute({ ...request, requestId: 'changed' }, directory)).error?.code, 'delivery_failed');
    await hooks.get('session_shutdown')!({}, ctx);
    await hooks.get('session_start')!({}, ctx);
    assert.notEqual((await list()).sessions![0].sessionId, first.sessionId);
    assert.equal((await execute(request, directory)).ok, false);
    await hooks.get('session_shutdown')!({}, ctx);
    await hooks.get('session_shutdown')!({}, ctx);
    assert.deepEqual((await list()).sessions, []);
  } finally {
    await hooks.get('session_shutdown')?.({}, ctx);
    if (previous === undefined) delete process.env.PI_SESSION_CONTROL_DIR;
    else process.env.PI_SESSION_CONTROL_DIR = previous;
    await rm(directory, { recursive: true, force: true });
  }
});
