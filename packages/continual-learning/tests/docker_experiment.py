"""Host-only Docker plumbing. Real provider credentials never enter an image."""
from __future__ import annotations

import hashlib
from collections.abc import Callable
import hmac
import ipaddress
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
MAX_JEV_CAPTURE_BYTES = 2 * 1024 * 1024
MAX_JEV_CAPTURE_TOTAL_BYTES = 64 * 1024 * 1024
PROJECTS = (
    {"name": "click", "repository": "https://github.com/pallets/click.git", "commit": "06b2a678741131fd577ce170e23e5ca0aeba0309"},
    {"name": "p-limit", "repository": "https://github.com/sindresorhus/p-limit.git", "commit": "a8a6fbec4e0e866d6d779b10889bb4f5567e70eb"},
    {"name": "mitt", "repository": "https://github.com/developit/mitt.git", "commit": "6b41670516ed8e8b738612f60491995470aa63b3"},
)


def model_prompt_observation(payload: dict) -> dict[str, object]:
    """Observe actual serialized system input; retain hashes and fixed labels only."""
    texts: list[str] = []
    messages = payload.get("messages", [])
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict) or message.get("role") not in ("system", "developer"):
                continue
            content = message.get("content")
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                texts.extend(block["text"] for block in content if isinstance(block, dict)
                             and block.get("type") == "text" and isinstance(block.get("text"), str))
    effort = payload.get("reasoning_effort")
    return {
        "memoryDiscoveryOnWire": any("<project_memory_discovery>" in text and "</project_memory_discovery>" in text for text in texts),
        "memoryProtocolOnWire": any("<project_memory_protocol>" in text and "</project_memory_protocol>" in text for text in texts),
        "systemTextSha256": hashlib.sha256(json.dumps(texts, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest(),
        "reasoningEffortOnWire": effort if effort in ("none", "minimal", "low", "medium", "high", "xhigh") else "other-or-absent",
    }


def command(args: list[str], *, timeout: int = 900, sanitize: Callable[[str], str] | None = None) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        stderr = sanitize(result.stderr) if sanitize else result.stderr
        raise RuntimeError(f"{args[0]} failed ({result.returncode}): {stderr[-2000:]}")
    return sanitize(result.stdout) if sanitize else result.stdout


def memory_policy_bytes(original: bytes, policy: str) -> bytes:
    if policy == "default":
        return original
    if policy != "composed":
        raise ValueError("Unknown Memory policy")
    old = b"const jevJudge = createJevJudge();"
    enabled = b"const jevJudge = createJevJudge({ independentMemoryApplication: true, composedMemoryApplication: true });"
    per_run = b"let jevJudge: JevJudge = createJevJudge({ independentMemoryApplication: true, composedMemoryApplication: true });"
    if original.count(old) + original.count(enabled) + original.count(per_run) != 1:
        raise ValueError("Expected exactly one recognized Jev constructor")
    return original.replace(old, enabled)


def prepare_memory_policy(package: Path, policy: str) -> dict[str, str]:
    source = package / "extensions/inject-memory.ts"
    original = source.read_bytes()
    installed = memory_policy_bytes(original, policy)
    if policy == "composed":
        archive = package / "tests/fixtures/project-policy-original-inject-memory.ts.txt"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(original)
    source.write_bytes(installed)
    manifest = {"memoryPolicy": policy, "originalSha256": hashlib.sha256(original).hexdigest(),
                "installedSha256": hashlib.sha256(installed).hexdigest()}
    (package / "tests").mkdir(exist_ok=True)
    (package / "tests/project-policy-manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def verify_memory_policy(package: Path, policy: str) -> dict[str, str]:
    installed = (package / "extensions/inject-memory.ts").read_bytes()
    path = package / "tests/project-policy-manifest.json"
    if not path.exists() and policy == "default":
        assert memory_policy_bytes(installed, "composed"), "Unexpected production constructor"
        return {"memoryPolicy": policy, "installedSha256": hashlib.sha256(installed).hexdigest()}
    manifest = json.loads(path.read_text())
    assert manifest["memoryPolicy"] == policy, "Image Memory policy differs from the requested policy"
    assert manifest["installedSha256"] == hashlib.sha256(installed).hexdigest(), "Installed policy source changed"
    original = installed if policy == "default" else (package / "tests/fixtures/project-policy-original-inject-memory.ts.txt").read_bytes()
    assert hashlib.sha256(original).hexdigest() == manifest["originalSha256"], "Original policy source changed"
    assert memory_policy_bytes(original, policy) == installed, "Unexpected policy instrumentation"
    return manifest


def source_digest(memory_policy: str = "default") -> str:
    digest = hashlib.sha256()
    for root in (PACKAGE / "extensions", PACKAGE / "prompts", REPO / "packages" / "kit" / "src"):
        for file in sorted(root.rglob("*")):
            if file.is_file():
                digest.update(str(file.relative_to(REPO)).encode())
                digest.update(b"\0")
                contents = file.read_bytes()
                if file == PACKAGE / "extensions/inject-memory.ts":
                    contents = memory_policy_bytes(contents, memory_policy)
                digest.update(contents)
    for file in (PACKAGE / "index.ts", PACKAGE / "package.json", REPO / "packages" / "kit" / "package.json", REPO / "packages" / "kit" / "index.ts",
                 PACKAGE / "tests" / "docker" / "Dockerfile", PACKAGE / "tests" / "docker_experiment.py",
                 PACKAGE / "tests" / "live_docker_projects.py", PACKAGE / "tests" / "live_smoke.py", PACKAGE / "tests" / "support.py"):
        digest.update(str(file.relative_to(REPO)).encode())
        digest.update(file.read_bytes())
    catalog = PACKAGE / "tests" / "heldout_project_catalog.py"
    digest.update(str(catalog.relative_to(REPO)).encode())
    digest.update(catalog.read_bytes())
    return digest.hexdigest()


def build_image(memory_policy: str = "default") -> tuple[str, str]:
    digest = source_digest(memory_policy)
    image = f"continual-learning-projects:{digest[:16]}"
    with tempfile.TemporaryDirectory(prefix="cl-docker-build-") as temporary:
        context = Path(temporary)
        for name in ("kit", "continual-learning"):
            shutil.copytree(REPO / "packages" / name, context / "packages" / name,
                            ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".pytest_cache", ".memory", ".pi", ".git", ".jev-*"))
        prepare_memory_policy(context / "packages/continual-learning", memory_policy)
        (context / "package.json").write_text(json.dumps({
            "private": True, "type": "module", "packageManager": "pnpm@11.21.0",
            "dependencies": {"@earendil-works/pi-coding-agent": "1.3.0", "@earendil-works/pi-ai": "1.3.0", "@earendil-works/pi-tui": "1.3.0", "tsx": "4.19.0"},
        }))
        (context / "pnpm-workspace.yaml").write_text('packages:\n  - packages/*\noverrides:\n  "@earendil-works/pi-coding-agent": 1.3.0\n  "@earendil-works/pi-ai": 1.3.0\n  "@earendil-works/pi-agent-core": 1.3.0\n  "@earendil-works/pi-codemode": 1.3.0\n  "@earendil-works/pi-mcp": 1.3.0\n  "@earendil-works/pi-telemetry": 1.3.0\n  "@earendil-works/pi-tui": 1.3.0\nallowBuilds:\n  esbuild: true\n  "@google/genai": true\n  protobufjs: true\n')
        shutil.copyfile(PACKAGE / "tests" / "docker" / "Dockerfile", context / "Dockerfile")
        command(["docker", "build", "--tag", image, str(context)], timeout=1200)
    return image, digest


class InferenceProxy:
    """Transparent streaming transport, not a provider fixture or model stub."""

    def __init__(self, config_root: Path, *, jev_key: str | None = None, request_budget: int | None = 180,
                 selection: dict[str, str] | None = None, jev_transport: str = "python-http", jev_model: str = "jev-1.13.0",
                 max_request_bytes: int | None = None, jev_resolved_address: str | None = None,
                 retain_jev_envelopes: bool = False) -> None:
        if jev_resolved_address is not None:
            try:
                address = ipaddress.IPv4Address(jev_resolved_address)
            except ipaddress.AddressValueError as error:
                raise ValueError("Jev route requires a public IPv4 literal") from error
            if not address.is_global or address.is_multicast or address.is_reserved or jev_transport not in ("bun-fetch", "node-https"):
                raise ValueError("Jev route requires a public IPv4 literal and explicit HTTPS transport")
        if jev_model not in ("jev-1.13.0", "jev-1.14.0"):
            raise ValueError("Unknown fixed Jev study model")
        self.jev_model = jev_model
        self.jev_resolved_address = jev_resolved_address
        if jev_transport not in ("python-http", "bun-fetch", "node-https"):
            raise ValueError("Unknown Jev transport")
        if max_request_bytes is not None and max_request_bytes <= 0:
            raise ValueError("max_request_bytes must be positive")
        self.max_request_bytes = max_request_bytes
        self.jev_transport = jev_transport
        if retain_jev_envelopes and jev_transport != "node-https":
            raise ValueError("Exact study envelope capture requires the reviewed Node forwarder")
        self.retain_jev_envelopes = retain_jev_envelopes
        self.jev_envelope_buffers: list[tuple[dict, bytes]] = []
        self._jev_envelope_write_attempted = False
        self.jev_envelope_bytes = 0
        self.request_budget = request_budget
        self.jev_requests = 0
        self.jev_usage: list[dict] = []
        self.jev_observations: list[dict] = []
        self.model_observations: list[dict] = []
        self.jev_key = jev_key
        self.selection = dict(selection) if selection is not None else json.loads((config_root / "memory.json").read_text())
        provider = json.loads((config_root / "models.json").read_text())["providers"][self.selection["provider"]]
        self.upstream = urlsplit(provider["baseUrl"])
        if self.upstream.scheme not in {"http", "https"} or not self.upstream.hostname:
            raise ValueError("Unsupported configured inference URL")
        key = provider.get("apiKey", "")
        if not isinstance(key, str) or not key or key.startswith("!"):
            raise ValueError("Experiment proxy requires the configured literal or environment API key")
        self.key = os.environ.get(key, key)
        self.token = secrets.token_urlsafe(32)
        self.slots = threading.BoundedSemaphore(4)
        self.jev_slots = threading.BoundedSemaphore(12)
        self.requests = 0
        self.errors = 0
        self.counter_lock = threading.RLock()
        self.active_requests = 0
        self.quiescence = threading.Condition(self.counter_lock)
        selected_model = next(model for model in provider["models"] if model["id"] == self.selection["model"])
        self.model = {name: value for name, value in selected_model.items()
                      if name in {"id", "name", "api", "contextWindow", "maxTokens", "input", "cost", "reasoning", "compat", "thinkingLevelMap"}}
        self.public_provider = {name: value for name, value in provider.items() if name in {"name", "api", "compat"}}
        self.headers = provider.get("headers", {})
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self) -> None:
                super().setup()
                self.connection.settimeout(30)

            def log_message(self, *_args: object) -> None:
                pass

            def do_POST(self) -> None:
                is_jev = self.path == "/jev/v1/systemone" and owner.jev_key is not None
                if not is_jev and self.path not in {"/v1/chat/completions", "/v1/responses"}:
                    self.send_error(404)
                    return
                if not hmac.compare_digest(self.headers.get("Authorization", "").encode(), f"Bearer {owner.token}".encode()):
                    self.send_error(401)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or (owner.max_request_bytes is not None and length > owner.max_request_bytes):
                        self.send_error(413)
                        return
                    body = self.rfile.read(length)
                    payload = json.loads(body)
                    if not isinstance(payload, dict) or payload.get("model") != (owner.jev_model if is_jev else owner.selection["model"]):
                        self.send_error(403)
                        return
                except (ValueError, json.JSONDecodeError):
                    self.send_error(400)
                    return
                slots = owner.jev_slots if is_jev else owner.slots
                if not slots.acquire(timeout=5):
                    with owner.counter_lock:
                        owner.record_error()
                    self.send_error(429)
                    return
                connection: http.client.HTTPConnection | None = None
                started = time.monotonic()
                observation = None
                admitted = False
                captured_response = None
                if is_jev:
                    observation = {'wireHash': hashlib.sha256(body).hexdigest(), 'wireBytes': len(body), 'status': 'running', 'longContext': self.headers.get('TypeSafe-Danger-Zone-Long-Context') == 'true'}
                    with owner.counter_lock:
                        if owner.request_budget is None or len(owner.jev_observations) < owner.request_budget:
                            owner.jev_observations.append(observation)
                try:
                    with owner.counter_lock:
                        if owner.request_budget is not None and owner.requests >= owner.request_budget:
                            if observation is not None:
                                observation['status'] = 'budget-exhausted'
                            self.send_error(429, "Experiment request budget exhausted")
                            return
                        owner.requests += 1
                        owner.active_requests += 1
                        admitted = True
                        if is_jev:
                            owner.jev_requests += 1
                            observation['request'] = owner.requests
                        elif owner.request_budget is None or len(owner.model_observations) < owner.request_budget:
                            messages = payload.get('messages', [])
                            tools = payload.get('tools', [])
                            choice = payload.get('tool_choice')
                            response_format = payload.get('response_format')
                            response_format = response_format if isinstance(response_format, dict) else {}
                            format_type = response_format.get('type')
                            schema = response_format.get('json_schema')
                            schema = schema if format_type == 'json_schema' and isinstance(schema, dict) else {}
                            schema_name = schema.get('name')
                            owner.model_observations.append({'request': owner.requests,
                                **model_prompt_observation(payload),
                                'toolCount': len(tools) if isinstance(tools, list) else None,
                                'toolChoice': choice if choice in ('none', 'auto', 'required') else 'other-or-absent',
                                'messageCount': len(messages) if isinstance(messages, list) else None,
                                'retainedToolResults': sum(isinstance(m, dict) and m.get('role') == 'tool' for m in messages) if isinstance(messages, list) else None,
                                'responseFormatType': format_type if format_type in ('json_object', 'json_schema') else 'other-or-absent',
                                'responseSchemaName': schema_name if schema_name in ('memory_selector', 'memory_delta', 'memory_amendment') else 'other-or-absent',
                                'responseSchemaStrict': schema.get('strict') is True})
                    if is_jev and owner.jev_transport in ("bun-fetch", "node-https"):
                        forward_env = {key: value for key, value in os.environ.items() if key in
                                       ("PATH", "HOME", "SSL_CERT_FILE", "SSL_CERT_DIR", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "NO_PROXY")}
                        if owner.jev_transport == "node-https":
                            forward_env = {key: value for key, value in forward_env.items() if key in ("PATH", "HOME")}
                        if self.headers.get("TypeSafe-Danger-Zone-Long-Context") == "true":
                            forward_env["JEV_LONG_CONTEXT"] = "true"
                        forward_env["TYPESAFE_API_KEY"] = owner.jev_key
                        forward_env["JEV_MODEL"] = owner.jev_model
                        if owner.jev_resolved_address is not None:
                            forward_env["JEV_RESOLVED_ADDRESS"] = owner.jev_resolved_address
                        runtime = "node" if owner.jev_transport == "node-https" else "bun"
                        script = "jev-https-forward.mjs" if runtime == "node" else "jev-http-forward.mjs"
                        forwarded = subprocess.run([shutil.which(runtime) or runtime, str(Path(__file__).with_name(script))],
                                                   input=body, env=forward_env, capture_output=True, timeout=35)
                        if forwarded.returncode:
                            observation['status'] = 'forwarder-error'
                            raise OSError("Host Jev forwarder failed")
                        value = json.loads(forwarded.stdout)
                        phase = value.get("transportObservation")
                        if isinstance(phase, dict) and all(type(phase.get(key)) is bool for key in
                                ("tcpConnected", "tlsVerified", "responseHeaders", "ownAbort")) and type(phase.get("receivedBytes")) is int and 0 <= phase["receivedBytes"] <= 2**53 - 1:
                            observation["transportObservation"] = {key: phase[key] for key in
                                ("tcpConnected", "tlsVerified", "responseHeaders", "receivedBytes", "ownAbort")}
                        if value.get("transportFailure") in ("connection-timeout", "connection-reset", "connection-closed", "connection-refused",
                                                              "dns-failure", "request-timeout", "aborted", "tls-certificate-verification-failed", "transport-unavailable", "invalid-request", "redirect-not-allowed", "response-too-large"):
                            observation['status'] = 'forwarder-error'
                            observation['failureCategory'] = value['transportFailure']
                            if value.get('failureCode') in ('ETIMEDOUT', 'ECONNRESET', 'ECONNREFUSED', 'ENOTFOUND', 'EAI_AGAIN', 'CERT_HAS_EXPIRED', 'ERR_TLS_CERT_ALTNAME_INVALID', 'UNABLE_TO_VERIFY_LEAF_SIGNATURE', 'UNABLE_TO_GET_ISSUER_CERT_LOCALLY', 'SELF_SIGNED_CERT_IN_CHAIN', 'DEPTH_ZERO_SELF_SIGNED_CERT'):
                                observation['failureCode'] = value['failureCode']
                            raise OSError("Host Jev transport failed")
                        if type(value.get("status")) is not int or not 200 <= value["status"] <= 599 or not isinstance(value.get("body"), str):
                            raise ValueError("Invalid forwarding response")
                        observation['durationMs'] = round((time.monotonic() - started) * 1000)
                        observation['httpStatus'] = value['status']
                        observation['status'] = 'completed' if value['status'] < 400 else 'http-error'
                        data = value["body"].encode()
                        captured_response = data
                        if len(data) > 2 * 1024 * 1024:
                            raise ValueError("Oversized forwarding response")
                        if value["status"] < 400:
                            owner.record_jev_usage(data)
                        else:
                            owner.record_error()
                            data = data.replace(owner.key.encode(), b"[redacted]").replace(owner.jev_key.encode(), b"[redacted]")
                        self.send_response(value["status"])
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(data)))
                        self.send_header("Connection", "close")
                        self.end_headers()
                        self.close_connection = True
                        self.wfile.write(data)
                        return
                    upstream = urlsplit("https://api.typesafe.ai") if is_jev else owner.upstream
                    connection_type = http.client.HTTPSConnection if upstream.scheme == "https" else http.client.HTTPConnection
                    connection = connection_type(upstream.hostname, upstream.port, timeout=300)
                    endpoint = "/v1/systemone" if is_jev else upstream.path.rstrip("/") + self.path.removeprefix("/v1")
                    connection.request("POST", endpoint, body, headers={**({} if is_jev else owner.headers),
                        **({"TypeSafe-Danger-Zone-Long-Context": "true"} if is_jev and self.headers.get("TypeSafe-Danger-Zone-Long-Context") == "true" else {}),
                        "Authorization": f"Bearer {owner.jev_key if is_jev else owner.key}", "Content-Type": "application/json"})
                    response = connection.getresponse()
                    if observation is not None:
                        observation['durationMs'] = round((time.monotonic() - started) * 1000)
                        observation['httpStatus'] = response.status
                        observation['status'] = 'receiving' if response.status < 400 else 'http-error'
                    self.send_response(response.status)
                    self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    if response.status >= 400:
                        owner.record_error()
                        self.wfile.write(response.read(65536).replace(owner.key.encode(), b"[redacted]").replace((owner.jev_key or owner.key).encode(), b"[redacted]"))
                    else:
                        jev_body = bytearray()
                        while block := response.read1(65536):
                            if is_jev and len(jev_body) < 2 * 1024 * 1024:
                                jev_body.extend(block)
                            self.wfile.write(block)
                            self.wfile.flush()
                        if observation is not None:
                            observation['status'] = 'completed'
                        if is_jev:
                            owner.record_jev_usage(bytes(jev_body))
                except (OSError, http.client.HTTPException, ValueError, subprocess.SubprocessError) as error:
                    if observation is not None:
                        if isinstance(error, (BrokenPipeError, ConnectionResetError)):
                            observation['status'] = 'client-disconnected'
                        elif isinstance(error, subprocess.TimeoutExpired):
                            observation['status'] = 'forwarder-timeout'
                        elif observation['status'] in ('running', 'receiving'):
                            observation['status'] = 'transport-error'
                    owner.record_error()
                    self.close_connection = True
                finally:
                    if observation is not None:
                        observation['durationMs'] = round((time.monotonic() - started) * 1000)
                        if admitted and owner.retain_jev_envelopes:
                            try:
                                owner.record_jev_envelope(observation, body, payload, captured_response)
                            except Exception:
                                # Diagnostic retention must not alter usage,
                                # release, retries or transport outcomes.
                                observation.setdefault('envelopeCapture', {}).update(status='capture-error')
                    try:
                        if connection:
                            connection.close()
                    finally:
                        slots.release()
                        if admitted:
                            with owner.quiescence:
                                owner.active_requests -= 1
                                owner.quiescence.notify_all()

        self.server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> InferenceProxy:
        self.thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        # Closing the accept loop does not join daemon request handlers. Stop
        # admission under the same lock and wait for every counted operation,
        # including late usage accounting, before declaring transport complete.
        with self.counter_lock:
            self.request_budget = self.requests
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if not self.wait_for_quiescence():
            raise RuntimeError("Inference transport still active; preserve reservation")

    def wait_for_quiescence(self, timeout: float = 35) -> bool:
        with self.quiescence:
            return self.quiescence.wait_for(lambda: self.active_requests == 0, timeout=timeout)

    @property
    def transport_quiescent(self) -> bool:
        with self.counter_lock:
            return self.active_requests == 0

    def record_error(self) -> None:
        with self.counter_lock:
            self.errors += 1

    def record_jev_envelope(self, observation: dict, request: bytes, payload: dict, response: bytes | None) -> None:
        """Keep bounded authorized study buffers, never headers or auth values.

        These are exact proxy UTF-8 buffers, not arbitrary upstream TLS octets.
        Privacy screening remains required before requests reach this proxy.
        The redactor below checks known transport credentials only.
        """
        def safe_answer(data: bytes) -> bool:
            try:
                value = json.loads(data)
                if not isinstance(value, dict) or set(value) - {'model','answers','usage'} or value.get('model') != self.jev_model:
                    return False
                answers, usage = value.get('answers'), value.get('usage')
                if not isinstance(answers, dict) or not isinstance(usage, dict) or set(usage) - {'input_tokens','output_tokens'}:
                    return False
                if not all(type(v) is int and v >= 0 for v in usage.values()):
                    return False
                questions = payload.get('questions', {})
                for key, answer in answers.items():
                    question = questions.get(key)
                    if not isinstance(question, dict) or not isinstance(answer, dict) or set(answer) - {'type','choice','confidence','probabilities','noul','score','expectation'}:
                        return False
                    if answer.get('type') != question.get('type') or answer.get('type') not in ('choice','noul','score'):
                        return False
                    criteria = question.get('criteria', {})
                    if not isinstance(criteria, dict):
                        return False
                    for field, item in answer.items():
                        if field == 'type':
                            continue
                        if field == 'choice':
                            if not isinstance(item, str) or item not in criteria:
                                return False
                        elif field == 'probabilities':
                            if not isinstance(item, dict) or set(item) - set(criteria) or not all(type(v) in (int,float) and math.isfinite(v) and 0 <= v <= 1 for v in item.values()):
                                return False
                        elif type(item) not in (int,float) or not math.isfinite(item):
                            return False
                return True
            except (ValueError, TypeError, AttributeError, OverflowError, RecursionError):
                return False

        capture = {'status':'buffered','exactUpstreamTlsBytes':False,'representation':'proxy-utf8-json-buffers'}
        observation['envelopeCapture'] = capture
        for direction, data in (('request',request), ('response',response)):
            if data is None:
                capture[direction] = {'status':'unavailable','reason':'no-complete-proxy-response'}
                continue
            item = {'status':'unavailable','sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
            capture[direction] = item
            if len(data) > MAX_JEV_CAPTURE_BYTES:
                item['reason'] = 'capture-size-bound'
            elif redact_transport_bytes(data, self) != data:
                item['reason'] = 'known-transport-credential'
            elif direction == 'response' and not safe_answer(data):
                item['reason'] = 'unsafe-response-shape'
            else:
                with self.counter_lock:
                    if self.jev_envelope_bytes + len(data) > MAX_JEV_CAPTURE_TOTAL_BYTES:
                        item['reason'] = 'capture-total-bound'
                    else:
                        item.update(status='buffered',file=f"request-{observation['request']:06d}-{direction}.json")
                        self.jev_envelope_buffers.append((item,data))
                        self.jev_envelope_bytes += len(data)

    def write_jev_envelopes(self, output: Path) -> dict:
        """Write private evidence once, after admission closes and handlers settle."""
        if not self.retain_jev_envelopes:
            return {'enabled':False}
        with self.counter_lock:
            if self.active_requests != 0 or self.thread.is_alive() or self.request_budget != self.requests:
                return {'enabled':True,'status':'not-quiescent','complete':False}
            if self._jev_envelope_write_attempted:
                return {'enabled':True,'status':'already-attempted','complete':False}
            self._jev_envelope_write_attempted = True
        captures = [item['envelopeCapture'] for item in self.jev_observations if 'envelopeCapture' in item]
        result = {'enabled':True,'status':'written','admittedExchanges':len(captures),'complete':False,
                  'maxBytesPerBuffer':MAX_JEV_CAPTURE_BYTES,'maxTotalBufferBytes':MAX_JEV_CAPTURE_TOTAL_BYTES,
                  'exactUpstreamTlsBytes':False}
        try:
            output.mkdir(mode=0o700)
            for metadata, data in self.jev_envelope_buffers:
                file = output / metadata['file']
                fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
                with os.fdopen(fd, 'wb') as target:
                    target.write(data)
                if file.read_bytes() != data:
                    raise OSError('Captured envelope readback differs')
                metadata['status'] = 'retained'
            result['complete'] = len(captures) == self.jev_requests and all(
                capture.get('status') != 'capture-error' and all(capture.get(direction, {}).get('status') == 'retained'
                    for direction in ('request','response')) for capture in captures)
        except OSError:
            result['status'] = 'write-failed'
            for metadata, _data in self.jev_envelope_buffers:
                if metadata['status'] == 'buffered':
                    metadata.update(status='unavailable',reason='capture-write-failed')
        finally:
            self.jev_envelope_buffers.clear()
            self.jev_envelope_bytes = 0
            for capture in captures:
                capture['status'] = 'retained' if capture.get('status') != 'capture-error' and all(capture.get(direction, {}).get('status') == 'retained'
                    for direction in ('request','response')) else 'incomplete'
        return result

    def record_jev_usage(self, data: bytes) -> None:
        try:
            answer = json.loads(data)
            usage = answer.get("usage", {})
            if answer.get("model") in ("jev-1.13.0", "jev-1.14.0") and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("input_tokens", "output_tokens")):
                with self.counter_lock:
                    self.jev_usage.append({"model": answer["model"], **{k: usage[k] for k in ("input_tokens", "output_tokens")}})
        except (ValueError, TypeError, AttributeError):
            pass

    def jev_environment(self) -> dict[str, str]:
        if not self.jev_key:
            return {}
        return {"TYPESAFE_API_KEY": self.token,
                "TYPESAFE_BASE_URL": f"http://host.docker.internal:{self.server.server_address[1]}/jev"}

    def write_agent_config(self, root: Path) -> None:
        root.mkdir(mode=0o700)
        port = self.server.server_address[1]
        provider = {**self.public_provider, "apiKey": self.token, "models": [self.model],
                    "baseUrl": f"http://host.docker.internal:{port}/v1"}
        (root / "models.json").write_text(json.dumps({"providers": {self.selection["provider"]: provider}}))
        (root / "memory.json").write_text(json.dumps(self.selection))
        (root / "settings.json").write_text(json.dumps({"defaultProvider": self.selection["provider"],
            "defaultModel": self.selection["model"], "packages": []}))
        if self.jev_key:
            # Only public synthetic personal preferences are used in this experiment.
            (root / "continual-learning.json").write_text(json.dumps({"jev": {
                "model": self.jev_model, "allowPrivateMemory": True}}))
        for file in root.iterdir():
            file.chmod(0o600)


def redact_transport_bytes(data: bytes, proxy: InferenceProxy) -> bytes:
    for secret in (proxy.key, proxy.jev_key, proxy.token):
        if secret:
            for spelling in (secret, json.dumps(secret)[1:-1]):
                data = data.replace(spelling.encode(), b"[redacted]")
    return data


def redact_transport_credentials(text: str, proxy: InferenceProxy) -> str:
    return redact_transport_bytes(text.encode(), proxy).decode()


# Pluggability arm: remove every copy of the SDK so absence is real. The package link
# and the root link are not enough: pnpm also keeps the store copy and a hoisted
# virtual copy under node_modules/.pnpm, and a runtime that consults the hoisted
# directory would still resolve the SDK. The command then proves the removal.
ABSENT_SDK_COMMAND = (
    "find /opt/experiment -type d -name '@typesafe-ai' -prune -exec rm -rf {} + ; "
    "cd /opt/experiment/packages/continual-learning && "
    "node -e \"try{require.resolve('@typesafe-ai/sdk');console.log('sdk-present')}"
    "catch{console.log('sdk-absent')}\" ; "
    "echo copies-remaining=$(find /opt/experiment -type d -name '@typesafe-ai' | wc -l)"
)


SEAM_FILE_NAME = "fixed-memories.json"
SEAM_ENVIRONMENT = f"PI_FIXED_MEMORIES=/home/node/agent/{SEAM_FILE_NAME}"


def fixed_memory_seam(source: str | None, directory: str | None, project: str) -> tuple[str | None, tuple[str, str] | None]:
    """The attribution seam as one decision.

    Returns the file to place in the agent configuration and the container
    environment that hands it to the extension. Both come from this single
    decision, so a supplied fixture can never be written without also being given
    to the extension. A per-project directory wins over a single source, because a
    widened cohort needs each project's own quotes, and a project with no file in
    that directory supplies nothing rather than a fixture from another project.
    """
    candidate = Path(directory) / f"{project}.json" if directory else None
    path: Path | None = None
    if candidate is not None and candidate.exists():
        path = candidate
    elif source and Path(source).exists():
        path = Path(source)
    if path is None:
        return None, None
    return path.read_text(), ("--env", SEAM_ENVIRONMENT)


def run_project(image: str, digest: str, proxy: InferenceProxy, project: dict[str, str], output: Path, *, jev_enabled: bool | None = None) -> dict:
    name = f"cl-project-{project['name']}-{secrets.token_hex(4)}"
    output.mkdir(parents=True)
    container = command(["docker", "run", "--detach", "--name", name, "--memory", "4g", "--cpus", "2",
        "--pids-limit", "256", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", image]).strip()
    report: dict = {"project": project["name"], "repository": project["repository"], "commit": project["commit"],
                    "status": "failed", "stage": "container-run", "sourceDigest": digest}
    try:
        with tempfile.TemporaryDirectory(prefix="cl-docker-config-") as temporary:
            config = Path(temporary) / "agent"
            proxy.write_agent_config(config)
            if jev_enabled is not None:
                (config / "continual-learning.json").write_text(json.dumps({"jev": {
                    "model": proxy.jev_model, "allowPrivateMemory": True} if jev_enabled else False}))
            contents = {file.name: file.read_text() for file in config.iterdir()}
            # Attribution experiment seam: one fixed candidate list for both arms.
            seam_contents, seam_environment = fixed_memory_seam(
                os.environ.get("PI_FIXED_MEMORIES_SOURCE"), os.environ.get("PI_FIXED_MEMORIES_DIR"), project["name"])
            if seam_contents is not None:
                contents[SEAM_FILE_NAME] = seam_contents
            writer = "import json,pathlib,sys;root=pathlib.Path('/home/node/agent');root.mkdir(mode=0o700);[(root/name).write_text(text) for name,text in json.load(sys.stdin).items()];[file.chmod(0o600) for file in root.iterdir()]"
            result = subprocess.run(["docker", "exec", "-i", container, "python3", "-c", writer],
                                    input=json.dumps(contents), capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise RuntimeError("Unable to initialize isolated agent configuration")
        environment = proxy.jev_environment() if jev_enabled else {}
        env_args = [item for key, value in environment.items() for item in ("--env", f"{key}={value}")]
        # Pluggability arm, default-off: make the SDK physically absent inside the
        # container, so the extension must load, learn and report Jev unavailable
        # instead of failing. The resolution check is recorded as evidence.
        if os.environ.get("PI_ABSENT_TYPESAFE_SDK") == "1":
            # The container runs as node, so removing a build-time dependency needs
            # root. Without it the removal fails and the arm silently keeps the SDK.
            removal = subprocess.run(["docker", "exec", "--user", "root", container, "sh", "-lc", ABSENT_SDK_COMMAND],
                                     capture_output=True, text=True, timeout=120)
            (output / "sdk-absence.txt").write_text(redact_transport_credentials(
                f"exit {removal.returncode}\n{removal.stdout}{removal.stderr}", proxy))
        # Experimental strategies stay default-off in production. An experiment that
        # measures one forwards its switch explicitly into the disposable container.
        if os.environ.get("PI_COVERAGE_REPAIR"):
            env_args.extend(["--env", f"PI_COVERAGE_REPAIR={os.environ['PI_COVERAGE_REPAIR']}"])
        # The seam environment comes from the same decision that wrote the file, so
        # the two can never disagree.
        if seam_environment:
            env_args.extend(seam_environment)
        mode_args = ["--jev", "on" if jev_enabled else "off"] if jev_enabled is not None else []
        result = subprocess.run(["docker", "exec", *env_args, container, "python3",
            "/opt/experiment/packages/continual-learning/tests/live_docker_projects.py", "--container",
            "--project", project["name"], "--cohort", project.get("cohort", "historical"),
            "--memory-policy", project.get("memoryPolicy", "default"), "--source-digest", digest, *mode_args,
            *(["--decoy-level", project["decoyLevel"]] if project.get("decoyLevel") else []),
            *(["--constraint-level", project["constraintLevel"]] if project.get("constraintLevel") else []),
            *(["--run-timeout", str(project["runTimeout"])] if project.get("runTimeout") else [])], capture_output=True, text=True, timeout=1800)
        (output / "runner-output.txt").write_text(redact_transport_credentials(result.stdout + result.stderr, proxy))
        report["containerExitCode"] = result.returncode
    except Exception as error:
        report["error"] = redact_transport_credentials(str(error), proxy)[-2000:]
        (output / "runner-failure.txt").write_text(report["error"])
    finally:
        try:
            # Keep raw copies in a private temporary directory; only sanitized
            # artifacts reach the durable experiment evidence directory.
            with tempfile.TemporaryDirectory(prefix="cl-docker-results-") as temporary:
                copied = Path(temporary)
                command(["docker", "cp", f"{container}:/home/node/results/.", temporary],
                        sanitize=lambda text: redact_transport_credentials(text, proxy))
                artifacts = list(copied.rglob("*"))
                for artifact in artifacts:
                    if artifact.is_symlink():
                        raise RuntimeError("Symlink experiment artifacts are unsupported")
                    relative = str(artifact.relative_to(copied))
                    if redact_transport_credentials(relative, proxy) != relative:
                        raise RuntimeError("Credential-bearing experiment artifact paths are unsupported")
                for artifact in artifacts:
                    if not artifact.is_file():
                        continue
                    target = output / artifact.relative_to(copied)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(redact_transport_bytes(artifact.read_bytes(), proxy))
            saved = output / "report.json"
            if saved.exists():
                report = {**json.loads(saved.read_text()), **{key: report[key] for key in ("containerExitCode", "error") if key in report}}
                if "error" in report or report.get("containerExitCode", 0) != 0:
                    report["status"] = "failed"
            elif "error" not in report:
                report["error"] = "Container emitted no report"
        except Exception as error:
            report["status"] = "failed"
            report["artifactError"] = redact_transport_credentials(str(error), proxy)[-2000:]
        report.update({"containerId": container, "image": image})
        (output / "report.json").write_text(json.dumps(report, indent=2))
        try:
            command(["docker", "rm", "--force", container], sanitize=lambda text: redact_transport_credentials(text, proxy))
        except Exception as error:
            report["cleanupError"] = redact_transport_credentials(str(error), proxy)[-2000:]
            report["status"] = "failed"
            (output / "report.json").write_text(json.dumps(report, indent=2))
    return report
