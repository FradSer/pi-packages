from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from support import run_bun as _run_bun, run_bun_script

POLICY_HARNESS = Path(__file__).with_name("learning-policy-harness.ts")


def run_bun(source: str, root: Path) -> dict:
    return _run_bun(
        source,
        {"CONTROL_TEST_ROOT": str(root), "PI_CODING_AGENT_DIR": str(root / "agent")},
        timeout=30,
    )


def test_harness_apply_rejection_is_reported_with_its_reason() -> None:
    value = run_bun_script(POLICY_HARNESS, "harness-rejected")
    assert any("rejected" in notice.lower() and "already belongs" in notice for notice in value["notices"]), value
    assert value["lock"] is False


def test_phase_policies_preserve_defaults_and_manual_behavior(tmp_path: Path) -> None:
    result = run_bun(r"""
      import { automaticPhasePolicies } from './packages/continual-learning/extensions/learning-controls.ts';
      let invalid = false;
      try { automaticPhasePolicies({automaticPhases:{memory:'wrong'}}, 'automatic'); } catch { invalid = true; }
      console.log(JSON.stringify({
        defaults: automaticPhasePolicies({}, 'automatic'),
        configured: automaticPhasePolicies({automaticPhases:{memory:'propose',harness:'off'}}, 'automatic'),
        manual: automaticPhasePolicies({automaticPhases:{memory:'off',harness:'off'}}, 'manual'),
        disabled: automaticPhasePolicies({agentsMd:{disabled:true}}, 'manual'), invalid,
      }));
    """, tmp_path)
    assert result["defaults"] == {"memory": "apply", "harness": "apply", "agents": "apply"}
    assert result["configured"] == {"memory": "propose", "harness": "off", "agents": "apply"}
    assert result["manual"] == result["defaults"]
    assert result["disabled"]["agents"] == "off"
    assert result["invalid"] is True


def test_history_undo_is_exact_and_refuses_stale_or_foreign_targets(tmp_path: Path) -> None:
    result = run_bun(r"""
      import fs from 'node:fs'; import path from 'node:path';
      import { recordLearningMutation, listLearningHistory, previewLearningUndo, undoLearningChange } from './packages/continual-learning/extensions/learning-history.ts';
      const cwd = path.join(process.env.CONTROL_TEST_ROOT, 'project'); fs.mkdirSync(cwd);
      const target = path.join(cwd, 'AGENTS.md'); fs.writeFileSync(target, 'Before\n');
      await recordLearningMutation(cwd, 'agents', [target], async () => fs.writeFileSync(target, 'After\n'));
      const [record] = await listLearningHistory(cwd);
      const preview = await previewLearningUndo(cwd, record.id);
      fs.writeFileSync(target, 'Manual edit\n');
      let stale = false;
      try { await undoLearningChange(cwd, record.id, preview.digest); } catch { stale = true; }
      const preserved = fs.readFileSync(target,'utf8');
      fs.writeFileSync(target, 'After\n');
      await undoLearningChange(cwd, record.id, preview.digest);
      let repeated = false;
      try { await undoLearningChange(cwd, record.id, preview.digest); } catch { repeated = true; }
      let foreign = false;
      try { await recordLearningMutation(cwd, 'agents', [path.join(cwd,'..','outside.md')], async()=>{}); } catch { foreign = true; }
      console.log(JSON.stringify({stale,preserved,repeated,foreign,restored:fs.readFileSync(target,'utf8'),status:(await listLearningHistory(cwd))[0].status}));
    """, tmp_path)
    assert result == {"stale": True, "preserved": "Manual edit\n", "repeated": True, "foreign": True, "restored": "Before\n", "status": "undone"}


def test_history_rejects_symlinks_and_records_proposals_without_mutation(tmp_path: Path) -> None:
    result = run_bun(r"""
      import fs from 'node:fs'; import path from 'node:path';
      import { recordLearningMutation, recordLearningProposal, listLearningHistory } from './packages/continual-learning/extensions/learning-history.ts';
      const cwd = path.join(process.env.CONTROL_TEST_ROOT, 'project'); fs.mkdirSync(cwd);
      const outside = path.join(process.env.CONTROL_TEST_ROOT,'outside');fs.mkdirSync(outside);
      fs.symlinkSync(outside,path.join(cwd,'.pi'));
      let symlink = false, called = false;
      try { await recordLearningMutation(cwd,'harness',[path.join(cwd,'.pi','harness.json')],async()=>{called=true}); } catch { symlink=true; }
      await recordLearningProposal(cwd,'memory',{operations:[],newMemories:[{name:'example.md'}]});
      const records = await listLearningHistory(cwd);
      console.log(JSON.stringify({symlink,called,status:records[0].status,phase:records[0].phase,outside:fs.readdirSync(outside)}));
    """, tmp_path)
    assert result == {"symlink": True, "called": False, "status": "proposed", "phase": "memory", "outside": []}


def test_history_refuses_sensitive_proposals_and_source_snapshots(tmp_path: Path) -> None:
    result = run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {recordLearningProposal,recordLearningMutation,listLearningHistory} from './packages/continual-learning/extensions/learning-history.ts';
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project');fs.mkdirSync(cwd);
      const target=path.join(cwd,'AGENTS.md');fs.writeFileSync(target,'token: sk-test-secret');
      const refused=[];let called=false;
      for(const phase of ['memory','harness','agents'])try{await recordLearningProposal(cwd,phase,{report:[{quote:'token: sk-test-secret'}]})}catch{refused.push(phase)}
      try{await recordLearningProposal(cwd,'memory',{grounding:{credential:'synthetic-value'}})}catch{refused.push('nested')}
      try{await recordLearningMutation(cwd,'agents',[target],async()=>{called=true})}catch{refused.push('snapshot')}
      console.log(JSON.stringify({refused,called,records:(await listLearningHistory(cwd)).length}));
    """, tmp_path)
    assert result == {"refused": ["memory", "harness", "agents", "nested", "snapshot"], "called": False, "records": 0}


def test_history_accepts_ordinary_text_and_still_refuses_credential_shapes(tmp_path: Path) -> None:
    corpus = json.loads((Path(__file__).with_name("sensitive_memory_corpus.json")).read_text(encoding="utf-8"))
    result = run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {containsSensitiveMemoryMaterial} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {recordLearningMutation,recordLearningProposal,listLearningHistory} from './packages/continual-learning/extensions/learning-history.ts';
      const corpus=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/sensitive_memory_corpus.json','utf8'));
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project');fs.mkdirSync(cwd);
      const target=path.join(cwd,'AGENTS.md');fs.writeFileSync(target,corpus.benign.join('\n')+'\n');
      let applied='',ran=false;
      try{const result=await recordLearningMutation(cwd,'agents',[target],async()=>{ran=true;fs.appendFileSync(target,'- Recorded during learning.\n');return {outcome:'applied'}});applied=result.outcome}catch(error){applied=`refused: ${error instanceof Error?error.message:String(error)}`}
      let proposal='recorded';
      try{await recordLearningProposal(cwd,'memory',{report:corpus.benign.map(quote=>({quote}))})}catch{proposal='refused'}
      let sensitive='recorded';
      try{await recordLearningProposal(cwd,'memory',{report:corpus.sensitive.map(quote=>({quote}))})}catch{sensitive='refused'}
      console.log(JSON.stringify({applied,ran,proposal,sensitive,detected:corpus.sensitive.filter(value=>containsSensitiveMemoryMaterial(value)).length,falsePositives:corpus.benign.filter(value=>containsSensitiveMemoryMaterial(value)).length,recorded:fs.readFileSync(target,'utf8').includes('- Recorded during learning.')}));
    """, tmp_path)
    assert result == {"applied": "applied", "ran": True, "proposal": "recorded", "sensitive": "refused", "detected": len(corpus["sensitive"]), "falsePositives": 0, "recorded": True}


def test_history_scope_stays_stable_when_agent_root_is_created(tmp_path: Path) -> None:
    result = run_bun(r"""
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {recordLearningProposal,listLearningHistory} from './packages/continual-learning/extensions/learning-history.ts';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'history-new-agent-'));
      try {
        process.env.PI_CODING_AGENT_DIR=path.join(root,'agent');
        const cwd=path.join(root,'project');fs.mkdirSync(cwd);
        const id=await recordLearningProposal(cwd,'memory',{operations:[]});
        const records=await listLearningHistory(cwd);
        console.log(JSON.stringify({found:records.some(record=>record.id===id)}));
      } finally {fs.rmSync(root,{recursive:true,force:true})}
    """, tmp_path)
    assert result == {"found": True}


def test_history_accepts_project_alias_paths_without_following_surface_symlinks(tmp_path: Path) -> None:
    result = run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {recordLearningMutation,listLearningHistory} from './packages/continual-learning/extensions/learning-history.ts';
      const root=process.env.CONTROL_TEST_ROOT,cwd=path.join(root,'project'),alias=path.join(root,'project-alias');
      fs.mkdirSync(cwd);fs.symlinkSync(cwd,alias);
      const target=path.join(alias,'.pi','harness.json');
      await recordLearningMutation(fs.realpathSync(cwd),'harness',[target],async()=>{fs.mkdirSync(path.dirname(target));fs.writeFileSync(target,'{"rules":[]}')});
      const records=await listLearningHistory(cwd);
      const outside=path.join(root,'outside');fs.mkdirSync(outside);
      fs.renameSync(path.join(cwd,'.pi'),path.join(cwd,'old-pi'));fs.symlinkSync(outside,path.join(cwd,'.pi'));
      let refused=false,called=false;try{await recordLearningMutation(fs.realpathSync(cwd),'harness',[target],async()=>{called=true})}catch{refused=true}
      console.log(JSON.stringify({status:records[0].status,target:records[0].changes[0].target,refused,called}));
    """, tmp_path)
    assert result == {"status": "applied", "target": {"root": "project", "name": ".pi/harness.json"}, "refused": True, "called": False}


def test_learning_file_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "suite.json"
    os.mkfifo(fifo)
    source = r"""
      import {readLearningFile} from './packages/continual-learning/extensions/learning-history.ts';
      let refused=false;try{await readLearningFile(process.env.CONTROL_TEST_ROOT+'/suite.json')}catch{refused=true}
      console.log(JSON.stringify({refused}));
    """
    try:
        result = _run_bun(source, {"CONTROL_TEST_ROOT": str(tmp_path)}, timeout=2, parse=False)
    except subprocess.TimeoutExpired:
        pytest.fail("Opening a non-regular learning file blocked")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"refused": True}


def test_rejected_mutation_cannot_own_a_concurrent_edit(tmp_path: Path) -> None:
    result = run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {recordLearningMutation,listLearningHistory,previewLearningUndo} from './packages/continual-learning/extensions/learning-history.ts';
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project');fs.mkdirSync(cwd);
      const file=path.join(cwd,'AGENTS.md');fs.writeFileSync(file,'before');
      await recordLearningMutation(cwd,'agents',[file],async()=>{fs.writeFileSync(file,'concurrent manual edit');return {outcome:'failed'};});
      const records=await listLearningHistory(cwd);
      let undoable=false;try{await previewLearningUndo(cwd,records[0].id);undoable=true}catch{}
      console.log(JSON.stringify({applied:records.some(record=>record.status==='applied'),undoable,content:fs.readFileSync(file,'utf8')}));
    """, tmp_path)
    assert result == {"applied": False, "undoable": False, "content": "concurrent manual edit"}


def test_management_requires_headless_approval_and_rechecks_tui_preview(tmp_path: Path) -> None:
    result = run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {recordLearningMutation,listLearningHistory} from './packages/continual-learning/extensions/learning-history.ts';
      import {handleLearningManagement} from './packages/continual-learning/extensions/learning-management.ts';
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project');fs.mkdirSync(cwd);
      const target=path.join(cwd,'AGENTS.md');fs.writeFileSync(target,'before');
      await recordLearningMutation(cwd,'agents',[target],async()=>fs.writeFileSync(target,'after'));
      const [record]=await listLearningHistory(cwd),notices=[];
      let settings={autoMemory:true,instructions:'preserved'};
      const dependencies={readSettings:async()=>settings,writeSettings:async(next)=>{settings=next},busy:()=>false};
      const ctx={cwd,hasUI:false,ui:{notify:text=>notices.push(text),confirm:async()=>{fs.writeFileSync(target,'later edit');return true}}};
      await handleLearningManagement('undo '+record.id,ctx,dependencies);
      const headlessPreserved=fs.readFileSync(target,'utf8');
      ctx.hasUI=true;await handleLearningManagement('undo '+record.id,ctx,dependencies);
      const laterPreserved=fs.readFileSync(target,'utf8');
      fs.writeFileSync(target,'after');ctx.hasUI=false;
      await handleLearningManagement('undo '+record.id+' --yes',ctx,dependencies);
      await handleLearningManagement('policy harness propose',ctx,dependencies);
      console.log(JSON.stringify({headlessPreserved,laterPreserved,restored:fs.readFileSync(target,'utf8'),settings,errors:notices.filter(text=>text.includes('failed')).length}));
    """, tmp_path)
    assert result == {"headlessPreserved": "after", "laterPreserved": "later edit", "restored": "before", "settings": {"autoMemory": True, "instructions": "preserved", "automaticPhases": {"harness": "propose"}}, "errors": 2}


def test_undo_cannot_restore_a_private_memory_leak(tmp_path: Path) -> None:
    result = run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';import {execFileSync} from 'node:child_process';
      import {recordLearningMutation,listLearningHistory,previewLearningUndo,undoLearningChange} from './packages/continual-learning/extensions/learning-history.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project');fs.mkdirSync(cwd);execFileSync('git',['init','-q',cwd]);
      const paths=resolveMemoryPaths(cwd);fs.mkdirSync(paths.harnessDir,{recursive:true});fs.mkdirSync(paths.publicDir,{recursive:true});
      fs.writeFileSync(path.join(paths.harnessDir,'MEMORY.md'),'- [preference](preference.md) (harness only)\n');
      fs.writeFileSync(path.join(paths.harnessDir,'preference.md'),'private preference');
      const target=path.join(paths.publicDir,'preference.md');fs.writeFileSync(target,'private preference');
      await recordLearningMutation(cwd,'memory',[target],async()=>fs.unlinkSync(target));
      const [record]=await listLearningHistory(cwd),preview=await previewLearningUndo(cwd,record.id);
      let refused=false;try{await undoLearningChange(cwd,record.id,preview.digest)}catch{refused=true}
      console.log(JSON.stringify({refused,leaked:fs.existsSync(target)}));
    """, tmp_path)
    assert result == {"refused": True, "leaked": False}


def test_undo_cannot_restore_private_metadata_to_the_shared_index(tmp_path: Path) -> None:
    result = run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';import {execFileSync} from 'node:child_process';
      import {recordLearningMutation,listLearningHistory,previewLearningUndo,undoLearningChange} from './packages/continual-learning/extensions/learning-history.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project');fs.mkdirSync(cwd);execFileSync('git',['init','-q',cwd]);
      const paths=resolveMemoryPaths(cwd);fs.mkdirSync(paths.harnessDir,{recursive:true});fs.mkdirSync(paths.publicDir,{recursive:true});
      const privateIndex='- [preference](preference.md) (harness only) - private project detail\n';
      fs.writeFileSync(path.join(paths.harnessDir,'MEMORY.md'),privateIndex);fs.writeFileSync(path.join(paths.harnessDir,'preference.md'),'private preference');
      const target=path.join(paths.publicDir,'MEMORY.md');fs.writeFileSync(target,privateIndex);
      await recordLearningMutation(cwd,'memory',[target],async()=>fs.writeFileSync(target,'# Memory\n'));
      const [record]=await listLearningHistory(cwd),preview=await previewLearningUndo(cwd,record.id);
      let refused=false;try{await undoLearningChange(cwd,record.id,preview.digest)}catch{refused=true}
      console.log(JSON.stringify({refused,index:fs.readFileSync(target,'utf8')}));
    """, tmp_path)
    assert result == {"refused": True, "index": "# Memory\n"}


def test_interrupted_undo_recovers_successors_and_refuses_foreign_edits(tmp_path: Path) -> None:
    result = run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {recordLearningMutation,listLearningHistory,recoverLearningUndo} from './packages/continual-learning/extensions/learning-history.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project');fs.mkdirSync(cwd);
      const file=path.join(cwd,'AGENTS.md');fs.writeFileSync(file,'before');
      await recordLearningMutation(cwd,'agents',[file],async()=>fs.writeFileSync(file,'after'));
      const [record]=await listLearningHistory(cwd);record.status='undoing';
      const paths=resolveMemoryPaths(cwd),directory=path.join(paths.agentDir,'memory','history',paths.scopeKey);
      const recordFile=path.join(directory,record.id+'.json'),pending=path.join(directory,'undo-pending.json');
      fs.writeFileSync(recordFile,JSON.stringify(record));fs.writeFileSync(pending,JSON.stringify({id:record.id}));
      fs.writeFileSync(file,'foreign edit');let refused=false;try{await recoverLearningUndo(cwd)}catch{refused=true}
      const preserved=fs.readFileSync(file,'utf8');fs.writeFileSync(file,'before');
      await recoverLearningUndo(cwd);
      console.log(JSON.stringify({refused,preserved,content:fs.readFileSync(file,'utf8'),status:(await listLearningHistory(cwd))[0].status,pending:fs.existsSync(pending),lock:fs.existsSync(paths.lockFile)}));
    """, tmp_path)
    assert result == {"refused": True, "preserved": "foreign edit", "content": "after", "status": "applied", "pending": False, "lock": False}


def test_interrupted_mutation_requires_exact_predecessors_before_resuming(tmp_path: Path) -> None:
    result = run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {recordLearningMutation,listLearningHistory,checkPendingLearningMutations} from './packages/continual-learning/extensions/learning-history.ts';
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project');fs.mkdirSync(cwd);
      const file=path.join(cwd,'AGENTS.md');fs.writeFileSync(file,'before');fs.chmodSync(file,0o600);
      await recordLearningMutation(cwd,'agents',[file],async()=>{fs.writeFileSync(file,'partial or later edit');return {outcome:'failed'}});
      let refused=false;try{await checkPendingLearningMutations(cwd)}catch{refused=true}
      const preserved=fs.readFileSync(file,'utf8');
      fs.writeFileSync(file,'before');fs.chmodSync(file,0o644);
      let modeRefused=false;try{await checkPendingLearningMutations(cwd)}catch{modeRefused=true}
      fs.chmodSync(file,0o600);await checkPendingLearningMutations(cwd);
      console.log(JSON.stringify({refused,modeRefused,preserved,status:(await listLearningHistory(cwd))[0].status}));
    """, tmp_path)
    assert result == {"refused": True, "modeRefused": True, "preserved": "partial or later edit", "status": "abandoned"}


def test_new_undo_cannot_replace_an_interrupted_undo_journal(tmp_path: Path) -> None:
    result = run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {recordLearningMutation,listLearningHistory,previewLearningUndo,undoLearningChange} from './packages/continual-learning/extensions/learning-history.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project');fs.mkdirSync(path.join(cwd,'.pi'),{recursive:true});
      const agents=path.join(cwd,'AGENTS.md'),harness=path.join(cwd,'.pi','harness.json');
      fs.writeFileSync(agents,'before');fs.writeFileSync(harness,'before');
      await recordLearningMutation(cwd,'agents',[agents],async()=>fs.writeFileSync(agents,'after'));
      const [first]=await listLearningHistory(cwd);
      await recordLearningMutation(cwd,'harness',[harness],async()=>fs.writeFileSync(harness,'after'));
      const second=(await listLearningHistory(cwd)).find(record=>record.id!==first.id),preview=await previewLearningUndo(cwd,second.id);
      const paths=resolveMemoryPaths(cwd),directory=path.join(paths.agentDir,'memory','history',paths.scopeKey),journal=path.join(directory,'undo-pending.json');
      first.status='undoing';fs.writeFileSync(path.join(directory,first.id+'.json'),JSON.stringify(first));fs.writeFileSync(journal,JSON.stringify({id:first.id}));
      let refused=false;try{await undoLearningChange(cwd,second.id,preview.digest)}catch{refused=true}
      console.log(JSON.stringify({refused,journalPreserved:fs.existsSync(journal)&&JSON.parse(fs.readFileSync(journal,'utf8')).id===first.id,content:fs.readFileSync(harness,'utf8')}));
    """, tmp_path)
    assert result == {"refused": True, "journalPreserved": True, "content": "after"}


def test_recovery_reads_pending_state_while_holding_the_project_lock(tmp_path: Path) -> None:
    result = run_bun(r"""
      import fs from 'node:fs';import fsp from 'node:fs/promises';import path from 'node:path';
      import {recordLearningMutation,listLearningHistory,checkPendingLearningMutations,recoverLearningUndo} from './packages/continual-learning/extensions/learning-history.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project');fs.mkdirSync(cwd);
      const file=path.join(cwd,'AGENTS.md');fs.writeFileSync(file,'before');
      await recordLearningMutation(cwd,'agents',[file],async()=>fs.writeFileSync(file,'after'));
      const [record]=await listLearningHistory(cwd),paths=resolveMemoryPaths(cwd);
      const directory=path.join(paths.agentDir,'memory','history',paths.scopeKey),pending=path.join(directory,'undo-pending.json');
      const readdir=fsp.readdir.bind(fsp),open=fsp.open.bind(fsp),scanLocks=[],journalLocks=[];
      fsp.readdir=async(file,...args)=>{if(String(file)===directory)scanLocks.push(fs.existsSync(paths.lockFile));return readdir(file,...args)};
      fsp.open=async(file,...args)=>{if(String(file)===pending)journalLocks.push(fs.existsSync(paths.lockFile));return open(file,...args)};
      await checkPendingLearningMutations(cwd);
      record.status='undoing';fs.writeFileSync(path.join(directory,record.id+'.json'),JSON.stringify(record));fs.writeFileSync(pending,JSON.stringify({id:record.id}));
      fs.writeFileSync(file,'before');await recoverLearningUndo(cwd);
      console.log(JSON.stringify({scanLocks,journalLocks,content:fs.readFileSync(file,'utf8')}));
    """, tmp_path)
    assert result == {"scanLocks": [True], "journalLocks": [True], "content": "after"}


def test_undo_recovery_refuses_untracked_private_mirror_drift(tmp_path: Path) -> None:
    result = run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';import {execFileSync} from 'node:child_process';
      import {recordLearningMutation,listLearningHistory,recoverLearningUndo} from './packages/continual-learning/extensions/learning-history.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project');fs.mkdirSync(cwd);execFileSync('git',['init','-q',cwd]);
      const paths=resolveMemoryPaths(cwd);fs.mkdirSync(paths.harnessDir,{recursive:true});fs.mkdirSync(paths.publicDir,{recursive:true});
      const canonical=path.join(paths.harnessDir,'known.md'),shared=path.join(paths.publicDir,'known.md');
      fs.writeFileSync(canonical,'before');fs.writeFileSync(shared,'before');
      await recordLearningMutation(cwd,'memory',[canonical,shared],async()=>{fs.writeFileSync(canonical,'after');fs.writeFileSync(shared,'after')});
      const [record]=await listLearningHistory(cwd);record.status='undoing';
      const directory=path.join(paths.agentDir,'memory','history',paths.scopeKey);
      fs.writeFileSync(path.join(directory,record.id+'.json'),JSON.stringify(record));fs.writeFileSync(path.join(directory,'undo-pending.json'),JSON.stringify({id:record.id}));
      fs.writeFileSync(canonical,'before');
      fs.writeFileSync(path.join(paths.harnessDir,'MEMORY.md'),'- [private](private.md) (harness only)\n');
      fs.writeFileSync(path.join(paths.harnessDir,'private.md'),'private detail');fs.writeFileSync(path.join(paths.publicDir,'private.md'),'private detail');
      let refused=false;try{await recoverLearningUndo(cwd)}catch{refused=true}
      const preserved=fs.readFileSync(canonical,'utf8');fs.unlinkSync(path.join(paths.publicDir,'private.md'));
      await recoverLearningUndo(cwd);
      console.log(JSON.stringify({refused,preserved,restored:fs.readFileSync(canonical,'utf8'),status:(await listLearningHistory(cwd))[0].status}));
    """, tmp_path)
    assert result == {"refused": True, "preserved": "before", "restored": "after", "status": "applied"}


def test_independent_evaluator_detects_overbroad_rules(tmp_path: Path) -> None:
    result = run_bun(r"""
      import { evaluateLearningRules } from './packages/continual-learning/extensions/learning-evaluation.ts';
      const suite = {version:1,cases:[
        {id:'protect',bash:'retired-compiler build',expected:'block'},
        {id:'ordinary',bash:'pnpm test',expected:'execute'},
        {id:'quotation',bash:'printf retired-compiler',expected:'execute'},
      ]};
      const baseline = {rules:[{id:'narrow',bash:'^retired-compiler\\s',action:'block',message:'Use supported compiler'}]};
      const candidate = {rules:[{id:'broad',bash:'.*',action:'block',message:'Stop'}]};
      console.log(JSON.stringify(evaluateLearningRules(suite,baseline,candidate)));
    """, tmp_path)
    assert result["baseline"]["accuracy"] == 1
    assert result["candidate"]["accuracy"] == 1 / 3
    assert result["candidate"]["falseBlocks"] == 2
    assert result["regressions"] == ["ordinary", "quotation"]
    assert result["suiteDigest"] and result["candidateDigest"]


def test_evaluator_accounts_for_legacy_guidance_and_weaker_protection(tmp_path: Path) -> None:
    result = run_bun(r"""
      import {evaluateLearningRules} from './packages/continual-learning/extensions/learning-evaluation.ts';
      const suite={version:1,cases:[{id:'block',bash:'retired-compiler build',expected:'block'},
        {id:'guidance',skill:'review',userMessage:'audit release',expected:true},
        {id:'other',skill:'review',userMessage:'inspect docs',expected:false}]};
      const baseline={rules:[{id:'retired',bash:'^retired-compiler ',action:'block',message:'Use maintained compiler'}],
        skillPrompts:{review:{target:'system',prompt:'Check release evidence',userMessagePattern:'release'}}};
      const candidate={...baseline,rules:[{...baseline.rules[0],action:'confirm'}]};
      console.log(JSON.stringify(evaluateLearningRules(suite,baseline,candidate)));
    """, tmp_path)
    assert result["baseline"]["accuracy"] == 1
    assert result["candidate"]["missedProtections"] == 1
    assert result["regressions"] == ["block"]


def test_recovery_rechecks_each_target_before_restoring(tmp_path: Path) -> None:
    result = run_bun(r"""
      import {mock} from 'bun:test';
      import fs from 'node:fs';import fsp from 'node:fs/promises';import path from 'node:path';
      import {recordLearningMutation,listLearningHistory,recoverLearningUndo} from './packages/continual-learning/extensions/learning-history.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project');fs.mkdirSync(path.join(cwd,'.pi'),{recursive:true});
      const agents=path.join(cwd,'AGENTS.md'),harness=path.join(cwd,'.pi','harness.json');
      fs.writeFileSync(agents,'before');fs.writeFileSync(harness,'before');
      await recordLearningMutation(cwd,'agents',[agents,harness],async()=>{fs.writeFileSync(agents,'after');fs.writeFileSync(harness,'after')});
      const [record]=await listLearningHistory(cwd);record.status='undoing';
      const paths=resolveMemoryPaths(cwd),directory=path.join(paths.agentDir,'memory','history',paths.scopeKey);
      fs.writeFileSync(path.join(directory,record.id+'.json'),JSON.stringify(record));fs.writeFileSync(path.join(directory,'undo-pending.json'),JSON.stringify({id:record.id}));
      fs.writeFileSync(agents,'before');fs.writeFileSync(harness,'before');
      const rename=fsp.rename.bind(fsp);
      mock.module('node:fs/promises',()=>({...fsp,rename:async(from,to)=>{await rename(from,to);if(String(to)===fs.realpathSync(agents))fs.writeFileSync(harness,'later edit')}}));
      let refused=false;try{await recoverLearningUndo(cwd)}catch{refused=true}
      console.log(JSON.stringify({refused,agents:fs.readFileSync(agents,'utf8'),harness:fs.readFileSync(harness,'utf8')}));
    """, tmp_path)
    assert result == {"refused": True, "agents": "after", "harness": "later edit"}


def test_undo_write_failure_rolls_back_prior_files(tmp_path: Path) -> None:
    result = run_bun(r"""
      import {mock} from 'bun:test';
      import fs from 'node:fs';import fsp from 'node:fs/promises';import path from 'node:path';
      import {recordLearningMutation,listLearningHistory,previewLearningUndo,undoLearningChange} from './packages/continual-learning/extensions/learning-history.ts';
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project');fs.mkdirSync(path.join(cwd,'.pi'),{recursive:true});
      const agents=path.join(cwd,'AGENTS.md'),harness=path.join(cwd,'.pi','harness.json');
      fs.writeFileSync(agents,'before');fs.writeFileSync(harness,'before');
      await recordLearningMutation(cwd,'agents',[agents,harness],async()=>{fs.writeFileSync(agents,'after');fs.writeFileSync(harness,'after')});
      const [record]=await listLearningHistory(cwd),preview=await previewLearningUndo(cwd,record.id);
      const rename=fsp.rename.bind(fsp);let injected=false;
      mock.module('node:fs/promises',()=>({...fsp,rename:async(from,to)=>{if(!injected&&String(to)===fs.realpathSync(agents)){injected=true;throw new Error('fixture disk failure')}await rename(from,to)}}));
      let refused=false;try{await undoLearningChange(cwd,record.id,preview.digest)}catch{refused=true}
      console.log(JSON.stringify({refused,injected,agents:fs.readFileSync(agents,'utf8'),harness:fs.readFileSync(harness,'utf8'),status:(await listLearningHistory(cwd))[0].status}));
    """, tmp_path)
    assert result == {"refused": True, "injected": True, "agents": "after", "harness": "after", "status": "applied"}


@pytest.mark.parametrize("scenario", ["memory-propose", "harness-propose", "memory-apply", "all-off", "agents-propose", "agents-extraction"])
def test_automatic_phase_policy_controls_real_pipeline(scenario: str) -> None:
    value = run_bun_script(POLICY_HARNESS, scenario)
    assert value["lock"] is False, value
    assert not any("failed" in notice.lower() or "rejected" in notice.lower() for notice in value["notices"]), value
    if scenario == "all-off":
        assert value["selectors"] == 0 and value["planners"] == [], value
    else:
        assert value["selectors"] == 1, value
        assert value["plannerSystemInstructions"] == [True], value
        assert value["planners"] == ["agents" if scenario.startswith("agents-") else "harness" if scenario == "harness-propose" else "memory"], value
    if scenario == "memory-apply":
        assert "concise.md" in value["privateFiles"], value
        assert "concise.md" not in value["publicFiles"], value
        assert any(record["status"] == "applied" and any(change["target"]["name"] == "concise.md" for change in record["changes"]) for record in value["history"]), value
    else:
        assert value["privateFiles"] == [] and value["publicFiles"] == [], value
        assert value["harnessExists"] is False, value
        assert value["agentsUnchanged"] is True, value
        assert [record["status"] for record in value["history"]] == ([] if scenario == "all-off" else ["proposed"]), value
