import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, mkdir, rm, chmod, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  createAgentSession,
  DefaultResourceLoader,
  SessionManager,
  SettingsManager,
  ModelRuntime,
  type ExtensionAPI,
  type ExtensionContext,
} from '@earendil-works/pi-coding-agent';
import registerLiveSessions, { parseDelivery } from '../extensions/live-sessions.ts';
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
    assert.equal((await execute(send, directory)).status, 'handed-over');
    assert.equal((await execute(send, directory)).status, 'handed-over');
    assert.deepEqual(deliveries, ['hello']);
    // The sender cannot witness delivery; the target can, and only for its own prompt.
    const confirm = request('status', { sessionId: 'session-a', confirmRequestId: 'test' });
    assert.equal((await execute(confirm, directory)).confirmed, false);
    server.observe('some other prompt');
    assert.equal((await execute(confirm, directory)).confirmed, false);
    server.observe('hello');
    assert.equal((await execute(confirm, directory)).confirmed, true);
    // A replayed receipt carries the confirmation instead of guessing again.
    assert.equal((await execute(send, directory)).confirmed, true);
    assert.equal((await execute(request('status', { sessionId: 'session-a', confirmRequestId: 'never-sent' }), directory)).confirmed, false);
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

test('real SDK receives literal live-session delivery with no model invocation', async () => {
  const directory = await mkdtemp('/tmp/psc-sdk-');
  const socketDirectory = join(directory, 's');
  const previous = process.env.PI_UTILS_LIVE_SESSIONS_DIR;
  process.env.PI_UTILS_LIVE_SESSIONS_DIR = socketDirectory;
  const inputs: { text: string; source: string }[] = [];
  const settingsManager = SettingsManager.inMemory();
  const loader = new DefaultResourceLoader({ cwd: directory, agentDir: directory, settingsManager,
    noExtensions: true, noSkills: true, noPromptTemplates: true, noThemes: true,
    agentsFilesOverride: () => ({ agentsFiles: [] }),
    extensionFactories: [registerLiveSessions, (pi) => {
      pi.on('input', (event) => { inputs.push({ text: event.text, source: event.source }); return { action: 'handled' }; });
    }],
  });
  await loader.reload();
  const modelRuntime = await ModelRuntime.create({ authPath: join(directory, 'auth.json'), modelsPath: join(directory, 'models.json'), allowModelNetwork: false });
  const { session } = await createAgentSession({ cwd: directory, agentDir: directory, resourceLoader: loader,
    modelRuntime, settingsManager, sessionManager: SessionManager.inMemory(directory), tools: [] });
  try {
    await session.bindExtensions({ mode: 'print' });
    const listed = await execute({ version: 1, requestId: 'list', command: 'list' }, socketDirectory);
    assert.equal(listed.sessions?.length, 1);
    const req = { version: 1, requestId: 'send', command: 'send', sessionId: listed.sessions![0].sessionId, text: '/literal $HOME; echo not-a-shell' };
    assert.equal((await execute(req, socketDirectory)).status, 'handed-over');
    assert.deepEqual(inputs, [{ text: req.text, source: 'extension' }]);
    assert.equal((await execute(req, socketDirectory)).status, 'handed-over');
    assert.equal(inputs.length, 1);
    assert.equal(session.messages.length, 0);
  } finally {
    await session.extensionRunner.emit({ type: 'session_shutdown', reason: 'quit' });
    session.dispose();
    if (previous === undefined) delete process.env.PI_UTILS_LIVE_SESSIONS_DIR;
    else process.env.PI_UTILS_LIVE_SESSIONS_DIR = previous;
    await rm(directory, { recursive: true, force: true });
  }
});

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
    const req = { version: 1, requestId: 'submit', command: 'send', sessionId: first.sessionId, text: '/literal prompt' };
    assert.equal((await execute(req, directory)).status, 'queued');
    assert.deepEqual(deliveries, [['/literal prompt', { deliverAs: 'followUp' }]]);
    durableId = 'durable-b';
    assert.equal((await execute({ ...req, requestId: 'changed' }, directory)).error?.code, 'delivery_failed');
    await hooks.get('session_shutdown')!({}, ctx);
    await hooks.get('session_start')!({}, ctx);
    assert.notEqual((await list()).sessions![0].sessionId, first.sessionId);
    assert.equal((await execute(req, directory)).ok, false);
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
    const nonMatching = (await command.getArgumentCompletions!('zzz-no-match')) as { value: string }[];
    assert.equal(nonMatching.length, 0);
    const matching = (await command.getArgumentCompletions!(target.slice(0, 4))) as { value: string }[];
    assert.deepEqual(matching.map((item) => item.value), [target]);

    idle = true;
    const accepted: { message: string; level: string }[] = [];
    await command.handler(`${target} check the failing test`, commandCtx(accepted));
    assert.deepEqual(deliveries.at(-1), ['check the failing test', { deliverAs: 'followUp' }]);
    assert.match(accepted[0].message, /handed over to its runtime — delivery is not confirmed and completion is not claimed/);

    idle = false;
    const queued: { message: string; level: string }[] = [];
    await command.handler(`steer ${target} stop and summarize`, commandCtx(queued));
    assert.deepEqual(deliveries.at(-1), ['stop and summarize', { deliverAs: 'steer' }]);
    assert.match(queued[0].message, /queued as a follow-up — delivery is not confirmed and completion is not claimed/);

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

test('a delivery is confirmed when the target observes it as its own prompt', async () => {
  const directory = await mkdtemp(join('/tmp', 'psc-confirm-'));
  const previous = process.env.PI_UTILS_LIVE_SESSIONS_DIR;
  process.env.PI_UTILS_LIVE_SESSIONS_DIR = directory;
  const hooks = new Map<string, (event: unknown, ctx: ExtensionContext) => Promise<void>>();
  const commands = new Map<string, { handler: (args: string, ctx: ExtensionContext) => Promise<void> }>();
  const notifications: { message: string; level: string }[] = [];
  const sessionCtx = { cwd: '/work', isIdle: () => true, sessionManager: { getSessionId: () => 'durable-confirm' } } as unknown as ExtensionContext;
  const delivered: string[] = [];
  const pi = {
    on: (event: string, handler: (event: unknown, ctx: ExtensionContext) => Promise<void>) => hooks.set(event, handler),
    registerCommand: (name: string, spec: unknown) => commands.set(name, spec as never),
    getSessionName: () => 'confirm-target',
    sendUserMessage: (message: string) => {
      delivered.push(message);
      setTimeout(() => void hooks.get('before_agent_start')?.({ prompt: message }, sessionCtx), 50);
    },
    getActiveTools: () => [],
    setActiveTools: () => {},
  } as unknown as ExtensionAPI;
  try {
    registerLiveSessions(pi);
    await hooks.get('session_start')!({}, sessionCtx);
    const target = (await execute({ version: 1, requestId: 'list', command: 'list' }, directory)).sessions![0].sessionId;
    await commands.get('live-sessions')!.handler(`${target} check the failing test`, {
      hasUI: false,
      ui: { notify: (message: string, level: string) => notifications.push({ message, level }), select: async () => undefined },
    } as unknown as ExtensionContext);
    assert.deepEqual(delivered, ['check the failing test']);
    assert.equal(notifications.length, 1);
    assert.match(notifications[0].message, /confirmed the delivery to its own prompt/);
    assert.match(notifications[0].message, /completion is still not claimed/);
    await hooks.get('session_shutdown')?.({}, sessionCtx);
  } finally {
    await hooks.get('session_shutdown')?.({}, sessionCtx);
    if (previous === undefined) delete process.env.PI_UTILS_LIVE_SESSIONS_DIR;
    else process.env.PI_UTILS_LIVE_SESSIONS_DIR = previous;
    await rm(directory, { recursive: true, force: true });
  }
});

test('a broken control directory is reported instead of an empty listing, and startup failures are remembered', async () => {
  const directory = await mkdtemp(join('/tmp', 'psc-broken-'));
  const previous = process.env.PI_UTILS_LIVE_SESSIONS_DIR;
  process.env.PI_UTILS_LIVE_SESSIONS_DIR = directory;
  const hooks = new Map<string, (event: unknown, ctx: ExtensionContext) => Promise<void>>();
  const commands = new Map<string, { handler: (args: string, ctx: ExtensionContext) => Promise<void> }>();
  const ctx = (notifications: { message: string; level: string }[]) =>
    ({ cwd: '/work', isIdle: () => true, sessionManager: { getSessionId: () => 'durable-broken' }, ui: { notify: (message: string, level: string) => notifications.push({ message, level }) } }) as unknown as ExtensionContext;
  try {
    registerLiveSessions(fakePi(hooks, commands as unknown as Map<string, unknown>, []));

    await chmod(directory, 0o755);
    const unsafe: { message: string; level: string }[] = [];
    await commands.get('live-sessions')!.handler('', commandCtx(unsafe));
    assert.equal(unsafe[0].level, 'error');
    assert.match(unsafe[0].message, /Live session discovery failed/);
    assert.match(unsafe[0].message, /0700/);

    process.env.PI_UTILS_LIVE_SESSIONS_DIR = join(directory, 'not-a-directory');
    await writeFile(process.env.PI_UTILS_LIVE_SESSIONS_DIR, 'x');
    const start: { message: string; level: string }[] = [];
    await hooks.get('session_start')!({}, ctx(start));
    assert.equal(start[0].level, 'warning');
    assert.match(start[0].message, /Live session control is unavailable/);
    const after: { message: string; level: string }[] = [];
    await commands.get('live-sessions')!.handler('', commandCtx(after));
    assert.equal(after[0].level, 'error');
    await hooks.get('session_shutdown')?.({}, ctx([]));
  } finally {
    if (previous === undefined) delete process.env.PI_UTILS_LIVE_SESSIONS_DIR;
    else process.env.PI_UTILS_LIVE_SESSIONS_DIR = previous;
    await rm(directory, { recursive: true, force: true });
  }

  const base = await mkdtemp(join('/tmp', 'psc-long-'));
  const longDir = join(base, 'long-directory-'.repeat(4));
  await mkdir(longDir, { recursive: true, mode: 0o700 });
  process.env.PI_UTILS_LIVE_SESSIONS_DIR = longDir;
  const hooks2 = new Map<string, (event: unknown, ctx: ExtensionContext) => Promise<void>>();
  const commands2 = new Map<string, { handler: (args: string, ctx: ExtensionContext) => Promise<void> }>();
  try {
    registerLiveSessions(fakePi(hooks2, commands2 as unknown as Map<string, unknown>, []));
    const start: { message: string; level: string }[] = [];
    await hooks2.get('session_start')!({}, ctx(start));
    assert.equal(start[0].level, 'warning');
    assert.match(start[0].message, /unavailable/);
    const listed: { message: string; level: string }[] = [];
    await commands2.get('live-sessions')!.handler('', commandCtx(listed));
    assert.equal(listed.length, 1);
    assert.equal(listed[0].level, 'warning');
    assert.match(listed[0].message, /unavailable in this session/);
    assert.ok(!listed.some((entry) => /No live Pi sessions found/.test(entry.message)));
    await hooks2.get('session_shutdown')?.({}, ctx([]));
  } finally {
    if (previous === undefined) delete process.env.PI_UTILS_LIVE_SESSIONS_DIR;
    else process.env.PI_UTILS_LIVE_SESSIONS_DIR = previous;
    await rm(base, { recursive: true, force: true });
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
