// Host-only transparent JSON transport. Keys never enter Docker or argv.
const body = await Bun.stdin.text();
const model = process.env.JEV_MODEL ?? 'jev-1.13.0';
if (!['jev-1.13.0', 'jev-1.14.0'].includes(model) || JSON.parse(body).model !== model
  || !process.env.TYPESAFE_API_KEY) throw new Error('Invalid Jev forwarding request');
// The host study validates an optional public IPv4 route; origin identity remains fixed.
const address = process.env.JEV_RESOLVED_ADDRESS;
if (address && !/^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$/.test(address)) throw new Error('Invalid Jev route');
let response;
let text;
try {
  response = await fetch(`https://${address || 'api.typesafe.ai'}/v1/systemone`, {
    ...(address ? {proxy: false, tls: {serverName: 'api.typesafe.ai'}} : {}),
    method: 'POST', body, redirect: 'error',
    headers: {...(process.env.JEV_LONG_CONTEXT === 'true' ? {'TypeSafe-Danger-Zone-Long-Context': 'true'} : {}), ...(address ? {Host: 'api.typesafe.ai'} : {}), Authorization: `Bearer ${process.env.TYPESAFE_API_KEY}`, 'Content-Type': 'application/json'},
    signal: AbortSignal.timeout(30000),
  });
  text = await response.text();
} catch (error) {
  // Error messages may contain credentials or request data. Emit fixed categories only.
  const categories = {
    ETIMEDOUT: 'connection-timeout', ECONNRESET: 'connection-reset',
    UNKNOWN_CERTIFICATE_VERIFICATION_ERROR: 'tls-certificate-verification-failed',
    CERT_HAS_EXPIRED: 'tls-certificate-verification-failed',
    ERR_TLS_CERT_ALTNAME_INVALID: 'tls-certificate-verification-failed',
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
