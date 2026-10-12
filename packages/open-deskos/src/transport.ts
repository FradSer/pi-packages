import { connect, type Socket } from "node:net";
import { ODK_LINK_PROTOCOL, type OdkLinkConfig, type OdkLinkRecord } from "./types.ts";

const MAX_INBOUND_FRAME_BYTES = 1024 * 1024;

/**
 * A Open DeskOS Link transport. The reporter never touches a socket directly, so the
 * wire contract is testable without a network.
 */
export interface DeskTransport {
  send(record: OdkLinkRecord): void;
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

/** The real Open DeskOS Link: one outbound TCP connection with newline-delimited JSON. */
export function createTcpTransport(config: OdkLinkConfig, options: { connectTimeoutMs?: number } = {}): DeskTransport {
  const openHandlers: Array<() => void> = [];
  const closeHandlers: Array<(reason: string) => void> = [];
  const recordHandlers: Array<(record: unknown) => void> = [];
  let remainder = "";
  let closed = false;

  const socket: Socket = connect({ host: config.host, port: config.port });
  socket.setKeepAlive(true, 15000);
  socket.setNoDelay(true);
  // Node's stream decoder retains incomplete UTF-8 code points across packets.
  socket.setEncoding("utf8");
  socket.setTimeout(options.connectTimeoutMs ?? 10000);

  const announceClose = (reason: string): void => {
    if (closed) return;
    closed = true;
    for (const handler of closeHandlers) handler(reason);
  };

  socket.on("connect", () => {
    if (closed) return;
    socket.setTimeout(0);
    for (const handler of openHandlers) handler();
  });
  socket.on("timeout", () => {
    announceClose("connection timeout");
    socket.destroy();
  });
  socket.on("data", (chunk: string) => {
    if (closed) return;
    const text = remainder + chunk;
    const lines = text.split("\n");
    // Never discard a prefix and parse the suffix as an independent record.
    if (lines.some((line) => Buffer.byteLength(line) + 1 > MAX_INBOUND_FRAME_BYTES)) {
      announceClose("inbound record exceeds 1 MiB frame limit");
      socket.destroy();
      return;
    }
    const parsed = parseRecords(chunk, remainder);
    remainder = parsed.pending;
    for (const record of parsed.records) for (const handler of recordHandlers) handler(record);
  });
  socket.on("error", (error: Error) => {
    announceClose(error.message);
    socket.destroy();
  });
  socket.on("close", () => announceClose("link closed"));

  return {
    send(record: OdkLinkRecord) {
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

export const ODK_LINK_PROTOCOL_DECLARATION = ODK_LINK_PROTOCOL;
