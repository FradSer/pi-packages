from support import isolated_run_bun


def test_frozen_prompt_transform_preserves_all_original_content() -> None:
    value = isolated_run_bun(r'''
      import {addHarnessRepairBindings} from './packages/continual-learning/tests/harness-binding-repair-research.ts';
      const payload={identity:{runId:'r',scopeDigest:'s',artifactHash:'a'},errors:['unchanged scope hold'],rejectedPlan:{operations:[{op:'addRule',rule:{id:'fixed'}}],evidence:[{index:0,source:'user',quote:'original exact quote',count:1,eventIndex:2}]}};
      const before='Original protocol\nReturn exactly one JSON object and no prose. Preserve the supplied identity, retained rule identities and their exact evidence quotes. Omit an unsupported operation rather than invent lasting authorization; reindex retained evidence/report. The parent retains omissions for review. Do not add a new rule identity.\nOriginal context instructions\n'+JSON.stringify(payload);
      const after=addHarnessRepairBindings(before);const changed=JSON.parse(after.split('\n').at(-1));const bindings=changed.immutableRetainedBindings;delete changed.immutableRetainedBindings;
      console.log(JSON.stringify({unchanged:JSON.stringify(changed)===JSON.stringify(payload),originalPrefixRetained:after.includes('Original protocol\n')&&after.includes('Original context instructions\n'),bindings}));
    ''')
    assert value['unchanged'] and value['originalPrefixRetained']
    assert value['bindings'][0]['evidence'][0]['eventIndex'] == 2


def test_replay_rejects_identity_and_complete_citation_drift() -> None:
    value = isolated_run_bun(r'''
      import {checkFrozenHarnessRepair} from './packages/continual-learning/tests/harness-binding-repair-research.ts';
      const quote='Never run retired-compiler through bash';const snapshot={contextEnabled:true,entries:[{role:'user',content:quote},{role:'user',content:quote}]};
      const original={kind:'harness-consolidation-plan',runId:'r',scopeDigest:'s',artifactHash:'a',operations:[{op:'addRule',rule:{id:'fixed',bash:'^retired-compiler ',action:'block',message:quote},cases:{positive:[{bash:'retired-compiler build',expected:'block'}],negative:[{bash:'printf safe'}]}}],evidence:[{index:0,source:'user',quote,count:1,eventIndex:0}]};
      const changedId=structuredClone(original);changedId.operations[0].rule.id='foreign';
      const changedQuote=structuredClone(original);changedQuote.evidence[0].quote=quote.slice(0,-5);
      const changedEvent=structuredClone(original);changedEvent.evidence[0].eventIndex=1;
      const values=[original,changedId,changedQuote,changedEvent].map(p=>checkFrozenHarnessRepair(JSON.stringify({type:"consolidation_plan",plan:p}),original,{snapshot,automatic:true,availableSkills:[]}).category);
      console.log(JSON.stringify({values}));
    ''')
    assert value['values'] == ['ready', 'identity-mismatch', 'citation-mismatch', 'citation-mismatch']


def test_paid_guard_survives_optimized_python() -> None:
    import subprocess
    import sys
    from pathlib import Path
    result = subprocess.run([sys.executable, '-O', '-c', "from live_harness_binding_repair import require_paid_permission\ntry: require_paid_permission(False)\nexcept PermissionError: print('denied')\nelse: raise SystemExit('guard bypass')"], cwd=Path(__file__).parent, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'denied'


def test_timed_out_native_call_keeps_partial_private_evidence(tmp_path, monkeypatch) -> None:
    import subprocess
    from types import SimpleNamespace
    from live_harness_binding_repair import run_recorded
    def timeout(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(['fixture'], 1, output=b'partial fixture-token', stderr=b'error fixture-token')
    monkeypatch.setattr(subprocess, 'run', timeout)
    value = run_recorded(['fixture'], timeout=1, prefix=tmp_path / 'arm', proxy=SimpleNamespace(key='fixture-token', jev_key=None, token='fixture-proxy'))
    assert value['outcome'] == 'timeout' and value['exitCode'] is None
    for suffix in ['stdout.jsonl', 'stderr.txt']:
        p = tmp_path / ('arm-' + suffix)
        assert p.exists() and 'fixture-token' not in p.read_text()
        assert p.stat().st_mode & 0o777 == 0o600


def test_container_cleanup_checks_state_and_continues_after_failure(monkeypatch) -> None:
    import subprocess
    from live_harness_binding_repair import stop_owned_containers
    calls: list[list[str]] = []
    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(args)
        if args[1:3] == ['rm', '--force'] and args[-1] == 'first':
            raise subprocess.TimeoutExpired(args, 1)
        if args[1] == 'ps':
            return subprocess.CompletedProcess(args, 0, b'first' if 'id=first' in args else b'', b'')
        if args[1] == 'inspect':
            return subprocess.CompletedProcess(args, 0, b'true\n', b'')
        return subprocess.CompletedProcess(args, 0, b'', b'')
    monkeypatch.setattr(subprocess, 'run', run)
    rows = stop_owned_containers(['first', 'second'])
    assert rows[0]['childStoppedConfirmed'] is False
    assert rows[1]['childStoppedConfirmed'] is True and rows[1]['observedState'] == 'removed'
    assert any(args[1:3] == ['rm', '--force'] and args[-1] == 'second' for args in calls)
