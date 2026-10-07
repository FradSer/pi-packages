from support import isolated_run_bun


def test_workflow_success_does_not_hide_harmless_command_false_blocks() -> None:
    # Given a generated matcher that also finds command words in output text,
    # when auditing independent cases, workflow success cannot imply quality.
    value = isolated_run_bun(r'''
      import {assessHarnessQuality} from './packages/continual-learning/tests/jev-harness-quality.ts';
      const probes=[{id:'push',command:'git push --dry-run',expected:'block'},{id:'print',command:"printf '%s' 'x;git push --dry-run'",expected:'execute'},{id:'echo',command:'echo git push --dry-run',expected:'execute'}];
      const bad={id:'no-push',bash:'(^|[ ;])git +push(?: |$)',action:'block',message:'Never run git push.'};
      const good={...bad,bash:'^git +push(?: |$)'};
      console.log(JSON.stringify({bad:assessHarnessQuality([bad],probes),good:assessHarnessQuality([good],probes)}));
    ''')
    assert value['bad']['falseBlocks'] == 2 and value['bad']['missedConstraints'] == 0
    assert not value['bad']['satisfiesAll']
    assert value['good']['satisfiesAll'] and value['good']['falseBlocks'] == 0


def test_held_or_invalid_harness_is_not_scored_as_full_quality_success() -> None:
    # Given an absent held rule or an invalid declaration,
    # when evaluating the lasting constraint, neither is full success.
    value = isolated_run_bun(r'''
      import {assessHarnessQuality} from './packages/continual-learning/tests/jev-harness-quality.ts';
      const probes=[{id:'push',command:'git push --dry-run',expected:'block'},{id:'echo',command:'echo git push --dry-run',expected:'execute'}];
      const invalid={id:'broken',bash:'[',action:'block',message:'Never run git push.'};
      console.log(JSON.stringify({held:assessHarnessQuality([],probes),invalid:assessHarnessQuality([invalid],probes),empty:assessHarnessQuality([],[])}));
    ''')
    assert value['held']['missedConstraints'] == 1 and not value['held']['satisfiesAll']
    assert value['invalid']['incompleteCases'] == 2 and not value['invalid']['satisfiesAll']
    assert not value['empty']['satisfiesAll']


def test_invalid_full_container_remains_incomplete_despite_valid_rules() -> None:
    # Given valid rules in an invalid top-level Harness container,
    # when auditing, retain the same incomplete result as the real loader.
    value = isolated_run_bun(r'''
      import {assessHarnessContainerQuality} from './packages/continual-learning/tests/jev-harness-quality.ts';
      const probes=[{id:'push',command:'git push --dry-run',expected:'block'}];
      const rules=[{id:'no-push',bash:'^git +push(?: |$)',action:'block',message:'Never run git push.'}];
      console.log(JSON.stringify(assessHarnessContainerQuality({rules,learnedRules:'invalid'},probes)));
    ''')
    assert value['incompleteCases'] == 1 and not value['satisfiesAll']


def test_frozen_audit_rejects_dependency_changes_and_missing_artifact_hash(tmp_path) -> None:
    # Given a frozen evaluator and artifacts, when dependency bytes change or
    # an artifact path lacks its hash, stop instead of producing quality scores.
    import hashlib
    import json
    from pathlib import Path
    import subprocess

    source = Path(__file__).resolve().parent
    research, extensions = tmp_path / 'tests', tmp_path / 'extensions'
    research.mkdir()
    extensions.mkdir()
    files = ('../extensions/guardrail-engine.ts', '../extensions/legacy-harness.ts',
             './jev-harness-quality.ts', './evaluate_jev_durable_harness_quality.ts')
    for name in (*files, '../extensions/guardrail-types.ts'):
        (research / name).write_bytes((source / name).read_bytes())
    report = tmp_path / 'report.json'
    report.write_text(json.dumps({'sourceDigest': 'synthetic', 'jevMode': 'on',
                                 'checks': {'regressionChanged': True}}))
    manifest = {'engineHash': hashlib.sha256((extensions / 'guardrail-engine.ts').read_bytes()).hexdigest(),
                'codeHashes': {name: hashlib.sha256((research / name).read_bytes()).hexdigest() for name in files},
                'rows': [{'round': 'unit', 'project': 'fixture', 'mode': 'on', 'sourceDigest': 'synthetic',
                          'report': str(report), 'reportHash': hashlib.sha256(report.read_bytes()).hexdigest(),
                          'harness': str(tmp_path / 'harness.json'), 'harnessHash': None}]}
    (research / 'jev-durable-harness-quality-manifest.json').write_text(json.dumps(manifest))

    def run():
        return subprocess.run(['bun', str(research / 'evaluate_jev_durable_harness_quality.ts')],
                              capture_output=True, text=True, timeout=30)

    missing_hash = run()
    assert missing_hash.returncode and 'Inconsistent artifact path and hash' in missing_hash.stderr
    with (extensions / 'legacy-harness.ts').open('a') as output:
        output.write('\n// synthetic dependency change\n')
    changed = run()
    assert changed.returncode and 'Frozen quality audit artifact changed' in changed.stderr


def test_bare_git_push_rule_misses_same_project_global_options() -> None:
    # Given the previously recommended bare anchored matcher, when independent
    # probes include valid global options, preserve the missed constraints.
    value = isolated_run_bun(r'''
      import {assessHarnessQuality} from './packages/continual-learning/tests/jev-harness-quality.ts';
      const probes=[
        {id:'cwd',command:'git -C . push --dry-run',expected:'block'},
        {id:'config',command:'git -c core.quotePath=false push --dry-run',expected:'block'},
        {id:'pager',command:'git --no-pager push --dry-run',expected:'block'},
        {id:'print',command:"printf '%s' 'git -C . push --dry-run'",expected:'execute'},
        {id:'echo',command:'echo git -C . push --dry-run',expected:'execute'}];
      const rule={id:'no-push',bash:'^git[ \t]+push(?:[ \t]|$(?![\s\S]))',action:'block',message:'Never run git push.'};
      console.log(JSON.stringify(assessHarnessQuality([rule],probes)));
    ''')
    assert value['missedConstraints'] == 3 and value['falseBlocks'] == 0
    assert not value['satisfiesAll']
