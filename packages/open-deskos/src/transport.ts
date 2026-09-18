import { connect, type Socket } from "node:net";
import { DESK_LINK_PROTOCOL, type DeskLinkConfig, type DeskLinkRecord } from "./types.ts";

/**
 * A Desk Link transport. The reporter never touches a socket directly, so the
 * wire contract is testable without a network.
 */
export interface DeskTransport {
  send(record: DeskLinkRecord): void;
  close(): void;
  onOpen(handler: () => void): void;
  onClose(handler: (reason: string) => void): void;
  onRecord(handler: (record: unknown) => void): void;
}

/** Split newline-delimited records on LF only, tolerating a trailing CR. */
export function parseRecords(chunk: string, remainder: string): { records: unknown[]; pending: string } {
  const text = `${remainder}${chunk}`;
  const lines = text.split("\n");
  const pending = lines.pop() ?? "";
  const records: unknown[] = [];
  for (const line of lines) {
    const trimmed = line.endsWith("\r") ? line.slice(0, -1) : line;
    if (trimmed.length === 0) continue;
    try {
      records.push(JSON.parse(trimmed));
    } catch {
      /* a malformed record is ignored, never fatal to the link */
    }
  }
  return { records, pending };
}

/** The real Desk Link: one outbound TCP connection with newline-delimited JSON. */
export function createTcpTransport(config: DeskLinkConfig): DeskTransport {
  const openHandlers: Array<() => void> = [];
  const closeHandlers: Array<(reason: string) => void> = [];
  const recordHandlers: Array<(record: unknown) => void> = [];
  let remainder = "";
  let closed = false;

  const socket: Socket = connect({ host: config.host, port: config.port });
  socket.setKeepAlive(true, 15000);
  socket.setNoDelay(true);

  const announceClose = (reason: string): void => {
    if (closed) return;
    closed = true;
    for (const handler of closeHandlers) handler(reason);
  };

  socket.on("connect", () => {
    for (const handler of openHandlers) handler();
  });
  socket.on("data", (chunk: Buffer) => {
    const parsed = parseRecords(chunk.toString("utf8"), remainder);
    remainder = parsed.pending.length > 4096 ? "" : parsed.pending;
    for (const record of parsed.records) for (const handler of recordHandlers) handler(record);
  });
  socket.on("error", (error: Error) => announceClose(error.message));
  socket.on("close", () => announceClose("link closed"));

  return {
    send(record: DeskLinkRecord) {
      if (closed || socket.destroyed) return;
      socket.write(`${JSON.stringify(record)}\n`);
    },
    close() {
      if (closed) return;
      closed = true;
      socket.end();
      socket.destroy();
    },
    onOpen(handler) {
      openHandlers.push(handler);
    },
    onClose(handler) {
      closeHandlers.push(handler);
    },
    onRecord(handler) {
      recordHandlers.push(handler);
    },
  };
}

export const DESK_LINK_PROTOCOL_DECLARATION = DESK_LINK_PROTOCOL;
