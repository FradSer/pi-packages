"""The real standalone entry mounts pi-kit's widget from roster callbacks."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from subagents_helpers import PACKAGE, SRC, run_node

SPAWNER = (SRC / 'spawner.ts').as_uri()
PREAMBLE = f"""
import assert from 'node:assert/strict';
import {{ mock }} from 'node:test';
import {{ visibleWidth }} from '@earendil-works/pi-tui';
import * as spawner from {json.dumps(SPAWNER)};
const spawns=[];
let acknowledge;
mock.module({json.dumps(SPAWNER)}, {{namedExports:{{...spawner,
  spawnResident:o=>(spawns.push(o),{{pid:7,accepted:new Promise(resolve=>acknowledge=resolve)}}),
  terminateAgent:async()=>({{outcome:'closed'}}),
}}}});
const {{default:extension,setAgentHost}}=await import({json.dumps((PACKAGE / 'index.ts').as_uri())});
const {{getAgent,resetRoster,registerAgent,updateAgent}}=await import({json.dumps((SRC / 'roster.ts').as_uri())});
resetRoster();setAgentHost(undefined);
const handlers=new Map(),tools=[],mounts=[],sent=[],widgets=new Map();
let renders=0;
const theme={{fg:(_color,text)=>text,bold:text=>text}};
const ui={{setWidget(key,factory,options){{
  widgets.get(key)?.dispose?.();widgets.delete(key);mounts.push({{key,mounted:!!factory,options}});
  if(factory)widgets.set(key,factory({{requestRender:()=>renders++}},theme));
}}}};
const pi={{registerTool:t=>tools.push(t),registerMessageRenderer(){{}},events:{{emit(){{}}}},
  sendMessage:(message,options)=>sent.push({{message,options}}),
  on:(name,handler)=>{{const list=handlers.get(name)??[];list.push(handler);handlers.set(name,list);}}
}};
extension(pi);
const ctx={{cwd:process.env.PI_TEST_CWD,mode:process.env.PI_TEST_MODE??'tui',ui}};
const event=async name=>{{for(const handler of handlers.get(name)??[])await handler({{}},ctx);}};
// The reload case: an extension loaded into a running session never sees a
// session start, so a test can ask for the surface without one.
if(!process.env.PI_TEST_SKIP_SESSION_START) await event('session_start');
const intentTools=new Map(tools.filter(t=>t.name.startsWith("agent_")).map(t=>[t.name,t]));
const call=(request)=>{{
  const {{operation,name,session,prompt,tools:grant,...rest}}=request;
  const tool=operation==="input"||operation==="steer"?"agent_input":operation==="inspect"?"agent_list"
    :operation==="stop"?"agent_stop":operation==="list"?"agent_list":"agent_start";
  const params=tool==="agent_start"
    ?{{prompt:prompt??"Start the assigned work.",...(name===undefined?{{}}:{{label:name}}),...(grant===undefined?{{}}:{{tools:grant}}),...rest}}
    :tool==="agent_input"?{{session,prompt,delivery:operation==="steer"?"steer":"next"}}:session===undefined?{{...rest}}:{{session,...rest}};
  return intentTools.get(tool).execute('probe',params,undefined,undefined,ctx);
}};
const lines=(width=90)=>[...widgets.values()].flatMap(widget=>widget.render(width));
const entry=(name,spawnId)=>({{name,role:name,spawnId,pid:8,status:'working',scope:'session',createdAt:1,updatedAt:1}});
"""


def run(script: str, tmp_path: Path, mode: str = 'tui', *, skip_session_start: bool = False) -> dict[str, object]:
    env = {
        'PI_TEST_CWD': str(tmp_path), 'PI_TEST_MODE': mode,
        'HOME': str(tmp_path), 'PI_CODING_AGENT_DIR': str(tmp_path / 'agent'),
        'XDG_CONFIG_HOME': str(tmp_path / 'config'), 'XDG_CACHE_HOME': str(tmp_path / 'cache'),
    }
    if skip_session_start:
        env['PI_TEST_SKIP_SESSION_START'] = '1'
    return run_node(PREAMBLE + script, module_mocks=True, env_overrides=env)


def test_a_child_started_without_a_session_start_still_mounts_activity(tmp_path: Path) -> None:
    """The reload case: no session start, so nothing may depend on having seen one.

    `session_start` used to be the only place the extension adopted its activity
    context. An extension reloaded into a running session never sees one, so the
    roster callback still ran, the widget update received no context, and the child
    working above the editor was invisible for the rest of the session. The live
    context is available on every tool call, which is exactly when a child starts.
    """
    result = run("""
      // The host fires `tool_call` before it executes the tool, which is where the
      // live context reaches the extension when no session start has.
      await event('tool_call');
      const pending=call({name:'reloaded',prompt:'1+1'});
      const mountedWhileStarting=mounts.length;
      acknowledge(true);
      await pending;
      console.log(JSON.stringify({
        mountedWhileStarting,
        rows:lines().filter(line=>line.includes('reloaded')).length,
      }));
    """, tmp_path, skip_session_start=True)
    assert result['mountedWhileStarting'] > 0, 'a child starting without a session start still paints the widget'
    assert result['rows'] > 0


def test_widget_mounts_while_start_acknowledgement_is_pending(tmp_path: Path) -> None:
    result = run("""
      const pending=call({name:'calculator',prompt:'1+1',tools:[]});
      await Promise.resolve();
      const before=lines();
      const placements=mounts.filter(m=>m.mounted).map(m=>m.options?.placement);
      acknowledge(true);const started=await pending;
      console.log(JSON.stringify({before,placements,started:started.details.ok,renders}));
    """, tmp_path)
    assert any('calculator · Starting' in line for line in result['before'])
    assert result['placements'] == ['aboveEditor']
    assert result['started'] is True
    assert result['renders'] > 0


def test_widget_streams_sanitized_activity_and_drops_settled_children(tmp_path: Path) -> None:
    result = run("""
      const first=call({name:'first',prompt:'1+1'});acknowledge(true);await first;
      const second=call({name:'second',prompt:'2+3'});acknowledge(true);await second;
      spawns[0].onUpdate({text:'',liveThinking:'**Checking** arithmetic',turns:1,finalResponse:false});
      const thinking=lines();
      spawns[0].onUpdate({text:'',activeTool:'read: 文件\u001b[31m\\n'+ 'x'.repeat(200),turns:1,finalResponse:false});
      const tool=lines(40);
      const bounded=[12,40,90,240].every(width=>lines(width).every(line=>visibleWidth(line)<=width&&!line.includes('\\n')));
      spawns[0].onUpdate({text:'2',turns:1,finalResponse:true,answerComplete:true});
      const remaining=lines();
      spawns[1].onError(new Error('fixture startup failure'));await new Promise(resolve=>setImmediate(resolve));
      console.log(JSON.stringify({thinking,tool,bounded,remaining,widgets:widgets.size,results:sent.length}));
    """, tmp_path)
    assert any('first · Checking arithmetic' in line for line in result['thinking'])
    assert any('read: 文件' in line for line in result['tool'])
    # pi-tui may add its own Markdown styling; the foreign red escape is stripped.
    assert all('\x1b[31m' not in line for line in result['tool'])
    assert result['bounded'] is True
    # The settled child left the area; the one still working keeps its row, and the
    # failed startup never gets one.
    assert len(result['remaining']) == 1
    assert any('second' in line for line in result['remaining'])
    assert not any('first' in line for line in result['remaining'])
    # Once the working child fails too, the area is empty and the widget unmounts.
    assert result['widgets'] == 0
    assert result['results'] == 2


def test_settled_standalone_child_leaves_the_activity_area(tmp_path: Path) -> None:
    result = run("""
      const pending=call({name:'resident',prompt:'1+1'});acknowledge(true);const started=await pending;
      spawns[0].onUpdate({text:'2',liveThinking:'old thinking',activeTool:'old tool',turns:1,finalResponse:true,answerComplete:true});
      const settled=lines();
      // Settling leaves the activity area; the child is still addressable, so it is
      // found through the roster rather than by a stale row.
      const page=await call({ operation:'list' });
      const child=page.details.sessions.find((row)=>row.session===started.details.session);
      console.log(JSON.stringify({settled,ok:page.details.ok,status:child?.status,
        label:child?.label,results:sent.length}));
    """, tmp_path)
    assert result['settled'] == []
    assert result['ok'] is True
    assert result['status'] == 'idle'
    assert result['label'] == 'resident'
    assert result['results'] == 1


def test_unanswered_settlement_also_leaves_the_activity_area(tmp_path: Path) -> None:
    result = run("""
      const pending=call({name:'resident',prompt:'finish safely'});acknowledge(true);await pending;
      spawns[0].onUpdate({text:'',liveThinking:'stale thinking',activeTool:'stale tool',turns:1,finalResponse:true,answerComplete:false,missingFinal:true});
      const settled=lines();
      console.log(JSON.stringify({settled,results:sent.length}));
    """, tmp_path)
    # An unanswered turn settles the child like any other, so the row goes with it
    # and its stale stream text never reaches the activity area.
    assert result['settled'] == []
    assert result['results'] == 1


def test_settled_residents_leave_the_area_while_confirmed_closure_clears_the_rest(tmp_path: Path) -> None:
    result = run("""
      const pendingFirst=call({name:'stopped',prompt:'one'});acknowledge(true);const first=await pendingFirst;
      const pendingSecond=call({name:'idle',prompt:'two'});acknowledge(true);const second=await pendingSecond;
      spawns[0].onUpdate({text:'done',turns:1,finalResponse:true,answerComplete:true});
      spawns[1].onUpdate({text:'done',turns:1,finalResponse:true,answerComplete:true});
      // Roster updates address the generated name behind the handle, not the label.
      updateAgent(first.details.name,{status:'stopped'});
      const rows=lines();
      console.log(JSON.stringify({rows,widgets:widgets.size,labels:[first.details.label,second.details.label]}));
    """, tmp_path)
    assert result['labels'] == ['stopped', 'idle']
    # Both children settled, so neither occupies the area; both stay addressable.
    assert result['rows'] == []
    assert result['widgets'] == 0, "an empty activity area mounts no widget at all"


def test_unconfirmed_stop_stays_visible_as_stopping_until_close(tmp_path: Path) -> None:
    result = run("""
      const pending=call({name:'resident',prompt:'one'});acknowledge(true);const started=await pending;
      // The child is still working when the leader asks it to stop, which is the
      // only state in which a stopping row exists: a settled child has left the area.
      spawns[0].onUpdate({text:'done',liveThinking:'stale',turns:1,finalResponse:false});
      const name=started.details.name;
      assert.notEqual(name,'resident','the roster address is the generated name');
      updateAgent(name,{leaderRequestedEnd:true});
      const stopping=lines();
      updateAgent(name,{status:'stopped'});
      const closed=lines();
      console.log(JSON.stringify({stopping,closed}));
    """, tmp_path)
    assert len(result['stopping']) == 1
    assert 'resident' in result['stopping'][0]
    assert 'Stopping...' in result['stopping'][0]
    assert 'Idle' not in result['stopping'][0]
    assert 'stale' not in result['stopping'][0]
    assert '⠋' in result['stopping'][0]
    assert result['closed'] == []


@pytest.mark.parametrize('mode', ['print', 'json', 'rpc'])
def test_non_terminal_sessions_never_mount_activity(tmp_path: Path, mode: str) -> None:
    result = run("""
      const pending=call({name:'headless',prompt:'1+1'});acknowledge(true);await pending;
      spawns[0].onUpdate({text:'2',turns:1,finalResponse:true,answerComplete:true});
      console.log(JSON.stringify({mounts:mounts.length,widgets:widgets.size,results:sent.length}));
    """, tmp_path, mode)
    assert result == {'mounts': 0, 'widgets': 0, 'results': 1}


def test_coordinator_widget_is_not_duplicated_but_standalone_work_still_renders(tmp_path: Path) -> None:
    directory = tmp_path / '.pi' / 'agents' / 'standalone'
    directory.mkdir(parents=True)
    (directory / 'agent.md').write_text('---\nname: standalone\ndescription: Independent durable role\ntools: read\n---\nStandalone role\n', encoding='utf-8')
    result = run("""
      setAgentHost({start:()=>({ok:true,session:'session:hosted:s1'}),stop:async()=>({ok:true})});
      registerAgent(entry('hosted','s1'));
      const hosted=lines();
      // Release the host so the next start really spawns: while a host owns the
      // session, the widget belongs to that host and this entry paints nothing.
      setAgentHost(undefined);
      const pending=call({name:'standalone',prompt:'1+1'});acknowledge(true);await pending;
      const standalone=lines();
      console.log(JSON.stringify({hosted,standalone}));
    """, tmp_path)
    assert result['hosted'] == []
    assert len(result['standalone']) == 1
    assert 'standalone' in result['standalone'][0]


def test_session_switch_remounts_and_shutdown_unsubscribes(tmp_path: Path) -> None:
    result = run("""
      const pending=call({name:'lifecycle',prompt:'1+1'});acknowledge(true);const started=await pending;
      const first=lines();await event('session_start');const restored=lines();
      await event('session_shutdown');const mountCount=mounts.length;
      // Address the real roster entry, so the no-remount claim is proven against
      // a live update rather than against a name nothing is filed under.
      updateAgent(started.details.name,{activeTool:'late progress'});
      console.log(JSON.stringify({first,restored,widgets:widgets.size,lateMounts:mounts.length-mountCount}));
    """, tmp_path)
    assert len(result['first']) == 1
    assert len(result['restored']) == 1
    assert result['widgets'] == 0
    assert result['lateMounts'] == 0
