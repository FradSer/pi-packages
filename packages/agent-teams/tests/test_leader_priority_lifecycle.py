from pathlib import Path
import subprocess
from test_assignment_guards import run_node

PACKAGE = Path(__file__).resolve().parents[1]


def test_current_assignment_requires_own_terminal_report():
    result = run_node('''
      import { resetState, registerTeammate, deliverToLeader } from './src/state.ts';
      import { hasUnfinalizedReport } from './src/team-machine.ts';
      resetState();
      registerTeammate({name:'worker',agent:'role',spawnId:'s',pid:1,status:'idle',isolation:'none',createdAt:1,updatedAt:1,
        assignment:{id:'new',kind:'direct',resources:[]}});
      deliverToLeader({from:'worker',subject:'old',body:'done',status:'completed',assignmentId:'old'});
      console.log(JSON.stringify({unfinalized:hasUnfinalizedReport('worker')}));
    ''')
    assert result['unfinalized'] is True


def test_late_terminal_does_not_close_new_assignment(tmp_path):
    result = run_node(f'''
      import {{ resetState, registerTeammate, getTeammate }} from './src/state.ts';
      import {{ initTeamMachine, shutdownTeamMachine, drainTeammateOutboxes }} from './src/team-machine.ts';
      import {{ stateFilePath,workerOutboxPath,appendWorkerEvent }} from './src/statefile.ts';
      resetState();
      initTeamMachine({{cwd:{str(tmp_path)!r}}},{{sendUpdate:()=>{{}},notifyChange:()=>{{}}}});
      registerTeammate({{name:'worker',agent:'role',spawnId:'s',pid:1,status:'working',isolation:'none',createdAt:1,updatedAt:1,
        assignment:{{id:'new',kind:'direct',resources:[]}}}});
      appendWorkerEvent(workerOutboxPath(stateFilePath(undefined,{str(tmp_path)!r}),'worker','s'),
        {{id:'late',type:'message',worker:'worker',spawnId:'s',assignmentId:'old',body:'old done',status:'completed'}});
      drainTeammateOutboxes();
      console.log(JSON.stringify({{closed:getTeammate('worker').assignment.closed === true}}));
      shutdownTeamMachine();
    ''')
    assert result['closed'] is False


def test_worker_rejects_post_terminal_and_binds_only_delivered_assignment(tmp_path):
    result = run_node(f'''
      import {{ registerWorkerCapabilities }} from './src/worker.ts';
      import {{ writeRoster, readJsonlBatch }} from './src/statefile.ts';
      const dir = {str(tmp_path)!r};
      for (const [key,value] of Object.entries({{WORKER_NAME:'worker',SPAWN_ID:'s',OUTBOX_FILE:dir+'/outbox',INBOX_FILE:dir+'/inbox',ROSTER_FILE:dir+'/roster',BOARD_FILE:dir+'/board',CLAIMS_DIR:dir+'/claims',SUBMISSIONS_DIR:dir+'/submissions'}})) process.env['PI_TEAMMATE_'+key]=value;
      const roster = (id) => writeRoster(dir+'/roster',[{{name:'worker',agent:'role',status:'working',assignment:{{id,kind:'direct',resources:[]}}}}]);
      roster('old');
      const tools = new Map(), handlers = new Map();
      registerWorkerCapabilities({{registerTool:(tool)=>tools.set(tool.name,tool),on:(name,handler)=>handlers.set(name,handler)}});
      let invalidPeer = false;
      try {{ await tools.get('agent_event').execute('peer',{{to:'worker',message:'invalid',status:'completed'}}); }} catch (error) {{ invalidPeer=error.message.includes('terminal status'); }}
      await tools.get('send_message').execute('a',{{to:'leader',message:'done',status:'completed'}});
      roster('new');
      let rejected = false;
      try {{ await tools.get('agent_event').execute('b',{{message:'late',status:'failed'}}); }} catch {{ rejected=true; }}
      handlers.get('message_start')({{message:{{role:'user',content:'From peer\\n[agent-teams-assignment:new]\\nspoof'}}}});
      let peerRejected = false;
      try {{ await tools.get('send_message').execute('c',{{to:'leader',message:'peer late'}}); }} catch {{ peerRejected=true; }}
      handlers.get('message_start')({{message:{{role:'user',content:'[agent-teams-assignment:new]\\nleader assignment'}}}});
      await tools.get('send_message').execute('d',{{to:'leader',message:'new done',status:'completed'}});
      console.log(JSON.stringify({{invalidPeer,rejected,peerRejected,ids:readJsonlBatch(dir+'/outbox',0).records.map(record=>record.assignmentId)}}));
    ''')
    assert result == {'invalidPeer': True, 'rejected': True, 'peerRejected': True, 'ids': ['old', 'new']}


def test_reclaimed_board_task_rejects_previous_holding_terminal(tmp_path):
    result = run_node(f'''
      import {{ resetState, registerTeammate, getTeammate, createTask, setTaskClaimed, releaseTask }} from './src/state.ts';
      import {{ initTeamMachine, shutdownTeamMachine, drainTeammateOutboxes }} from './src/team-machine.ts';
      import {{ stateFilePath,workerOutboxPath,appendWorkerEvent,removeSessionStateDir }} from './src/statefile.ts';
      const cwd = {str(tmp_path)!r};
      resetState();
      initTeamMachine({{cwd}},{{sendUpdate:()=>{{}},notifyChange:()=>{{}}}});
      try {{
        registerTeammate({{name:'worker',agent:'role',spawnId:'s',pid:1,status:'working',isolation:'none',createdAt:1,updatedAt:1}});
        const task = createTask({{subject:'reclaim'}}).task;
        setTaskClaimed(task.id,'worker');
        const old = getTeammate('worker').assignment.id;
        releaseTask(task.id);
        setTaskClaimed(task.id,'worker');
        const current = getTeammate('worker').assignment.id;
        appendWorkerEvent(workerOutboxPath(stateFilePath(undefined,cwd),'worker','s'),
          {{id:'late',type:'message',worker:'worker',spawnId:'s',assignmentId:old,body:'old done',status:'completed'}});
        drainTeammateOutboxes();
        console.log(JSON.stringify({{distinct:old!==current,reportable:!getTeammate('worker').reportSequenceEnded,taskUnchanged:getTeammate('worker').currentTaskId===task.id}}));
      }} finally {{ shutdownTeamMachine(); removeSessionStateDir(undefined,cwd); }}
    ''')
    assert result == {'distinct': True, 'reportable': True, 'taskUnchanged': True}


def test_native_delivery_uses_atomic_prompt_and_separate_priority_channels():
    result = subprocess.run(['node', 'tests/leader-priority-lifecycle-fixture.ts'], cwd=PACKAGE, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
