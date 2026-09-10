import type { ExtensionAPI } from '@earendil-works/pi-coding-agent';
import { randomUUID } from 'node:crypto';
import { startServer } from './src/server.ts';
import { controlDirectory } from './src/transport.ts';

export default function sessionControl(pi: ExtensionAPI): void {
  let server: Awaited<ReturnType<typeof startServer>> | undefined;
  pi.on('session_start', async (_event, ctx) => {
    await server?.close();
    const sessionId = randomUUID();
    const piSessionId = ctx.sessionManager.getSessionId();
    server = await startServer(controlDirectory(), sessionId, () => ({
      sessionId, piSessionId, cwd: ctx.cwd, pid: process.pid,
      name: pi.getSessionName()?.slice(0, 256),
      state: ctx.isIdle() ? 'idle' : 'running',
    }), (text, deliverAs) => {
      if (ctx.sessionManager.getSessionId() !== piSessionId) throw new Error('Session changed');
      pi.sendUserMessage(text, { deliverAs });
    });
  });
  pi.on('session_shutdown', async () => {
    const previous = server;
    server = undefined;
    await previous?.close();
  });
}
