// Host-only transparent JSON transport. Keys never enter Docker or argv.
const body = await Bun.stdin.text();
if (Buffer.byteLength(body) > 64000 || JSON.parse(body).model !== 'jev-1.13.0'
  || !process.env.TYPESAFE_API_KEY) throw new Error('Invalid Jev forwarding request');
let response;
let text;
try {
  response = await fetch('https://api.typesafe.ai/v1/systemone', {
    method: 'POST', body, redirect: 'error',
    headers: {Authorization: `Bearer ${process.env.TYPESAFE_API_KEY}`, 'Content-Type': 'application/json'},
    signal: AbortSignal.timeout(30000),
  });
  text = await response.text();
} catch (error) {
  // Error messages may contain credentials or request data. Emit fixed categories only.
  const categories = {
    ETIMEDOUT: 'connection-timeout', ECONNRESET: 'connection-reset',
    ConnectionClosed: 'connection-closed', ConnectionRefused: 'connection-refused',
    ECONNREFUSED: 'connection-refused', ENOTFOUND: 'dns-failure', EAI_AGAIN: 'dns-failure',
  };
  const category = Object.hasOwn(categories, error?.code) ? categories[error.code]
    : error?.name === 'TimeoutError' ? 'request-timeout'
    : error?.name === 'AbortError' ? 'aborted' : 'transport-unavailable';
  process.stdout.write(JSON.stringify({transportFailure: category}));
  process.exit(0);
}
if (Buffer.byteLength(text) > 2 * 1024 * 1024) throw new Error('Jev response exceeds transport bound');
process.stdout.write(JSON.stringify({status: response.status, body: text}));
