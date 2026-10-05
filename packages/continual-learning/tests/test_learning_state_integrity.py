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


def test_shutdown_during_zero_screen_receipt_never_queues_a_task() -> None:
    result = run_bun_script(PREPARATION, "shutdown-zero-receipt")
    assert result["selectors"] == 0 and result["reported"] == 0, result
    assert result["backlog"]["pending"] == 0 and result["lock"] is False, result


def test_shutdown_during_selector_receipt_never_reports_a_result() -> None:
    result = run_bun_script(PREPARATION, "shutdown-current-receipt")
    assert result["selectors"] == 1 and result["reported"] == 0, result
    assert result["backlog"]["pending"] == 0 and result["lock"] is False, result


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
    for value in ("Auto-memory: off", "Knowledge entries:", "Automatic phases:", "Skipped task references: 1", "Learning pipeline: idle"):
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
      enqueueBacklog({cwd,sessionFile:session,from:0,to:0,digest:'new-task',reason:'auto-memory-off'});
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
      const input={cwd,sessionFile:session,from:0,to:0,digest:'task',reason:'auto-memory-off'};
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
      const input={cwd,sessionFile:session,from:0,to:0,digest:'legacy-task',reason:'auto-memory-off'};
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
      const file=path.join(agent,'memory','settings.json');fs.mkdirSync(path.dirname(file),{recursive:true});
      const values=['{','null','[]','{"autoMemory":"false"}','{"autoMemory":false,"automaticPhases":{"memory":"invalid"}}'];
      const states=[];for(const raw of values){fs.writeFileSync(file,raw);const state=await readLearningSettings(cwd);states.push({enabled:state.autoMemory,diagnostic:Boolean(state.invalid)});}
      fs.unlinkSync(file);const missing=await readLearningSettings(cwd);
      console.log(JSON.stringify({states,missing:missing.autoMemory}));
    """)
    assert result == {"states": [{"enabled": False, "diagnostic": True}] * 5, "missing": True}


def test_learning_settings_never_read_a_symlinked_parent() -> None:
    result = isolated_run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {readLearningSettings,writeLearningSettings} from './packages/continual-learning/extensions/learning-settings.ts';
      const agent=process.env.PI_CODING_AGENT_DIR,cwd=path.join(agent,'project'),outside=path.join(agent,'outside');fs.mkdirSync(cwd);fs.mkdirSync(outside);
      const file=path.join(outside,'settings.json');fs.writeFileSync(file,'{"autoMemory":true}');fs.symlinkSync(outside,path.join(agent,'memory'));
      const state=await readLearningSettings(cwd);let refused=false;try{await writeLearningSettings({autoMemory:false},cwd)}catch{refused=true}
      console.log(JSON.stringify({enabled:state.autoMemory,diagnostic:Boolean(state.invalid),refused,content:fs.readFileSync(file,'utf8')}));
    """)
    assert result == {"enabled": False, "diagnostic": True, "refused": True, "content": '{"autoMemory":true}'}


def test_backlog_is_project_scoped() -> None:
    result = isolated_run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {enqueueBacklog,backlogStatus} from './packages/continual-learning/extensions/learning-backlog.ts';
      const agent=process.env.PI_CODING_AGENT_DIR,a=path.join(agent,'a'),b=path.join(agent,'b');
      fs.mkdirSync(a);fs.mkdirSync(b);const session=path.join(agent,'session.jsonl');fs.writeFileSync(session,'{}\n');
      const queued=enqueueBacklog({cwd:a,sessionFile:session,from:0,to:0,digest:'task-a',reason:'auto-memory-off'});
      console.log(JSON.stringify({queued,a:backlogStatus(a).pending,b:backlogStatus(b).pending}));
    """)
    assert result == {"queued": True, "a": 1, "b": 0}


def test_backlog_cursor_does_not_shift_when_consumed_session_disappears() -> None:
    result = isolated_run_bun(r"""
      import fs from 'node:fs';import path from 'node:path';
      import {enqueueBacklog,backlogStatus,advanceCursor} from './packages/continual-learning/extensions/learning-backlog.ts';
      const agent=process.env.PI_CODING_AGENT_DIR,cwd=path.join(agent,'project');fs.mkdirSync(cwd);
      const first=path.join(agent,'first.jsonl'),second=path.join(agent,'second.jsonl');fs.writeFileSync(first,'{}\n');fs.writeFileSync(second,'{}\n');
      for(const [sessionFile,digest] of [[first,'first'],[second,'second']])enqueueBacklog({cwd,sessionFile,from:0,to:0,digest,reason:'auto-memory-off'});
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
      const input={cwd,sessionFile:session,from:0,to:0,digest:'task',reason:'auto-memory-off'};
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
      const queued=enqueueBacklog({cwd,sessionFile:session,from:0,to:0,digest:'task',reason:'auto-memory-off'});
      console.log(JSON.stringify({queued,preserved:fs.readFileSync(file,'utf8')===original}));
    """)
    assert result == {"queued": False, "preserved": True}
