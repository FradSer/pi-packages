from pathlib import Path
import http.client
import socket
import subprocess
import time

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
MAX_BODY_BYTES = 1024 * 1024


def test_bounded_body_reader_preserves_utf8_and_discards_aborted_requests() -> None:
    result = subprocess.run(
        ["node", str(PACKAGE / "tests/http_body_harness.mjs")],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture
def live_server(tmp_path: Path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen(
        ["node", str(PACKAGE / "scripts/live-server.mjs"), f"--port={port}"],
        cwd=tmp_path, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    try:
        for _ in range(100):
            assert process.poll() is None, process.stderr.read().decode()
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            pytest.fail("Live server did not start")
        yield port
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        process.stderr.close()


@pytest.mark.parametrize("route", ["/events", "/poll", "/manual-edit-stash", "/manual-edit-repair-decision"])
@pytest.mark.parametrize("chunked", [False, True])
def test_live_json_bodies_are_rejected_before_unbounded_aggregation(live_server: int, route: str, chunked: bool) -> None:
    body = b'{"padding":"' + b"x" * MAX_BODY_BYTES + b'"}'
    connection = http.client.HTTPConnection("127.0.0.1", live_server, timeout=5)
    try:
        connection.request(
            "POST", route,
            body=iter([body[:30], body[30:]]) if chunked else body,
            headers={"Content-Type": "application/json"}, encode_chunked=chunked,
        )
        response = connection.getresponse()
        assert response.status == 413, response.read().decode()
        assert b"large" in response.read().lower()
    finally:
        connection.close()
    connection = http.client.HTTPConnection("127.0.0.1", live_server, timeout=5)
    try:
        connection.request("POST", route, body=b"{}")
        response = connection.getresponse()
        assert response.status == 401
        response.read()
    finally:
        connection.close()
