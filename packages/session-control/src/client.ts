import { readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { checkDirectory, controlDirectory, exchange } from './transport.ts';
import { failure, parseRequest, type Response } from './protocol.ts';

export async function execute(value: unknown, directory = controlDirectory()): Promise<Response> {
  let request;
  try { request = parseRequest(value); }
  catch { return failure(null, 'invalid_request', 'Invalid version, command, requestId, target, or text'); }
  const { requestId } = request;
  try { await checkDirectory(directory); }
  catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
      return request.command === 'list' ? { version: 1, requestId, ok: true, sessions: [] } : failure(requestId, 'not_found', 'No live session at this target');
    }
    return failure(requestId, 'unsafe_directory', 'Control directory must be owned by this user with mode 0700');
  }
  if (request.command !== 'list') {
    try { return await exchange(join(directory, `${request.sessionId}.sock`), request); }
    catch { return failure(requestId, 'not_found', 'Target unavailable; delivery outcome may be unknown. Retry only the identical requestId and payload'); }
  }
  try {
    const entries = (await readdir(directory)).filter((name) => /^[\w.-]+\.sock$/.test(name));
    if (entries.length > 128) return failure(requestId, 'capacity', 'More than 128 socket entries; remove stale entries while sessions are stopped');
    const replies = await Promise.all(entries.map(async (name) => {
      try {
        const response = await exchange(join(directory, name), { version: 1, requestId, command: 'status', sessionId: name.slice(0, -5) });
        return response.ok && response.session?.sessionId === name.slice(0, -5) ? response.session : undefined;
      } catch { return undefined; }
    }));
    return { version: 1, requestId, ok: true, sessions: replies.filter((session) => session !== undefined) };
  } catch { return failure(requestId, 'discovery_failed', 'Could not enumerate live sessions'); }
}
