import https from 'node:https';
import {pathToFileURL} from 'node:url';

const ORIGIN = 'api.typesafe.ai';
const MAX_RESPONSE_BYTES = 2 * 1024 * 1024;
const FAILURES = {
  ETIMEDOUT: 'connection-timeout', ECONNRESET: 'connection-reset',
  ECONNREFUSED: 'connection-refused', ENOTFOUND: 'dns-failure', EAI_AGAIN: 'dns-failure',
  CERT_HAS_EXPIRED: 'tls-certificate-verification-failed',
  ERR_TLS_CERT_ALTNAME_INVALID: 'tls-certificate-verification-failed',
  UNABLE_TO_VERIFY_LEAF_SIGNATURE: 'tls-certificate-verification-failed',
  UNABLE_TO_GET_ISSUER_CERT_LOCALLY: 'tls-certificate-verification-failed',
  SELF_SIGNED_CERT_IN_CHAIN: 'tls-certificate-verification-failed',
  DEPTH_ZERO_SELF_SIGNED_CERT: 'tls-certificate-verification-failed',
};

// Host-only study transport, not a change to the production SDK. A resolved
// address changes lookup only; URL, SNI, hostname verification and Host agree.
// request injection lets local TLS fixtures exercise that identical contract.
export async function forwardJev(body, {key, address, longContext = false, model = 'jev-1.13.0'}, request = https.request) {
  let input;
  try { input = JSON.parse(body); } catch { return {transportFailure: 'invalid-request'}; }
  if (!['jev-1.13.0', 'jev-1.14.0'].includes(model) || input?.model !== model || !key
    || address && !/^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$/.test(address)) {
    return {transportFailure: 'invalid-request'};
  }
  return new Promise(resolve => {
    let settled = false;
    const signal = AbortSignal.timeout(30_000);
    const observation = {tcpConnected: false, tlsVerified: false,
      responseHeaders: false, receivedBytes: 0, ownAbort: false};
    const onAbort = () => { observation.ownAbort = true; };
    signal.addEventListener('abort', onAbort, {once: true});
    const finish = value => {
      if (!settled) {
        settled = true;
        signal.removeEventListener('abort', onAbort);
        resolve({...value, transportObservation: {...observation}});
      }
    };
    const failure = error => {
      const code = Object.hasOwn(FAILURES, error?.code) ? error.code : undefined;
      finish({transportFailure: code ? FAILURES[code]
        : error?.name === 'AbortError' ? 'request-timeout' : 'transport-unavailable',
        ...(code ? {failureCode: code} : {})});
    };
    try {
      const req = request(`https://${ORIGIN}/v1/systemone`, {
        method: 'POST', agent: false, rejectUnauthorized: true,
        signal,
        ...(address ? {lookup(hostname, options, callback) {
          if (hostname !== ORIGIN) return callback(Object.assign(new Error('Invalid origin'), {code: 'ENOTFOUND'}));
          if (options?.all) callback(null, [{address, family: 4}]);
          else callback(null, address, 4);
        }} : {}),
        headers: {Host: ORIGIN, Authorization: `Bearer ${key}`,
          'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body),
          ...(longContext === true ? {'TypeSafe-Danger-Zone-Long-Context': 'true'} : {})},
      }, res => {
        observation.responseHeaders = true;
        if (res.statusCode >= 300 && res.statusCode < 400) {
          finish({transportFailure: 'redirect-not-allowed'}); res.destroy(); return;
        }
        const chunks = []; let bytes = 0;
        res.on('data', chunk => {
          bytes += chunk.length;
          observation.receivedBytes = bytes;
          if (bytes > MAX_RESPONSE_BYTES) {
            finish({transportFailure: 'response-too-large'}); res.destroy(); return;
          }
          chunks.push(chunk);
        });
        res.on('error', failure);
        res.on('end', () => finish({status: res.statusCode, body: Buffer.concat(chunks).toString('utf8')}));
      });
      req.on('socket', socket => {
        socket.once('connect', () => { observation.tcpConnected = true; });
        socket.once('secureConnect', () => { observation.tlsVerified = socket.authorized === true; });
      });
      req.on('error', failure);
      req.end(body);
    } catch (error) { failure(error); }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  const result = await forwardJev(Buffer.concat(chunks).toString('utf8'), {
    key: process.env.TYPESAFE_API_KEY, address: process.env.JEV_RESOLVED_ADDRESS,
    model: process.env.JEV_MODEL ?? 'jev-1.13.0',
    longContext: process.env.JEV_LONG_CONTEXT === 'true',
  });
  process.stdout.write(JSON.stringify(result));
}
