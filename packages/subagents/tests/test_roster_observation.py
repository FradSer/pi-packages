"""Event-driven UI observation shares the same global roster as its writers."""
from __future__ import annotations

import json

from subagents_helpers import SRC, run_node


def test_observers_see_another_module_root_and_unsubscribe() -> None:
    url = (SRC / 'roster.ts').as_uri()
    result = run_node(f"""
      const a=await import({json.dumps(url + '?observer')});
      const b=await import({json.dumps(url + '?writer')});
      a.resetRoster();
      let calls=0;
      const stop=a.observeAgentRoster(()=>calls++);
      b.registerAgent({{name:'observed',role:'test',spawnId:'current',pid:1,status:'starting',scope:'session',createdAt:1,updatedAt:1}});
      b.updateAgentProgress('observed','current',{{liveText:'part',turns:1,sequenceEnded:false}});
      const afterUpdate=calls;
      b.updateAgentProgress('observed','retired',{{liveText:'stale',turns:1,sequenceEnded:false}});
      const afterStale=calls;
      stop();b.updateAgent('observed',{{status:'stopped'}});
      console.log(JSON.stringify({{distinct:a!==b,afterUpdate,afterStale,afterStop:calls}}));
    """)
    assert result == {'distinct': True, 'afterUpdate': 2, 'afterStale': 2, 'afterStop': 2}


def test_a_failed_ui_observer_cannot_hide_state_from_other_observers() -> None:
    url = (SRC / 'roster.ts').as_uri()
    result = run_node(f"""
      const {{resetRoster,observeAgentRoster,registerAgent,getAgent}}=await import({json.dumps(url)});
      resetRoster();let calls=0;
      const first=observeAgentRoster(()=>{{throw new Error('fixture render failure');}});
      const second=observeAgentRoster(()=>calls++);
      const registered=registerAgent({{name:'render-error',role:'test',spawnId:'s',pid:1,status:'starting',scope:'session',createdAt:1,updatedAt:1}});
      first();second();
      console.log(JSON.stringify({{ok:registered.ok,calls,visible:getAgent('render-error').name}}));
    """)
    assert result == {'ok': True, 'calls': 1, 'visible': 'render-error'}
