"""Observe real parent-model tool selection and TUI, separate from direct RPC tests."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0,"/opt/study/packages/subagents/tests")
from native_support import NativeTui


def main() -> None:
    prompt=("Use a temporary reviewer agent to review /work/heldout/delivery. "
        "No saved identity should be created for this one-off task. Delegate the review and wait for the automatically delivered result, "
        "then report the finding and finish your report with PARENT_REVIEW_DONE. "
        "Do not edit files or poll for the answer.")
    command=["pi","--approve","--no-session","--no-extensions","-e","/opt/study/packages/subagents/index.ts",
        "-e","/opt/study/packages/subagents/tests/docker-study/audit.ts","--provider","cli-proxy","--model","opencode/deepseek-v4.1-flash","--thinking","off","--tools","read,agent_start,agent_input,agent_stop,agent_list",prompt]
    result={"prompt":prompt,"command":command}
    terminal=NativeTui(command,cwd=Path("/work"),env=dict(os.environ),timeout=180)
    try:
        audit=Path(f"/results/child-{terminal.process.pid}.jsonl")
        phase_start=0
        def final_seen() -> bool:
            if not audit.exists():return False
            delivered=False
            for line in audit.read_text().splitlines()[phase_start:]:
                event=json.loads(line)
                message=event.get("message",{})
                if message.get("role")=="custom" and message.get("customType")=="subagents-session-result":delivered=True
                if delivered and message.get("role")=="assistant" and any(block.get("type")=="text" and "PARENT_REVIEW_DONE" in block.get("text","") for block in message.get("content",[])):
                    return True
            return False
        terminal.wait_for(final_seen)
        Path("/results/parent-tui-collapsed.txt").write_text(terminal.screen())
        before=len(terminal.transcript)
        terminal.send(b"\x0f")
        terminal.wait_for(lambda:len(terminal.transcript)>before)
        result["expandRepaintObserved"]=True
        before=len(terminal.transcript)
        terminal.resize(60)
        terminal.wait_for(lambda:len(terminal.transcript)>before)
        result["resizeRepaintObserved"]=True
        result["markerObserved"]=True
        result["phases"]=[{"kind":"temporary","attempt":0,"complete":True}]
        for attempt in range(1,3):
            phase_start=len(audit.read_text().splitlines())
            terminal.send(("Repeat the same task with a new temporary reviewer agent; do not select a saved identity. Review /work/heldout/delivery, wait for its result and finish the final report with PARENT_REVIEW_DONE. Do not poll or edit files.\r").encode())
            terminal.wait_for(final_seen)
            result["phases"].append({"kind":"temporary","attempt":attempt,"complete":True})
        phase_start=len(audit.read_text().splitlines())
        terminal.send(("Now delegate this same review to the existing saved identity learned-reviewer with only read access. Wait for the result and finish with PARENT_REVIEW_DONE. Do not poll or edit files.\r").encode())
        terminal.wait_for(final_seen)
        result["phases"].append({"kind":"saved","complete":True})
    except BaseException as error:
        result["markerObserved"]=False
        result["error"]=str(error)[-1000:]
    finally:
        terminal.close()
        Path("/results/parent-tui.txt").write_text(terminal.screen())
        Path("/results/parent-tui.json").write_text(json.dumps(result,indent=2))


if __name__=="__main__":main()
