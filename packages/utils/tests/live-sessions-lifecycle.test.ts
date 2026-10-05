import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, rm } from 'node:fs/promises';
import { join } from 'node:path';
import type { ExtensionAPI, ExtensionContext } from '@earendil-works/pi-coding-agent';
import registerLiveSessions, { parseDelivery } from '../extensions/live-sessions.ts';
import { execute } from '../extensions/live-sessions/client.ts';

function fakePi(hooks: Map<string, (event: unknown, ctx: ExtensionContext) => Promise<void>>, commands: Map<string, unknown>, deliveries: unknown[]) {
  return {
    on: (event: string, handler: (event: unknown, ctx: ExtensionContext) => Promise<void>) => hooks.set(event, handler),
    registerCommand: (name: string, spec: unknown) => commands.set(name, spec),
    getSessionName: () => 'test',
    sendUserMessage: (...args: unknown[]) => deliveries.push(args),
  } as unknown as ExtensionAPI;
}

function commandCtx(notifications: { message: string; level: string }[], hasUI = false) {
  return {
    hasUI,
    ui: {
      notify: (message: string, level: string) => notifications.push({ message, level }),
      select: async () => undefined,
    },
  } as unknown as ExtensionContext;
}

test('extension opens no factory resource and rotates targets across session lifecycle', async () => {
  const directory = await mkdtemp(join('/tmp', 'psc-'));
  const previous = process.env.PI_UTILS_LIVE_SESSIONS_DIR;
  process.env.PI_UTILS_LIVE_SESSIONS_DIR = directory;
  const hooks = new Map<string, (event: unknown, ctx: ExtensionContext) => Promise<void>>();
  const deliveries: unknown[] = [];
  const pi = fakePi(hooks, new Map(), deliveries);
  let durableId = 'durable-a';
  const ctx = { cwd: '/work', isIdle: () => false, sessionManager: { getSessionId: () => durableId } } as unknown as ExtensionContext;
  const list = () => execute({ version: 1, requestId: 'list', command: 'list' }, directory);
  try {
    registerLiveSessions(pi);
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
    if (previous === undefined) delete process.env.PI_UTILS_LIVE_SESSIONS_DIR;
    else process.env.PI_UTILS_LIVE_SESSIONS_DIR = previous;
    await rm(directory, { recursive: true, force: true });
  }
});

test('the /live-sessions command is the capability entry point and never claims completion', async () => {
  const directory = await mkdtemp(join('/tmp', 'psc-cmd-'));
  const previous = process.env.PI_UTILS_LIVE_SESSIONS_DIR;
  process.env.PI_UTILS_LIVE_SESSIONS_DIR = directory;
  const hooks = new Map<string, (event: unknown, ctx: ExtensionContext) => Promise<void>>();
  const commands = new Map<string, { handler: (args: string, ctx: ExtensionContext) => Promise<void>; getArgumentCompletions?: (prefix: string) => Promise<unknown> }>();
  const deliveries: unknown[] = [];
  let idle = false;
  const sessionCtx = { cwd: '/work', isIdle: () => idle, sessionManager: { getSessionId: () => 'durable-cmd' } } as unknown as ExtensionContext;
  try {
    registerLiveSessions(fakePi(hooks, commands as unknown as Map<string, unknown>, deliveries));
    const command = commands.get('live-sessions')!;
    assert.ok(command, 'live-sessions command is not registered');

    const empty: { message: string; level: string }[] = [];
    await command.handler('', commandCtx(empty));
    assert.deepEqual(empty, [{ message: 'No live Pi sessions found.', level: 'info' }]);

    await hooks.get('session_start')!({}, sessionCtx);
    const listed: { message: string; level: string }[] = [];
    await command.handler('', commandCtx(listed));
    assert.equal(listed.length, 1);
    assert.match(listed[0].message, /running · pid \d+ · \/work/);

    const completions = (await command.getArgumentCompletions!('')) as { value: string }[];
    assert.equal(completions.length, 1);
    const target = completions[0].value;

    idle = true;
    const accepted: { message: string; level: string }[] = [];
    await command.handler(`${target} check the failing test`, commandCtx(accepted));
    assert.deepEqual(deliveries.at(-1), ['check the failing test', { deliverAs: 'followUp' }]);
    assert.match(accepted[0].message, /accepted — the text was delivered, not completed/);

    idle = false;
    const queued: { message: string; level: string }[] = [];
    await command.handler(`steer ${target} stop and summarize`, commandCtx(queued));
    assert.deepEqual(deliveries.at(-1), ['stop and summarize', { deliverAs: 'steer' }]);
    assert.match(queued[0].message, /queued as follow-up — the text was delivered, not completed/);

    const failed: { message: string; level: string }[] = [];
    await command.handler(`${target}`, commandCtx(failed));
    assert.equal(failed[0].level, 'error');
    assert.match(failed[0].message, /delivery text is required/);

    const missing: { message: string; level: string }[] = [];
    await command.handler('no-such-instance hello', commandCtx(missing));
    assert.equal(missing[0].level, 'error');
    assert.match(missing[0].message, /Live delivery failed/);
  } finally {
    await hooks.get('session_shutdown')?.({}, sessionCtx);
    if (previous === undefined) delete process.env.PI_UTILS_LIVE_SESSIONS_DIR;
    else process.env.PI_UTILS_LIVE_SESSIONS_DIR = previous;
    await rm(directory, { recursive: true, force: true });
  }
});

test('delivery arguments are bounded before any socket call', () => {
  assert.deepEqual(parseDelivery('abc hello'), { deliverAs: 'followUp', sessionId: 'abc', text: 'hello' });
  assert.deepEqual(parseDelivery('steer abc hello'), { deliverAs: 'steer', sessionId: 'abc', text: 'hello' });
  assert.match((parseDelivery('') as { error: string }).error, /usage/);
  assert.match((parseDelivery('abc') as { error: string }).error, /delivery text is required/);
  assert.match((parseDelivery(`abc ${'x'.repeat(5000)}`) as { error: string }).error, /longer than 4000/);
  assert.match((parseDelivery(`${'x'.repeat(200)} hello`) as { error: string }).error, /longer than 128/);
});
