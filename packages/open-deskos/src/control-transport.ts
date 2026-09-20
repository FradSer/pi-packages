import { connect, type Socket } from "node:net";
import { StringDecoder } from "node:string_decoder";
import type { DeskLinkConfig } from "./types.ts";

export const DESK_LINK_CONTROL_PROTOCOL = 2;
export const MAX_CONTROL_RECORD_BYTES = 1024 * 1024;

export interface ControlTransport {
  send(record: Record<string, unknown>): void;
  close(): void;
  onOpen(handler: () => void): void;
  onClose(handler: (reason: string) => void): void;
  onRecord(handler: (record: unknown) => void): void;
}

/** Bounded LF-only NDJSON reader that discards one oversized line and resumes. */
export function createControlRecordReader(maxBytes = MAX_CONTROL_RECORD_BYTES): (chunk: Buffer | string) => unknown[] {
  const decoder = new StringDecoder("utf8");
  let pending = "";
  let dropping = false;
  return (chunk) => {
    let text = typeof chunk === "string" ? chunk : decoder.write(chunk);
    const records: unknown[] = [];
    while (text.length > 0) {
      if (dropping) {
        const newline = text.indexOf("\n");
        if (newline < 0) return records;
        text = text.slice(newline + 1);
        dropping = false;
        continue;
      }
      const newline = text.indexOf("\n");
      if (newline < 0) {
        pending += text;
        if (Buffer.byteLength(pending) > maxBytes) {
          pending = "";
          dropping = true;
        }
        return records;
      }
      const line = `${pending}${text.slice(0, newline)}`.replace(/\r$/, "");
      pending = "";
      text = text.slice(newline + 1);
      if (line.length === 0 || Buffer.byteLength(line) > maxBytes) continue;
      try {
        records.push(JSON.parse(line));
      } catch {
        // A malformed control record is isolated to its line.
      }
    }
    return records;
  };
}

export function createControlTcpTransport(config: DeskLinkConfig): ControlTransport {
  const openHandlers: Array<() => void> = [];
  const closeHandlers: Array<(reason: string) => void> = [];
  const recordHandlers: Array<(record: unknown) => void> = [];
  const readRecords = createControlRecordReader();
  let closed = false;
  let opened = false;
  const socket: Socket = connect({ host: config.host, port: config.port });
  socket.setKeepAlive(true, 15000);
  socket.setNoDelay(true);

  const announceClose = (reason: string): void => {
    if (closed) return;
    closed = true;
    for (const handler of closeHandlers) handler(reason);
  };
  socket.on("connect", () => {
    opened = true;
    for (const handler of openHandlers) handler();
  });
  socket.on("data", (chunk: Buffer) => {
    for (const record of readRecords(chunk)) for (const handler of recordHandlers) handler(record);
  });
  socket.on("error", (error: Error) => announceClose(error.message));
  socket.on("close", () => announceClose("control link closed"));

  return {
    send(record) {
      if (closed || socket.destroyed) return;
      const line = `${JSON.stringify(record)}\n`;
      if (Buffer.byteLength(line) > MAX_CONTROL_RECORD_BYTES) throw new Error("control record exceeds 1 MiB");
      socket.write(line);
    },
    close() {
      if (closed) return;
      closed = true;
      socket.end();
      socket.destroy();
    },
    onOpen(handler) {
      openHandlers.push(handler);
      if (opened && !closed) queueMicrotask(handler);
    },
    onClose(handler) { closeHandlers.push(handler); },
    onRecord(handler) { recordHandlers.push(handler); },
  };
}
