"""Real temporary child remains sendable; two accepted inputs, two results, one process."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
from http.server import BaseHTTPRequestHandler

from native_support import LoopbackServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_temporary_agent_retains_history_until_explicit_stop(tmp_path: Path) -> None:
    requests: list[dict[str, object]] = []

    class LocalModel(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(payload)
            answer = "2" if len(requests) == 1 else "5"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for delta, finish in (({"role":"assistant","content":answer},None),({},"stop")):
                chunk={"id":"temporary-answer","object":"chat.completion.chunk","created":1,"model":"arithmetic",
                    "choices":[{"index":0,"delta":delta,"finish_reason":finish}]}
                self.wfile.write(("data: "+json.dumps(chunk)+"\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()

    server = LoopbackServer(LocalModel)
    agent_dir=tmp_path/"agent";agent_dir.mkdir()
    credential=secrets.token_hex(16)
    (agent_dir/"settings.json").write_text(json.dumps({"quietStartup":True}))
    (agent_dir/"models.json").write_text(json.dumps({"providers":{
        "temporary-loopback":{"baseUrl":f"http://127.0.0.1:{server.server_port}/v1",
            "api":"openai-completions","apiKey":credential,"models":[{"id":"arithmetic",
            "reasoning":False,"input":["text"],"contextWindow":200000,"maxTokens":4096,
            "cost":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0}}]}
    }}))
    evidence=tmp_path/"temporary-evidence.json"
    env={"PATH":os.environ["PATH"],"HOME":str(tmp_path),"PI_CODING_AGENT_DIR":str(agent_dir),
        "PI_OFFLINE":"1","PI_TEMPORARY_AUTH":credential,"PI_TEMPORARY_EVIDENCE":str(evidence)}
    cli=REPO/"node_modules"/"@earendil-works"/"pi-coding-agent"/"dist"/"cli.js"
    try:
        result=subprocess.run(["node",str(cli),"--print","--no-session","--no-extensions",
            "--no-skills","--no-prompt-templates","--no-themes","--no-context-files","--no-approve",
            "--no-builtin-tools","--extension",str(REPO/"tests"/"live-temporary-resident-fixture.ts"),
            "--provider","temporary-parent","--model","scripted","--thinking","off",
            "Run two prompts through the same temporary agent"],cwd=tmp_path,env=env,
            input="",capture_output=True,text=True,timeout=45)
        assert result.returncode == 0, result.stderr+result.stdout
        assert evidence.is_file(), result.stderr + result.stdout
        report=json.loads(evidence.read_text())
        assert report["texts"] == ["2","5"], report
        assert report["turns"] == [1,2], report
        assert report["sameSession"] is True and report["idleAfterFirst"] is True, report
        assert report["stopped"] is True and report["living"] == 0, report
        assert len(requests) == 2
        transcript=json.dumps(requests[1]["messages"],ensure_ascii=False)
        assert "1+1" in transcript and "2+3" in transcript
        assert not (agent_dir/"agents").exists()
        assert not (agent_dir/"subagent-sessions").exists()
        assert not (agent_dir/"workspaces").exists()
    finally:
        server.close()
