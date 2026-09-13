// Modified for @fradser/pi-impeccable: locally authored bounded HTTP body reader.
export const MAX_JSON_BODY_BYTES = 1024 * 1024;

/** Read live JSON text without retaining an oversized or aborted request. */
export function readLiveRequestBody(req, res, onBody) {
  const chunks = [];
  let size = 0;
  let finished = false;
  const discard = () => {
    finished = true;
    chunks.length = 0;
  };
  req.on('data', (chunk) => {
    if (finished) return;
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += bytes.length;
    if (size > MAX_JSON_BODY_BYTES) {
      discard();
      res.writeHead(413, { 'Content-Type': 'application/json', Connection: 'close' });
      res.end(JSON.stringify({ error: 'Payload too large', maxBytes: MAX_JSON_BODY_BYTES }));
      return;
    }
    chunks.push(bytes);
  });
  req.once('end', () => {
    if (finished) return;
    const body = Buffer.concat(chunks, size).toString('utf8');
    discard();
    onBody(body);
  });
  req.once('aborted', discard);
  req.once('error', () => {
    if (finished) return;
    discard();
    if (!res.destroyed) {
      res.writeHead(400, { 'Content-Type': 'application/json', Connection: 'close' });
      res.end(JSON.stringify({ error: 'Request body could not be read' }));
    }
  });
}
