"""Capture real Pi terminal frames with deterministic data and production TUI code.
Run: uv run --no-project --with pyte --with pillow python packages/continual-learning/tests/tui_showcase.py OUTPUT_DIR
"""
from __future__ import annotations
import errno
import fcntl
import json
import os
from pathlib import Path
import pty
import secrets
import re
import select
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import pyte
from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    output = Path(sys.argv[1]).resolve(); output.mkdir(parents=True, exist_ok=True)
    captures: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="cl-tui-showcase-") as raw:
        cwd=Path(raw); agent=cwd/"agent"; agent.mkdir(); (agent/"memory").mkdir()
        (agent/"settings.json").write_text(json.dumps({"theme":"dark","quietStartup":True,"packages":[]}))
        (agent/"memory/settings.json").write_text(json.dumps({"autoMemory":False}))
        events=cwd/"events.jsonl"
        env={k:v for k,v in os.environ.items() if k in {"PATH","LANG","LC_ALL"}}
        env.update({"HOME":str(cwd),"PI_CODING_AGENT_DIR":str(agent),"PI_OFFLINE":"1","TERM":"xterm-256color","PI_DETAILS_LIVE_AUTH":secrets.token_hex(16),"PI_DETAILS_LIVE_SNAPSHOTS":str(events)})
        master,slave=pty.openpty(); width,height=120,40
        screen=pyte.Screen(width,height); stream=pyte.Stream(screen); transcript=bytearray()
        fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack("HHHH",height,width,0,0))
        command=[shutil.which("pi"),"--no-session","--no-extensions","--no-skills","--no-prompt-templates","--no-themes","--no-context-files","--no-approve","--extension",str(Path(__file__).with_name("tui-showcase-fixture.ts").resolve()),"--provider","meaningful-details-fixture","--model","deterministic","--thinking","off","--no-builtin-tools","Run the offline display fixture"]
        process=subprocess.Popen(command,cwd=cwd,env=env,stdin=slave,stdout=slave,stderr=slave);os.close(slave)
        def rows() -> list[dict]:
            return [json.loads(line) for line in events.read_text().splitlines() if line.endswith("}")] if events.exists() else []
        def pump(timeout: float=.05) -> bool:
            if not select.select([master],[],[],timeout)[0]: return False
            try: data=os.read(master,65536)
            except OSError as error:
                if error.errno==errno.EIO:return False
                raise
            transcript.extend(data);stream.feed(data.decode("utf8",errors="replace"));return True
        def wait(predicate) -> None:
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                pump()
                if predicate():return
                if process.poll() is not None:break
            raise AssertionError(transcript.decode(errors="replace")[-5000:])
        def send(data: bytes) -> None:os.write(master,data)
        def resize(w: int,h: int) -> None:
            nonlocal width,height
            width,height=w,h;screen.resize(lines=h,columns=w)
            fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack("HHHH",h,w,0,0));process.send_signal(signal.SIGWINCH)
        def menus() -> list[dict]:return [r for r in rows() if r["kind"]=="menu"]
        def action(data: bytes,title: str) -> dict:
            before=len(menus());send(data);wait(lambda:len(menus())>before and title in menus()[-1]["title"]);return menus()[-1]
        colors={"default":"#dadada","black":"#000000","red":"#cc5555","green":"#55aa55","brown":"#c4a000","blue":"#5555cc","magenta":"#aa55aa","cyan":"#55aaaa","white":"#dadada","brightblack":"#777777","brightred":"#ff7777","brightgreen":"#77dd77","brightyellow":"#eeee77","brightblue":"#7777ff","brightmagenta":"#ee77ee","brightcyan":"#77eeee","brightwhite":"#ffffff"}
        font=ImageFont.truetype("/System/Library/Fonts/Menlo.ttc",20)
        def color(value: str,bg=False) -> str:
            if value=="default":return "#161616" if bg else "#dadada"
            return colors.get(value,"#"+value if len(value)==6 else "#dadada")
        def capture(name: str,description: str,cases: list[int]) -> None:
            # Capture only after the native output queue is quiet; events fire before paint.
            while pump(.15):pass
            image=Image.new("RGB",(width*13+32,height*26+32),"#161616");draw=ImageDraw.Draw(image)
            for y in range(height):
                for x in range(width):
                    cell=screen.buffer[y][x];fg,bg=color(cell.fg),color(cell.bg,True)
                    if cell.reverse:fg,bg=bg,fg
                    draw.rectangle((16+x*13,16+y*26,29+x*13,41+y*26),fill=bg)
                    if cell.data:draw.text((16+x*13,16+y*26),cell.data,font=font,fill=fg)
            image.save(output/f"{name}.png")
            text="\n".join(screen.display);(output/f"{name}.txt").write_text(text)
            (output/f"{name}.ansi").write_bytes(transcript)
            captures.append({"name":name,"description":description,"cases":cases,"width":width,"height":height,"image":f"{name}.png"})
        try:
            wait(lambda:b"CL_DETAILS_LIVE_READY" in transcript)
            send(b"/case-status\r");wait(lambda:any(r.get("name")=="status" for r in rows()))
            capture("01-status","Partial failure, blocked/error/warning colors, compact Harness started row",[2,6,7])
            resize(48,24)
            action(b"/case-memory\r","Memory");action(b"\r","Browse memories")
            capture("02-memory-list","Long descriptions bounded to 48 columns",[1])
            send(b"\x1b[B"*32)
            capture("03-memory-next","Focus follows item 33; Next page and controls stay visible",[1])
            action(b"\r","page 2/5")
            for _ in range(3):
                index=menus()[-1]["options"].index("Next page");action(b"\x1b[B"*index+b"\r","Browse memories")
            action(b"\r","Memory entry")
            capture("04-reader-start","Full document start and reader controls share the viewport",[3])
            send(b"\x1b[6~"*5);capture("24-reader-middle-narrow","Reading position before resize",[3])
            before_line=int(re.search(r"line-(\d+)",(output/"24-reader-middle-narrow.txt").read_text()).group(1))
            resize(120,40);capture("25-reader-middle-wide","Same logical reading position after resize",[3])
            after_line=int(re.search(r"line-(\d+)",(output/"25-reader-middle-wide.txt").read_text()).group(1))
            assert abs(before_line-after_line)<=1,(before_line,after_line)
            resize(48,24)
            send(b"\x1b[6~"*20);capture("05-reader-tail","The final line 100 is reachable without chat notifications",[3])
            resize(120,40);capture("06-reader-resize","Same reader adapts to a wider/taller terminal",[3])
            action(b"\r","page 5/5");capture("07-memory-return","Close returns to page 5 and the selected memory",[8])
            action(b"\x1b","Memory");resize(120,40)
            action(b"\x1b[B"*2+b"\r","Recent learning");send(b"\x1b[B"*44)
            capture("08-history","50 records with readable dates, phases, statuses and targets",[1,11])
            resize(48,24);capture("21-history-narrow","Targets remain visible at 48 columns",[11])
            assert "build-command.md" in (output/"21-history-narrow.txt").read_text()
            resize(120,40)
            action(b"\r","Learning change");send(b"\x1bOC");capture("09-history-detail","History detail preserves internal ID and before/after; Undo is an action",[11])
            action(b"\x1bOD\r","Recent learning");capture("10-history-return","Close retains the selected history item",[8])
            action(b"\x1b","Memory");action(b"\x1b[B\r","Learning settings");capture("11-settings","Automatic learning state and continued retrieval are explained",[9])
            action(b"\x1b[B"*2+b"\r","Advanced phase policies");action(b"\x1b[B"*2+b"\r","Agents policy");capture("12-policy","Current off, automatic-only scope, AGENTS disabled override and consolidate semantics",[9])
            resize(48,24);capture("22-policy-narrow","Short policy title and separate help at 48 columns",[9]);resize(120,40)
            action(b"\x03","Advanced phase policies");action(b"\x03","Learning settings");action(b"\x03","Memory");send(b"\x03");wait(lambda:any(r.get("name")=="memory" for r in rows()))
            resize(48,24);send(b"/case-model\r");wait(lambda:any(r["kind"]=="management-render" and not r.get("title") for r in rows()))
            send(b"jk");capture("13-model-search","j and k enter the query; all rows fit 48 columns",[4,5])
            send(b"\x1b[C"*8);capture("14-model-tail","Right scroll reveals the full identifier tail",[4])
            resize(48,12);capture("15-model-resize","Same model picker recomputes viewport at 12 rows",[4])
            assert "Esc: cancel" in (output/"15-model-resize.txt").read_text()
            send(b"\x03");wait(lambda:any(r.get("name")=="model" for r in rows()))
            resize(48,24);action(b"/case-harness\r","Harness rules");action(b"\r","Harness rule:")
            capture("23-rule-default","Rule reader defaults to Close",[8])
            assert "> Close" in (output/"23-rule-default.txt").read_text()
            action(b"\x1b","Harness rules");send(b"\x1b[B"*menus()[-1]["options"].index("View diagnostics"));capture("16-harness-list","Long Harness list scrolls to View diagnostics",[1])
            action(b"\r","Harness diagnostics");capture("17-diagnostics-start","Diagnostics begin at the first error",[10])
            send(b"\x1b[6~"*3);capture("18-diagnostics-tail","Error 12 and incomplete layer diagnostics remain readable",[10])
            action(b"\r","Harness rules");capture("19-harness-return","Close restores rule-list position",[8])
            send(b"\x03");wait(lambda:any(r.get("name")=="harness" for r in rows()))
            resize(120,40);send(b"/case-recovery\r");wait(lambda:any(r.get("name")=="recovery" for r in rows()));capture("20-recovery","Recovered retry is successful; a later terminal failure remains an error",[2,6])
            send(b"/quit\r");wait(lambda:process.poll() is not None);assert process.returncode==0
            rpc=subprocess.Popen([*command[:-1],"--mode","rpc"],cwd=cwd,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            requests=[]; pending=b""
            try:
                rpc.stdin.write((json.dumps({"id":"showcase-rpc","type":"prompt","message":"/case-rpc"})+"\n").encode());rpc.stdin.flush()
                deadline=time.monotonic()+30
                completed=False
                while time.monotonic()<deadline and not completed:
                    if not select.select([rpc.stdout],[],[],.1)[0]:continue
                    pending+=os.read(rpc.stdout.fileno(),65536)
                    while b"\n" in pending:
                        line,pending=pending.split(b"\n",1)
                        try: row=json.loads(line)
                        except json.JSONDecodeError:continue
                        if row.get("type")=="extension_ui_request" and row.get("method")=="select":
                            requests.append(row)
                            value="Next page" if "Next page" in row["options"] else "Close"
                            rpc.stdin.write((json.dumps({"type":"extension_ui_response","id":row["id"],"value":value})+"\n").encode());rpc.stdin.flush()
                        if row.get("id")=="showcase-rpc" and row.get("type")=="response":
                            assert row.get("success"),row
                            completed=True
                assert completed and len(requests)==2,requests
                assert "RPC_BODY_START" in requests[0]["title"] and "RPC_BODY_TAIL" in requests[1]["title"]
                (output/"rpc-dialogs.json").write_text(json.dumps(requests,ensure_ascii=False,indent=2))
            finally:rpc.terminate();rpc.wait(timeout=5)
            (output/"events.jsonl").write_text(events.read_text())
            (output/"manifest.json").write_text(json.dumps({"source":"real Pi PTY, production renderers, deterministic isolated fixture data","remoteRequests":0,"rpcDialogs":len(requests),"captures":captures},ensure_ascii=False,indent=2))
            print(json.dumps({"captures":len(captures),"rpcDialogs":len(requests),"output":str(output),"remoteRequests":0}))
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=5)
            os.close(master)


if __name__=="__main__":main()
