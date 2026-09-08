from __future__ import annotations

import errno
import os
import pty
import select
import secrets
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from test_teammate_package import PACKAGE, SRC, run_node


def test_finish_entry_describes_assignment_not_process() -> None:
    payload = run_node(f'''
        import extension, {{ TEAMMATE_FINISHED_ENTRY_TYPE }} from "{(SRC / 'index.ts').as_uri()}";
        const renderers = new Map();
        extension({{
          on() {{}}, registerTool() {{}}, registerCommand() {{}}, registerMessageRenderer() {{}},
          registerEntryRenderer(type, renderer) {{ renderers.set(type, renderer); }},
          getActiveTools: () => [], getAllTools: () => [], setActiveTools() {{}},
        }});
        const theme = {{ fg: (_color, text) => text }};
        const output = renderers.get(TEAMMATE_FINISHED_ENTRY_TYPE)({{ data: {{ teammate: 'worker' }} }}, {{}}, theme).render(100).join('');
        console.log(JSON.stringify({{ output }}));
    ''')
    assert "Assignment" in payload["output"]
    assert "Agent @worker finished" not in payload["output"]


def test_late_report_label_is_visible_collapsed_and_expanded() -> None:
    payload = run_node(f'''
        import extension from "{(SRC / 'index.ts').as_uri()}";
        import {{ initTheme }} from "@earendil-works/pi-coding-agent";
        import {{ visibleWidth }} from "@earendil-works/pi-tui";
        initTheme('dark');
        const renderers = new Map();
        extension({{
          on() {{}}, registerTool() {{}}, registerCommand() {{}}, registerEntryRenderer() {{}},
          registerMessageRenderer(type, renderer) {{ renderers.set(type, renderer); }},
        }});
        const theme = {{ fg: (_color, text) => text, bg: (_color, text) => text, bold: (text) => text }};
        const renderer = renderers.get('agent-teams-report');
        const message = {{ details: {{ agent: 'role', teammate: 'worker', body: 'Original report body.', deliveredAfterStop: true }} }};
        const outputs = [false, true].map((expanded) => renderer(message, {{ expanded, outputPad: 0 }}, theme).render(100).join('\\n'));
        const narrow = renderer(message, {{ expanded: false, outputPad: 0 }}, theme).render(24);
        const normal = renderer({{ details: {{ agent: 'role', teammate: 'worker', body: 'Normal.' }} }}, {{ expanded: false, outputPad: 0 }}, theme).render(100).join('\\n');
        console.log(JSON.stringify({{ outputs, narrowFits: narrow.every((line) => visibleWidth(line) <= 24), normal }}));
    ''')
    assert all("late delivery" in output.lower() for output in payload["outputs"])
    assert "Original report body." in payload["outputs"][1]
    assert payload["narrowFits"]
    assert "late delivery" not in payload["normal"].lower()


def test_normal_report_keeps_authored_time_without_after_stop_marker() -> None:
    payload = run_node(f'''
        import {{ annotateReportDelivery, formatReports }} from "{(SRC / 'leader-reports.ts').as_uri()}";
        const original = {{ agent: 'role', teammate: 'worker', body: 'Original.', timestamp: 100 }};
        const report = annotateReportDelivery(original, 200);
        console.log(JSON.stringify({{ original, report, content: formatReports([report]) }}));
    ''')
    assert payload["report"]["timestamp"] == 100
    assert payload["report"]["deliveredAt"] == 200
    assert "deliveredAfterStop" not in payload["report"]
    assert "deliveredAt" not in payload["original"]
    assert 'delivery="after-stop"' not in payload["content"]


def run_pi_in_terminal(command: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    master, slave = pty.openpty()
    output = bytearray()
    sent_exit = False
    try:
        with subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, cwd=cwd, env=env) as process:
            os.close(slave)
            deadline = time.monotonic() + 20
            try:
                while True:
                    assert time.monotonic() < deadline, "Pi terminal fixture timed out"
                    if select.select([master], [], [], 0.1)[0]:
                        try:
                            chunk = os.read(master, 65536)
                        except OSError as error:
                            if error.errno != errno.EIO:
                                raise
                            break
                        if not chunk:
                            break
                        output.extend(chunk)
                    elif process.poll() is not None:
                        break
                    if not sent_exit and b"PI_LATE_REPORT_" in output:
                        os.write(master, b"\x04")
                        sent_exit = True
                return subprocess.CompletedProcess(command, process.wait(timeout=2), output.decode(errors="replace"), "")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
    finally:
        os.close(master)


@pytest.mark.parametrize("mode", ["print", "tui"])
@pytest.mark.parametrize("stop_boundary", ["before-delivery", "during-delivery"])
def test_real_pi_classifies_delivery_boundary(tmp_path: Path, mode: str, stop_boundary: str) -> None:
    pi = shutil.which("pi")
    if pi is None:
        pytest.skip("Pi CLI is required for native delivery integration")
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    env.update({
        "HOME": str(tmp_path),
        "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "PI_OFFLINE": "1",
        "PI_REPORT_STOP_BOUNDARY": stop_boundary,
        "PI_REPORT_FIXTURE_AUTH": secrets.token_hex(16),
    })
    command = [
        pi, *(["--print"] if mode == "print" else []), "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates",
        "--no-themes", "--no-context-files", "--no-approve",
        "--extension", str(PACKAGE / "tests/late-report-fixture.ts"),
        "--provider", "late-report-fixture", "--model", "deterministic", "--thinking", "off",
        "--tools", "queue_and_stop,check_late_report", "Run the late report fixture",
    ]
    result = (run_pi_in_terminal(command, env, tmp_path) if mode == "tui" else
              subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=25))
    assert result.returncode == 0, result.stderr
    assert "PI_LATE_REPORT_OK" in result.stdout, result.stdout + result.stderr
    assert "PI_LATE_REPORT_FAILED" not in result.stdout
    if mode == "tui":
        assert ("Late delivery: process already stopped." in result.stdout) == (stop_boundary == "before-delivery")
