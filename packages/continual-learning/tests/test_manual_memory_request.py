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
      console.log(JSON.stringify({bytes:Buffer.byteLength(JSON.stringify(slice)),count:slice.entries.length,first:slice.entries[0].message.content,last:slice.entries.at(-1).message.content,omitted:slice.omittedEntries,unchanged:slice.entries.slice(1).every(entry=>context.includes(entry)),oversizedRequest}));
    ''')
    assert result["bytes"] <= 512_000 and result["count"] <= 256
    assert result["first"] == "Remember MY_EXACT_REQUEST"
    assert result["last"] == "FINAL_RESULT"
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
    assert len(dossiers) == 1 and dossiers[0]["memoryRequest"] == {"entryIndex": 0}, result


def test_secret_request_does_not_launch_workers_or_repeat_secret() -> None:
    result = run_bun_script(Path(__file__).with_name("learning-policy-harness.ts"), "remember-secret")
    assert result["selectors"] == 0 and result["planners"] == [], result
    assert "secret" in " ".join(result["notices"]).lower(), result
    assert "sk-test-secret" not in " ".join(result["notices"])
    assert result["privateFiles"] == [] and result["publicFiles"] == []


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
    assert result['totalRepairs'] == 1
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
