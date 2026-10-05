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
            proxy.requests = 180
            assert request("/v1/chat/completions", {"model": "selected"})[0] == 429
            assert len(observed) == 1
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


def test_real_jev_proxy_route_and_model_stream_do_not_compete_for_slots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[dict] = []
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass
        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            observed.append({'path': self.path, 'auth': self.headers.get('Authorization'), 'model': body['model']})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({'model': 'jev-1.13.0', 'usage': {'input_tokens': 123, 'output_tokens': 4}, 'answers': {}}).encode())
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
        with InferenceProxy(root, jev_key='HOST_JEV_SECRET') as proxy:
            # Holding every model-stream slot must not induce a fake Jev failure.
            for _ in range(4):
                assert proxy.slots.acquire(blocking=False)
            connection = http.client.HTTPConnection('127.0.0.1', proxy.server.server_address[1], timeout=5)
            connection.request('POST', '/jev/v1/systemone', json.dumps({'model': 'jev-1.13.0', 'state': 'public fixture', 'questions': {}}),
                               headers={'Authorization': f'Bearer {proxy.token}'})
            response = connection.getresponse()
            assert response.status == 200
            response.read()
            connection.close()
            for _ in range(4):
                proxy.slots.release()
            assert proxy.jev_requests == 1 and proxy.errors == 0
            assert proxy.jev_usage == [{'model': 'jev-1.13.0', 'input_tokens': 123, 'output_tokens': 4}]
            assert observed == [{'path': '/v1/systemone', 'auth': 'Bearer HOST_JEV_SECRET', 'model': 'jev-1.13.0'}]
    finally:
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=5)
