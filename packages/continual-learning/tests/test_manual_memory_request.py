from __future__ import annotations

from pathlib import Path

import pytest

from support import run_bun, run_bun_script


def test_explicit_request_keeps_bounded_context_without_clipping_evidence() -> None:
    result = run_bun(r'''
      import { requestedMemoryTaskSlice } from './packages/continual-learning/extensions/incremental-learning.ts';
      const message = (role, content) => ({message:{role,content}});
      const context = [message('user', '界'.repeat(180000)), ...Array.from({length:120}, (_,i)=>message('toolResult', `verification ${i}`)), message('assistant','FINAL_RESULT')];
      const slice = requestedMemoryTaskSlice('Remember MY_EXACT_REQUEST', context);
      let oversizedRequest;
      try { requestedMemoryTaskSlice('界'.repeat(180000), []); } catch(error) { oversizedRequest=error.message; }
      console.log(JSON.stringify({bytes:Buffer.byteLength(JSON.stringify(slice)),count:slice.entries.length,first:slice.entries[0].message.content,last:slice.entries.at(-1).message.content,omitted:slice.omittedEntries,unchanged:slice.entries.slice(0,-1).every(entry=>context.includes(entry)),summary:slice.entries.some(entry=>entry.message.content==='FINAL_RESULT'),requestIndex:slice.memoryRequest.entryIndex,oversizedRequest}));
    ''')
    assert result["bytes"] <= 512_000 and result["count"] <= 256
    assert result["last"] == "Remember MY_EXACT_REQUEST"
    assert result["summary"] is True
    assert result["requestIndex"] == result["count"] - 1
    assert result["omitted"] > 0 and result["unchanged"] is True
    assert "request" in result["oversizedRequest"].lower()


@pytest.mark.parametrize("scenario", ["remember-private", "remember-declined", "remember-shared"])
def test_explicit_request_is_grounded_applied_and_memory_only(scenario: str) -> None:
    result = run_bun_script(Path(__file__).with_name("learning-policy-harness.ts"), scenario)
    assert result["selectors"] == (1 if scenario == "remember-declined" else 0) and result["requestCaptured"] is True, result
    assert result["planners"] == ["memory"], result
    assert result["registryReceipt"]["operations"] == 1, result
    assert result["registryReceipt"]["screen"]["harness"] is False
    assert result["registryReceipt"]["screen"]["agents"] is False
    assert result["harnessExists"] is False and result["agentsUnchanged"] is True
    assert "concise.md" in result["privateFiles"]
    assert ("concise.md" in result["publicFiles"]) is (scenario == "remember-shared")
    assert result["memoryMirrored"] is (scenario == "remember-shared")
    assert result["lock"] is False
    dossiers = [run["dossier"] for run in result["runs"] if "dossier" in run]
    assert len(dossiers) == 1 and dossiers[0]["memoryRequest"] == {"entryIndex": 1}, result


def test_secret_request_does_not_launch_workers_or_repeat_secret() -> None:
    result = run_bun_script(Path(__file__).with_name("learning-policy-harness.ts"), "remember-secret")
    assert result["selectors"] == 0 and result["planners"] == [], result
    assert "secret" in " ".join(result["notices"]).lower(), result
    assert "sk-test-secret" not in " ".join(result["notices"])
    assert result["privateFiles"] == [] and result["publicFiles"] == []


def test_sensitive_tool_observation_keeps_a_safe_pre_generation_failure_reason() -> None:
    import json
    # Given a valid request whose original tool evidence contains a credential,
    # When the Memory worker refuses setup, Then retain a safe reason and zero
    # generation calls without deleting evidence or opening later planners.
    result = run_bun_script(Path(__file__).with_name("learning-policy-harness.ts"), "remember-shared",
                            env={"CL_STARTUP_SECRET_OBSERVATION":"1"})
    receipt = result["registryReceipt"]
    attempt = next(item for item in receipt["attempts"] if item["phase"] == "memory")
    assert attempt["outcome"] == "failed" and attempt["operations"] == 0
    assert attempt["diagnostic"] == "Memory worker setup refused sensitive frozen evidence; no planner started."
    assert attempt["modelCalls"] == 0 and attempt["usage"]["totalTokens"] == 0
    assert result["planners"] == [] and not result["harnessExists"]
    assert "CL_BASH_LEARNING_SECRET_0123456789" not in json.dumps(receipt)
    assert any("CL_BASH_LEARNING_SECRET_0123456789" in json.dumps(run.get("dossier")) for run in result["runs"])
    assert "concise.md" not in result["privateFiles"] and result["lock"] is False


def test_invalid_evidence_cannot_save_a_memory() -> None:
    result = run_bun_script(Path(__file__).with_name("learning-policy-harness.ts"), "remember-invalid")
    # Empty-index routing skips selection; the bounded repair cannot authorize bad evidence.
    assert result["selectors"] == 1 and result["planners"] == ["memory"], result
    assert "concise.md" not in result["privateFiles"]
    assert result["registryReceipt"]["operations"] == 0, result
    assert result["harnessExists"] is False and result["agentsUnchanged"] is True
    assert result["lock"] is False


def test_consolidate_completion_exposes_only_full() -> None:
    result = run_bun(r'''
      import register from './packages/continual-learning/extensions/inject-memory.ts';
      const commands = new Map();
      register({on(){},registerCommand:(name,command)=>commands.set(name,command),registerMessageRenderer(){},registerEntryRenderer(){},getCommands:()=>[]});
      const complete=commands.get('consolidate').getArgumentCompletions;
      console.log(JSON.stringify({empty:complete?.('')?.map(item=>item.value)??[],partial:complete?.('fu')?.map(item=>item.value)??[],legacy:complete?.('back')??[]}));
    ''', temp_dirs=("PI_CODING_AGENT_DIR",))
    assert result == {"empty": ["full"], "partial": ["full"], "legacy": []}


def test_malformed_json_on_empty_scope_is_corrected_and_revalidated_once() -> None:
    result = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-syntax', env={'CL_JEV_FIXTURE':'supported'})
    assert result['totalRepairs'] == 1, result
    assert result['structuralContextReceived'] is True
    assert result['jevValidations'] == ['memory']
    assert result['registryReceipt']['operations'] == 1
    assert 'concise.md' in result['privateFiles']


@pytest.mark.parametrize('reason', ['unsupported', 'structural-tamper-snapshot', 'structural-tamper-dossier'])
def test_syntax_correction_cannot_bypass_semantics_or_frozen_evidence(reason: str) -> None:
    result = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-syntax', env={'CL_JEV_FIXTURE':reason})
    assert result['totalRepairs'] == (2 if reason == 'unsupported' else 1)
    assert result['registryReceipt']['operations'] == 0
    assert 'concise.md' not in result['privateFiles']


def test_syntax_correction_refuses_existing_scope_ambiguity_and_oversize() -> None:
    result = run_bun(r'''
      import {malformedIncrementalRepairText} from './packages/continual-learning/extensions/inject-memory.ts';
      const broken='{"kind":"incremental-memory-plan","newMemories":[{"name":"unfinished.md\n}]}';
      console.log(JSON.stringify({eligible:!!malformedIncrementalRepairText(broken,[]),
        selected:malformedIncrementalRepairText(broken,['existing.md'])??null,
        ambiguous:malformedIncrementalRepairText(broken+broken,[])??null,
        valid:malformedIncrementalRepairText('{"kind":"incremental-memory-plan"}',[])??null,
        prose:malformedIncrementalRepairText('Here is the plan: '+broken,[])??null,
        oversized:malformedIncrementalRepairText(broken+'x'.repeat(600000),[])??null}));
    ''')
    assert result.pop('eligible') is True
    assert all(value is None for value in result.values())


def test_syntax_correction_does_not_override_multiple_plan_rejection() -> None:
    result = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-syntax-multiple', env={'CL_JEV_FIXTURE':'supported'})
    assert result['totalRepairs'] == 0, result
    assert result['jevValidations'] == []
    assert 'concise.md' not in result['privateFiles']


def test_malformed_regeneration_cannot_publish_reclassified_private_project() -> None:
    result = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-syntax', env={'CL_JEV_FIXTURE':'syntax-privacy-downgrade'})
    assert result['totalRepairs'] == 1
    assert result['registryReceipt']['operations'] == 1
    assert 'concise.md' in result['privateFiles']
    assert 'concise.md' not in result['publicFiles'], result


def test_only_empty_tool_delimiters_admit_one_frozen_fresh_plan() -> None:
    result = run_bun(r'''
      import {emptyPlannerToolDelimiters} from './packages/continual-learning/extensions/inject-memory.ts';
      console.log(JSON.stringify({observed:emptyPlannerToolDelimiters('<tool_call>\n<tool_call>\n<tool_call>\n</function>\n</tool_call>'),denied:['','Please retry','<tool_call>rm -rf x</tool_call>','{"kind":"incremental-memory-plan"}','<other></other>','<tool_call>'.repeat(1000)].map(emptyPlannerToolDelimiters)}));
    ''')
    assert result['observed'] is True
    assert result['denied'] == [False] * 6


def test_normal_exit_empty_tool_delimiters_use_existing_slot_without_skipping_semantics() -> None:
    for reason in ['supported', 'unsupported']:
        result = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-empty-delimiters', env={'CL_JEV_FIXTURE': reason})
        assert result['totalRepairs'] >= 1
        assert result['registryReceipt']['operations'] == (1 if reason == 'supported' else 0)
        assert 'memory' in result['jevValidations']
        assert 'concise.md' not in result['publicFiles']


def test_empty_tool_delimiter_recovery_preserves_selected_scope_and_retention_review() -> None:
    result = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-empty-delimiters', env={'CL_JEV_FIXTURE': 'retention-fixed'})
    assert result['registryReceipt']['operations'] == 1
    assert result['totalRepairs'] == 2  # One structure slot and the existing semantic correction.
    assert result['jevValidations'].count('memory') >= 2
    assert 'known.md' in result['privateFiles']
    assert 'concise.md' not in result['privateFiles']


def test_second_empty_tool_delimiter_answer_stays_failed_without_another_structural_retry() -> None:
    result = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-empty-delimiters-invalid', env={'CL_JEV_FIXTURE': 'supported'})
    assert result['totalRepairs'] == 1
    assert result['registryReceipt']['operations'] == 0
    assert result['jevValidations'] == []
    assert 'concise.md' not in result['privateFiles']


@pytest.mark.parametrize("scenario,action,raw_args", [("manual-consolidate", "current-task", ""), ("manual-full", "full-corpus", "  full  ")])
def test_consolidate_current_command_is_bound_separately_from_source_evidence(scenario, action, raw_args):
    # Given an actual command handler call after the source task, When capturing
    # each planner run, Then preserve original entries and bind only this action.
    result = run_bun_script(Path(__file__).with_name("learning-policy-harness.ts"), scenario)
    snapshots = [run["snapshot"] for run in result["runs"] if run.get("snapshot")]
    assert snapshots, result
    invocation_ids = set()
    for snapshot in snapshots:
        request = snapshot.get("currentMaintenanceRequest")
        assert request is not None, snapshot
        assert request["kind"] == "user-maintenance-command" and request["version"] == 1
        assert request["command"] == "consolidate" and request["arguments"] == raw_args
        assert request["action"] == action
        assert request["runId"] == snapshot["runId"] and request["scopeKey"] == snapshot["scopeKey"]
        assert snapshot["entries"][0]["message"]["content"] == "Fix the failing build."
        assert len(snapshot["entries"]) == 4
        invocation_ids.add(request["invocationId"])
    assert len(invocation_ids) == 1


def test_explicit_backfill_keeps_original_task_and_current_command_namespaces_separate():
    result = run_bun_script(Path(__file__).with_name("learning-policy-harness.ts"), "manual-backfill")
    snapshots = [run["snapshot"] for run in result["runs"] if run.get("snapshot")]
    assert snapshots, result
    assert result["maintenanceClaimChecks"] > 0
    for snapshot in snapshots:
        command = snapshot["currentMaintenanceRequest"]
        assert command["action"] == "backfill" and command["arguments"] == "backfill"
        assert command["sessionId"] == "current-backfill-invocation"
        assert command["runId"] == snapshot["runId"]
        assert len(snapshot["entries"]) == 2
        assert snapshot["entries"][0]["message"]["content"] == "Fix the failing build."
        assert snapshot["entries"][1]["message"]["content"] == [{"type": "text", "text": "Original task result."}]
