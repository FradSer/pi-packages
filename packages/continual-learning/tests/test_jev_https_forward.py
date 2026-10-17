from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import ssl
import subprocess
import threading
import time

import pytest


@pytest.fixture(scope='module')
def tls_certificates(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp('jev-local-tls')

    def openssl(*args: str) -> None:
        subprocess.run(['openssl', *args], cwd=root, check=True, capture_output=True)

    openssl('req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1',
            '-nodes', '-days', '1', '-subj', '/CN=isolated-fixture-root',
            '-keyout', 'ca.key', '-out', 'ca.pem')
    for name, hostname in [('valid', 'api.typesafe.ai'), ('wrong', 'wrong.example.invalid')]:
        openssl('req', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1',
                '-nodes', '-subj', f'/CN={hostname}', '-keyout', f'{name}.key', '-out', f'{name}.csr')
        (root / f'{name}.ext').write_text(f'subjectAltName=DNS:{hostname}\n')
        openssl('x509', '-req', '-in', f'{name}.csr', '-CA', 'ca.pem', '-CAkey', 'ca.key',
                '-CAcreateserial', '-days', '1', '-extfile', f'{name}.ext', '-out', f'{name}.pem')
    for file in root.iterdir():
        file.chmod(0o600)
    return root


@pytest.mark.parametrize('case', ['valid', 'valid-1.14', 'foreign-version', 'valid-long-context', 'wrong-hostname', 'untrusted-issuer', 'redirect', 'oversized', 'hanging-body'])
def test_actual_node_tls_preserves_origin_and_rejects_unsafe_peers(tls_certificates: Path, case: str) -> None:
    # Given an isolated TLS peer and an original hostname resolved to loopback,
    # When the actual Node transport connects, Then only a trusted matching peer
    # receives one unchanged body. No retry, redirect or hostname bypass follows.
    release = threading.Event()
    observed: list[dict] = []
    server_names: list[str] = []
    requested_model = 'jev-1.14.0' if case in ('valid-1.14','foreign-version') else 'jev-1.13.0'
    expected_model = 'jev-1.14.0' if case == 'valid-1.14' else 'jev-1.13.0'
    body = json.dumps({'model': requested_model, 'state': 'complete public fixture\n' + 'x' * 90000,
                       'questions': {}}, ensure_ascii=False)

    class Peer(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_POST(self) -> None:
            received = self.rfile.read(int(self.headers['Content-Length'])).decode()
            observed.append({'body': received, 'host': self.headers.get('Host'), 'path': self.path, 'longContext': self.headers.get('TypeSafe-Danger-Zone-Long-Context')})
            self.send_response(307 if case == 'redirect' else 200)
            if case == 'redirect':
                self.send_header('Location', 'https://never-follow.example.invalid/private')
            self.end_headers()
            if case == 'hanging-body':
                self.wfile.flush()
                release.wait(35)
                return
            try:
                self.wfile.write(b'x' * (2 * 1024 * 1024 + 1) if case == 'oversized' else b'{"answers":{}}')
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Peer)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    leaf = 'wrong' if case == 'wrong-hostname' else 'valid'
    context.load_cert_chain(tls_certificates / f'{leaf}.pem', tls_certificates / f'{leaf}.key')
    context.set_servername_callback(lambda _socket, hostname, _context: server_names.append(hostname))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    script = Path(__file__).with_name('jev-https-forward.mjs').resolve().as_uri()
    code = f'''
      import https from 'node:https'; import {{forwardJev}} from {json.dumps(script)};
      const chunks=[];for await(const c of process.stdin)chunks.push(c);
      const calls=[];
      const result=await forwardJev(Buffer.concat(chunks).toString(),{{model:{json.dumps(expected_model)},key:'LOCAL_ONLY_FIXTURE',address:'127.0.0.1',longContext:{str(case == 'valid-long-context').lower()}}},(url,options,callback)=>{{
        calls.push({{url,rejectUnauthorized:options.rejectUnauthorized,agent:options.agent,deadline:options.signal instanceof AbortSignal}});
        return https.request(url,{{...options,port:{server.server_address[1]}}},callback);
      }});
      process.stdout.write(JSON.stringify({{result,calls}}));
    '''
    # This fixture's temporary CA never enters the production forwarder's
    # controlled environment. No actual Typesafe or model request is made.
    env = {key: value for key, value in os.environ.items() if key in ('PATH', 'HOME')}
    if case != 'untrusted-issuer':
        env['NODE_EXTRA_CA_CERTS'] = str(tls_certificates / 'ca.pem')
    try:
        started = time.monotonic()
        completed = subprocess.run(['node', '--input-type=module', '-e', code], input=body,
                                   text=True, capture_output=True, check=True, env=env, timeout=35 if case == 'hanging-body' else 10)
        value = json.loads(completed.stdout)
        if case == 'foreign-version':
            assert value == {'result': {'transportFailure':'invalid-request'}, 'calls':[]}
            assert not observed and not server_names
            return
        assert value['calls'] == [{'url': 'https://api.typesafe.ai/v1/systemone',
                                   'rejectUnauthorized': True, 'agent': False, 'deadline': True}]
        assert server_names == ['api.typesafe.ai']
        assert 'LOCAL_ONLY_FIXTURE' not in completed.stdout + completed.stderr
        if case in ('wrong-hostname', 'untrusted-issuer'):
            assert not observed
            assert value['result']['transportObservation'] == {
                'tcpConnected': True, 'tlsVerified': False, 'responseHeaders': False,
                'receivedBytes': 0, 'ownAbort': False}
            assert value['result']['transportFailure'] == 'tls-certificate-verification-failed'
            if case == 'wrong-hostname':
                assert value['result']['failureCode'] == 'ERR_TLS_CERT_ALTNAME_INVALID'
            else:
                assert value['result']['failureCode'] in ('UNABLE_TO_VERIFY_LEAF_SIGNATURE', 'UNABLE_TO_GET_ISSUER_CERT_LOCALLY')
        else:
            assert observed == [{'body': body, 'host': 'api.typesafe.ai', 'path': '/v1/systemone', 'longContext':'true' if case=='valid-long-context' else None}]
            if case == 'hanging-body':
                assert value['result']['transportFailure'] == 'request-timeout'
                assert value['result']['transportObservation']['ownAbort'] is True
                assert value['result']['transportObservation']['tlsVerified'] is True
                assert value['result']['transportObservation']['responseHeaders'] is True
                assert 29 <= time.monotonic() - started < 35
            elif case in ('valid','valid-1.14','valid-long-context'):
                assert value['result'] == {'status': 200, 'body': '{"answers":{}}',
                    'transportObservation': {'tcpConnected': True, 'tlsVerified': True,
                        'responseHeaders': True, 'receivedBytes': 14, 'ownAbort': False}}
            else:
                assert value['result']['transportFailure'] == ('redirect-not-allowed' if case == 'redirect' else 'response-too-large')
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
