from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from support import run_bun as _run_bun, run_bun_script

POLICY_HARNESS = Path(__file__).with_name("learning-policy-harness.ts")


@pytest.mark.parametrize('scenario,reason,held', [
    ('memory-apply', 'repair-held', True),
    ('memory-apply', 'subset-independent', True),
    ('memory-apply', 'repair-supported', False),
    ('memory-propose', 'supported', False),
])
def test_semantically_held_memory_cannot_launch_later_planners(scenario, reason, held):
    # Given Memory that is held after its bounded repair, When later phases
    # are selected, Then retain the proposal/cost but do not call those workers.
    # A verified repair and an intentional validated preview still permit them.
    value = run_bun_script(POLICY_HARNESS, scenario,
                           env={'CL_JEV_FIXTURE': reason, 'CL_LATER_AFTER_MEMORY': '1'})
    receipts = [r for r in [value.get('registryReceipt'), *[run.get('receipt') for run in value['runs']]] if r]
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt['screen']['harness'] and receipt['screen']['agents']
    assert receipt['totals']['totalTokens'] >= 0
    if held:
        assert receipt['totals']['totalTokens'] > 0
        assert value['planners'] == ['memory'], value['planners']
        assert not any(a['phase'] in ('harness', 'agents') for a in receipt['attempts'])
        assert any(a['phase'] == 'memory' and (a['outcome'] == 'proposed' or a.get('pendingOperations')) for a in receipt['attempts'])
        if reason == 'subset-independent':
            assert receipt['operations'] == 2
            assert any(a.get('pendingOperations') == 1 for a in receipt['attempts'])
        else:
            assert receipt['operations'] == 0
        assert any(r['phase'] == 'memory' and r['status'] == 'proposed' for r in value['history'])
        assert not value['harnessExists'] and value['agentsUnchanged']
    else:
        assert set(value['planners']) == {'memory', 'harness', 'agents'}, value['planners']
    assert not value['lock']


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
      const refused=[];let called=false;let snapshotError='';
      for(const phase of ['memory','harness','agents'])try{await recordLearningProposal(cwd,phase,{report:[{quote:'token: sk-test-secret'}]})}catch{refused.push(phase)}
      try{await recordLearningProposal(cwd,'memory',{grounding:{credential:'synthetic-value'}})}catch{refused.push('nested')}
      try{await recordLearningMutation(cwd,'agents',[target],async()=>{called=true})}catch(error){refused.push('snapshot');snapshotError=error instanceof Error?error.message:String(error)}
      console.log(JSON.stringify({refused,called,snapshotError,records:(await listLearningHistory(cwd)).length}));
    """, tmp_path)
    assert result["refused"] == ["memory", "harness", "agents", "nested", "snapshot"]
    assert result["called"] is False and result["records"] == 0
    assert "refuses sensitive material" in result["snapshotError"] and "project/AGENTS.md" in result["snapshotError"], result["snapshotError"]


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
      // Measure the file operation after imports, independently of Bun startup.
      let watchdog;
      const result = await Promise.race([
        readLearningFile(process.env.CONTROL_TEST_ROOT+'/suite.json').then(
          () => ({refused:false}), () => ({refused:true})),
        new Promise(resolve => {watchdog=setTimeout(() => resolve({blocked:true}),1000)}),
      ]);
      clearTimeout(watchdog);
      console.log(JSON.stringify(result));
      if (result.blocked) process.exit(1);
    """
    try:
        result = _run_bun(source, {"CONTROL_TEST_ROOT": str(tmp_path)}, timeout=10, parse=False)
    except subprocess.TimeoutExpired:
        pytest.fail("Opening a non-regular learning file blocked")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"refused": True}


@pytest.mark.parametrize('operation', ['read', 'hash', 'agents-race'])
def test_consolidation_read_refuses_fifo_without_blocking(tmp_path: Path, operation: str) -> None:
    # Given a FIFO (or a regular file replaced after lstat), When reading for
    # consolidation, Then refuse without waiting for another process to open it.
    source = r'''
      import fs from 'node:fs/promises';import {spawnSync} from 'node:child_process';
      import {readBoundedRegularFile,sha256File} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {planAgentsMdConsolidationPhase} from './packages/continual-learning/extensions/agents-md-consolidation.ts';
      const cwd=process.env.CONTROL_TEST_ROOT,file=cwd+'/AGENTS.md',mode=process.env.CL_FILE_OPERATION;
      if(mode==='agents-race') {
        await fs.writeFile(file,'Project instructions.');const original=fs.lstat.bind(fs);let swapped=false;
        fs.lstat=async (p,...args)=>{const st=await original(p,...args);
          if(p===file&&!swapped){swapped=true;await fs.unlink(file);const r=spawnSync('mkfifo',[file]);if(r.status!==0)throw Error('FIFO setup failed');}return st;};
      } else {const r=spawnSync('mkfifo',[file]);if(r.status!==0)throw Error('FIFO setup failed');}
      let watchdog;const action=mode==='agents-race'
        ? planAgentsMdConsolidationPhase({ui:{notify(){}}},{active:true,generation:1,cancelled:false},
          {cwd,pkgDir:process.cwd(),reason:'test',budgetBytes:16384,disabled:false},{manifest:{}},1)
          .then(r=>({refused:r.outcome==='failed'}))
        : (mode==='hash'?sha256File(file,100):readBoundedRegularFile(file,100)).then(()=>({refused:false}),()=>({refused:true}));
      const result=await Promise.race([action,new Promise(resolve=>{watchdog=setTimeout(()=>resolve({blocked:true}),1000)})]);
      clearTimeout(watchdog);console.log(JSON.stringify(result));if(result.blocked)process.exit(1);
    '''
    result = _run_bun(source, {'CONTROL_TEST_ROOT': str(tmp_path), 'CL_FILE_OPERATION': operation}, timeout=10, parse=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {'refused': True}


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
      let settings={autoSettledLearning:true,autoContinualLearning:false,instructions:'preserved'};
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
    assert result == {"headlessPreserved": "after", "laterPreserved": "later edit", "restored": "before", "settings": {"autoSettledLearning": True, "autoContinualLearning": False, "instructions": "preserved", "automaticPhases": {"harness": "propose"}}, "errors": 2}


def test_policy_refuses_to_display_or_write_invalid_settings(tmp_path: Path) -> None:
    result = run_bun(r"""
      import {handleLearningManagement} from './packages/continual-learning/extensions/learning-management.ts';
      const notices=[];let writes=0;
      const ctx={cwd:process.env.CONTROL_TEST_ROOT,hasUI:false,ui:{notify:(text,level)=>notices.push({text,level})}};
      const dependencies={readSettings:async()=>({autoSettledLearning:false,autoContinualLearning:false,invalid:'Repair settings first'}),writeSettings:async()=>{writes++},busy:()=>false};
      await handleLearningManagement('policy',ctx,dependencies);
      await handleLearningManagement('policy memory apply',ctx,dependencies);
      console.log(JSON.stringify({writes,notices}));
    """, tmp_path)
    assert result["writes"] == 0, result
    assert len(result["notices"]) == 2, result
    assert all(notice["level"] == "error" and "Repair settings first" in notice["text"] for notice in result["notices"]), result


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


def test_normalize_tracks_bare_private_mirror_deletion_and_refuses_unsafe_undo(tmp_path: Path) -> None:
    result = run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';import {execFileSync} from 'node:child_process';
      import {normalizeTrackedMemory,listLearningHistory,previewLearningUndo,undoLearningChange} from './packages/continual-learning/extensions/learning-history.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project');fs.mkdirSync(cwd);execFileSync('git',['init','-q',cwd]);
      const paths=resolveMemoryPaths(cwd);fs.mkdirSync(paths.harnessDir,{recursive:true});fs.mkdirSync(paths.publicDir,{recursive:true});
      fs.writeFileSync(path.join(paths.harnessDir,'MEMORY.md'),'Preference.md (harness only)\n');
      fs.writeFileSync(path.join(paths.harnessDir,'Preference.md'),'private preference');
      const publicSecret=path.join(paths.publicDir,'Preference.md');fs.writeFileSync(publicSecret,'private preference');
      const normalized=await normalizeTrackedMemory(paths);
      const [record]=await listLearningHistory(cwd);
      const tracked=record?.changes.some(change=>change.target.root==='public'&&change.target.name==='Preference.md');
      const preview=await previewLearningUndo(cwd,record.id);let refused=false;
      try{await undoLearningChange(cwd,record.id,preview.digest)}catch{refused=true}
      console.log(JSON.stringify({removed:normalized.removed,tracked,refused,leaked:fs.existsSync(publicSecret)}));
    """, tmp_path)
    assert result == {"removed": ["Preference.md"], "tracked": True, "refused": True, "leaked": False}


def test_undo_rejects_a_bare_private_reference_in_the_shared_index(tmp_path: Path) -> None:
    result = run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';import {execFileSync} from 'node:child_process';
      import {recordLearningMutation,listLearningHistory,previewLearningUndo,undoLearningChange} from './packages/continual-learning/extensions/learning-history.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project');fs.mkdirSync(cwd);execFileSync('git',['init','-q',cwd]);
      const paths=resolveMemoryPaths(cwd);fs.mkdirSync(paths.harnessDir,{recursive:true});fs.mkdirSync(paths.publicDir,{recursive:true});
      fs.writeFileSync(path.join(paths.harnessDir,'MEMORY.md'),'secret.md (harness only)\n');
      fs.writeFileSync(path.join(paths.harnessDir,'secret.md'),'private preference');
      const publicIndex=path.join(paths.publicDir,'MEMORY.md');fs.writeFileSync(publicIndex,'secret.md\n');
      await recordLearningMutation(cwd,'memory',[publicIndex],async()=>fs.writeFileSync(publicIndex,'# Memory\n'));
      const [record]=await listLearningHistory(cwd),preview=await previewLearningUndo(cwd,record.id);let refused=false;
      try{await undoLearningChange(cwd,record.id,preview.digest)}catch{refused=true}
      console.log(JSON.stringify({refused,index:fs.readFileSync(publicIndex,'utf8')}));
    """, tmp_path)
    assert result == {"refused": True, "index": "# Memory\n"}


def test_undo_allows_a_bare_private_body_update_without_public_mirror(tmp_path: Path) -> None:
    result = run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';import {execFileSync} from 'node:child_process';
      import {recordLearningMutation,listLearningHistory,previewLearningUndo,undoLearningChange} from './packages/continual-learning/extensions/learning-history.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project');fs.mkdirSync(cwd);execFileSync('git',['init','-q',cwd]);
      const paths=resolveMemoryPaths(cwd);fs.mkdirSync(paths.harnessDir,{recursive:true});fs.mkdirSync(paths.publicDir,{recursive:true});
      fs.writeFileSync(path.join(paths.harnessDir,'MEMORY.md'),'private.md (harness only)\n');
      const privateFile=path.join(paths.harnessDir,'private.md');fs.writeFileSync(privateFile,'before\n');
      fs.writeFileSync(path.join(paths.publicDir,'MEMORY.md'),'# Memory\n');
      await recordLearningMutation(cwd,'memory',[privateFile],async()=>fs.writeFileSync(privateFile,'after\n'));
      const [record]=await listLearningHistory(cwd),preview=await previewLearningUndo(cwd,record.id);
      await undoLearningChange(cwd,record.id,preview.digest);
      console.log(JSON.stringify({body:fs.readFileSync(privateFile,'utf8'),publicExists:fs.existsSync(path.join(paths.publicDir,'private.md'))}));
    """, tmp_path)
    assert result == {"body": "before\n", "publicExists": False}


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


@pytest.mark.parametrize("scenario,expected", [
    ("manual-declined", []),
    ("manual-constraint", ["memory", "harness"]),
    ("manual-harness-marker", ["harness"]),
])
def test_manual_consolidation_honors_the_reviewed_selector_verdict(scenario: str, expected: list[str]) -> None:
    value = run_bun_script(POLICY_HARNESS, scenario)
    assert value["selectors"] == 1, value
    assert value["planners"] == expected, value
    assert value["lock"] is False, value
    for record in value["history"]:
        assert {change["target"]["name"] for change in record["changes"]} <= {"MEMORY.md"}, record
    assert not any("failed" in notice.lower() or "rejected" in notice.lower() for notice in value["notices"]), value
    if scenario == "manual-declined":
        assert value["registryReceipt"]["screen"]["memory"] is False, value["registryReceipt"]
        assert value["registryReceipt"]["screen"]["harness"] is False, value["registryReceipt"]
        assert "selector-declined-memory" in value["registryReceipt"]["screen"]["reasons"], value["registryReceipt"]
        assert [attempt["phase"] for attempt in value["registryReceipt"]["attempts"]] == ["selector"], value["registryReceipt"]


def test_completed_memory_runs_keep_their_plan_for_inspection() -> None:
    value = run_bun_script(POLICY_HARNESS, "manual-constraint")
    planned = [run for run in value["runs"] if "plan.json" in run["files"]]
    assert len(planned) == 1, value["runs"]
    assert {"plan.json", "task.md", "pre-receipt.json", "post-receipt.json", "manifest.json", "snapshot.json"} <= set(planned[0]["files"]), planned[0]


@pytest.mark.parametrize("scenario", ["memory-propose", "harness-propose", "memory-apply", "all-off", "agents-propose", "agents-extraction"])
def test_automatic_phase_policy_controls_real_pipeline(scenario: str) -> None:
    value = run_bun_script(POLICY_HARNESS, scenario)
    assert value["lock"] is False, value
    assert not any("failed" in notice.lower() or "rejected" in notice.lower() for notice in value["notices"]), value
    if scenario == "all-off":
        assert value["selectors"] == 0 and value["planners"] == [], value
    else:
        assert value["selectors"] == (1 if scenario.startswith("agents-") else 0), value
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


def test_consolidation_model_is_frozen_per_pipeline_and_refreshed_next_pipeline() -> None:
    value = run_bun_script(POLICY_HARNESS, "model-freeze")
    assert value["selectors"] == 2, value
    assert value["modelCalls"] == [
        "selector:old/one", "planner:old/one", "planner:old/one", "planner:old/one",
        "selector:new/two", "planner:new/two", "planner:new/two", "planner:new/two",
    ], value


def test_session_model_fallback_is_frozen_across_all_learning_phases() -> None:
    value = run_bun_script(POLICY_HARNESS, "session-model-freeze")
    assert value["selectors"] == 2, value
    assert value["modelCalls"] == [
        "selector:session/active", "planner:session/active", "planner:session/active", "planner:session/active",
        "selector:new/two", "planner:new/two", "planner:new/two", "planner:new/two",
    ], value


def test_harness_repair_receipt_counts_both_workers_and_one_retry() -> None:
    value = run_bun_script(POLICY_HARNESS, "harness-repair-cost")
    receipt = value["registryReceipt"]
    assert receipt["kind"] == "learning-pipeline-receipt", value
    attempts = [attempt for attempt in receipt["attempts"] if attempt["phase"] == "harness"]
    assert value["planners"] == ["harness", "harness"], value
    assert [(attempt["attempt"], attempt["outcome"]) for attempt in attempts] == [(0, "rejected"), (1, "proposed")], receipt
    assert [attempt["usage"]["totalTokens"] for attempt in attempts] == [15, 30], receipt
    assert receipt["totals"]["input"] == 30, receipt
    assert receipt["totals"]["output"] == 6, receipt
    assert receipt["totals"]["cacheRead"] == 9, receipt
    assert receipt["totals"]["totalTokens"] == 45, receipt
    assert receipt["totals"]["cost"] == pytest.approx(0.03), receipt
    assert receipt["retries"] == 1, receipt
    assert receipt["operations"] == 0, receipt


def test_code_expressions_and_env_references_do_not_trip_sensitive_detector(tmp_path: Path) -> None:
    result = run_bun(r"""
      import {containsSensitiveMemoryMaterial} from './packages/continual-learning/extensions/consolidation-run.ts';
      const benignCode = [
        'apiKey: process.env.TYPESAFE_API_KEY',
        'apiKey = live ? process.env.TYPESAFE_API_KEY : "fixture-only"',
        'apiKey: "fixture"',
        'apiKey: "fixture-absent-sdk"',
        'apiKey: config.apiKey',
        'apiKey: options.apiKey',
        'apiKey: (config.apiKey || "fallback")',
        'token = process.env.GITHUB_TOKEN',
        'password: "test-password-123"',
      ];
      const realSecrets = [
        'password: hunter2-super-secret-value',
        'api_key: my-secret-prod-token-12345',
        'export API_KEY=sk-live-9f3a2b7c4d5e6f70',
      ];
      console.log(JSON.stringify({
        benignPassed: benignCode.every(code => !containsSensitiveMemoryMaterial(code)),
        secretsCaught: realSecrets.every(secret => containsSensitiveMemoryMaterial(secret)),
      }));
    """, tmp_path)
    assert result == {"benignPassed": True, "secretsCaught": True}


def test_agent_triggered_memory_learns_once_before_the_answer_and_deduplicates_settlement() -> None:
    # Given the agent trigger is enabled with Memory apply, When the agent calls
    # the learning tool before answering, Then exactly one Memory pipeline runs
    # under the configured policy, a second call echoes the recorded outcome,
    # and the settled run keeps Harness/AGENTS handling without a second Memory run.
    value = run_bun_script(POLICY_HARNESS, "agent-memory-apply")
    assert value["agentFirst"] == {
        "text": "Memory learning finished: Learning 1 memory applied · usage unavailable · cost unavailable",
        "status": "applied", "operations": 1,
        "settledSubject": "learned 1 Memory change", "replayBound": True, "isError": False,
    }, value["agentFirst"]
    assert value["agentSecond"]["text"] == value["agentFirst"]["text"], value["agentSecond"]
    assert value["agentSecond"]["status"] == "already-learned" and value["agentSecond"]["isError"] is False, value["agentSecond"]
    assert value["planners"] == ["memory"], value["planners"]
    # The empty Memory index parent-routes explicit evidence without a selector
    # worker for both the agent run and the settled run.
    assert value["selectors"] == 0, value["selectors"]
    # A normal interactive session binds the receipt for later replay.
    assert value["agentFirst"].get("replayBound") is True, value["agentFirst"]
    assert "concise.md" in value["privateFiles"], value
    assert value["harnessExists"] is False and value["agentsUnchanged"] is True, value
    # No second Memory pipeline runs: the acknowledged replay reference lets
    # the settled learner skip the whole already-processed task.
    assert [phase for phase in value["planners"] if phase == "memory"] == ["memory"], value["planners"]


def test_started_no_change_run_still_reports_its_outcome_row() -> None:
    # Given the real open-deskos failure: `[learning] started · <topic>` was
    # emitted, the tool result honestly said "Learning no changes written" (or
    # "Memory organized in-process"), but no terminal transcript row followed.
    # An automatic noop/screened receipt was filtered out of reporting while
    # its started row was not. When that pipeline finishes, Then every started
    # row has its paired result row describing the same receipt.
    value = run_bun_script(POLICY_HARNESS, "agent-memory-organize")
    assert value["startedSubjects"], value
    assert len(value["resultContents"]) == len(value["startedSubjects"]), value
    receipt = value["registryReceipt"]
    assert receipt is not None, value
    assert "organized" in value["resultContents"][0].lower(), value["resultContents"]
    assert "organized" in value["agentFirst"]["text"].lower(), value["agentFirst"]


def test_pure_organize_request_completes_in_process_without_workers() -> None:
    # Given the user only asks to organize Memory, When the parent tool runs,
    # Then it finishes the organization itself: no selector or planner child,
    # no proposal for external action, and a receipt with an explicit scope.
    value = run_bun_script(POLICY_HARNESS, "agent-memory-organize")
    first = value["agentFirst"]
    assert first["status"] == "organized" and first["isError"] is False, first
    assert value["selectors"] == 0 and value["planners"] == [], value
    assert [record["status"] for record in value["history"] if record["status"] == "proposed"] == [], value["history"]
    receipt = value["registryReceipt"]
    assert receipt is not None, value
    assert "organized-in-process" in receipt["screen"].get("routing", []), receipt["screen"]
    assert receipt["input"]["screenedEntryCount"] == 1, receipt["input"]
    assert "no proposals" in first["text"].lower(), first["text"]


def test_agent_triggered_memory_propose_saves_a_reviewable_outcome() -> None:
    value = run_bun_script(POLICY_HARNESS, "agent-memory-propose")
    assert value["agentFirst"]["status"] == "proposed" and value["agentFirst"]["isError"] is False, value["agentFirst"]
    assert value["planners"] == ["memory"], value["planners"]
    assert value["privateFiles"] == [] and value["publicFiles"] == [], value
    assert [record["status"] for record in value["history"]] == ["proposed"], value["history"]


def test_disabled_agent_trigger_never_starts_a_pipeline() -> None:
    value = run_bun_script(POLICY_HARNESS, "agent-memory-disabled")
    assert value["agentFirst"] == {
        "text": "Agent-triggered Memory learning is disabled by settings. Report this accurately and continue the task; do not retry.",
        "status": "disabled", "operations": None,
        "settledSubject": "agent-triggered learning is disabled", "isError": False,
    }, value["agentFirst"]
    assert value["selectors"] == 0 and value["planners"] == [], value
    assert "registryReceipt" not in value or value["registryReceipt"] is None, value
    assert "concise.md" not in value["privateFiles"], value


def test_agent_trigger_never_runs_harness_or_agents_even_when_configured_to_apply() -> None:
    # Given every automatic phase is configured to apply, When the agent requests
    # current-task Memory learning, Then only the Memory phase may run: the tool
    # never rewrites execution rules or always-loaded instructions.
    value = run_bun_script(POLICY_HARNESS, "agent-memory-all-phases")
    assert value["agentFirst"]["status"] == "applied", value["agentFirst"]
    assert value["planners"] == ["memory"], value["planners"]
    assert value["harnessExists"] is False, value
    assert value["agentsUnchanged"] is True, value
    receipt = value["registryReceipt"]
    assert receipt["screen"]["harness"] is False and receipt["screen"]["agents"] is False, receipt


def test_extension_only_learning_model_blocks_before_any_worker_spawns() -> None:
    # A model registered by a session extension resolves in the parent but not in
    # read-only planner children, which run without extensions. The parent must
    # refuse up front with the actionable fix instead of failing the selector.
    value = run_bun_script(POLICY_HARNESS, "manual-model-unavailable")
    assert value["selectors"] == 0 and value["planners"] == [], value
    assert any("Learning is blocked" in notice and "/memory model" in notice for notice in value["notices"]), value["notices"]
    receipt = value["registryReceipt"]
    assert [(attempt["phase"], attempt["outcome"]) for attempt in receipt["attempts"]] == [("selector", "failed")], receipt
    assert "read-only planner workers" in receipt["attempts"][0]["diagnostic"], receipt
    assert value["lock"] is False, value
    assert value["history"] == [], value


def test_agent_learning_still_runs_when_the_replay_backlog_is_unavailable() -> None:
    # Given a malformed historical backlog row, When the agent requests Memory
    # learning before answering, Then the parent still runs the validated
    # pipeline: replay bookkeeping is best-effort, not a precondition.
    value = run_bun_script(POLICY_HARNESS, "agent-memory-backlog-unavailable")
    first = value["agentFirst"]
    assert first["status"] in {"applied", "no-change", "proposed"}, first
    assert first["isError"] is False, first
    assert "learning was not started" not in first["text"].lower(), first
    assert "Memory learning finished" in first["text"], first
    assert first.get("replayBound") is False, first
    assert "no replay reference" in first["text"], first
    assert value["planners"] == ["memory"], value["planners"]
    assert "concise.md" in value["privateFiles"], value


def test_sensitive_frozen_evidence_does_not_stop_learning() -> None:
    # Given frozen task evidence containing credential-shaped text, When the
    # agent asks for Memory learning, Then the normal pipeline starts so the
    # model can handle the evidence and the validated plan is applied;
    # write-side guards still refuse credential-shaped Memory bodies.
    value = run_bun_script(POLICY_HARNESS, "agent-memory-sensitive",
                           env={"CL_STARTUP_SECRET_OBSERVATION": "1"})
    first = value["agentFirst"]
    assert first["status"] in {"applied", "no-change", "proposed"}, first
    assert value["planners"], value["planners"]
    receipt = value["registryReceipt"]
    assert not any("sensitive" in reason for reason in receipt["screen"]["reasons"]), receipt
    assert "CL_BASH_LEARNING_SECRET_0123456789" not in json.dumps(receipt), receipt


def test_private_memory_is_reviewable_by_default_without_a_consent_gate() -> None:
    # Given a corpus with private entries and no `allowPrivateMemory` setting,
    # When the agent requests learning and any consent dialog would be declined,
    # Then no dialog appears, no private-memory hold occurs, and the validated
    # Memory phase runs. All Memory is reviewable by default.
    value = run_bun_script(POLICY_HARNESS, "agent-memory-private-default")
    assert value["consentCount"] == 0, value
    assert value["agentFirst"]["status"] != "held", value["agentFirst"]
    assert "private-memory-denied" not in str(value["registryReceipt"]), value["registryReceipt"]
    assert "memory" in value["planners"], value


def test_empty_selector_output_does_not_fail_the_whole_learning_run() -> None:
    # Given a selector worker that exits normally but emits no text (output
    # budget exhausted before JSON), When the agent requests learning, Then the
    # parent records a bounded diagnostic and still completes the validated
    # Memory phase instead of reporting `selector failed` with no changes.
    value = run_bun_script(POLICY_HARNESS, "agent-memory-selector-empty")
    assert value["agentFirst"]["status"] != "failed", value["agentFirst"]
    assert "selector failed" not in str(value["registryReceipt"]), value["registryReceipt"]
    assert "memory" in value["planners"], value


def test_unparseable_selector_output_is_reported_as_failed() -> None:
    # A non-empty but undecidable selector response must still surface as a
    # failure, never as a silent "no-change" outcome.
    value = run_bun_script(POLICY_HARNESS, "agent-memory-selector-garbage")
    assert value["agentFirst"]["status"] == "failed", value["agentFirst"]
    assert value["agentFirst"]["isError"] is True, value["agentFirst"]
    assert "selector rejected" in str(value["registryReceipt"]), value["registryReceipt"]


def test_selector_defaults_to_low_thinking_and_honors_an_operator_override(tmp_path: Path) -> None:
    result = run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {learningPlannerArgs} from './packages/continual-learning/extensions/planner-prompts.ts';
      fs.mkdirSync(process.env.PI_CODING_AGENT_DIR,{recursive:true});
      const cfg=path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json');
      const selector=()=>learningPlannerArgs('memory-selector');
      const delta=()=>learningPlannerArgs('memory-delta');
      const read=(args)=>{const i=args.indexOf('--thinking');return i<0?null:args[i+1]};
      const defaultSelector=read(selector()),defaultDelta=read(delta());
      fs.writeFileSync(cfg,JSON.stringify({plannerThinkingLevel:'max'}));
      const overridden=read(selector());
      console.log(JSON.stringify({defaultSelector,defaultDelta,overridden}));
    """, tmp_path)
    assert result == {"defaultSelector": "off", "defaultDelta": None, "overridden": "max"}


def test_fenced_coverage_response_completes_the_learning_pipeline() -> None:
    # Given a coverage worker that wraps its valid decision in a Markdown JSON
    # fence, When the parent runs the real Memory pipeline, Then coverage is
    # reviewed and the validated Memory change is applied.
    value = run_bun_script(POLICY_HARNESS, "remember-shared",
                           env={"CL_JEV_FIXTURE": "coverage-real-correction", "CL_FENCED_COVERAGE": "1"})
    assert value["registryReceipt"]["operations"] == 1, value["registryReceipt"]
    assert value["memoryMirrored"], value
    assert "invalid-response" not in str(value["registryReceipt"]), value["registryReceipt"]
    assert value["semanticRepairs"] == 1 and value["bodyReviewCalls"] == 2, value


def test_non_git_mirror_normalization_never_ingests_existing_bodies(tmp_path: Path) -> None:
    # Given a project outside any Git repository (publicDir undefined) whose
    # private Memory already contains credential-shaped text, When mirror
    # normalization runs before any worker, Then there is no mutation to record:
    # no history row, no exception and no model call. Existing bodies must not
    # be copied into a WAL that scans them as if they were new evidence.
    result = run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {normalizeTrackedMemory,listLearningHistory} from './packages/continual-learning/extensions/learning-history.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project');fs.mkdirSync(cwd);
      const paths=resolveMemoryPaths(cwd);fs.mkdirSync(paths.harnessDir,{recursive:true});
      fs.writeFileSync(path.join(paths.harnessDir,'MEMORY.md'),'- [note](note.md) (harness only)\n');
      const note=path.join(paths.harnessDir,'note.md');
      fs.writeFileSync(note,'Auth: provider=antigravity, oauth\napi_key: sk-abcdefghijklmnop\n');
      const before=fs.readFileSync(note,'utf8');let error='';
      let normalized={};
      try{normalized=await normalizeTrackedMemory(paths)}catch(e){error=e instanceof Error?e.message:String(e)}
      const history=await listLearningHistory(cwd);
      console.log(JSON.stringify({error,normalized,publicDir:paths.publicDir??null,
        historyCount:history.length,unchanged:fs.readFileSync(note,'utf8')===before}));
    """, tmp_path)
    assert result["publicDir"] is None, result
    assert result["error"] == "", result
    assert result["historyCount"] == 0, result
    assert result["unchanged"] is True
    assert result["normalized"] == {"repaired": [], "removed": []}, result


def test_assigned_credential_guard_separates_mode_labels_placeholders_and_real_secrets(tmp_path: Path) -> None:
    # Given three real-world shapes plus a *_WEB_KEY assignment, When the
    # Memory/Jev guard scans them, Then only the real secrets are refused.
    # "Auth: <mode-label>" is a diagnostic label, not a credential; a quoted
    # placeholder value must not be swallowed by the value class; a *_WEB_KEY
    # assignment must be recognized like other credential-named keys.
    result = run_bun(r"""
      import {containsSensitiveMemoryMaterial} from './packages/continual-learning/extensions/consolidation-run.ts';
      const samples={
        modeLabel:'Auth: provider=antigravity, oauth (user@example.invalid)',
        quotedPlaceholder:'{"username":"admin","password":"<pw>"}',
        realSecret:'controller 127.0.0.1:9090 secret=abcdefghijklmnop hot reload',
        webKey:'MAGPIE_WEB_KEY=abcdefghijklmnop',
        realWebKey:'export MAGPIE_WEB_KEY=abcdefghijklmnop',
      };
      console.log(JSON.stringify(Object.fromEntries(Object.entries(samples).map(([k,v])=>[k,containsSensitiveMemoryMaterial(v)]))));
    """, tmp_path)
    assert result == {
        "modeLabel": False,
        "quotedPlaceholder": False,
        "realSecret": True,
        "webKey": True,
        "realWebKey": True,
    }, result


def test_legacy_backlog_reason_does_not_block_replay_binding(tmp_path: Path) -> None:
    # Given historical "auto-memory-off" rows from before the setting rename,
    # When the current scope has a real pending row and no malformed row of its
    # own, Then the parent binds that row for replay. Old rows stay quarantined
    # rather than being re-queued or reported as global corruption.
    result = run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      const B=await import('./packages/continual-learning/extensions/learning-backlog.ts');
      const R=await import('./packages/continual-learning/extensions/learning-replay.ts');
      const {resolveMemoryPaths}=await import('./packages/continual-learning/extensions/memory-paths.ts');
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project'),agent=path.join(process.env.CONTROL_TEST_ROOT,'agent');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(agent,{recursive:true});
      const session=path.join(process.env.CONTROL_TEST_ROOT,'session.jsonl');
      fs.writeFileSync(session,JSON.stringify({type:'message',message:{role:'user',content:'a'}})+'\n');
      const file=B.backlogFile(cwd,agent);fs.mkdirSync(path.dirname(file),{recursive:true});
      const legacy=(scope,digest)=>JSON.stringify({version:1,sessionFile:session,from:0,to:1,digest,reason:'auto-memory-off',queuedAt:new Date().toISOString(),scopeKey:scope});
      const scope=resolveMemoryPaths(cwd,agent).scopeKey,other='--unrelated--';
      fs.writeFileSync(file,[legacy(other,'one'),legacy(other,'two'),legacy(scope,'three')].join('\n')+'\n');
      const read=B.readBacklog(cwd,agent),status=B.backlogStatus(cwd,agent);
      B.enqueueBacklog({cwd,sessionFile:session,from:2,to:3,digest:'current',reason:'settled-learning-off',agentDir:agent});
      const pending=B.readBacklog(cwd,agent).pendingEntries.map(({entry})=>entry);
      const bound=pending.length===1?R.beginBacklogAttempt(cwd,pending[0],agent):false;
      console.log(JSON.stringify({malformed:read.malformed,quarantined:read.quarantined,
        legacyPending:read.pending,statusMalformed:status.malformed,pending:pending.length,bound}));
    """, tmp_path)
    assert result == {"malformed": 0, "quarantined": 3, "legacyPending": 0,
                      "statusMalformed": 0, "pending": 1, "bound": True}, result


def test_cancelled_started_run_reports_a_terminal_outcome_row() -> None:
    # Given a session_shutdown during an agent-triggered pipeline, When the
    # parent writes its cancelled receipt, Then every started row still has a
    # paired terminal row. The cancelled `finally` branch used to write the
    # receipt to disk but never report it to the transcript.
    value = run_bun_script(POLICY_HARNESS, "agent-memory-apply",
                           env={"CL_JEV_FIXTURE": "repair-cancel"})
    assert value["startedSubjects"], value
    # Two distinct started runs in this fixture each get exactly one terminal
    # row. Equal totals prove neither the cancelled finally nor the error
    # handler doubled or dropped a report for a single started run.
    assert len(value["resultContents"]) == len(value["startedSubjects"]), value
    assert any("cancel" in text.lower() for text in value["resultContents"]), value["resultContents"]


def test_applied_tool_result_row_names_the_real_memory_count() -> None:
    # Given a real `~/Documents/Home Lab` report: `[learning] settled · learned
    # 0 Memory changes` appeared even though the same run's transcript row said
    # "2 memories applied". The tool-result renderer reads details.operations,
    # which learn() never populated. When a run applies records, Then the row
    # names the same count as its receipt, and no-change still says zero.
    applied = run_bun_script(POLICY_HARNESS, "agent-memory-selector-empty")
    first = applied["agentFirst"]
    assert first["status"] == "applied", first
    assert first["operations"] == applied["registryReceipt"]["operations"] == 1, first
    assert first["settledSubject"] == "learned 1 Memory change", first
    # The renderer's zero/missing-count path is covered directly in
    # learn-harness-route.test.ts; a proposed or failed outcome carries 0.
    assert "learned 0 Memory changes" not in first["settledSubject"], first


def test_zero_write_result_row_states_what_was_checked_but_failures_do_not() -> None:
    # Given an in-process organize run that normally settled with zero writes,
    # When its terminal result row is built, Then it expands to say what was
    # checked and that nothing was written. A failed or proposed run must not
    # be dressed up as a completed no-change check.
    organized = run_bun_script(POLICY_HARNESS, "agent-memory-organize")
    assert organized["resultContents"], organized
    assert "--- no changes ---" in organized["resultContents"][0], organized["resultContents"]
    assert "No Memory or AGENTS.md changes were written" in organized["resultContents"][0], organized["resultContents"]
    for scenario in ("agent-memory-apply", "manual-full", "agent-memory-selector-garbage"):
        value = run_bun_script(POLICY_HARNESS, scenario)
        for content in value["resultContents"]:
            assert "--- no changes ---" not in content, (scenario, content)


def test_agents_applied_result_row_names_the_applied_edit() -> None:
    # Given a run that applied one validated AGENTS.md edit, When its terminal
    # result row is built, Then the stored custom message carries the operation
    # and applied unit text for the expandable view, while the receipt in
    # details stays unchanged.
    value = run_bun_script(POLICY_HARNESS, "agents-apply")
    receipt = value["registryReceipt"]
    assert receipt["operations"] == 1, receipt
    assert any(a["phase"] == "agents" and a["outcome"] == "applied" for a in receipt["attempts"]), receipt
    assert value["resultContents"], value
    content = value["resultContents"][0]
    assert "--- AGENTS.md changes ---" in content, content
    assert "rewriteUnit" in content and "Run tests with pnpm test" in content, content
    assert "digestBefore" not in content and "bytesAfter" not in content, content


def test_automatic_run_holds_a_plan_with_too_many_new_memory_files() -> None:
    # Given an automatic learning run that proposes four independent new Memory
    # files, When the parent applies its configured per-run cap (default two),
    # Then it holds the plan without writing any Memory file or applied receipt
    # and reports the exact count and limit for review.
    value = run_bun_script(POLICY_HARNESS, "agent-memory-apply",
                           env={"CL_NEW_MEMORY_COUNT": "4"})
    receipt = value["registryReceipt"]
    assert receipt["operations"] == 0, receipt
    # The shared MEMORY.md index is created by setup and is not a written
    # candidate; no proposed candidate file may appear in either root.
    written = [name for name in value["privateFiles"] + value["publicFiles"] if name.startswith("candidate-")]
    assert written == [], (written, value)
    assert any("4 new Memory files" in notice and "limit 2" in notice for notice in value["notices"]), value["notices"]
    held = [record for record in value["history"]
            if record["status"] == "proposed" and record["phase"] == "memory"]
    assert held, value["history"]
    # The held proposal retains every grounded candidate for review; nothing
    # was silently discarded or written.
    assert [entry["name"] for entry in held[0]["proposal"]["newMemories"]] == [
        "candidate-0.md", "candidate-1.md", "candidate-2.md", "candidate-3.md"], held[0]
    # A held run still closes every started row with exactly one terminal row.
    assert len(value["resultContents"]) == len(value["startedSubjects"]), value
    # But it must not be dressed up as a normally completed zero-write check:
    # the cap held a grounded plan for review, so the result row says so and
    # never claims mirrors/indexes/consistency were verified.
    assert value["resultContents"], value
    result = value["resultContents"][0].lower()
    assert "held" in result, value["resultContents"]
    assert "review" in result, value["resultContents"]
    assert "--- no changes ---" not in result, value["resultContents"]
    assert "verified" not in result, value["resultContents"]


def test_automatic_run_holds_the_six_new_memory_files_seen_in_real_logs() -> None:
    # Regression for the hud-playground automatic batch whose plan.json held
    # six newMemories with selected=[] (batch ops 6). The debug log's
    # pipeline:started mode sha256 resolves to "automatic"; cap must hold it.
    value = run_bun_script(POLICY_HARNESS, "agent-memory-apply",
                           env={"CL_NEW_MEMORY_COUNT": "6"})
    assert value["registryReceipt"]["operations"] == 0, value["registryReceipt"]
    assert any("6 new Memory files" in notice and "limit 2" in notice
               for notice in value["notices"]), value["notices"]
    written = [name for name in value["privateFiles"] + value["publicFiles"] if name.startswith("candidate-")]
    assert written == [], (written, value)


def test_automatic_run_at_or_below_the_new_memory_cap_is_unaffected() -> None:
    # Given an automatic plan proposing exactly two new files (the default cap),
    # When the parent validates it, Then the run proceeds normally and applies
    # both files; the cap must not reject a plan within its bound.
    value = run_bun_script(POLICY_HARNESS, "agent-memory-apply",
                           env={"CL_NEW_MEMORY_COUNT": "2"})
    receipt = value["registryReceipt"]
    assert receipt["operations"] == 2, receipt
    assert not any("new Memory files" in notice for notice in value["notices"]), value["notices"]


def test_configured_new_memory_cap_is_honored_and_explicit_requests_are_exempt() -> None:
    # Given a configured cap of three, When an automatic plan proposes four
    # files, Then the exact configured limit appears in the hold diagnostic.
    # But an explicit /memory request is not subject to the automatic cap.
    automatic = run_bun_script(POLICY_HARNESS, "agent-memory-apply",
                               env={"CL_NEW_MEMORY_COUNT": "4", "CL_MAX_NEW_MEMORIES": "3"})
    assert automatic["registryReceipt"]["operations"] == 0, automatic["registryReceipt"]
    assert any("4 new Memory files" in notice and "limit 3" in notice
               for notice in automatic["notices"]), automatic["notices"]

    explicit = run_bun_script(POLICY_HARNESS, "remember-shared",
                              env={"CL_NEW_MEMORY_COUNT": "4", "CL_MAX_NEW_MEMORIES": "1"})
    assert explicit["registryReceipt"]["operations"] == 4, explicit["registryReceipt"]
    assert not any("new Memory files" in notice and "limit" in notice
                   for notice in explicit["notices"]), explicit["notices"]
