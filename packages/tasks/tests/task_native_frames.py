from __future__ import annotations
import os,pty,fcntl,termios,struct,subprocess,time,select,json,signal,tempfile
from pathlib import Path
from task_terminal_frames import TerminalFrames
repo=Path(__file__).resolve().parents[3]
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True);results=[]
fixture=out/'long-fixture.ts'
source=(repo/'packages/tasks/tests/task-stop-live-fixture.ts').read_text()
source=source.replace('Inspect the current interaction.\\nCheck the input handling and report failures.', 'Inspect the current interaction. ' * 25 + 'TASK_DESCRIPTION_TAIL')
source=source.replace('Confirm the input checks pass.', 'Confirm the input checks pass. ' * 20 + 'TASK_VERIFY_TAIL')
source=source.replace('subject: \"Inspect the task content\"', 'subject: \"Inspect the task content ' + 'complete title word ' * 15 + 'TASK_TITLE_TAIL\"')
fixture.write_text(source)
(out/'node_modules').symlink_to(repo/'node_modules',target_is_directory=True) if not (out/'node_modules').exists() else None
for mode in ['content','ignore','progress']:
 with tempfile.TemporaryDirectory(prefix='tasks-native-') as raw:
  work=Path(raw);agent=work/'agent';agent.mkdir();trace=work/'events.jsonl';(agent/'settings.json').write_text(json.dumps({'packages':[str(repo/'packages/tasks')],'quietStartup':True,'retry':{'enabled':False},'compaction':{'enabled':False}}))
  env={k:v for k,v in os.environ.items() if not k.startswith('PI_TEAMMATE_') and k not in {'PI_TASK_HOLDER','PI_TEAM_STATE_DIR'}}
  env.update(PI_OFFLINE='1',TERM='xterm-256color',PI_CODING_AGENT_DIR=str(agent),PI_TASK_TEST_MODE=mode,PI_TASK_TEST_OUTPUT=str(trace),PI_TASK_TEST_WORK_DIR=str(work))
  master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',500,80,0,0));child=subprocess.Popen([str(repo/'node_modules/.bin/pi'),'-ns','-np','-nc','--no-session','--provider','tasks-stop-test','--model','scripted','-e',str(out/'long-fixture.ts'),'--tools','create_task,get_task,list_tasks,update_task,read,write'],cwd=work,env=env,stdin=slave,stdout=slave,stderr=slave,start_new_session=True);os.close(slave);frames=TerminalFrames(80,500)
  def entries():return [json.loads(x) for x in trace.read_text().splitlines()] if trace.exists() else []
  def wait(predicate):
   end=time.monotonic()+30
   while not predicate():
    if child.poll() is not None or time.monotonic()>end:
     (out/f'{mode}-failed-trace.json').write_text(json.dumps(entries(),indent=2));(out/f'{mode}-failed-frame.txt').write_text('\n'.join(frames.display));raise AssertionError('\n'.join(frames.display)[-4000:])
    if select.select([master],[],[],.05)[0]:
     data=os.read(master,65536);frames.feed(data)
     if b'\x1b[6n' in data:os.write(master,b'\x1b[1;1R')
  try:
   wait(lambda:any(x['type']=='ready' for x in entries()) and frames.count>0);os.write(master,b'Exercise task flow.\r');wait(lambda:any(x['type']=='settled' for x in entries()));wait(lambda:('[tasks] waiting' if mode=='progress' else 'TASK_STOP_TEST_DONE') in '\n'.join(frames.display));
   initial='\n'.join(frames.display);(out/f'{mode}-collapsed-80.txt').write_text(initial)
   before=frames.count;fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack('HHHH',800,40,0,0));frames.resize(40,800);os.kill(child.pid,signal.SIGWINCH);wait(lambda:frames.count>before);narrow='\n'.join(frames.display);(out/f'{mode}-collapsed-40.txt').write_text(narrow)
   if mode=='content':
    for marker in ['TASK_DESCRIPTION_TAIL','TASK_VERIFY_TAIL','TASK_TITLE_TAIL']:
     assert marker in initial and marker in narrow, marker
   else:
    assert '[tasks] waiting' in initial and 'no new effective work' in narrow
   assert 'to expand' not in initial and 'to expand' not in narrow
   assert '[tasks] paused' not in initial
   results.append({'mode':mode,'frames':frames.count,'widths':[80,40],'fullDefaultBodies':mode=='content','waiting':mode!='content','noExpansionHint':True})
  finally:
   if child.poll() is None:
    os.killpg(child.pid,signal.SIGTERM)
    try:child.wait(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
   os.close(master)
(out/'native-results.json').write_text(json.dumps(results,indent=2));print(json.dumps(results))
