"""One native parent-model tool selection and TUI repaint, separate from direct RPC."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, "/opt/study/packages/subagents/tests")
from native_support import NativeTui


def main() -> None:
    prompt = ("Delegate to one temporary reviewer: reply exactly PARENT_OK through the child. "
        "After the single automatic result, finish your report with PARENT_REVIEW_DONE and stop. "
        "Do not call agent_list or any other tool again, and do not edit files or poll.")
    command = ["pi", "--approve", "--no-session", "--no-extensions", "--no-skills",
        "--no-prompt-templates", "--no-themes", "--no-context-files",
        "-e", "/opt/study/packages/subagents/index.ts",
        "-e", "/opt/study/packages/subagents/tests/docker-study/audit.ts",
        "--model", "magpie-hy4/hunyuan-eval/hy4-dev", "--thinking", "off",
        "--tools", "read,agent_start,agent_input,agent_stop,agent_list", prompt]
    result = {"prompt": prompt, "command": command}
    terminal = NativeTui(command, cwd=Path("/work"), env=dict(os.environ), timeout=180)
    try:
        audit = Path(f"/results/child-{terminal.process.pid}.jsonl")
        phase_start = 0

        def final_seen() -> bool:
            if not audit.exists():
                return False
            delivered = False
            for line in audit.read_text().splitlines()[phase_start:]:
                message = json.loads(line).get("message", {})
                if message.get("role") == "custom" and message.get("customType") == "subagents-session-result":
                    delivered = True
                if delivered and message.get("role") == "assistant" and any(
                        block.get("type") == "text" and "PARENT_REVIEW_DONE" in block.get("text", "")
                        for block in message.get("content", [])):
                    return True
            return False

        terminal.wait_for(final_seen)
        Path("/results/parent-tui-collapsed.txt").write_text(terminal.screen())
        before = len(terminal.transcript)
        terminal.send(b"\x0f")
        terminal.wait_for(lambda: len(terminal.transcript) > before)
        result["expandRepaintObserved"] = True
        before = len(terminal.transcript)
        terminal.resize(60)
        terminal.wait_for(lambda: len(terminal.transcript) > before)
        result["resizeRepaintObserved"] = True
        result["markerObserved"] = True
    except BaseException as error:
        result["markerObserved"] = False
        result["error"] = str(error)[-1000:]
    finally:
        terminal.close()
        Path("/results/parent-tui.txt").write_text(terminal.screen())
        Path("/results/parent-tui.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
