import { lstat, mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { homedir } from 'node:os';
import { createConnection, type Socket } from 'node:net';
import { MAX_BYTES, TIMEOUT_MS, type Response, type Request } from './protocol.ts';

export function controlDirectory(): string {
  return process.env.PI_UTILS_LIVE_SESSIONS_DIR ?? join(homedir(), '.pi', 'live-sessions');
}
export async function checkDirectory(directory: string, create = false): Promise<void> {
  if (create) await mkdir(directory, { recursive: true, mode: 0o700 });
  const info = await lstat(directory);
  if (!info.isDirectory() || info.isSymbolicLink() || info.uid !== process.getuid?.() || (info.mode & 0o077) !== 0) {
    throw new Error('unsafe_directory');
  }
}
export function readFrame(socket: Socket): Promise<string> {
  return new Promise((resolve, reject) => {
    let buffer = Buffer.alloc(0);
    const timer = setTimeout(() => finish(new Error('timeout')), TIMEOUT_MS);
    const finish = (error?: Error, line?: string) => {
      clearTimeout(timer);
      socket.off('data', onData);
      socket.off('error', onError);
      socket.off('end', onEnd);
      socket.off('close', onEnd);
      if (error) reject(error); else resolve(line!);
    };
    const onError = (error: Error) => finish(error);
    const onEnd = () => finish(new Error('incomplete_frame'));
    const onData = (chunk: Buffer) => {
      buffer = Buffer.concat([buffer, chunk]);
      if (buffer.length > MAX_BYTES) return finish(new Error('frame_too_large'));
      const end = buffer.indexOf(10);
      if (end !== -1) finish(undefined, buffer.subarray(0, end).toString('utf8'));
    };
    socket.on('data', onData).once('error', onError).once('end', onEnd).once('close', onEnd);
  });
}
export async function exchange(path: string, request: Request): Promise<Response> {
  const info = await lstat(path);
  if (!info.isSocket() || info.uid !== process.getuid?.() || (info.mode & 0o077)) throw new Error('unsafe_socket');
  const socket = createConnection(path);
  try {
    const reply = readFrame(socket);
    socket.once('connect', () => socket.write(JSON.stringify(request) + '\n'));
    const response = JSON.parse(await reply) as Response;
    if (response.version !== 1 || response.requestId !== request.requestId || typeof response.ok !== 'boolean') throw new Error('invalid_response');
    return response;
  } finally {
    socket.destroy();
  }
}
