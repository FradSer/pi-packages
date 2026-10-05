"""Host-only Docker plumbing. Real provider credentials never enter an image."""
from __future__ import annotations

import hashlib
from collections.abc import Callable
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import threading
from urllib.parse import urlsplit

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
PROJECTS = (
    {"name": "click", "repository": "https://github.com/pallets/click.git", "commit": "06b2a678741131fd577ce170e23e5ca0aeba0309"},
    {"name": "p-limit", "repository": "https://github.com/sindresorhus/p-limit.git", "commit": "a8a6fbec4e0e866d6d779b10889bb4f5567e70eb"},
    {"name": "mitt", "repository": "https://github.com/developit/mitt.git", "commit": "6b41670516ed8e8b738612f60491995470aa63b3"},
)


def command(args: list[str], *, timeout: int = 900, sanitize: Callable[[str], str] | None = None) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        stderr = sanitize(result.stderr) if sanitize else result.stderr
        raise RuntimeError(f"{args[0]} failed ({result.returncode}): {stderr[-2000:]}")
    return sanitize(result.stdout) if sanitize else result.stdout


def source_digest() -> str:
    digest = hashlib.sha256()
    for root in (PACKAGE / "extensions", PACKAGE / "prompts", REPO / "packages" / "kit" / "src"):
        for file in sorted(root.rglob("*")):
            if file.is_file():
                digest.update(str(file.relative_to(REPO)).encode())
                digest.update(b"\0")
                digest.update(file.read_bytes())
    for file in (PACKAGE / "index.ts", PACKAGE / "package.json", REPO / "packages" / "kit" / "package.json", REPO / "packages" / "kit" / "index.ts",
                 PACKAGE / "tests" / "docker" / "Dockerfile", PACKAGE / "tests" / "docker_experiment.py",
                 PACKAGE / "tests" / "live_docker_projects.py", PACKAGE / "tests" / "live_smoke.py", PACKAGE / "tests" / "support.py"):
        digest.update(str(file.relative_to(REPO)).encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()


def build_image() -> tuple[str, str]:
    digest = source_digest()
    image = f"continual-learning-projects:{digest[:16]}"
    with tempfile.TemporaryDirectory(prefix="cl-docker-build-") as temporary:
        context = Path(temporary)
        for name in ("kit", "continual-learning"):
            shutil.copytree(REPO / "packages" / name, context / "packages" / name,
                            ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".pytest_cache", ".memory", ".pi", ".git"))
        (context / "package.json").write_text(json.dumps({
            "private": True, "type": "module", "packageManager": "pnpm@11.21.0",
            "dependencies": {"@earendil-works/pi-coding-agent": "1.0.2", "@earendil-works/pi-tui": "^1.0.0", "tsx": "4.19.0"},
        }))
        (context / "pnpm-workspace.yaml").write_text('packages:\n  - packages/*\nallowBuilds:\n  esbuild: true\n  "@google/genai": true\n  protobufjs: true\n')
        shutil.copyfile(PACKAGE / "tests" / "docker" / "Dockerfile", context / "Dockerfile")
        command(["docker", "build", "--tag", image, str(context)], timeout=1200)
    return image, digest


class InferenceProxy:
    """Transparent streaming transport, not a provider fixture or model stub."""

    def __init__(self, config_root: Path, *, jev_key: str | None = None, request_budget: int = 180) -> None:
        self.request_budget = request_budget
        self.jev_requests = 0
        self.jev_usage: list[dict] = []
        self.jev_key = jev_key
        self.selection = json.loads((config_root / "memory.json").read_text())
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
                    payload = json.loads(body)
                    if not isinstance(payload, dict) or payload.get("model") != ("jev-1.13.0" if is_jev else owner.selection["model"]):
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
                    "model": "jev-1.13.0", "allowPrivateMemory": True} if jev_enabled else False}))
            contents = {file.name: file.read_text() for file in config.iterdir()}
            writer = "import json,pathlib,sys;root=pathlib.Path('/home/node/agent');root.mkdir(mode=0o700);[(root/name).write_text(text) for name,text in json.load(sys.stdin).items()];[file.chmod(0o600) for file in root.iterdir()]"
            result = subprocess.run(["docker", "exec", "-i", container, "python3", "-c", writer],
                                    input=json.dumps(contents), capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise RuntimeError("Unable to initialize isolated agent configuration")
        environment = proxy.jev_environment() if jev_enabled else {}
        env_args = [item for key, value in environment.items() for item in ("--env", f"{key}={value}")]
        mode_args = ["--jev", "on" if jev_enabled else "off"] if jev_enabled is not None else []
        result = subprocess.run(["docker", "exec", *env_args, container, "python3",
            "/opt/experiment/packages/continual-learning/tests/live_docker_projects.py", "--container",
            "--project", project["name"], "--source-digest", digest, *mode_args], capture_output=True, text=True, timeout=1800)
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
