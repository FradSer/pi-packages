import importlib.util
import json
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
import urllib.error
import urllib.request

spec = importlib.util.spec_from_file_location('native_jev_proxy', Path(__file__).parent/'native/jev-proxy.py')
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_proxy_keeps_host_credentials_private_enforces_cap_and_strips_provider_text() -> None:
    received: list[str | None] = []

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_args: Any) -> None:
            pass

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers['Content-Length']))
            received.append(self.headers.get('Authorization'))
            raw = json.dumps({'model':'jev-1.13.0','usage':{'input_tokens':10,'output_tokens':3,'extra':'PRIVATE PROVIDER TEXT'},
                'answers':{'supported_0':{'type':'choice','choice':'grounded','confidence':1,'probabilities':{'grounded':1},'extra':'PRIVATE PROVIDER TEXT'}}}).encode()
            self.send_response(200); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)

    upstream = ThreadingHTTPServer(('127.0.0.1',0),Upstream)
    threading.Thread(target=upstream.serve_forever,daemon=True).start()
    proxy = module.BoundedJevProxy('host-only-fixture','gate-fixture',f'http://127.0.0.1:{upstream.server_port}/v1/systemone')
    server = proxy.create_server()
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}/v1/systemone'
    payload = {'model':'jev-1.13.0','state':module.PUBLIC_QUOTES[0],
        'questions':{'supported_0':{'type':'choice','instructions':'fixed','criteria':{'grounded':'grounded'}}}}

    def send(value: dict[str, Any], token: str = 'gate-fixture') -> int:
        try:
            with urllib.request.urlopen(urllib.request.Request(url,data=json.dumps(value).encode(),headers={'Authorization':'Bearer '+token}),timeout=2) as response:
                response.read(); return response.status
        except urllib.error.HTTPError as error:
            error.read(); return error.code

    try:
        assert send(payload,'wrong') == 403
        assert send({**payload,'model':'jev-latest'}) == 400
        assert send({**payload,'state':'not the frozen public evidence'}) == 400
        assert send({**payload,'state':'x'*70000}) == 413
        assert not received and not proxy.rows
        for _ in range(24):
            assert send(payload) == 200
        assert send(payload) == 429
        assert len(received)==24 and set(received)=={'Bearer host-only-fixture'}
        assert proxy.rejected==1
        assert all(row['completed'] for row in proxy.rows)
        logged = json.dumps(proxy.rows)
        assert 'PRIVATE PROVIDER TEXT' not in logged and 'host-only-fixture' not in logged and 'gate-fixture' not in logged
        assert all(row['usage']=={'input_tokens':10,'output_tokens':3} for row in proxy.rows)
    finally:
        server.shutdown(); server.server_close(); upstream.shutdown(); upstream.server_close()


def test_proxy_rejects_provider_redirect_without_forwarding_credentials() -> None:
    destination_hits: list[str | None] = []

    class Destination(BaseHTTPRequestHandler):
        def log_message(self, *_args: Any) -> None:
            pass

        def do_POST(self) -> None:
            destination_hits.append(self.headers.get('Authorization'))
            self.send_response(200); self.end_headers()

        do_GET = do_POST

    destination = ThreadingHTTPServer(('127.0.0.1', 0), Destination)
    threading.Thread(target=destination.serve_forever, daemon=True).start()

    class Redirect(BaseHTTPRequestHandler):
        def log_message(self, *_args: Any) -> None:
            pass

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(302)
            self.send_header('Location', f'http://127.0.0.1:{destination.server_port}/elsewhere')
            self.end_headers()

    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Redirect)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    proxy = module.BoundedJevProxy('host-only-fixture', 'gate-fixture', f'http://127.0.0.1:{upstream.server_port}/v1/systemone')
    server = proxy.create_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    payload = {'model': 'jev-1.13.0', 'state': module.PUBLIC_QUOTES[0],
               'questions': {'supported_0': {'type': 'choice', 'criteria': {'grounded': 'grounded'}}}}
    try:
        try:
            urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{server.server_port}/v1/systemone',
                data=json.dumps(payload).encode(), headers={'Authorization': 'Bearer gate-fixture'}), timeout=2).close()
        except urllib.error.HTTPError:
            pass
        assert not destination_hits
        assert proxy.rows[0]['status'] == 302
        assert proxy.rows[0]['redirectRejected'] is True
    finally:
        server.shutdown(); server.server_close()
        upstream.shutdown(); upstream.server_close()
        destination.shutdown(); destination.server_close()


def test_readiness_is_opt_in_and_rejects_changed_public_material_before_transport() -> None:
    calls: list[int] = []

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_args: Any) -> None:
            pass

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers['Content-Length'])); calls.append(1)
            raw = json.dumps({'model': 'jev-1.13.0', 'usage': {'input_tokens': 10, 'output_tokens': 3},
                'answers': {'ready': {'type': 'choice', 'choice': 'selfContained', 'confidence': 1,
                    'probabilities': {'selfContained': 1, 'needsOther': 0, 'unresolved': 0}}}}).encode()
            self.send_response(200); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)

    facts = ['This project uses pnpm.', 'Cache service is permanently unavailable.', 'Its license is MIT.']
    originals = [{'name': name, 'kind': 'project', 'classification': 'safe',
        'content': f'---\nname: {name[:-3]}\ndescription: {body}\ntype: project\n---\n{body}\n',
        'evidence': [{'index': 0, 'quote': module.PUBLIC_QUOTES[0]}]}
        for name, body in zip(['tools.md', 'cache.md', 'license.md'], facts)]
    state = {'originalEvidence': {'contextEnabled': True, 'entries': [{'role': 'user', 'content': module.PUBLIC_QUOTES[0]}]},
        'originalCandidates': originals, 'target': {'body': facts[0]+'\n', 'description': facts[0]},
        'targetIndex': 0, 'otherNewRecordsAreWritten': False}
    payload = {'model': 'jev-1.13.0', 'state': json.dumps(state),
        'questions': {'ready': {'type': 'choice', 'criteria': {'selfContained': 'yes', 'needsOther': 'no', 'unresolved': 'unknown'}}}}
    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    proxy = module.BoundedJevProxy('host-only-fixture', 'gate-fixture', f'http://127.0.0.1:{upstream.server_port}/v1/systemone', max_requests=2, allow_readiness=True)
    server = proxy.create_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def send(value: dict[str, Any]) -> int:
        try:
            with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{server.server_port}/v1/systemone',
                data=json.dumps(value).encode(), headers={'Authorization': 'Bearer gate-fixture'}), timeout=2) as response:
                response.read(); return response.status
        except urllib.error.HTTPError as error:
            error.read(); return error.code

    try:
        proxy.allow_readiness = False
        assert send(payload) == 400
        proxy.allow_readiness = True
        changed = {**state, 'originalCandidates': [{**originals[0], 'content': 'private modified material'}, *originals[1:]]}
        assert send({**payload, 'state': json.dumps(changed)}) == 400
        assert send({**payload, 'state': json.dumps({**state, 'extra': 'private text'})}) == 400
        wrapped = {'type':'message','message':{'role':'user','content':module.PUBLIC_QUOTES[0]},'content':'PRIVATE_CANARY'}
        changed_evidence = {**state['originalEvidence'],'entries':[wrapped]}
        assert send({**payload,'state':json.dumps({**state,'originalEvidence':changed_evidence})}) == 400
        shadowed = {'type':'message','message':{'role':'user','content':module.PUBLIC_QUOTES[0]},'id':'PRIVATE/CANARY'}
        changed_evidence = {**state['originalEvidence'],'id':'valid','entries':[shadowed]}
        assert send({**payload,'state':json.dumps({**state,'originalEvidence':changed_evidence})}) == 400
        approved_raw = json.dumps(payload)
        duplicate_raw = '{"state":"PRIVATE_CANARY",' + approved_raw[1:]
        try:
            urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{server.server_port}/v1/systemone',
                data=duplicate_raw.encode(), headers={'Authorization':'Bearer gate-fixture'}), timeout=2).close()
            raise AssertionError('Duplicate outer state was accepted')
        except urllib.error.HTTPError as error:
            assert error.code == 400
        proxy.allowed_requests = {module.canonical_request_digest(payload)}
        altered_questions = {'ready':{**payload['questions']['ready'],'instructions':'PRIVATE_CANARY'}}
        assert send({**payload,'questions':altered_questions}) == 400
        assert send({**payload,'extra':'PRIVATE_CANARY'}) == 400
        different_target = {**state,'targetIndex':2,'target':{'body':facts[2]+'\n','description':facts[2]}}
        assert send({**payload,'state':json.dumps(different_target)}) == 400
        assert not calls and not proxy.rows
        assert send(payload) == send(payload) == 200
        assert send(payload) == 429
        assert len(calls) == len(proxy.rows) == 2
    finally:
        server.shutdown(); server.server_close(); upstream.shutdown(); upstream.server_close()


def test_frozen_request_digest_preserves_every_non_generated_field() -> None:
    original = {'model':'jev-1.13.0','questions':{'ready':{'type':'choice','criteria':{'selfContained':'yes'}}},
        'state':json.dumps({'runId':'run_abc_0123456789abcdef','capturedAt':'2026-10-06T00:00:00.000Z','content':'public'})}
    other = {**original,'state':json.dumps({'runId':'run_xyz_abcdef0123456789','capturedAt':'2026-10-07T00:00:00.000Z','content':'public'})}
    assert module.canonical_request_digest(original) == module.canonical_request_digest(other)
    changed = {**other,'state':json.dumps({'runId':'run_xyz_abcdef0123456789','capturedAt':'2026-10-07T00:00:00.000Z','content':'PRIVATE_CANARY'})}
    assert module.canonical_request_digest(original) != module.canonical_request_digest(changed)


def test_duplicate_fields_cannot_hide_material_from_the_request_fingerprint() -> None:
    import pytest
    request = {'model':'jev-1.13.0','questions':{'ready':{'type':'choice','criteria':{'selfContained':'yes'}}},
        'state':'{"content":"PRIVATE_CANARY","content":"public"}'}
    with pytest.raises(ValueError):
        module.canonical_request_digest(request)
