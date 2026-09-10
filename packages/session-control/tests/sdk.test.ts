import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, rm } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { spawn } from 'node:child_process';
import { createAgentSession, DefaultResourceLoader, SessionManager, SettingsManager, ModelRuntime } from '@earendil-works/pi-coding-agent';
import sessionControl from '../index.ts';
import type { Response } from '../src/protocol.ts';

async function cli(directory: string, request: object): Promise<Response> {
  const child = spawn(process.execPath, [resolve('packages/session-control/bin/pi-session-control.mjs')], {
    env: { ...process.env, PI_SESSION_CONTROL_DIR: directory },
  });
  let output = '';
  child.stdout.on('data', (chunk) => { output += chunk; });
  child.stdin.end(JSON.stringify(request) + '\n');
  await new Promise<void>((done, reject) => {
    child.once('error', reject);
    child.once('close', (code) => code === 0 ? done() : reject(new Error(`CLI exited ${code}`)));
  });
  return JSON.parse(output);
}

test('real SDK receives literal CLI socket delivery with no model invocation', async () => {
  const directory = await mkdtemp('/tmp/psc-sdk-');
  const socketDirectory = join(directory, 's');
  const previous = process.env.PI_SESSION_CONTROL_DIR;
  process.env.PI_SESSION_CONTROL_DIR = socketDirectory;
  const inputs: { text: string; source: string }[] = [];
  const settingsManager = SettingsManager.inMemory();
  const loader = new DefaultResourceLoader({ cwd: directory, agentDir: directory, settingsManager,
    noExtensions: true, noSkills: true, noPromptTemplates: true, noThemes: true,
    agentsFilesOverride: () => ({ agentsFiles: [] }),
    extensionFactories: [sessionControl, (pi) => {
      pi.on('input', (event) => { inputs.push({ text: event.text, source: event.source }); return { action: 'handled' }; });
    }],
  });
  await loader.reload();
  const modelRuntime = await ModelRuntime.create({ authPath: join(directory, 'auth.json'), modelsPath: join(directory, 'models.json'), allowModelNetwork: false });
  const { session } = await createAgentSession({ cwd: directory, agentDir: directory, resourceLoader: loader,
    modelRuntime, settingsManager, sessionManager: SessionManager.inMemory(directory), tools: [] });
  try {
    await session.bindExtensions({ mode: 'print' });
    const listed = await cli(socketDirectory, { version: 1, requestId: 'list', command: 'list' });
    assert.equal(listed.sessions?.length, 1);
    const request = { version: 1, requestId: 'send', command: 'send', sessionId: listed.sessions![0].sessionId, text: '/literal $HOME; echo not-a-shell' };
    assert.equal((await cli(socketDirectory, request)).status, 'accepted');
    assert.deepEqual(inputs, [{ text: request.text, source: 'extension' }]);
    assert.equal((await cli(socketDirectory, request)).status, 'accepted');
    assert.equal(inputs.length, 1);
    assert.equal(session.messages.length, 0);
  } finally {
    await session.extensionRunner.emit({ type: 'session_shutdown', reason: 'quit' });
    session.dispose();
    if (previous === undefined) delete process.env.PI_SESSION_CONTROL_DIR;
    else process.env.PI_SESSION_CONTROL_DIR = previous;
    await rm(directory, { recursive: true, force: true });
  }
});
