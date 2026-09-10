from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_real_tool_hook_blocks_invalid_harness_writes_and_reports_inactive_skills() -> None:
    source = r'''
      import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path';
      import register from './packages/continual-learning/extensions/guardrails.ts';
      const dir=fs.mkdtempSync(path.join(os.tmpdir(),'cl-write-gate-'));
      const hooks={},commands={},notices=[];
      const pi={on:(n,f)=>hooks[n]=f,registerCommand:(n,c)=>commands[n]=c,
        registerMessageRenderer(){},registerEntryRenderer(){},appendEntry(){},getCommands:()=>[{name:'skill:known',source:'skill'}]};
      const ctx={cwd:dir,hasUI:true,ui:{notify:(m)=>notices.push(m)}};
      try {
        register(pi);
        const target=path.join(dir,'.pi/harness.local.json');
        const invoke=(p,c)=>hooks.tool_call({toolName:'write',input:{path:p,content:JSON.stringify(c)}},ctx);
        const edit=await hooks.tool_call({toolName:'edit',input:{path:target,oldText:'{}',newText:'bad'}},ctx);
        const bad=await invoke(target,{skillPrompts:{invented:{prompt:'global rule',target:'system'}}});
        const string=await invoke(target,{skillPrompts:{known:'not an object'}});
        const good=await invoke(target,{skillPrompts:{known:{prompt:'guidance',target:'system'}}});
        const unrelated=await invoke(path.join(dir,'ordinary.json'),{skillPrompts:{invented:'text'}});
        fs.mkdirSync(path.dirname(target),{recursive:true});
        fs.writeFileSync(target,JSON.stringify({skillPrompts:{invented:{prompt:'old',target:'system'}}}));
        await commands.harness.handler('',ctx);
        console.log(JSON.stringify({edit:edit??null,bad,string,good:good??null,unrelated:unrelated??null,notices}));
      } finally {fs.rmSync(dir,{recursive:true,force:true})}
    '''
    result = subprocess.run(['bun', '-e', source], cwd=REPO, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert out['edit']['block'] is True
    assert out['bad']['block'] is True
    assert out['string']['block'] is True
    assert out['good'] is None
    assert out['unrelated'] is None
    assert any('inactive' in message and 'invented' in message for message in out['notices'])
