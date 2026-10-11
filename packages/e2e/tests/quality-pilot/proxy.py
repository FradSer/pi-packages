"""Frozen host-only transport extracted from the prior audited experiment.

No credentials are copied into Docker; body/output limits precede forwarding.
"""
from __future__ import annotations
import hashlib,hmac,http.client,json,os,secrets,threading
from pathlib import Path
from urllib.parse import urlsplit
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from budget import validate_payload
class InferenceProxy:
    """Transparent streaming transport, not a provider fixture or model stub."""

    def __init__(self, config_root: Path, *, jev_key: str | None = None, request_budget: int = 180,
                 selection: dict[str, str] | None = None) -> None:
        self.request_budget = request_budget
        self.jev_requests = 0
        self.jev_usage: list[dict] = []
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
        self.counter_lock = threading.Lock()
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
                    if not 0 < length <= 2 * 1024 * 1024:
                        self.send_error(413)
                        return
                    body = self.rfile.read(length)
                    validate_payload(body, is_jev)
                    payload = json.loads(body)
                    if not isinstance(payload, dict) or payload.get("model") != ("jev-latest" if is_jev else owner.selection["model"]):
                        self.send_error(403)
                        return
                except (ValueError, json.JSONDecodeError):
                    self.send_error(400)
                    return
                slots = owner.jev_slots if is_jev else owner.slots
                if not slots.acquire(timeout=5):
                    with owner.counter_lock:
                        owner.errors += 1
                    self.send_error(429)
                    return
                connection: http.client.HTTPConnection | None = None
                try:
                    with owner.counter_lock:
                        if owner.requests >= owner.request_budget:
                            self.send_error(429, "Experiment request budget exhausted")
                            return
                        owner.requests += 1
                        if is_jev:
                            owner.jev_requests += 1
                    upstream = urlsplit("https://api.typesafe.ai") if is_jev else owner.upstream
                    connection_type = http.client.HTTPSConnection if upstream.scheme == "https" else http.client.HTTPConnection
                    connection = connection_type(upstream.hostname, upstream.port, timeout=300)
                    endpoint = "/v1/systemone" if is_jev else upstream.path.rstrip("/") + self.path.removeprefix("/v1")
                    connection.request("POST", endpoint, body, headers={**({} if is_jev else owner.headers),
                        "Authorization": f"Bearer {owner.jev_key if is_jev else owner.key}", "Content-Type": "application/json"})
                    response = connection.getresponse()
                    self.send_response(response.status)
                    self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    if response.status >= 400:
                        owner.errors += 1
                        self.wfile.write(response.read(65536).replace(owner.key.encode(), b"[redacted]").replace((owner.jev_key or owner.key).encode(), b"[redacted]"))
                    else:
                        jev_body = bytearray()
                        while block := response.read1(65536):
                            if is_jev and len(jev_body) < 2 * 1024 * 1024:
                                jev_body.extend(block)
                            self.wfile.write(block)
                            self.wfile.flush()
                        if is_jev:
                            try:
                                answer = json.loads(jev_body)
                                usage = answer.get("usage", {})
                                if answer.get("model") == "jev-1.13.0" and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("input_tokens", "output_tokens")):
                                    with owner.counter_lock:
                                        owner.jev_usage.append({"model": "jev-1.13.0", **{k: usage[k] for k in ("input_tokens", "output_tokens")}})
                            except (ValueError, TypeError, AttributeError):
                                pass
                except (OSError, http.client.HTTPException):
                    owner.errors += 1
                    self.close_connection = True
                finally:
                    if connection:
                        connection.close()
                    slots.release()

        self.server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> InferenceProxy:
        self.thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

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
                "model": "jev-1.13.0", "allowPrivateMemory": True}}))
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


