export const MAX_BYTES = 65536;
export const TIMEOUT_MS = 2000;
export interface Request {
  version: 1;
  requestId: string;
  command: 'list' | 'status' | 'send';
  sessionId?: string;
  text?: string;
  deliverAs?: 'steer' | 'followUp';
}
export interface Session {
  sessionId: string;
  cwd: string;
  pid: number;
  state: string;
  name?: string;
  piSessionId?: string;
}
export interface Response {
  version: 1;
  requestId: string | null;
  ok: boolean;
  sessions?: Session[];
  session?: Session;
  sessionId?: string;
  status?: 'accepted' | 'queued';
  error?: { code: string; message: string };
}
export function failure(requestId: string | null, code: string, message: string): Response {
  return { version: 1, requestId, ok: false, error: { code, message } };
}
export function parseRequest(value: unknown): Request {
  if (!value || typeof value !== 'object') throw new Error('Expected a JSON object');
  const r = value as Record<string, unknown>;
  if (r.version !== 1 || typeof r.requestId !== 'string' || !/^[\w.-]{1,128}$/.test(r.requestId)) throw new Error('Invalid version or requestId');
  const { command, sessionId, text, deliverAs } = r;
  if (command !== 'list' && command !== 'status' && command !== 'send') throw new Error('Unknown command');
  if (deliverAs !== undefined && deliverAs !== 'steer' && deliverAs !== 'followUp') throw new Error('Invalid deliverAs');
  const base: Request = { version: 1, requestId: r.requestId, command };
  if (command === 'list') return base;
  if (typeof sessionId !== 'string' || !/^[\w.-]{1,128}$/.test(sessionId)) throw new Error('Invalid sessionId');
  if (command === 'status') return { ...base, sessionId };
  if (typeof text !== 'string' || !text.trim() || Buffer.byteLength(text) > 48000) throw new Error('Text must contain 1–48000 bytes');
  return { ...base, sessionId, text, ...(deliverAs === undefined ? {} : { deliverAs }) };
}
