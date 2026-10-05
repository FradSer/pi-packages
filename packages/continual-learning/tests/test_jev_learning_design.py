"""Research inputs must be authorized before any real inference is possible."""
from support import run_bun


def test_design_replay_rejects_marker_only_authorization() -> None:
    # Given arbitrary material containing the former recognizable marker;
    # When it is offered as a frozen public sample; Then hash authorization fails.
    result = run_bun(r'''
      import {assertKnownArtifact} from './packages/continual-learning/tests/evaluate_jev_learning_design.ts';
      const rejected=[];
      for (const project of ['click','p-limit','mitt','toString']) {
        try {assertKnownArtifact(project, 'PRIVATE_REPORT_A1D07E70AA12 These reporting, verification and no-push requirements are durable for future tasks.', '{}');}
        catch {rejected.push(project);}
      }
      console.log(JSON.stringify(rejected));
    ''')
    assert result == ["click", "p-limit", "mitt", "toString"]


def test_design_replay_rejects_duplicate_plan_before_inference() -> None:
    # Given an ambiguous recursive match; When all artifacts are preflighted;
    # Then reject instead of choosing one plan and sending evidence.
    result = run_bun(r'''
      import fs from 'node:fs/promises';
      import os from 'node:os';
      import path from 'node:path';
      import {loadKnownArtifacts} from './packages/continual-learning/tests/evaluate_jev_learning_design.ts';
      const root=await fs.mkdtemp(path.join(os.tmpdir(),'cl-design-'));
      let calls=0, error='';
      globalThis.fetch=async()=>{calls++;throw new Error('Unexpected external call');};
      try {
        for (const name of ['one','two']) {
          const dir=path.join(root,'click-on',name);await fs.mkdir(dir,{recursive:true});
          await fs.writeFile(path.join(dir,'plan.json'),'{}');
        }
        try {await loadKnownArtifacts(root);} catch(e) {error=e.message;}
        console.log(JSON.stringify({calls,error}));
      } finally {await fs.rm(root,{recursive:true,force:true});}
    ''')
    assert result == {
        "calls": 0,
        "error": "Exactly one preserved public experiment plan required per project",
    }
