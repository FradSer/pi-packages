"""One widget owner when a standalone child runs alongside a team."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_team_widget_excludes_standalone_children(tmp_path: Path) -> None:
    package = Path(__file__).resolve().parents[1]
    script = r'''
      import { ensureTeamWidget } from './src/ui.ts';
      import { registerAgent, resetRoster } from '@fradser/pi-subagents';
      resetRoster();
      const rows=[];
      const ctx={mode:'tui',ui:{setWidget(_key,factory){
        if(factory)rows.push(...factory({requestRender(){}},{fg:(_color,text)=>text,bold:text=>text}).render(90));
      }}};
      const base={role:'test',pid:1,status:'working',isolation:'none',createdAt:1,updatedAt:1};
      registerAgent({...base,name:'hosted',spawnId:'h'});
      registerAgent({...base,name:'standalone',spawnId:'s',standalone:true});
      ensureTeamWidget(ctx);
      console.log(JSON.stringify({rows}));
    '''
    result = subprocess.run(['node', '--input-type=module', '--eval', script],
        cwd=package, capture_output=True, text=True, timeout=30,
        env={**{key: value for key, value in os.environ.items() if not key.startswith('PI_TEAMMATE_')},
            'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)['rows']
    assert len(rows) == 1, rows
    assert 'hosted' in rows[0]
    assert 'standalone' not in rows[0]
