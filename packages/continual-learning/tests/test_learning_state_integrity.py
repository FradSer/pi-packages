from __future__ import annotations

from pathlib import Path

from support import isolated_run_bun, run_bun_script

PREPARATION = Path(__file__).with_name("learning-preparation-harness.ts")


def test_manual_learning_freezes_before_any_recovery_await() -> None:
    result = run_bun_script(PREPARATION, "freeze")
    assert result["selectors"] == 1 and result["original"] and not result["replacement"], result
    assert result["lock"] is False, result


def test_shutdown_during_preparation_never_starts_a_worker() -> None:
    result = run_bun_script(PREPARATION, "shutdown")
    assert result["selectors"] == 0 and result["lock"] is False, result


def test_shutdown_during_zero_screen_receipt_retains_prequeued_recovery_reference() -> None:
    result = run_bun_script(PREPARATION, "shutdown-zero-receipt")
    assert result["selectors"] == 0 and result["reported"] == 0, result
    assert result["backlog"]["pending"] == 1 and result["lock"] is False, result
    copies=result['receiptCopies']
    assert copies and all(receipt==copies[0] for receipt in copies), copies
    assert any(a['outcome']=='cancelled' for a in copies[0]['attempts'])


def test_shutdown_during_selector_receipt_never_reports_a_result() -> None:
    result = run_bun_script(PREPARATION, "shutdown-current-receipt")
    assert result["selectors"] == 1 and result["reported"] == 0, result
    assert result["backlog"]["pending"] == 0 and result["lock"] is False, result
    copies=result['receiptCopies']
    assert copies and all(receipt==copies[0] for receipt in copies), copies
    assert any(a['outcome']=='cancelled' for a in copies[0]['attempts'])


def test_invalid_settings_do_not_start_automatic_selection() -> None:
    result = run_bun_script(PREPARATION, "invalid-settings")
    assert result["selectors"] == 0, result
    assert any("settings" in notice.lower() for notice in result["notices"]), result


def test_disabled_automatic_learning_queues_one_frozen_task() -> None:
    result = run_bun_script(PREPARATION, "disabled")
    assert result["selectors"] == 0 and result["backlog"]["pending"] == 1, result
    assert result["entries"][0]["from"] == 0 and result["entries"][0]["to"] == 1, result


def test_status_reports_the_loop_without_starting_a_learner() -> None:
    result = run_bun_script(PREPARATION, "disabled-status")
    text = "\n".join(result["notices"])
    assert result["selectors"] == 0, result
    for value in ("Settled learning: off", "Agent-triggered: off", "Knowledge entries:", "Automatic phases:", "Skipped task references: 1", "Learning pipeline: idle"):
        assert value in text, result


def test_status_and_backfill_report_malformed_references_without_a_learner() -> None:
    result = run_bun_script(PREPARATION, "disabled-corrupt-status")
    assert result["selectors"] == 0, result
    assert result["backlog"]["malformed"] == 1, result
    assert sum("Malformed references: 1" in notice for notice in result["notices"]) == 2, result


def test_skipped_task_positions_do_not_match_an_older_identical_result() -> None:
    result = run_bun_script(PREPARATION, "disabled-later")
    assert result["backlog"]["pending"] == 1, result
    assert (result["entries"][0]["from"], result["entries"][0]["to"]) == (2, 3), result


def test_legacy_global_cursor_does_not_consume_new_scoped_references() -> None:
    result = isolated_run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {enqueueBacklog,backlogStatus} from './packages/continual-learning/extensions/learning-backlog.ts';
      const agent=process.env.PI_CODING_AGENT_DIR,cwd=path.join(agent,'project');fs.mkdirSync(cwd);
      const session=path.join(agent,'session.jsonl');fs.writeFileSync(session,'{}\n');
      enqueueBacklog({cwd,sessionFile:session,from:0,to:0,digest:'new-task',reason:'settled-learning-off'});
      fs.writeFileSync(path.join(agent,'learning','learning-backlog.cursor.json'),JSON.stringify({consumed:1}));
      console.log(JSON.stringify({pending:backlogStatus(cwd).pending,consumed:backlogStatus(cwd).consumed}));
    """)
    assert result == {"pending": 1, "consumed": 0}


def test_backlog_capacity_reservation_serializes_interleaved_writers() -> None:
    result = isolated_run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {enqueueBacklog,backlogFile,MAX_BACKLOG_BYTES} from './packages/continual-learning/extensions/learning-backlog.ts';
      const agent=process.env.PI_CODING_AGENT_DIR,cwd=path.join(agent,'project');fs.mkdirSync(cwd);
      const session=path.join(agent,'session.jsonl');fs.writeFileSync(session,'{}\n');
      const input={cwd,sessionFile:session,from:0,to:0,digest:'task',reason:'settled-learning-off'};
      enqueueBacklog(input);const file=backlogFile(cwd),line=fs.readFileSync(file);fs.writeFileSync(file,Buffer.alloc(MAX_BACKLOG_BYTES-line.length,10));
      const stat=fs.fstatSync;let injected=false,competing;
      fs.fstatSync=(fd,...args)=>{const value=stat(fd,...args);if(!injected&&value.size===MAX_BACKLOG_BYTES-line.length){injected=true;competing=enqueueBacklog(input)}return value};
      const queued=enqueueBacklog(input);fs.fstatSync=stat;
      console.log(JSON.stringify({queued,competing,bounded:fs.statSync(file).size<=MAX_BACKLOG_BYTES}));
    """)
    assert result == {"queued": True, "competing": False, "bounded": True}


def test_legacy_consumed_prefix_is_preserved_only_for_legacy_records() -> None:
    result = isolated_run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {enqueueBacklog,backlogStatus,backlogFile} from './packages/continual-learning/extensions/learning-backlog.ts';
      const agent=process.env.PI_CODING_AGENT_DIR,cwd=path.join(agent,'project');fs.mkdirSync(cwd);
      const session=path.join(agent,'session.jsonl');fs.writeFileSync(session,JSON.stringify({type:'session',cwd})+'\n');
      const input={cwd,sessionFile:session,from:0,to:0,digest:'legacy-task',reason:'settled-learning-off'};
      enqueueBacklog(input);const file=backlogFile(cwd),legacy=JSON.parse(fs.readFileSync(file,'utf8'));delete legacy.scopeKey;fs.writeFileSync(file,JSON.stringify(legacy)+'\n');
      fs.writeFileSync(path.join(agent,'learning','learning-backlog.cursor.json'),JSON.stringify({consumed:1}));
      enqueueBacklog({...input,digest:'new-task'});
      console.log(JSON.stringify({pending:backlogStatus(cwd).pending,consumed:backlogStatus(cwd).consumed}));
    """)
    assert result == {"pending": 1, "consumed": 0}


def test_cursor_update_is_serialized_and_can_be_retried_after_contention() -> None:
    result = isolated_run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {advanceCursor,readCursor} from './packages/continual-learning/extensions/learning-backlog.ts';
      const agent=process.env.PI_CODING_AGENT_DIR,cwd=path.join(agent,'project');fs.mkdirSync(cwd);
      const rename=fs.renameSync;let injected=false,competing;
      fs.renameSync=(from,to)=>{if(!injected&&String(to).endsWith('learning-backlog.cursor.json')){injected=true;competing=advanceCursor(cwd,2)}return rename(from,to)};
      const first=advanceCursor(cwd,1);fs.renameSync=rename;const retried=advanceCursor(cwd,2),regressed=advanceCursor(cwd,1);
      console.log(JSON.stringify({first,competing,retried,regressed,consumed:readCursor(cwd)}));
    """)
    assert result == {"first": True, "competing": False, "retried": True, "regressed": False, "consumed": 2}


def test_invalid_learning_settings_fail_closed_with_a_diagnostic() -> None:
    result = isolated_run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {readLearningSettings} from './packages/continual-learning/extensions/learning-settings.ts';
      const agent=process.env.PI_CODING_AGENT_DIR,cwd=path.join(agent,'project');fs.mkdirSync(cwd);
      const file=path.join(agent,'continual-learning.json');
      const values=['{','null','[]','{"autoSettledLearning":"false"}','{"autoContinualLearning":false,"automaticPhases":{"memory":"invalid"}}'];
      const states=[];for(const raw of values){fs.writeFileSync(file,raw);const state=await readLearningSettings(cwd);states.push({settled:state.autoSettledLearning,continual:state.autoContinualLearning,diagnostic:Boolean(state.invalid)});}
      fs.unlinkSync(file);const missing=await readLearningSettings(cwd);
      console.log(JSON.stringify({states,missing:{settled:missing.autoSettledLearning,continual:missing.autoContinualLearning}}));
    """)
    assert result == {"states": [{"settled": False, "continual": False, "diagnostic": True}] * 5,
                     "missing": {"settled": False, "continual": False}}


def test_learning_settings_split_triggers_and_ignore_retired_auto_memory() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {readLearningSettings} from './packages/continual-learning/extensions/learning-settings.ts';
      const cwd=path.join(process.env.PI_CODING_AGENT_DIR,'project');fs.mkdirSync(cwd);
      const file=path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json');
      fs.writeFileSync(file,'{"autoMemory":true}');const retired=await readLearningSettings(cwd);
      fs.writeFileSync(file,'{"autoSettledLearning":true,"autoContinualLearning":false}');const split=await readLearningSettings(cwd);
      fs.writeFileSync(file,'{"autoSettledLearning":"yes"}');const invalid=await readLearningSettings(cwd);
      console.log(JSON.stringify({retired:{settled:retired.autoSettledLearning,continual:retired.autoContinualLearning,invalid:Boolean(retired.invalid)},
        split:{settled:split.autoSettledLearning,continual:split.autoContinualLearning,invalid:Boolean(split.invalid)},
        invalid:{settled:invalid.autoSettledLearning,continual:invalid.autoContinualLearning,diagnostic:Boolean(invalid.invalid)}}));
    ''')
    assert result == {
        "retired": {"settled": False, "continual": False, "invalid": False},
        "split": {"settled": True, "continual": False, "invalid": False},
        "invalid": {"settled": False, "continual": False, "diagnostic": True},
    }


def test_learning_settings_never_read_a_symlinked_config() -> None:
    result = isolated_run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {readLearningSettings,writeLearningSettings} from './packages/continual-learning/extensions/learning-settings.ts';
      const agent=process.env.PI_CODING_AGENT_DIR,cwd=path.join(agent,'project'),outside=path.join(agent,'outside');fs.mkdirSync(cwd);fs.mkdirSync(outside);
      const target=path.join(outside,'continual-learning.json');fs.writeFileSync(target,'{"autoSettledLearning":true,"autoContinualLearning":true}');
      fs.symlinkSync(target,path.join(agent,'continual-learning.json'));
      // The single configuration file may never be read or written through a symlink.
      const state=await readLearningSettings(cwd);
      let refused=false;try{await writeLearningSettings({autoSettledLearning:false,autoContinualLearning:false},cwd)}catch{refused=true}
      console.log(JSON.stringify({settled:state.autoSettledLearning,continual:state.autoContinualLearning,diagnostic:Boolean(state.invalid),refused,
        target:fs.readFileSync(target,'utf8')}));
    """)
    assert result == {"settled": False, "continual": False, "diagnostic": True, "refused": True,
                      "target": '{"autoSettledLearning":true,"autoContinualLearning":true}'}


def test_backlog_is_project_scoped() -> None:
    result = isolated_run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {enqueueBacklog,backlogStatus} from './packages/continual-learning/extensions/learning-backlog.ts';
      const agent=process.env.PI_CODING_AGENT_DIR,a=path.join(agent,'a'),b=path.join(agent,'b');
      fs.mkdirSync(a);fs.mkdirSync(b);const session=path.join(agent,'session.jsonl');fs.writeFileSync(session,'{}\n');
      const queued=enqueueBacklog({cwd:a,sessionFile:session,from:0,to:0,digest:'task-a',reason:'settled-learning-off'});
      console.log(JSON.stringify({queued,a:backlogStatus(a).pending,b:backlogStatus(b).pending}));
    """)
    assert result == {"queued": True, "a": 1, "b": 0}


def test_backlog_cursor_does_not_shift_when_consumed_session_disappears() -> None:
    result = isolated_run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {enqueueBacklog,backlogStatus,advanceCursor} from './packages/continual-learning/extensions/learning-backlog.ts';
      const agent=process.env.PI_CODING_AGENT_DIR,cwd=path.join(agent,'project');fs.mkdirSync(cwd);
      const first=path.join(agent,'first.jsonl'),second=path.join(agent,'second.jsonl');fs.writeFileSync(first,'{}\n');fs.writeFileSync(second,'{}\n');
      for(const [sessionFile,digest] of [[first,'first'],[second,'second']])enqueueBacklog({cwd,sessionFile,from:0,to:0,digest,reason:'settled-learning-off'});
      advanceCursor(cwd,1);fs.unlinkSync(first);const status=backlogStatus(cwd);
      console.log(JSON.stringify({pending:status.pending,consumed:status.consumed}));
    """)
    assert result == {"pending": 1, "consumed": 1}


def test_backlog_refuses_symlink_storage_and_invalid_pointers() -> None:
    result = isolated_run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {enqueueBacklog,backlogFile,advanceCursor} from './packages/continual-learning/extensions/learning-backlog.ts';
      const agent=process.env.PI_CODING_AGENT_DIR,cwd=path.join(agent,'project');fs.mkdirSync(cwd);
      const session=path.join(agent,'session.jsonl');fs.writeFileSync(session,'{}\n');
      const input={cwd,sessionFile:session,from:0,to:0,digest:'task',reason:'settled-learning-off'};
      const invalid=enqueueBacklog({...input,from:-1});const cursor=advanceCursor(cwd,-1);
      const file=backlogFile(cwd),outside=path.join(agent,'outside');fs.mkdirSync(path.dirname(file),{recursive:true});fs.rmSync(file,{force:true});fs.writeFileSync(outside,'untouched');fs.symlinkSync(outside,file);
      const symlink=enqueueBacklog(input);
      console.log(JSON.stringify({invalid,cursor,symlink,outside:fs.readFileSync(outside,'utf8')}));
    """)
    assert result == {"invalid": False, "cursor": False, "symlink": False, "outside": "untouched"}


def test_backlog_capacity_preserves_existing_records() -> None:
    result = isolated_run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {enqueueBacklog,backlogFile,MAX_BACKLOG_BYTES} from './packages/continual-learning/extensions/learning-backlog.ts';
      const agent=process.env.PI_CODING_AGENT_DIR,cwd=path.join(agent,'project');fs.mkdirSync(cwd);
      const session=path.join(agent,'session.jsonl');fs.writeFileSync(session,'{}\n');
      const file=backlogFile(cwd);fs.mkdirSync(path.dirname(file),{recursive:true});const original='x'.repeat(MAX_BACKLOG_BYTES-1)+'\n';fs.writeFileSync(file,original);
      const queued=enqueueBacklog({cwd,sessionFile:session,from:0,to:0,digest:'task',reason:'settled-learning-off'});
      console.log(JSON.stringify({queued,preserved:fs.readFileSync(file,'utf8')===original}));
    """)
    assert result == {"queued": False, "preserved": True}


def test_learning_settings_live_in_the_single_unified_configuration() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {readLearningSettings,writeLearningSettings} from './packages/continual-learning/extensions/learning-settings.ts';
      const agent=process.env.PI_CODING_AGENT_DIR,cwd=path.join(agent,'project');fs.mkdirSync(cwd);
      const unified=path.join(agent,'continual-learning.json');
      // Given both files define learning fields, When settings are read, Then the unified file wins.
      fs.writeFileSync(unified,JSON.stringify({model:'p/m',jev:{scopes:['memory']},autoSettledLearning:true,autoContinualLearning:false}));
      const preferred=await readLearningSettings(cwd);
      // Given the unified file only carries unrelated sections, Then no learning field exists anywhere.
      fs.writeFileSync(unified,JSON.stringify({model:'p/m'}));
      const legacyFallback=await readLearningSettings(cwd);
      // When settings are written, Then they merge into the unified file and preserve other sections.
      fs.writeFileSync(unified,JSON.stringify({model:'p/m',jev:{scopes:['memory']}}));
      await writeLearningSettings({autoSettledLearning:true,autoContinualLearning:true},cwd);
      const merged=JSON.parse(fs.readFileSync(unified,'utf8'));
      const reread=await readLearningSettings(cwd);
      // And a broken predecessor is never clobbered.
      fs.writeFileSync(unified,'{ broken');
      let refused=false;try{await writeLearningSettings({autoSettledLearning:false,autoContinualLearning:false},cwd)}catch{refused=true}
      console.log(JSON.stringify({preferred:{settled:preferred.autoSettledLearning,continual:preferred.autoContinualLearning},
        legacyFallback:{settled:legacyFallback.autoSettledLearning,continual:legacyFallback.autoContinualLearning},
        merged,reread:{settled:reread.autoSettledLearning,continual:reread.autoContinualLearning},refused,broken:fs.readFileSync(unified,'utf8')}));
    ''')
    assert result["preferred"] == {"settled": True, "continual": False}
    assert result["legacyFallback"] == {"settled": False, "continual": False}
    assert result["merged"] == {"model": "p/m", "jev": {"scopes": ["memory"]},
                                "autoSettledLearning": True, "autoContinualLearning": True}
    assert result["reread"] == {"settled": True, "continual": True}
    assert result["refused"] is True
    assert result["broken"] == "{ broken"


def test_learning_settings_reject_invalid_unified_values_without_writing() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {readLearningSettings} from './packages/continual-learning/extensions/learning-settings.ts';
      const agent=process.env.PI_CODING_AGENT_DIR,cwd=path.join(agent,'project');fs.mkdirSync(cwd);
      const unified=path.join(agent,'continual-learning.json');
      const states={};
      for (const [name,value] of Object.entries({wrongType:'yes',badPhase:'invalid',badAgents:{disabled:'yes'}})) {
        fs.writeFileSync(unified,JSON.stringify(name==='badAgents'
          ? {autoSettledLearning:true,agentsMd:value}
          : name==='badPhase' ? {autoContinualLearning:true,automaticPhases:{memory:value}} : {autoSettledLearning:value}));
        const state=await readLearningSettings(cwd);
        states[name]={settled:state.autoSettledLearning,continual:state.autoContinualLearning,diagnostic:Boolean(state.invalid)};
      }
      console.log(JSON.stringify(states));
    ''')
    assert result == {
        "wrongType": {"settled": False, "continual": False, "diagnostic": True},
        "badPhase": {"settled": False, "continual": False, "diagnostic": True},
        "badAgents": {"settled": False, "continual": False, "diagnostic": True},
    }
