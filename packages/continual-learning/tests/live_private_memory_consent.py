"""Actual Pi /memory privacy preflight; isolated native PTY and RPC, no remote calls."""
from __future__ import annotations
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time

REPO = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).with_name('private-memory-consent-live-fixture.ts')
CLI = REPO/'node_modules/@earendil-works/pi-coding-agent/dist/cli.js'


def main() -> None:
    parent=Path(sys.argv[1]).resolve(); parent.mkdir(parents=True,exist_ok=True)
    output=Path(tempfile.mkdtemp(prefix='private-consent-',dir=parent))
    sources=[FIXTURE,Path(__file__),REPO/'packages/continual-learning/extensions/inject-memory.ts',
             REPO/'packages/continual-learning/extensions/jev-learning.ts',
             REPO/'packages/continual-learning/extensions/memory-review-consent.ts',
             REPO/'packages/continual-learning/extensions/learning-efficiency.ts']
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    version=subprocess.run(['node',str(CLI),'--version'],capture_output=True,text=True,check=True).stdout.strip()
    results=[]
    for mode in ['print','pty','rpc']:
        root=output/mode; cwd=root/'project'; agent=root/'agent'; cwd.mkdir(parents=True);agent.mkdir()
        subprocess.run(['git','init','-q',str(cwd)],check=True)
        key='--'+str(cwd).strip('/').replace('/','-')+'--'
        memory=agent/'memory'/key;memory.mkdir(parents=True)
        body='---\nname: private\ndescription: Keep updates concise\ntype: feedback\n---\nKeep updates concise.\n'
        (memory/'private.md').write_text(body)
        (agent/'settings.json').write_text(json.dumps({'packages':[],'quietStartup':True}))
        (agent/'memory/settings.json').write_text(json.dumps({'autoMemory':False}))
        config={'jev':{'enabled':True,'apiKey':'offline-fixture-only','allowPrivateMemory':False}}
        (agent/'continual-learning.json').write_text(json.dumps(config))
        events=root/'events.jsonl'
        env={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL'}}
        env.update(HOME=str(root),PI_CODING_AGENT_DIR=str(agent),PI_OFFLINE='1',TERM='xterm-256color',CL_PRIVATE_CONSENT_EVENTS=str(events))
        command=['node',str(CLI),'--no-session','--no-extensions','--no-skills','--no-prompt-templates','--no-themes','--no-context-files','--no-builtin-tools','--extension',str(FIXTURE),'--provider','private-consent-fixture','--model','deterministic']
        if mode=='print':
            completed=subprocess.run(command+['--print','/memory 整理记忆'],cwd=cwd,env=env,capture_output=True,timeout=40)
            (root/'stdout.txt').write_bytes(completed.stdout);(root/'stderr.txt').write_bytes(completed.stderr)
            rows=[json.loads(s) for s in events.read_text().splitlines()] if events.exists() else []
            assert completed.returncode==0,(completed.stdout,completed.stderr)
            assert not any(r['kind'] in ['confirm','forbidden-network','forbidden-model'] for r in rows),rows
            receipt=next(r['receipt'] for r in rows if r['kind']=='receipt')
            assert receipt['operations']==0 and receipt['totals']['cost']==0 and receipt['costAvailable'],receipt
            assert not list((agent/'memory/runs').rglob('manifest.json'))
            assert (memory/'private.md').read_text()==body and json.loads((agent/'continual-learning.json').read_text())==config
            results.append({'mode':mode,'status':'passed','remoteRequests':0,'plannerRuns':0,'unchanged':True})
            continue
        transcript=bytearray();dialogs=[];pending=b''
        master=None
        if mode=='pty':
            master,slave=pty.openpty();fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack('HHHH',40,120,0,0))
            process=subprocess.Popen(command,cwd=cwd,env=env,stdin=slave,stdout=slave,stderr=slave);os.close(slave);read_fd=master
        else:
            process=subprocess.Popen(command+['--mode','rpc'],cwd=cwd,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE);read_fd=process.stdout.fileno()
        sent=False;declined=False
        try:
            deadline=time.monotonic()+40
            while time.monotonic()<deadline:
                rows=[json.loads(s) for s in events.read_text().splitlines()] if events.exists() else []
                if any(r['kind']=='ready' for r in rows) and not sent:
                    if mode=='pty':os.write(master,'/memory 整理记忆\r'.encode())
                    else:process.stdin.write((json.dumps({'id':'maintenance','type':'prompt','message':'/memory 整理记忆'})+'\n').encode());process.stdin.flush()
                    sent=True
                if select.select([read_fd],[],[],.05)[0]:
                    chunk=os.read(read_fd,65536);transcript.extend(chunk);pending+=chunk
                    if mode=='rpc':
                        while b'\n' in pending:
                            line,pending=pending.split(b'\n',1)
                            try:row=json.loads(line)
                            except json.JSONDecodeError:continue
                            if row.get('type')=='extension_ui_request' and row.get('method')=='confirm':
                                dialogs.append(row);process.stdin.write((json.dumps({'type':'extension_ui_response','id':row['id'],'confirmed':False})+'\n').encode());process.stdin.flush();declined=True
                if mode=='pty' and not declined and any(r['kind']=='confirm' for r in rows):
                    # Resize the same live native confirmation before actual Escape.
                    for width,height in [(48,24),(48,12),(120,40)]:
                        fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack('HHHH',height,width,0,0));process.send_signal(signal.SIGWINCH)
                    os.write(master,b'\x1b');declined=True
                if any(r['kind']=='receipt' for r in rows):break
                if process.poll() is not None:raise AssertionError(transcript.decode(errors='replace')[-3000:])
            else:raise AssertionError('Native consent did not finish: '+transcript.decode(errors='replace')[-3000:])
            assert declined and not any(r['kind'] in ['forbidden-network','forbidden-model'] for r in rows),rows
            receipt=next(r['receipt'] for r in rows if r['kind']=='receipt')
            assert receipt['operations']==0 and any(a.get('jev',{}).get('reason')=='private-memory-denied' for a in receipt['attempts']),receipt
            assert (memory/'private.md').read_text()==body
            assert json.loads((agent/'continual-learning.json').read_text())==config
            assert not list((agent/'memory/runs').rglob('manifest.json')), 'A planner run was created before consent'
            results.append({'mode':mode,'status':'passed','remoteRequests':0,'plannerRuns':0,'unchanged':True,'dialogs':dialogs})
        finally:
            process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
            if master is not None:os.close(master)
            (root/'terminal.ansi').write_bytes(transcript)
            (root/'rpc-dialogs.json').write_text(json.dumps(dialogs,indent=2))
    assert hashes=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'Source changed during native verification'
    manifest={'status':'passed','source':'actual workspace Pi command, isolated fixture Memory, no external services',
              'piVersion':version,'sourceSha256':hashes,'sourceUnchanged':True,
              'ptyInteractions':[{'input':'/memory 整理记忆','dimensions':[120,40]},
                                 {'resize':[48,24]},{'resize':[48,12]},{'resize':[120,40]},{'key':'Escape'}],
              'resizeLayoutVerified':False,'cases':results,'outputDir':str(output)}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest))


if __name__=='__main__':main()
