from __future__ import annotations

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import subprocess
from types import SimpleNamespace

import pytest

import docker_experiment
from docker_experiment import InferenceProxy
from live_docker_projects import full_memory_read, invokes_check, learned_block_result


def test_explicit_main_selection_does_not_follow_or_modify_ambient_model(tmp_path: Path) -> None:
    # Given an ambient alternate model, When selecting the requested model,
    # Then temporary agent config uses the requested identity without host edits.
    config = tmp_path / 'host'
    config.mkdir()
    (config / 'memory.json').write_text('{"provider":"cli-proxy","model":"ambient-other"}')
    (config / 'models.json').write_text(json.dumps({'providers': {'cli-proxy': {
        'apiKey': 'HOST_ONLY_FIXTURE', 'baseUrl': 'http://127.0.0.1:1/v1',
        'api': 'openai-completions', 'models': [
            {'id': 'ambient-other', 'maxTokens': 1000},
            {'id': 'opencode/space-bunny-free', 'maxTokens': 2000},
        ],
    }}}))
    before = {p.name: p.read_bytes() for p in config.iterdir()}
    selection = {'provider': 'cli-proxy', 'model': 'opencode/space-bunny-free'}
    with InferenceProxy(config, selection=selection) as proxy:
        assert proxy.selection == selection and proxy.model['id'] == selection['model']
        target = tmp_path / 'temporary-agent'
        proxy.write_agent_config(target)
        assert json.loads((target / 'memory.json').read_text()) == selection
        assert proxy.requests == 0
    assert {p.name: p.read_bytes() for p in config.iterdir()} == before


def test_fresh_verification_rejects_echoes_and_partial_memory_reads() -> None:
    project = Path("/work/click")
    check = ["uv", "run", "--no-sync", "pytest", "-q"]
    assert invokes_check({"command": "uv run --no-sync pytest -q"}, project, check)
    assert invokes_check({"command": "cd /work/click && uv run --no-sync pytest -q"}, project, check)
    for command in ("printf 'uv run --no-sync pytest -q'", "echo uv run --no-sync pytest -q",
                    "printf ';' uv run --no-sync pytest -q", "# uv run --no-sync pytest -q"):
        assert not invokes_check({"command": command}, project, check)
    body = "---\ndescription: Personal reporting preference\n---\nFinish with PRIVATE_FIXTURE.\n"
    calls = [{"role": "assistant", "content": [{"type": "toolCall", "id": "read1", "name": "read",
              "arguments": {"path": "/memory/preference.md", "offset": 4, "limit": 1}}]}]
    partial = {"role": "toolResult", "toolCallId": "read1", "toolName": "read", "isError": False,
               "content": [{"type": "text", "text": "Finish with PRIVATE_FIXTURE."}]}
    assert not full_memory_read([*calls, partial], project, (Path("/memory/preference.md"),), body)
    complete = {**partial, "content": [{"type": "text", "text": body}]}
    full_calls = [{"role": "assistant", "content": [{"type": "toolCall", "id": "read1", "name": "read",
                   "arguments": {"path": "/memory/preference.md"}}]}]
    assert full_memory_read([*full_calls, complete], project, (Path("/memory/preference.md"),), body)



def test_native_block_proof_uses_the_configured_message_not_english_keywords() -> None:
    message = "Do not run git push, including --dry-run."
    rules = [{"action": "block", "message": message}]
    call = {"role": "assistant", "content": [{"type": "toolCall", "id": "push", "name": "bash",
            "arguments": {"command": "git push --dry-run"}}]}
    result = {"role": "toolResult", "toolCallId": "push", "toolName": "bash", "isError": True,
              "content": [{"type": "text", "text": message}]}
    assert learned_block_result([call, result], "git push --dry-run", rules)
    assert not learned_block_result([call, {**result, "isError": False}], "git push --dry-run", rules)
    assert not learned_block_result([call, {**result, "content": [{"type": "text", "text": "ordinary shell error"}]}],
                                    "git push --dry-run", rules)
    assert not learned_block_result([call, result], "git push --dry-run", [{**rules[0], "enabled": False}])
    wrapped = {**call, "content": [{**call["content"][0], "arguments": {"command": "cd /work/click && git push --dry-run 2>&1"}}]}
    assert learned_block_result([wrapped, result], "git push --dry-run", rules, Path("/work/click"))
    echo = {**call, "content": [{**call["content"][0], "arguments": {"command": "printf 'git push --dry-run'"}}]}
    assert not learned_block_result([echo, result], "git push --dry-run", rules, Path("/work/click"))

def test_container_timeout_keeps_failure_report_before_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "results"
    cleaned: list[str] = []

    def fixture_command(args: list[str], **_kwargs: object) -> str:
        if args[1] == "run":
            return "owned-container\n"
        if args[1] == "cp":
            raise RuntimeError("fixture artifact transfer failure")
        if args[1] == "rm":
            saved = json.loads((output / "report.json").read_text())
            assert saved["status"] == "failed" and saved["artifactError"]
            cleaned.append(args[-1])
        return ""

    def fixture_run(args: list[str], **_kwargs: object) -> SimpleNamespace:
        if "-i" in args:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise subprocess.TimeoutExpired(args, 1800)

    class FixtureProxy:
        key = "fixture-main-credential"
        jev_key = None
        token = "fixture-container-credential"

        def write_agent_config(self, root: Path) -> None:
            root.mkdir()
            (root / "settings.json").write_text("{}")

    monkeypatch.setattr(docker_experiment, "command", fixture_command)
    monkeypatch.setattr(docker_experiment.subprocess, "run", fixture_run)
    result = docker_experiment.run_project("fixture-image", "fixture-digest", FixtureProxy(),
                                         {"name": "fixture", "repository": "https://github.com/example/example.git", "commit": "fixture"}, output)
    assert result["status"] == "failed" and "timed out" in result["error"]
    assert cleaned == ["owned-container"]



def test_nonzero_runner_exit_cannot_be_overridden_by_passed_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "results"

    def fixture_command(args: list[str], **_kwargs: object) -> str:
        if args[1] == "run":
            return "owned-container\n"
        if args[1] == "cp":
            (Path(args[-1]) / "report.json").write_text(json.dumps({"status": "passed", "stage": "complete"}))
        return ""

    class FixtureProxy:
        key = "fixture-main-credential"
        jev_key = None
        token = "fixture-container-credential"

        def write_agent_config(self, root: Path) -> None:
            root.mkdir()
            (root / "settings.json").write_text("{}")

    def fixture_run(args: list[str], **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=0 if "-i" in args else 1, stdout="", stderr="")

    monkeypatch.setattr(docker_experiment, "command", fixture_command)
    monkeypatch.setattr(docker_experiment.subprocess, "run", fixture_run)
    result = docker_experiment.run_project("fixture-image", "fixture-digest", FixtureProxy(),
        {"name": "fixture", "repository": "https://github.com/example/example.git", "commit": "fixture"}, output)
    assert result["status"] == "failed" and result["containerExitCode"] == 1

def test_experiment_proxy_bounds_routing_and_never_copies_host_credentials(tmp_path: Path) -> None:
    observed: list[dict] = []

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_POST(self) -> None:
            observed.append({"path": self.path, "auth": self.headers.get("Authorization"),
                             "body": json.loads(self.rfile.read(int(self.headers["Content-Length"])))})
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b'data: {"id":"real-upstream-response"}\n\ndata: [DONE]\n\n')

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    try:
        config = tmp_path / "host"
        config.mkdir()
        (config / "memory.json").write_text(json.dumps({"provider": "fixture", "model": "selected"}))
        (config / "models.json").write_text(json.dumps({"providers": {"fixture": {
            "apiKey": "HOST_ONLY_SECRET", "headers": {"X-Secret": "HOST_HEADER_SECRET"},
            "baseUrl": f"http://127.0.0.1:{upstream.server_address[1]}/v1", "api": "openai-completions",
            "models": [{"id": "selected", "headers": {"X-Key": "HOST_MODEL_SECRET"}, "contextWindow": 10000, "maxTokens": 1000}],
        }}}))
        for foreign_model in ('jev-latest', 'jev-preview', 'jev-1.15.0', 'other', '', None):
            with pytest.raises(ValueError, match='fixed Jev study model'):
                InferenceProxy(config, jev_model=foreign_model)
        with InferenceProxy(config) as proxy:
            public = tmp_path / "container"
            proxy.write_agent_config(public)
            copied = "".join(file.read_text() for file in public.iterdir())
            assert "HOST_ONLY_SECRET" not in copied and "HOST_HEADER_SECRET" not in copied and "HOST_MODEL_SECRET" not in copied

            def request(path: str, payload: object, *, authorized: bool = True) -> tuple[int, bytes]:
                connection = http.client.HTTPConnection("127.0.0.1", proxy.server.server_address[1], timeout=5)
                connection.request("POST", path, json.dumps(payload), headers={"Content-Type": "application/json",
                    "Authorization": f"Bearer {proxy.token}" if authorized else "Bearer wrong"})
                response = connection.getresponse()
                result = response.status, response.read()
                connection.close()
                return result

            assert request("/v1/files", {"model": "selected"})[0] == 404
            assert request("/v1/chat/completions", {"model": "selected"}, authorized=False)[0] == 401
            assert request("/v1/chat/completions", {"model": "foreign"})[0] == 403
            assert request("/v1/chat/completions", ["invalid"])[0] == 403
            assert not observed
            status, data = request("/v1/chat/completions", {"model": "selected", "messages": []})
            assert status == 200 and b"real-upstream-response" in data and data.endswith(b"[DONE]\n\n")
            assert observed == [{"path": "/v1/chat/completions", "auth": "Bearer HOST_ONLY_SECRET",
                                 "body": {"model": "selected", "messages": []}}]
            assert [{k: v for k, v in row.items() if k not in ('memoryDiscoveryOnWire', 'memoryProtocolOnWire', 'systemTextSha256', 'reasoningEffortOnWire')} for row in proxy.model_observations] == [{'request': 1, 'route':'/v1/chat/completions', 'toolCount': 0,
                'toolChoice': 'other-or-absent', 'messageCount': 0, 'retainedToolResults': 0,
                'responseFormatType': 'other-or-absent', 'responseSchemaName': 'other-or-absent', 'responseSchemaStrict': False}]
            assert request('/v1/chat/completions', {'model': 'selected', 'tools': [], 'tool_choice': 'none',
                'messages': [{'role': 'tool', 'content': 'PRIVATE_BODY_NOT_FOR_METADATA'}],
                'response_format': {'type': 'json_schema', 'json_schema': {'name': 'memory_delta', 'strict': True, 'schema': {'private': 'PRIVATE_BODY_NOT_FOR_METADATA'}}}})[0] == 200
            assert {k: v for k, v in proxy.model_observations[-1].items() if k not in ('memoryDiscoveryOnWire', 'memoryProtocolOnWire', 'systemTextSha256', 'reasoningEffortOnWire')} == {'request': 2, 'route':'/v1/chat/completions', 'toolCount': 0,
                'toolChoice': 'none', 'messageCount': 1, 'retainedToolResults': 1,
                'responseFormatType': 'json_schema', 'responseSchemaName': 'memory_delta', 'responseSchemaStrict': True}
            assert 'PRIVATE_BODY_NOT_FOR_METADATA' not in json.dumps(proxy.model_observations)
            assert request('/v1/chat/completions', {'model': 'selected', 'response_format': {
                'type': 'PRIVATE_BODY_NOT_FOR_METADATA', 'json_schema': {'name': 'PRIVATE_BODY_NOT_FOR_METADATA', 'strict': 'true'}}})[0] == 200
            assert proxy.model_observations[-1]['responseFormatType'] == 'other-or-absent'
            assert proxy.model_observations[-1]['responseSchemaName'] == 'other-or-absent'
            assert proxy.model_observations[-1]['responseSchemaStrict'] is False
            assert 'PRIVATE_BODY_NOT_FOR_METADATA' not in json.dumps(proxy.model_observations)
            responses = {'model': 'selected', 'instructions': '<project_memory_protocol>PRIVATE_BODY_NOT_FOR_METADATA</project_memory_protocol>',
                'input': [{'type': 'message', 'role': 'developer', 'content': [{'type': 'input_text', 'text': '<project_memory_discovery>PRIVATE_BODY_NOT_FOR_METADATA</project_memory_discovery>'}]},
                          {'type': 'function_call_output', 'call_id': 'PRIVATE_BODY_NOT_FOR_METADATA', 'output': 'PRIVATE_BODY_NOT_FOR_METADATA'}],
                'reasoning': {'effort': 'max'}, 'tools': [{'type': 'function', 'name': 'PRIVATE_BODY_NOT_FOR_METADATA'}],
                'tool_choice': 'auto', 'text': {'format': {'type': 'json_schema', 'name': 'memory_amendment', 'strict': True,
                    'schema': {'private': 'PRIVATE_BODY_NOT_FOR_METADATA'}}}}
            assert request('/v1/responses', responses)[0] == 200
            row = proxy.model_observations[-1]
            assert row['memoryDiscoveryOnWire'] and row['memoryProtocolOnWire']
            assert row['reasoningEffortOnWire'] == 'max'
            assert {key: row[key] for key in ('toolCount', 'toolChoice', 'messageCount', 'retainedToolResults', 'responseFormatType', 'responseSchemaName', 'responseSchemaStrict')} == {
                'toolCount': 1, 'toolChoice': 'auto', 'messageCount': 2, 'retainedToolResults': 1,
                'responseFormatType': 'json_schema', 'responseSchemaName': 'memory_amendment', 'responseSchemaStrict': True}
            assert observed[-1]['path'] == '/v1/responses' and observed[-1]['body'] == responses
            assert request('/v1/responses', {'model': 'selected', 'input': 'PRIVATE_BODY_NOT_FOR_METADATA',
                'text': {'format': {'type': 'json_schema', 'name': 'PRIVATE_BODY_NOT_FOR_METADATA', 'strict': 'true'}}})[0] == 200
            assert proxy.model_observations[-1]['messageCount'] == 1
            assert proxy.model_observations[-1]['responseSchemaName'] == 'other-or-absent'
            assert proxy.model_observations[-1]['responseSchemaStrict'] is False
            assert 'PRIVATE_BODY_NOT_FOR_METADATA' not in json.dumps(proxy.model_observations)
            proxy.requests = 180
            assert request("/v1/chat/completions", {"model": "selected"})[0] == 429
            assert len(observed) == 5
    finally:
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=5)


def test_jev_proxy_configuration_keeps_real_credentials_host_only(tmp_path: Path) -> None:
    root = tmp_path / 'host'
    root.mkdir()
    (root / 'memory.json').write_text(json.dumps({'provider': 'fixture', 'model': 'selected'}))
    (root / 'models.json').write_text(json.dumps({'providers': {'fixture': {
        'apiKey': 'HOST_MODEL_SECRET', 'baseUrl': 'https://example.invalid/v1',
        'models': [{'id': 'selected'}],
    }}}))
    with InferenceProxy(root, jev_key='HOST_JEV_SECRET') as proxy:
        target = tmp_path / 'isolated'
        proxy.write_agent_config(target)
        text = ''.join(file.read_text() for file in target.iterdir())
        assert 'HOST_JEV_SECRET' not in text and 'HOST_MODEL_SECRET' not in text
        assert json.loads((target / 'continual-learning.json').read_text())['jev']['model'] == 'jev-1.13.0'
        assert proxy.jev_environment()['TYPESAFE_API_KEY'] == proxy.token
        assert proxy.jev_environment()['TYPESAFE_BASE_URL'].endswith('/jev')


@pytest.mark.parametrize("jev_model", ["jev-1.13.0", "jev-1.14.0"])
@pytest.mark.parametrize("long_context", [None, "true", "false", "TRUE"])
def test_real_jev_proxy_route_and_model_stream_do_not_compete_for_slots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, long_context: str | None, jev_model: str) -> None:
    observed: list[dict] = []
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass
        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            observed.append({'path': self.path, 'auth': self.headers.get('Authorization'), 'model': body['model'], 'longContext':self.headers.get('TypeSafe-Danger-Zone-Long-Context')})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({'model': jev_model, 'usage': {'input_tokens': 123, 'output_tokens': 4}, 'answers': {}}).encode())
    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    root = tmp_path / 'host'
    root.mkdir()
    (root / 'memory.json').write_text(json.dumps({'provider': 'fixture', 'model': 'selected'}))
    (root / 'models.json').write_text(json.dumps({'providers': {'fixture': {'apiKey': 'HOST_MODEL_SECRET',
        'baseUrl': f'http://127.0.0.1:{upstream.server_address[1]}/v1', 'models': [{'id': 'selected'}]}}}))
    monkeypatch.setattr(docker_experiment.http.client, 'HTTPSConnection',
                        lambda *_args, **_kwargs: http.client.HTTPConnection('127.0.0.1', upstream.server_address[1], timeout=5))
    try:
        with InferenceProxy(root, jev_key='HOST_JEV_SECRET', **({'jev_model':jev_model} if jev_model!='jev-1.13.0' else {})) as proxy:
            # Holding every model-stream slot must not induce a fake Jev failure.
            for _ in range(4):
                assert proxy.slots.acquire(blocking=False)
            foreign = http.client.HTTPConnection('127.0.0.1', proxy.server.server_address[1], timeout=5)
            foreign.request('POST', '/jev/v1/systemone', json.dumps({'model':'jev-1.13.0' if jev_model=='jev-1.14.0' else 'jev-1.14.0'}),headers={'Authorization':f'Bearer {proxy.token}'})
            assert foreign.getresponse().status==403
            foreign.close()
            connection = http.client.HTTPConnection('127.0.0.1', proxy.server.server_address[1], timeout=5)
            connection.request('POST', '/jev/v1/systemone', json.dumps({'model': jev_model, 'state': 'public fixture', 'questions': {}}),
                               headers={'Authorization': f'Bearer {proxy.token}', **({'TypeSafe-Danger-Zone-Long-Context':long_context} if long_context is not None else {})})
            response = connection.getresponse()
            assert response.status == 200
            response.read()
            connection.close()
            for _ in range(4):
                proxy.slots.release()
            assert proxy.jev_requests == 1 and proxy.errors == 0
            assert proxy.jev_usage == [{'model': jev_model, 'input_tokens': 123, 'output_tokens': 4}]
            assert observed == [{'path': '/v1/systemone', 'auth': 'Bearer HOST_JEV_SECRET', 'model': jev_model, 'longContext':'true' if long_context=='true' else None}]
    finally:
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("long_context", [False, True])
@pytest.mark.parametrize("transport", ["bun-fetch", "node-https"])
@pytest.mark.parametrize("status", [200, 502])
@pytest.mark.parametrize("jev_model", ["jev-1.13.0", "jev-1.14.0"])
@pytest.mark.parametrize("evidence_bytes", [20, 90000])
def test_jev_bun_forwarder_preserves_wire_and_keeps_secret_out_of_arguments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int, evidence_bytes: int, transport: str, long_context: bool, jev_model: str) -> None:
    root=tmp_path/'host';root.mkdir()
    (root/'memory.json').write_text(json.dumps({'provider':'fixture','model':'selected'}))
    (root/'models.json').write_text(json.dumps({'providers':{'fixture':{'apiKey':'MODEL_SECRET','baseUrl':'https://example.invalid/v1','models':[{'id':'selected'}]}}}))
    observed=[]
    def run(args, **kwargs):
        observed.append((args,kwargs))
        body=json.dumps({'model':jev_model,'usage':{'input_tokens':17,'output_tokens':3},'answers':{}}) if status==200 else 'error HOST_JEV_SECRET MODEL_SECRET'
        return __import__('subprocess').CompletedProcess(args,0,json.dumps({'status':status,'body':body}).encode(),b'')
    monkeypatch.setattr(docker_experiment.subprocess,'run',run)
    monkeypatch.setattr(docker_experiment, '_run_jev_forwarder',
                        lambda args, **kwargs: (run(args, **{k: v for k, v in kwargs.items() if k != 'downstream'}), False))
    monkeypatch.setenv('NODE_TLS_REJECT_UNAUTHORIZED', '0')
    monkeypatch.setenv('NODE_OPTIONS', '--require=/untrusted/injection.cjs')
    monkeypatch.setenv('NODE_EXTRA_CA_CERTS', '/untrusted/ca.pem')
    payload=json.dumps({'model':jev_model,'state':'complete frozen evidence'+'x'*evidence_bytes,'questions':{}}).encode()
    with InferenceProxy(root,jev_key='HOST_JEV_SECRET',jev_transport=transport, **({'jev_model':jev_model} if jev_model!='jev-1.13.0' else {})) as proxy:
        conn=http.client.HTTPConnection('127.0.0.1',proxy.server.server_address[1],timeout=5)
        conn.request('POST','/jev/v1/systemone',payload,headers={'Authorization':f'Bearer {proxy.token}', **({'TypeSafe-Danger-Zone-Long-Context':'true'} if long_context else {})})
        response=conn.getresponse();assert response.status==status
        body=response.read();assert int(response.getheader('Content-Length'))==len(body);conn.close()
        assert b'HOST_JEV_SECRET' not in body and b'MODEL_SECRET' not in body
        assert proxy.jev_usage==([{'model':jev_model,'input_tokens':17,'output_tokens':3}] if status==200 else [])
        assert len(proxy.jev_observations) == 1
        observation = proxy.jev_observations[0]
        assert observation['wireHash'] == __import__('hashlib').sha256(payload).hexdigest()
        assert observation['wireBytes'] == len(payload)
        assert observation['status'] == ('completed' if status == 200 else 'http-error')
        assert observation['httpStatus'] == status and observation['durationMs'] >= 0
        assert 'HOST_JEV_SECRET' not in str(observation) and 'complete frozen evidence' not in str(observation)

    assert len(observed)==1
    args,kwargs=observed[0]
    assert 'HOST_JEV_SECRET' not in str(args)
    assert kwargs['env'].get('JEV_MODEL') == jev_model
    assert kwargs['env'].get('JEV_LONG_CONTEXT') == ('true' if long_context else None)
    assert proxy.jev_observations[0]['longContext'] is long_context
    assert kwargs['input']==payload and kwargs['env']['TYPESAFE_API_KEY']=='HOST_JEV_SECRET'
    assert 'MODEL_SECRET' not in str(kwargs)
    if transport == 'node-https':
        assert Path(args[0]).name == 'node' and Path(args[1]).name == 'jev-https-forward.mjs'
        assert kwargs['timeout'] == 35
        assert set(kwargs['env']) <= {'PATH', 'HOME', 'TYPESAFE_API_KEY', 'JEV_RESOLVED_ADDRESS', 'JEV_LONG_CONTEXT', 'JEV_MODEL'}


@pytest.mark.parametrize("jev_model", ["jev-1.13.0", "jev-1.14.0"])
def test_jev_forwarder_rejects_redirects_and_keeps_the_complete_wire(tmp_path: Path, jev_model: str) -> None:
    preload=tmp_path/'preload.mjs'
    preload.write_text('''globalThis.fetch=async(url,options)=>{
      if(url!=='https://api.typesafe.ai/v1/systemone'||options.redirect!=='error'||!options.signal
         ||JSON.parse(options.body).state!=='complete wire')throw Error('Invalid transparent transport');
      return new Response(JSON.stringify({model:JSON.parse(options.body).model}));
    };''')
    result=__import__('subprocess').run(['bun','--preload',str(preload),str(Path(docker_experiment.__file__).with_name('jev-http-forward.mjs'))],
        input=json.dumps({'model':jev_model,'state':'complete wire'}).encode(),capture_output=True,
        env={**__import__('os').environ,'TYPESAFE_API_KEY':'synthetic-host-only-key','JEV_MODEL':jev_model},timeout=10)
    assert result.returncode==0, result.stderr.decode()
    assert json.loads(result.stdout)['status']==200
    assert json.loads(json.loads(result.stdout)['body'])['model']==jev_model


@pytest.mark.parametrize("failure", ["error", "timeout", "classified", "tls", "untrusted"])
def test_jev_forwarder_failure_has_controlled_diagnostics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    # Given a failed host forwarder, When the original connection closes,
    # Then retain only controlled metadata and never child stderr or credentials.
    import subprocess
    root = tmp_path / 'host'
    root.mkdir()
    (root / 'memory.json').write_text(json.dumps({'provider': 'fixture', 'model': 'selected'}))
    (root / 'models.json').write_text(json.dumps({'providers': {'fixture': {'apiKey': 'MODEL_SECRET',
        'baseUrl': 'https://example.invalid/v1', 'models': [{'id': 'selected'}]}}}))
    def run(args, **kwargs):
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(args, 35, stderr=b'HOST_JEV_SECRET private context')
        if failure in ('classified', 'tls', 'untrusted'):
            category = 'connection-timeout' if failure == 'classified' else 'tls-certificate-verification-failed' if failure == 'tls' else 'HOST_JEV_SECRET private context'
            return subprocess.CompletedProcess(args, 0, json.dumps({'transportFailure': category, 'transportObservation': {
                'tcpConnected': True, 'tlsVerified': False, 'responseHeaders': False,
                'receivedBytes': 0, 'ownAbort': False, 'untrusted': 'HOST_JEV_SECRET private context'}}).encode(), b'')
        return subprocess.CompletedProcess(args, 1, b'', b'HOST_JEV_SECRET private context')
    monkeypatch.setattr(docker_experiment.subprocess, 'run', run)
    with InferenceProxy(root, jev_key='HOST_JEV_SECRET', jev_transport='bun-fetch') as proxy:
        conn = http.client.HTTPConnection('127.0.0.1', proxy.server.server_address[1], timeout=5)
        conn.request('POST', '/jev/v1/systemone', json.dumps({'model': 'jev-1.13.0', 'state': 'private context'}),
                     headers={'Authorization': f'Bearer {proxy.token}'})
        with pytest.raises(http.client.RemoteDisconnected):
            conn.getresponse()
        conn.close()
        assert proxy.jev_observations[0]['status'] == ('forwarder-timeout' if failure == 'timeout' else 'transport-error' if failure == 'untrusted' else 'forwarder-error')
        assert proxy.jev_observations[0]['durationMs'] >= 0
        if failure in ('classified', 'tls'):
            assert proxy.jev_observations[0]['transportObservation'] == {
                'tcpConnected': True, 'tlsVerified': False, 'responseHeaders': False,
                'receivedBytes': 0, 'ownAbort': False}
            assert proxy.jev_observations[0]['failureCategory'] == ('connection-timeout' if failure == 'classified' else 'tls-certificate-verification-failed')
        assert proxy.jev_usage == [] and proxy.errors == 1
        assert 'HOST_JEV_SECRET' not in str(proxy.jev_observations)
        assert 'private context' not in str(proxy.jev_observations)


@pytest.mark.parametrize("code,category", [("ETIMEDOUT", "connection-timeout"), ("ECONNRESET", "connection-reset"), ("ConnectionClosed", "connection-closed"), ("ConnectionRefused", "connection-refused"), ("UNKNOWN_CERTIFICATE_VERIFICATION_ERROR", "tls-certificate-verification-failed"), ("CERT_HAS_EXPIRED", "tls-certificate-verification-failed"), ("ERR_TLS_CERT_ALTNAME_INVALID", "tls-certificate-verification-failed"), ("PRIVATE_SECRET", "transport-unavailable")])
def test_forwarder_emits_only_controlled_fetch_failure_categories(tmp_path: Path, code: str, category: str) -> None:
    preload = tmp_path / 'preload.mjs'
    preload.write_text('globalThis.fetch=async()=>{throw Object.assign(new Error("private context"),{code:'+json.dumps(code)+'});};')
    result = __import__('subprocess').run(['bun', '--preload', str(preload), str(Path(docker_experiment.__file__).with_name('jev-http-forward.mjs'))],
        input=json.dumps({'model':'jev-1.13.0'}).encode(), capture_output=True,
        env={**__import__('os').environ,'TYPESAFE_API_KEY':'synthetic-host-only-key'},timeout=10)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {'transportFailure': category}
    assert result.stderr == b''


def test_explicit_public_jev_route_preserves_hostname_tls_and_wire(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given an explicit public address for this isolated study,
    # When forwarding a complete wire, Then retain origin identity and default TLS validation.
    root = tmp_path / 'host'
    root.mkdir()
    (root / 'memory.json').write_text(json.dumps({'provider': 'fixture', 'model': 'selected'}))
    (root / 'models.json').write_text(json.dumps({'providers': {'fixture': {'apiKey': 'MODEL_SECRET',
        'baseUrl': 'https://example.invalid/v1', 'models': [{'id': 'selected'}]}}}))
    observed = []
    def run(args, **kwargs):
        observed.append(kwargs)
        return __import__('subprocess').CompletedProcess(args, 0, b'{"status":200,"body":"{}"}', b'')
    monkeypatch.setattr(docker_experiment.subprocess, 'run', run)
    with InferenceProxy(root, jev_key='HOST_JEV_SECRET', jev_transport='bun-fetch', jev_resolved_address='104.18.25.46') as proxy:
        conn = http.client.HTTPConnection('127.0.0.1', proxy.server.server_address[1])
        wire = b'{"model":"jev-1.13.0","state":"complete wire"}'
        conn.request('POST', '/jev/v1/systemone', wire, headers={'Authorization': f'Bearer {proxy.token}'})
        assert conn.getresponse().read() == b'{}'
        conn.close()
    assert observed[0]['input'] == wire
    assert observed[0]['env']['JEV_RESOLVED_ADDRESS'] == '104.18.25.46'
    monkeypatch.undo()
    preload = tmp_path / 'route.mjs'
    preload.write_text('''globalThis.fetch=async(url,options)=>{
      if(url!=='https://104.18.25.46/v1/systemone'||options.headers.Host!=='api.typesafe.ai'
        ||options.tls?.serverName!=='api.typesafe.ai'||options.tls?.rejectUnauthorized===false
        ||options.proxy!==false||options.redirect!=='error'||JSON.parse(options.body).state!=='complete wire')
        throw Error('Invalid isolated route');
      return new Response('{}');};''')
    result = __import__('subprocess').run(['bun', '--preload', str(preload), str(Path(docker_experiment.__file__).with_name('jev-http-forward.mjs'))],
        input=wire, capture_output=True, env={**__import__('os').environ, 'TYPESAFE_API_KEY':'fixture', 'JEV_RESOLVED_ADDRESS':'104.18.25.46'}, timeout=10)
    assert result.returncode == 0
    assert json.loads(result.stdout)['status'] == 200


@pytest.mark.parametrize('transport', ['bun-fetch', 'node-https'])
@pytest.mark.parametrize('address', ['127.0.0.1', '198.18.16.25', '10.0.0.1', '224.0.0.1', '239.255.255.250', '240.0.0.1', '255.255.255.255', 'api.typesafe.ai', '104.18.25.46/path', '::1'])
def test_explicit_jev_route_refuses_nonpublic_or_nonliteral_addresses(tmp_path: Path, address: str, transport: str) -> None:
    with pytest.raises(ValueError, match='public IPv4'):
        InferenceProxy(tmp_path, jev_transport=transport, jev_resolved_address=address)


@pytest.mark.parametrize('drain', [True, False])
def test_shutdown_requires_counted_forwarder_quiescence_before_settlement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drain: bool) -> None:
    # Given an admitted forwarder is blocked, When accepting connections stops,
    # Then settlement waits for its late usage or reports uncertain termination.
    root = tmp_path / 'host'
    root.mkdir()
    (root / 'memory.json').write_text(json.dumps({'provider': 'fixture', 'model': 'selected'}))
    (root / 'models.json').write_text(json.dumps({'providers': {'fixture': {
        'apiKey': 'LOCAL_MODEL_FIXTURE', 'baseUrl': 'https://example.invalid/v1',
        'models': [{'id': 'selected'}]}}}))
    entered, release, waiting, closed = (threading.Event() for _ in range(4))
    outcomes: list[str] = []

    def forward(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        entered.set()
        assert release.wait(5)
        answer = {'model': 'jev-1.13.0', 'usage': {'input_tokens': 23, 'output_tokens': 1}}
        return subprocess.CompletedProcess(args, 0, json.dumps({'status': 200, 'body': json.dumps(answer)}).encode(), b'')

    monkeypatch.setattr(docker_experiment.subprocess, 'run', forward)
    monkeypatch.setattr(docker_experiment, '_run_jev_forwarder',
                        lambda args, **kwargs: (forward(args, **{k: v for k, v in kwargs.items() if k != 'downstream'}), False))
    proxy = InferenceProxy(root, jev_key='LOCAL_JEV_FIXTURE', jev_transport='node-https', retain_jev_envelopes=True)
    proxy.__enter__()

    def client() -> None:
        connection = http.client.HTTPConnection('127.0.0.1', proxy.server.server_address[1], timeout=5)
        try:
            connection.request('POST', '/jev/v1/systemone', b'{"model":"jev-1.13.0"}',
                               headers={'Authorization': f'Bearer {proxy.token}'})
            assert connection.getresponse().read()
        finally:
            connection.close()

    caller = threading.Thread(target=client)
    caller.start()
    closer = None
    try:
        assert entered.wait(5)
        assert getattr(proxy, 'active_requests', None) == 1
        original_wait = proxy.wait_for_quiescence

        def controlled_wait(timeout: float = 35) -> bool:
            waiting.set()
            return original_wait(timeout=timeout if drain else 0)

        monkeypatch.setattr(proxy, 'wait_for_quiescence', controlled_wait)

        def close() -> None:
            try:
                proxy.__exit__()
                outcomes.append('settled')
            except RuntimeError:
                outcomes.append('uncertain')
            finally:
                closed.set()

        closer = threading.Thread(target=close)
        closer.start()
        assert waiting.wait(5)
        assert not proxy.thread.is_alive()
        if drain:
            assert not closed.is_set()
        else:
            assert closed.wait(5) and outcomes == ['uncertain']
        assert proxy.active_requests == 1 and proxy.requests == proxy.request_budget == 1
        capture_output = tmp_path / 'late-envelopes'
        assert proxy.write_jev_envelopes(capture_output)['status'] == 'not-quiescent'
        assert not capture_output.exists()
        release.set()
        caller.join(timeout=5)
        closer.join(timeout=5)
        assert not caller.is_alive() and not closer.is_alive()
        assert proxy.active_requests == 0 and proxy.transport_quiescent
        assert outcomes == ['settled' if drain else 'uncertain']
        assert proxy.jev_usage == [{'model': 'jev-1.13.0', 'input_tokens': 23, 'output_tokens': 1}]
        assert proxy.write_jev_envelopes(capture_output)['status'] == 'written'
    finally:
        release.set()
        caller.join(timeout=5)
        if closer is not None:
            closer.join(timeout=5)
        else:
            proxy.__exit__()


@pytest.mark.parametrize('mode', ['reset', 'half-close', 'complete-before-reset'])
def test_confirmed_downstream_reset_cancels_owned_node_forwarder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    # Given a real local Node forwarder waiting for a local HTTP response,
    # when its downstream caller resets the connection after admission,
    # then reap that owned child before reporting request quiescence.
    import select
    import socket
    import struct

    root = tmp_path / 'host'
    root.mkdir()
    (root / 'memory.json').write_text(json.dumps({'provider': 'fixture', 'model': 'selected'}))
    (root / 'models.json').write_text(json.dumps({'providers': {'fixture': {
        'apiKey': 'LOCAL_MODEL_FIXTURE', 'baseUrl': 'https://example.invalid/v1',
        'models': [{'id': 'selected'}]}}}))
    entered, release = (threading.Event() for _ in range(2))
    received: list[bytes] = []

    class Peer(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_POST(self) -> None:
            received.append(self.rfile.read(int(self.headers['Content-Length'])))
            entered.set()
            if not release.wait(10):
                return
            answer = json.dumps({'model': 'jev-1.13.0', 'usage': {'input_tokens': 23, 'output_tokens': 1}}).encode()
            try:
                self.send_response(200)
                self.send_header('Content-Length', str(len(answer)))
                self.end_headers()
                self.wfile.write(answer)
            except (BrokenPipeError, ConnectionResetError):
                pass

    peer = ThreadingHTTPServer(('127.0.0.1', 0), Peer)
    peer_thread = threading.Thread(target=peer.serve_forever, daemon=True)
    peer_thread.start()
    # Use the actual forwardJev function with its existing request-injection
    # seam. Only the fixture's explicit loopback port can receive HTTP traffic.
    script = Path(docker_experiment.__file__).with_name('jev-https-forward.mjs').resolve().as_uri()
    code = f'''
      import http from 'node:http'; import {{forwardJev}} from {json.dumps(script)};
      const chunks=[]; for await(const c of process.stdin) chunks.push(c);
      const result=await forwardJev(Buffer.concat(chunks).toString(),{{key:process.env.TYPESAFE_API_KEY}},
        (_url,options,callback)=>http.request({{...options,hostname:'127.0.0.1',port:{peer.server_address[1]},
          path:'/v1/systemone'}},callback));
      process.stdout.write(JSON.stringify(result));
    '''
    real_popen = subprocess.Popen
    children: list[subprocess.Popen] = []

    def popen(args: list[str], **kwargs: object) -> subprocess.Popen:
        child = real_popen([args[0], '--input-type=module', '-e', code], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(docker_experiment.subprocess, 'Popen', popen)
    proxy = InferenceProxy(root, jev_key='LOCAL_JEV_FIXTURE', jev_transport='node-https',
                           request_budget=1, retain_jev_envelopes=True)
    original_get_request = proxy.server.get_request
    downstream: list[socket.socket] = []

    def get_request() -> tuple[socket.socket, object]:
        connection, address = original_get_request()
        downstream.append(connection)
        return connection, address

    monkeypatch.setattr(proxy.server, 'get_request', get_request)
    proxy.__enter__()
    caller = http.client.HTTPConnection('127.0.0.1', proxy.server.server_address[1], timeout=5)
    payload = b'{"model":"jev-1.13.0","state":"local cancellation fixture"}'
    try:
        caller.request('POST', '/jev/v1/systemone', payload,
                       headers={'Authorization': f'Bearer {proxy.token}'})
        assert entered.wait(5), 'The actual owned Node child never reached the local peer'
        assert received == [payload] and proxy.active_requests == proxy.requests == 1
        assert caller.sock is not None
        if mode == 'half-close':
            caller.sock.shutdown(socket.SHUT_WR)
            release.set()
            assert caller.getresponse().status == 200
        else:
            if mode == 'complete-before-reset':
                release.set()
                assert children[0].wait(timeout=5) == 0
            caller.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
            caller.close()
        settled = proxy.wait_for_quiescence(timeout=5)
        reset_confirmed = False
        if not settled:
            # Failure-only readback proves this was RST, not a legal write
            # half-close. Do not compete with a working cancellation monitor.
            ready, _, _ = select.select(downstream, [], [], 0)
            assert ready, 'Caller close did not yield a verifiable downstream event'
            try:
                ready[0].recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT)
            except ConnectionResetError:
                reset_confirmed = True
            assert reset_confirmed, 'Cannot distinguish caller reset from a write half-close'
        print(json.dumps({'downstreamResetConfirmed': reset_confirmed, 'settledBeforePeerRelease': settled,
                          'ownedChildCompleted': all(child.poll() is not None for child in children), 'activeRequests': proxy.active_requests,
                          'requests': proxy.requests, 'externalRequests': 0}))
        assert settled and all(child.poll() is not None for child in children), 'Confirmed downstream RST left owned Node upstream work running'
        assert proxy.requests == proxy.jev_requests == 1
        observation = proxy.jev_observations[0]
        if mode == 'reset':
            assert observation['status'] == 'caller-cancelled'
            assert observation['callerCancellation'] == 'downstream-reset' and observation['usageUnknown'] is True
            assert proxy.jev_usage == []
        else:
            assert proxy.jev_usage == [{'model': 'jev-1.13.0', 'input_tokens': 23, 'output_tokens': 1}]
            assert not observation.get('usageUnknown') and not observation.get('callerCancellation')
    finally:
        release.set()
        caller.close()
        assert proxy.wait_for_quiescence(timeout=5), 'Fixture cleanup did not drain the owned child'
        proxy.__exit__()
        peer.shutdown()
        peer.server_close()
        peer_thread.join(timeout=5)


@pytest.mark.parametrize('failure', ['pipe', 'popen', 'thread-start'])
def test_owned_forwarder_setup_failure_closes_pipes_and_reaps_child(monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    # Given a local-only child, when setup fails, leave no owned process or FD.
    import os
    import shutil
    import socket

    real_pipe, real_popen, real_thread = os.pipe, subprocess.Popen, threading.Thread
    pipes: list[int] = []
    children: list[subprocess.Popen] = []

    def fail() -> None:
        raise RuntimeError('controlled setup failure')

    def pipe() -> tuple[int, int]:
        if failure == 'pipe':
            fail()
        descriptors = real_pipe()
        pipes.extend(descriptors)
        return descriptors

    def popen(*args: object, **kwargs: object) -> subprocess.Popen:
        if failure == 'popen':
            fail()
        child = real_popen(*args, **kwargs)
        children.append(child)
        return child

    def thread(*args: object, **kwargs: object) -> threading.Thread:
        worker = real_thread(*args, **kwargs)
        monkeypatch.setattr(worker, 'start', fail)
        return worker

    monkeypatch.setattr(docker_experiment.os, 'pipe', pipe)
    monkeypatch.setattr(docker_experiment.subprocess, 'Popen', popen)
    monkeypatch.setattr(docker_experiment.threading, 'Thread', thread)
    caller, downstream = socket.socketpair()
    try:
        with pytest.raises(RuntimeError, match='controlled setup failure'):
            docker_experiment._run_jev_forwarder([shutil.which('node') or 'node', '-e', 'process.stdin.resume()'],
                input=b'local fixture', env={key: value for key, value in os.environ.items() if key in ('PATH', 'HOME')},
                capture_output=True, timeout=35, downstream=downstream)
        assert all(child.poll() is not None for child in children)
        for descriptor in pipes:
            with pytest.raises(OSError):
                os.fstat(descriptor)
    finally:
        caller.close()
        downstream.close()


def test_actual_wire_memory_discovery_observation_ignores_user_claims_and_retains_no_text() -> None:
    from docker_experiment import model_prompt_observation
    private = 'PRIVATE_MEMORY_METADATA_NOT_FOR_TELEMETRY'
    system = '<project_memory_protocol>Read relevant entries</project_memory_protocol>\n<project_memory_discovery>' + private + '</project_memory_discovery>'
    base = {'messages': [{'role': 'system', 'content': system}], 'reasoning_effort': 'medium'}
    observed = model_prompt_observation(base)
    assert observed['memoryDiscoveryOnWire'] and observed['memoryProtocolOnWire']
    assert observed['reasoningEffortOnWire'] == 'medium'
    # Given a native max effort request, retain its fixed label without
    # treating absent or unrecognized values as known effort.
    assert model_prompt_observation({'reasoning_effort': 'max'})['reasoningEffortOnWire'] == 'max'
    assert model_prompt_observation({})['reasoningEffortOnWire'] == 'other-or-absent'
    assert len(observed['systemTextSha256']) == 64
    assert private not in json.dumps(observed)
    assert model_prompt_observation({'messages': [{'role': 'user', 'content': system}]})['memoryDiscoveryOnWire'] is False
    assert model_prompt_observation({'messages': [{'role': 'developer', 'content': [{'type': 'text', 'text': system}]}]})['memoryDiscoveryOnWire'] is True
    assert model_prompt_observation({'messages': [{'role': 'system', 'content': private}]})['systemTextSha256'] != observed['systemTextSha256']
    assert model_prompt_observation({'reasoning_effort': private})['reasoningEffortOnWire'] == 'other-or-absent'
    responses = {'instructions': system, 'input': [{'type': 'message', 'role': 'developer', 'content': [{'type': 'input_text', 'text': private}]}], 'reasoning': {'effort': 'high'}}
    actual = model_prompt_observation(responses, responses=True)
    expected = model_prompt_observation({'messages': [{'role': 'system', 'content': system}, {'role': 'developer', 'content': private}], 'reasoning_effort': 'high'})
    assert actual == expected
    assert private not in json.dumps(actual)
    assert model_prompt_observation({'input': system}, responses=True)['memoryDiscoveryOnWire'] is False
    assert model_prompt_observation({'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': system}]}]}, responses=True)['memoryDiscoveryOnWire'] is False
    assert model_prompt_observation({'input': [{'type': 'function_call_output', 'role': 'developer', 'content': system, 'output': system}]}, responses=True)['memoryDiscoveryOnWire'] is False
    assert model_prompt_observation({'input': [{'role': 'developer', 'content': [{'type': 'input_text', 'text': system}]}]}, responses=True)['memoryDiscoveryOnWire'] is True
    assert model_prompt_observation({'instructions': private, 'reasoning': {'effort': private}}, responses=True)['reasoningEffortOnWire'] == 'other-or-absent'
    assert model_prompt_observation({'instructions': system}, responses=False)['memoryDiscoveryOnWire'] is False


@pytest.mark.parametrize('budget, expected', [(None, 3), (0, 0), (1, 1)])
def test_explicit_unlimited_proxy_retains_every_request_and_zero_preflight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, budget: int | None, expected: int) -> None:
    # Given unlimited paid admission or zero-call preflight, When calls arrive,
    # Then None admits all and zero admits none; closing still settles exactly.
    root = tmp_path / 'host'
    root.mkdir()
    (root / 'memory.json').write_text(json.dumps({'provider':'fixture','model':'selected'}))
    (root / 'models.json').write_text(json.dumps({'providers':{'fixture':{
        'apiKey':'LOCAL_MODEL_FIXTURE','baseUrl':'https://example.invalid/v1',
        'models':[{'id':'selected'}]}}}))
    upstream = []
    def forward(args, **kwargs):
        upstream.append(args)
        answer = {'model':'jev-1.13.0','usage':{'input_tokens':23,'output_tokens':1}}
        return subprocess.CompletedProcess(args, 0, json.dumps({'status':200,'body':json.dumps(answer)}).encode(), b'')
    monkeypatch.setattr(docker_experiment.subprocess, 'run', forward)
    monkeypatch.setattr(docker_experiment, '_run_jev_forwarder',
                        lambda args, **kwargs: (forward(args, **{k: v for k, v in kwargs.items() if k != 'downstream'}), False))
    with InferenceProxy(root, request_budget=budget, jev_key='LOCAL_JEV_FIXTURE', jev_transport='node-https') as proxy:
        statuses = []
        for _ in range(3):
            connection = http.client.HTTPConnection('127.0.0.1', proxy.server.server_address[1], timeout=5)
            try:
                connection.request('POST','/jev/v1/systemone',b'{"model":"jev-1.13.0"}',headers={'Authorization':f'Bearer {proxy.token}'})
                response = connection.getresponse()
                statuses.append(response.status)
                response.read()
            finally:
                connection.close()
        assert statuses == [200]*expected + [429]*(3-expected)
        assert proxy.requests == proxy.jev_requests == len(upstream) == expected
        assert len(proxy.jev_usage) == expected
        assert len(proxy.jev_observations) == (3 if budget is None else min(budget, 3))
        assert proxy.request_budget == budget
    assert proxy.transport_quiescent and proxy.active_requests == 0
    assert proxy.request_budget == proxy.requests == expected


@pytest.mark.parametrize('mode', ['exact', 'request-secret', 'response-secret', 'unsafe-answer', 'oversize', 'budget-zero', 'write-failed', 'buffer-full', 'connection-failed', 'cancel-after-response'])
def test_opt_in_jev_envelopes_preserve_exact_buffers_without_changing_transport(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    # Given explicit public-study capture, When an actual local proxy forwards
    # one admitted request, Then retain safe complete buffers after quiescence.
    import hashlib
    root = tmp_path / 'host'
    root.mkdir()
    (root / 'memory.json').write_text(json.dumps({'provider':'fixture','model':'selected'}))
    (root / 'models.json').write_text(json.dumps({'providers':{'fixture':{
        'apiKey':'MODEL_SECRET','baseUrl':'https://example.invalid/v1','models':[{'id':'selected'}]}}}))
    payload = json.dumps({'model':'jev-1.14.0','state':'public source ' + ('MODEL_SECRET' if mode == 'request-secret' else 'x' * (2_097_153 if mode == 'oversize' else 20)),
        'questions':{'support':{'type':'choice','instructions':'Is the observation supported?', 'criteria':{'grounded':'Supported','unsupported':'Not supported'}}}}, ensure_ascii=False).encode()
    answer = {'model':'jev-1.14.0','usage':{'input_tokens':17,'output_tokens':3},
        'answers':{'support':{'type':'choice','choice':'grounded','confidence':1,'probabilities':{'grounded':1,'unsupported':0}}}}
    if mode in ('response-secret', 'unsafe-answer'):
        answer['message'] = 'MODEL_SECRET' if mode == 'response-secret' else 'UNRECOGNIZED_SECRET'
    raw_answer = json.dumps(answer, indent=1).encode()
    forwarded = []
    def forward(args, **kwargs):
        forwarded.append(kwargs['input'])
        if mode == 'connection-failed':
            return subprocess.CompletedProcess(args, 0, b'{"transportFailure":"connection-reset"}', b'')
        return subprocess.CompletedProcess(args, -15 if mode == 'cancel-after-response' else 0,
                                           json.dumps({'status':200,'body':raw_answer.decode()}).encode(), b'')
    monkeypatch.setattr(docker_experiment.subprocess, 'run', forward)
    monkeypatch.setattr(docker_experiment, '_run_jev_forwarder',
                        lambda args, **kwargs: (forward(args, **{k: v for k, v in kwargs.items() if k != 'downstream'}), mode == 'cancel-after-response'))
    if mode == 'buffer-full':
        monkeypatch.setattr(docker_experiment, 'MAX_JEV_CAPTURE_TOTAL_BYTES', 1)
    proxy = InferenceProxy(root, jev_key='HOST_JEV_SECRET', jev_model='jev-1.14.0', jev_transport='node-https',
        request_budget=0 if mode == 'budget-zero' else 1, retain_jev_envelopes=True)
    output = tmp_path / 'private-envelopes'
    with proxy:
        assert proxy.write_jev_envelopes(output)['status'] == 'not-quiescent'
        assert not output.exists()
        connection = http.client.HTTPConnection('127.0.0.1', proxy.server.server_address[1], timeout=5)
        connection.request('POST','/jev/v1/systemone',payload,headers={'Authorization':f'Bearer {proxy.token}'})
        if mode == 'connection-failed':
            with pytest.raises(http.client.RemoteDisconnected):
                connection.getresponse()
        else:
            response = connection.getresponse()
            assert response.status == (429 if mode == 'budget-zero' else 200)
            response.read()
        connection.close()
    if mode == 'write-failed':
        output.mkdir()
        (output / 'unrelated').write_text('keep')
    result = proxy.write_jev_envelopes(output)
    assert proxy.transport_quiescent
    assert proxy.requests == proxy.jev_requests == len(forwarded) == (0 if mode == 'budget-zero' else 1)
    assert forwarded == ([] if mode == 'budget-zero' else [payload])
    assert proxy.jev_usage == ([] if mode in ('budget-zero','connection-failed') else [{'model':'jev-1.14.0','input_tokens':17,'output_tokens':3}])
    if mode == 'cancel-after-response':
        assert proxy.jev_observations[0]['callerCancellation'] == 'downstream-reset'
        assert 'usageUnknown' not in proxy.jev_observations[0]
    if mode == 'write-failed':
        assert result['status'] == 'write-failed' and (output / 'unrelated').read_text() == 'keep'
        repeated = tmp_path / 'repeat-after-failure'
        assert proxy.write_jev_envelopes(repeated)['status'] == 'already-attempted'
        assert not repeated.exists()
        return
    assert result['status'] == 'written'
    assert output.stat().st_mode & 0o077 == 0
    bodies = {f.name:f.read_bytes() for f in output.iterdir()}
    assert all((output / name).stat().st_mode & 0o077 == 0 for name in bodies)
    assert all(secret not in data for data in bodies.values() for secret in (b'MODEL_SECRET', b'HOST_JEV_SECRET', b'UNRECOGNIZED_SECRET', proxy.token.encode()))
    if mode == 'budget-zero':
        assert not bodies and result['admittedExchanges'] == 0
        return
    captured = proxy.jev_observations[0]['envelopeCapture']
    assert captured['request']['sha256'] == hashlib.sha256(payload).hexdigest()
    if mode == 'connection-failed':
        assert captured['response']['status'] == 'unavailable'
        assert captured['response']['reason'] == 'no-complete-proxy-response'
        assert not result['complete'] and proxy.errors == 1
        assert bodies[captured['request']['file']] == payload
        return
    assert captured['response']['sha256'] == hashlib.sha256(raw_answer).hexdigest()
    assert captured['exactUpstreamTlsBytes'] is False
    request_kept = mode not in ('request-secret', 'oversize', 'buffer-full')
    response_kept = mode not in ('response-secret', 'unsafe-answer', 'buffer-full')
    assert (captured['request']['status'] == 'retained') == request_kept
    assert (captured['response']['status'] == 'retained') == response_kept
    if request_kept:
        assert bodies[captured['request']['file']] == payload
    if response_kept:
        assert bodies[captured['response']['file']] == raw_answer
    assert result['complete'] == (request_kept and response_kept)
    if mode == 'exact':
        repeated = tmp_path / 'repeat-after-success'
        again = proxy.write_jev_envelopes(repeated)
        assert again['status'] == 'already-attempted' and again['complete'] is False
        assert not repeated.exists()


def _study_freeze_fixture(tmp_path: Path):
    import importlib.util
    script = Path(__file__).resolve().parents[1] / 'scripts/freeze-correction-study-source.py'
    spec = importlib.util.spec_from_file_location('study_freeze_contract', script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / 'source'
    for name in ('continual-learning', 'kit'):
        root = source / 'packages' / name
        root.mkdir(parents=True)
        (root / 'index.ts').write_text('export {};\n')
    sdk = source / module.SDK_RELATIVE
    sdk.mkdir(parents=True)
    (sdk / 'index.js').write_text('export {};\n')
    parser = source / 'packages/continual-learning/node_modules/@babel/parser'
    (parser / 'lib').mkdir(parents=True)
    (parser / 'package.json').write_text('{"main":"./lib/index.js"}\n')
    (parser / 'lib/index.js').write_text('exports.parse = () => ({});\n')
    module.REPO = source
    return module, source, tmp_path / 'frozen'


def test_frozen_study_source_binds_the_native_kit_dependency(tmp_path: Path) -> None:
    # Given local dependencies, When frozen, Then exact kit resolution is required.
    module, source, destination = _study_freeze_fixture(tmp_path)
    files, native = module.freeze(destination)
    module.verify(destination, files, native)
    manifest = json.loads((destination / 'native-dependency-bindings.json').read_text())
    kit = destination / 'packages/kit'
    link = destination / 'packages/continual-learning/node_modules/@fradser/pi-kit'
    assert manifest['kitRoot'] == str(kit)
    parser_entry = 'packages/continual-learning/node_modules/@babel/parser/lib/index.js'
    assert parser_entry in native
    assert (destination / parser_entry).read_bytes() == (source / parser_entry).read_bytes()
    assert link.is_symlink() and link.resolve() == kit.resolve()
    assert not Path(link.readlink()).is_absolute()
    assert not link.parent.stat().st_mode & 0o222
    link.parent.chmod(0o755)
    link.unlink()
    link.symlink_to(source / 'packages/kit', target_is_directory=True)
    with pytest.raises(SystemExit, match='kit dependency'):
        module.verify(destination, files, native)


@pytest.mark.parametrize('missing', ['sdk', 'kit', 'kit-entry', 'parser', 'parser-entry'])
def test_frozen_study_refuses_missing_dependencies(tmp_path: Path, missing: str) -> None:
    # Given incomplete dependencies, When freezing, Then no verified freeze exists.
    import shutil
    module, source, destination = _study_freeze_fixture(tmp_path)
    if missing == 'sdk':
        shutil.rmtree(source / module.SDK_RELATIVE)
    elif missing == 'parser':
        shutil.rmtree(source / 'packages/continual-learning/node_modules/@babel/parser')
    elif missing == 'parser-entry':
        (source / 'packages/continual-learning/node_modules/@babel/parser/lib/index.js').unlink()
    elif missing == 'kit':
        shutil.rmtree(source / 'packages/kit')
    else:
        (source / 'packages/kit/index.ts').unlink()
    with pytest.raises(SystemExit, match='dependency'):
        module.freeze(destination)
    assert not destination.exists()


@pytest.mark.parametrize('symlink', [False, True])
@pytest.mark.parametrize('dependency', ['sdk', 'parser'])
def test_frozen_study_refuses_unbound_native_entries(tmp_path: Path, symlink: bool, dependency: str) -> None:
    # Given a verified SDK inventory, When a file/link is added, Then reverify fails.
    module, source, destination = _study_freeze_fixture(tmp_path)
    files, native = module.freeze(destination)
    relative = module.SDK_RELATIVE if dependency == 'sdk' else Path('packages/continual-learning/node_modules/@babel/parser')
    sdk = destination / relative
    sdk.chmod(0o755)
    extra = sdk / 'unbound.js'
    if symlink:
        entry = source / relative / ('index.js' if dependency == 'sdk' else 'lib/index.js')
        extra.symlink_to(entry)
    else:
        extra.write_text('export {};\n')
        extra.chmod(0o444)
    with pytest.raises(SystemExit, match='native'):
        module.verify(destination, files, native)


@pytest.mark.parametrize('expected_api', [None, 'openai-responses', 'openai-completions'])
def test_expected_model_api_pins_route_before_admission_and_keeps_jev(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, expected_api: str | None) -> None:
    # Given explicit model API metadata (overriding the provider), only its
    # pinned model route may spend admission. Jev keeps its independent path.
    observed: list[dict] = []
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:pass
        def do_POST(self) -> None:
            raw=self.rfile.read(int(self.headers['Content-Length']))
            observed.append({'path':self.path,'raw':raw})
            self.send_response(200);self.end_headers()
            self.wfile.write(b'{"model":"jev-1.13.0","usage":{"input_tokens":1,"output_tokens":1},"answers":{}}')
    upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream)
    thread=threading.Thread(target=upstream.serve_forever,daemon=True);thread.start()
    root=tmp_path/'config';root.mkdir()
    (root/'memory.json').write_text(json.dumps({'provider':'fixture','model':'selected'}))
    effective=expected_api or 'openai-completions'
    provider_api='openai-responses' if effective=='openai-completions' else 'openai-completions'
    (root/'models.json').write_text(json.dumps({'providers':{'fixture':{'apiKey':'LOCAL_FIXTURE_KEY',
        'baseUrl':f'http://127.0.0.1:{upstream.server_address[1]}/v1','api':provider_api,
        'models':[{'id':'selected','api':effective}]}}}))
    monkeypatch.setattr(docker_experiment.http.client,'HTTPSConnection',
        lambda *_args,**_kwargs:http.client.HTTPConnection('127.0.0.1',upstream.server_address[1],timeout=5))
    try:
        with InferenceProxy(root,jev_key='LOCAL_JEV_KEY',expected_api=expected_api) as proxy:
            def request(route: str, payload: bytes) -> int:
                connection=http.client.HTTPConnection('127.0.0.1',proxy.server.server_address[1],timeout=2)
                try:
                    connection.request('POST',route,payload,headers={'Authorization':f'Bearer {proxy.token}'})
                    response=connection.getresponse();response.read();return response.status
                finally:connection.close()
            routes={'openai-responses':'/v1/responses','openai-completions':'/v1/chat/completions'}
            body=b'{"model":"selected","input":"complete local wire"}'
            if expected_api is not None:
                wrong=routes[provider_api]
                for _ in range(4):assert proxy.slots.acquire(blocking=False)
                try:assert request(wrong,body)==403
                finally:
                    for _ in range(4):proxy.slots.release()
                assert observed==[] and proxy.requests==proxy.active_requests==proxy.errors==0
                assert proxy.model_route_refusals=={wrong:1}
                admitted=[routes[expected_api]]
            else:admitted=list(routes.values())
            for route in admitted:assert request(route,body)==200
            assert [row['path'] for row in observed]==admitted
            assert all(row['raw']==body for row in observed)
            assert [row['route'] for row in proxy.model_observations]==admitted
            assert proxy.effective_api==effective
            before=proxy.requests
            assert request('/jev/v1/systemone',b'{"model":"jev-1.13.0"}')==200
            assert proxy.requests==before+1 and proxy.jev_requests==1 and proxy.errors==0
            assert observed[-1]['path']=='/v1/systemone'
    finally:upstream.shutdown();upstream.server_close();thread.join(timeout=5)


@pytest.mark.parametrize('provider_api,model_api,expected_api,accepted',[
    ('openai-responses',None,'openai-responses',True),
    ('openai-completions','openai-responses','openai-responses',True),
    ('openai-responses','openai-completions','openai-responses',False),
    ('openai-completions',None,'openai-responses',False),
    (None,None,'openai-responses',False),
    ('openai-responses',None,'unknown-api',False)])
def test_expected_model_api_validates_effective_model_precedence_before_start(tmp_path: Path, provider_api: str | None, model_api: str | None, expected_api: str, accepted: bool) -> None:
    (tmp_path/'memory.json').write_text('{"provider":"fixture","model":"selected"}')
    provider={'apiKey':'LOCAL_FIXTURE_KEY','baseUrl':'http://127.0.0.1:1/v1',
        'models':[{'id':'selected',**({'api':model_api} if model_api else {})}],**({'api':provider_api} if provider_api else {})}
    (tmp_path/'models.json').write_text(json.dumps({'providers':{'fixture':provider}}))
    if accepted:
        with InferenceProxy(tmp_path,expected_api=expected_api) as proxy:
            assert proxy.effective_api==expected_api and proxy.requests==0
    else:
        with pytest.raises(ValueError):InferenceProxy(tmp_path,expected_api=expected_api)


@pytest.mark.parametrize('api,route', [
    ('openai-responses', '/v1/responses'),
    ('openai-completions', '/v1/chat/completions'),
])
@pytest.mark.parametrize('credential', ['HOST_ONLY_SECRET', '33'])
def test_model_retry_after_reaches_http_client_without_proxy_retry(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, api: str, route: str, credential: str) -> None:
    # Given gateway failures, When forwarding through the real HTTP proxy,
    # Then only valid end-to-end retry advice reaches the unchanged client.
    cases = [
        (503, [('Retry-After', '33')], '33'),
        (429, [('retry-after', '0')], '0'),
        (503, [('Retry-After', 'Wed, 21 Oct 2037 07:28:00 GMT')], 'Wed, 21 Oct 2037 07:28:00 GMT'),
        (503, [('Retry-After', 'Sunday, 06-Nov-94 08:49:37 GMT')], 'Sunday, 06-Nov-94 08:49:37 GMT'),
        (503, [('Retry-After', 'Sun Nov  6 08:49:37 1994')], 'Sun Nov  6 08:49:37 1994'),
        (503, [], None),
        (503, [('Retry-After', '-1')], None),
        (503, [('Retry-After', '1.5')], None),
        (503, [('Retry-After', 'not a date')], None),
        (503, [('Retry-After', 'Wed, 99 Oct 2037 07:28:00 GMT')], None),
        (503, [('Retry-After', 'Wed, 21 Oct 2037 07:28:00 GMT extra')], None),
        (503, [('Retry-After', '9' * 129)], None),
        (503, [('Retry-After', '33\r\n X-Injected: secret')], None),
        (503, [('Retry-After', 'HOST_ONLY_SECRET')], None),
        (503, [('Retry-After', 'Wed, 21 Oct 2037 07:28:00 GMT (HOST_ONLY_SECRET)')], None),
        (503, [('Retry-After', '33'), ('Retry-After', '44')], None),
        (503, [('Retry-After', '33'), ('Connection', 'keep-alive, Retry-After')], None),
    ]
    observed: list[tuple[str, bytes]] = []
    upstream_body = json.dumps({'error': {'code': 'internal_server_error', 'message': credential}}).encode()
    expected_body = upstream_body.replace(credential.encode(), b'[redacted]')

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_POST(self) -> None:
            index = len(observed)
            observed.append((self.path, self.rfile.read(int(self.headers['Content-Length']))))
            status, headers, _expected = cases[index] if index < len(cases) else (503, [('Retry-After', '33')], None)
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('X-Private', 'HOST_ONLY_SECRET')
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(upstream_body)

    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    (tmp_path / 'memory.json').write_text('{"provider":"fixture","model":"selected"}')
    (tmp_path / 'models.json').write_text(json.dumps({'providers': {'fixture': {
        'apiKey': credential, 'baseUrl': f'http://127.0.0.1:{upstream.server_address[1]}/v1',
        'api': api, 'models': [{'id': 'selected'}],
    }}}))
    monkeypatch.setattr(docker_experiment.http.client, 'HTTPSConnection',
        lambda *_args, **_kwargs: http.client.HTTPConnection('127.0.0.1', upstream.server_address[1], timeout=5))
    try:
        with InferenceProxy(tmp_path, jev_key='LOCAL_JEV_KEY', expected_api=api,
                            request_budget=len(cases) + 1) as proxy:
            body = b'{"model":"selected","input":[]}' if api == 'openai-responses' else b'{"model":"selected","messages":[]}'

            def request(path: str, payload: bytes) -> tuple[int, dict[str, str], bytes]:
                connection = http.client.HTTPConnection('127.0.0.1', proxy.server.server_address[1], timeout=5)
                try:
                    connection.request('POST', path, payload, headers={'Authorization': f'Bearer {proxy.token}'})
                    response = connection.getresponse()
                    return response.status, dict(response.getheaders()), response.read()
                finally:
                    connection.close()

            for index, (status, _headers, expected) in enumerate(cases):
                actual_status, headers, data = request(route, body)
                assert actual_status == status and data == expected_body
                if expected is not None and credential in expected:
                    expected = None
                assert headers.get('Retry-After') == expected
                assert headers.get('Connection') == 'close' and 'X-Private' not in headers
                assert headers.get('Retry-After') != credential
                assert observed == [(route, body)] * (index + 1)
                assert proxy.requests == index + 1 and proxy.errors == index + 1

            # Jev's existing one-attempt policy receives no new retry hint.
            status, headers, data = request('/jev/v1/systemone', b'{"model":"jev-1.13.0"}')
            assert status == 503 and data == expected_body and 'Retry-After' not in headers
            assert proxy.jev_requests == 1 and proxy.requests == len(cases) + 1
            assert request(route, body)[0] == 429
            assert len(observed) == len(cases) + 1 and proxy.requests == len(cases) + 1
            assert proxy.wait_for_quiescence(timeout=2)
    finally:
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=5)
