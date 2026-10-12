/** Offline native command reproduction: every external request is forbidden. */
import fs from 'node:fs';
import type { ExtensionAPI } from '@earendil-works/pi-coding-agent';
import registerMemory from '../extensions/inject-memory.ts';

export default function(pi: ExtensionAPI): void {
  const events = process.env.CL_PRIVATE_CONSENT_EVENTS;
  if (!events || !process.env.PI_OFFLINE) throw new Error('Isolated offline consent fixture required');
  const log = (row: unknown) => fs.appendFileSync(events, JSON.stringify(row)+'\n');
  globalThis.fetch = async () => { log({kind:'forbidden-network'}); throw new Error('External requests forbidden in consent fixture'); };
  pi.registerProvider('private-consent-fixture', {
    api: 'private-consent-fixture', baseUrl: 'http://127.0.0.1', apiKey: 'offline-fixture-only',
    models: [{id: 'deterministic', name: 'Offline consent fixture', reasoning: false, input: ['text'],
      contextWindow: 200000, maxTokens: 4096, cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0}}],
    streamSimple() { log({kind:'forbidden-model'}); throw new Error('No model call is allowed before consent'); },
  });
  registerMemory({...pi, sendMessage(message, options) {
    if (message.customType === 'continual-learning-result') log({kind:'receipt',receipt:message.details});
    return pi.sendMessage(message, options);
  }});
  pi.on('session_start', (_event, ctx) => {
    const confirm = ctx.ui.confirm.bind(ctx.ui);
    ctx.ui.confirm = async (...args) => {
      log({kind:'confirm',title:args[0],body:args[1]});
      const accepted = await confirm(...args);
      log({kind:'confirmed',accepted});
      return accepted;
    };
    log({kind:'ready'});
  });
}
