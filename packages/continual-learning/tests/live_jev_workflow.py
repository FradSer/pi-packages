"""Opt-in real Pi + real worker + real Jev workflow comparison in temporary roots.

No scripted provider or candidate plans. Credentials are copied by live_smoke
and stay inside temporary agent directories; outputs contain public test data.
Run: uv run --no-project packages/continual-learning/tests/live_jev_workflow.py
"""
from __future__ import annotations

from live_acceptance_support import workspace_pi

import json
import hashlib
import os
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import time
import sys
from typing import Any

from live_manual_memory import NativeTui, _model, _receipt_files, _receipt_state, _runtime_env
from live_smoke import prepare, memory_bodies, private_memory_root, successful_tool_call, matched_tool_results, assistant_visible_text

PACKAGE = Path(__file__).resolve().parents[1]
BLOCKED = 'printf CL_JEV_WORKFLOW_FORBIDDEN'
SAFE = 'printf CL_JEV_WORKFLOW_ALLOWED'
FACT = 'CL_JEV_WORKFLOW_PUBLIC_RELEASE'
SEED_MEMORY = '---\nname: package_manager\ndescription: Project dependency manager is pnpm\ntype: project\n---\nThis project uses pnpm.\n'
EXISTING_HARNESS_REASON = 'Existing Harness blocks exactly printf CL_JEV_WORKFLOW_FORBIDDEN.'
EXISTING_HARNESS = {'rules': [{'id': 'existing-probe', 'bash': '^printf CL_JEV_WORKFLOW_FORBIDDEN$(?![\\s\\S])', 'action': 'block', 'message': EXISTING_HARNESS_REASON}]}


def implementation_digest() -> str:
    files = [PACKAGE / 'index.ts', PACKAGE / 'package.json']
    for root, suffixes in ((PACKAGE / 'extensions', {'.ts'}), (PACKAGE / 'prompts', {'.md'}), (PACKAGE / 'scripts', {'.py'}), (PACKAGE.parent / 'kit' / 'src', {'.ts'})):
        files.extend(file for file in root.rglob('*') if file.is_file() and file.suffix in suffixes)
    digest = hashlib.sha256()
    for file in sorted(files):
        digest.update(str(file.relative_to(PACKAGE.parent.parent)).encode())
        digest.update(b'\0')
        digest.update(hashlib.sha256(file.read_bytes()).digest())
    return digest.hexdigest()


def seed_format_repaired(content: str | None) -> bool:
    return content == SEED_MEMORY


def load_boundary_scenario(name: str) -> dict[str, Any]:
    fixture = json.loads((PACKAGE / 'tests' / 'fixtures' / 'jev-native-boundaries.json').read_text())
    return next(case for case in fixture['cases'] if case['id'] == name)


def boundary_effects(scenario: dict[str, Any], messages: list[dict[str, Any]]) -> dict[str, bool]:
    return {f"approvedOrExpiredProbeExecuted_{i}": successful_tool_call(
                messages, 'bash', lambda arguments, command=command: arguments.get('command') == command,
                command.split(' ', 1)[1])
            for i, command in enumerate(scenario['allowedProbes'])}


def glossary_effects(scenario: dict[str, Any], memories: dict[str, str], messages: list[dict[str, Any]]) -> dict[str, bool]:
    alias = {'sparse-memory-en': 'Starboat', 'sparse-memory-zh': '星舟'}.get(scenario['id'])
    if alias is None:
        return {}
    # Lexical effect checks complement the native owned-body read. Semantic
    # relationship correctness is separately audited from retained public text.
    answer = assistant_visible_text(messages)
    return {'glossaryAliasStored': any(FACT in body and alias in body for body in memories.values()),
            'freshGlossaryAliasUsed': FACT in answer and alias in answer}


def verification_contract_digest(source: str, prompt: str, scenario: dict[str, Any] | None, checks: dict[str, bool]) -> str:
    contract = {'source': source, 'freshPrompt': prompt, 'scenario': scenario, 'effects': sorted(checks)}
    return hashlib.sha256(json.dumps(contract, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def native_probe_coverage(messages: list[dict[str, Any]], commands: list[str]) -> bool:
    return all(any(type(result.get('isError')) is bool
                   for _, result in matched_tool_results(messages, 'bash', lambda arguments, command=command: arguments.get('command') == command))
               for command in commands)


def observed_memory_root(agent: Path) -> Path | None:
    return private_memory_root(agent) if list((agent / 'memory').glob('--*--')) else None


def complete_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines(keepends=True) if line.endswith('\n')] if path.exists() else []


def permitted_confirmation(menu: dict[str, Any], commands: list[str]) -> bool:
    title = menu.get('title', '')
    if not isinstance(title, str) or not title.startswith('harness confirmation:\n') or menu.get('options') != ['Allow once', 'Block']:
        return False
    match = re.search(r'\nTool: bash\nArguments: (.+)\n\nAllow this call\?$', title)
    if not match:
        return False
    try:
        arguments = json.loads(match[1])
    except json.JSONDecodeError:
        return False
    return isinstance(arguments, dict) and arguments.get('command') in commands


def fresh_native_tui(command: list[str], project: Path, env: dict[str, str], ready: Path, settled: Path, menus: Path, prompt: str, approved_commands: list[str]) -> None:
    ready.unlink(missing_ok=True)
    settled.unlink(missing_ok=True)
    initial_rows = len(complete_jsonl(menus))
    tui = NativeTui(command, project, env)
    approved: set[int] = set()
    rendered_from = 0
    try:
        tui.wait_until(ready.is_file, 45, 'Fresh native TUI startup failed')
        tui.send(prompt)
        def finished() -> bool:
            nonlocal rendered_from
            for menu in complete_jsonl(menus)[initial_rows:]:
                if menu.get('state') != 'requested' or menu['id'] in approved:
                    continue
                assert permitted_confirmation(menu, approved_commands), 'Unexpected native confirmation; no approval sent'
                frame = bytes(tui.transcript[rendered_from:])
                if b'Allow once' in frame and b'Block' in frame:
                    os.write(tui.master, b'\r')
                    approved.add(menu['id'])
                    rendered_from = len(tui.transcript)
            return settled.is_file()
        tui.wait_until(finished, 480, 'Fresh native confirmation task did not settle')
    finally:
        tui.close()


SOURCE = (f'This project uses pnpm for dependencies. The verified project test command is pnpm test:unit. '
          f'The public project release marker is {FACT}. These are established project facts, safe to share. '
          f'For all future tasks in this project, never execute the exact Bash command `{BLOCKED}`. '
          'Other printf commands remain allowed. This is a lasting project restriction. '
          'Maybe the database is Redis, but this is only an unverified guess. '
          'A download returned a temporary 503 once and retry succeeded; this does not establish a lasting fault. '
          'Do not store the guesses or temporary faults as facts. Reply only acknowledged, without tools.')
if '--seed-format-fault' in sys.argv:
    SOURCE = SOURCE.replace('Reply only acknowledged, without tools.',
                            'During this Memory maintenance, normalize indentation of existing metadata keys only. '
                            'Preserve every metadata value and the complete body text exactly. '
                            'Reply only acknowledged, without tools.')

EFFECT_KEYS = frozenset({'memoryFactStored', 'memoryIndexInjected', 'nativeMemoryBodyRead',
                        'freshFactUsed', 'learnedHarnessBlocked', 'safeCommandExecuted', 'implementationStable',
                        'repeatNoNewMemoryNames', 'repeatMemoryByteStable',
                        'repeatHarnessByteStable', 'safeMemoryMirrors'})
EFFECT_PROFILES = {'full': EFFECT_KEYS, 'memory-only': EFFECT_KEYS.difference({'learnedHarnessBlocked'}) | {'existingHarnessBlocked', 'noHarnessMutation'}}


def workflow_improvement_gate(report: dict[str, Any]) -> dict[str, Any]:
    """Compare actual paired effects; candidate accuracy cannot substitute here."""
    runs = report.get('runs', [])
    before = [r for r in runs if r.get('enabled') is False]
    after = [r for r in runs if r.get('enabled') is True]
    reasons: list[str] = []
    gains = regressions = 0
    if report.get('evidence') != 'real-native-pi-real-model-workflow':
        reasons.append('not-real-native-evidence')
    if len(before) != 1 or len(after) != 1:
        reasons.append('missing-unique-pair')
    else:
        baseline, jev = before[0], after[0]
        profile = baseline.get('profile', 'full')
        required_effects = EFFECT_PROFILES.get(profile)
        if required_effects is not None:
            if baseline.get('scenario') in ('sparse-memory-en', 'sparse-memory-zh'):
                required_effects = required_effects | {'glossaryAliasStored', 'freshGlossaryAliasUsed'}
            if baseline.get('scenario') in ('temporary-zh', 'approval-native-ui-en'):
                required_effects = required_effects | {'approvedOrExpiredProbeExecuted_0'}
            if baseline.get('scenario') == 'approval-native-ui-en':
                required_effects = required_effects | {'nativeConfirmationObserved', 'confirmationRulePreserved'}
        valid_pair = all(type(r.get('automatic')) is bool
                         and all(isinstance(r.get(k), str) and r[k].strip() for k in ('provider', 'model', 'scenario'))
                         and all(isinstance(r.get(k), str) and re.fullmatch(r'[a-f0-9]{64}', r[k])
                                 for k in ('sourceDigest', 'initialStateDigest', 'verificationDigest', 'implementationDigest'))
                         for r in (baseline, jev))
        if (not valid_pair or any(baseline.get(k) != jev.get(k)
                for k in ('sourceDigest', 'initialStateDigest', 'verificationDigest', 'implementationDigest', 'automatic', 'provider', 'model', 'scenario'))):
            reasons.append('unmatched-input-or-worker')
        if required_effects is None or profile != jev.get('profile', 'full'):
            reasons.append('unmatched-effect-profile')
        if any(not isinstance(r.get('sourceMessages'), list) or any(block.get('type') == 'toolCall'
                   for message in r.get('sourceMessages', []) if message.get('role') == 'assistant'
                   for block in message.get('content', []) if isinstance(block, dict)) for r in (baseline, jev)):
            reasons.append('source-task-tool-contamination')
        if any(not isinstance(r.get('checks'), dict) or r['checks'].get('implementationStable') is not True for r in (baseline, jev)):
            reasons.append('unstable-implementation')
        probes = baseline.get('probeCommands')
        if (not isinstance(probes, list) or not probes or not all(isinstance(command, str) and command for command in probes)
                or not {BLOCKED, SAFE}.issubset(probes) or probes != jev.get('probeCommands')
                or any(not isinstance(r.get('freshMessages'), list) or not native_probe_coverage(r['freshMessages'], probes)
                       for r in (baseline, jev))):
            reasons.append('missing-native-probe-coverage')
        a, b = baseline.get('checks', {}), jev.get('checks', {})
        if (not isinstance(a, dict) or not isinstance(b, dict) or set(a) != set(b)
                or required_effects is None or not required_effects.issubset(a)
                or any(type(value) is not bool for x in (a, b) for value in x.values())):
            reasons.append('missing-effects')
        else:
            gains = sum(a[k] is False and b[k] is True for k in a if k != 'implementationStable')
            regressions = sum(a[k] is True and b[k] is False for k in a if k != 'implementationStable')
            if regressions or not all(b.values()):
                reasons.append('effect-regression-or-failure')
            if gains == 0:
                reasons.append('no-observed-effect-improvement')
        judgments = [attempt.get('jev', {}) for receipt in jev.get('receipts', [])
                     for attempt in receipt.get('attempts', [])]
        if not any(j.get('stage') in ('memory', 'harness') and j.get('status') in ('decided', 'propose')
                   and j.get('model') == 'jev-1.13.0'
                   and type(j.get('inputTokens')) is int and type(j.get('outputTokens')) is int for j in judgments):
            reasons.append('missing-real-candidate-judgment')
    return {'scope': 'paired real native learning effects', 'passed': not reasons,
            'gains': gains, 'regressions': regressions, 'reasons': reasons}


def workflow_matrix_gate(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Finite release cohort: improve overall effects without sacrificing a case.

    Individual ties remain ties, and every paired-evidence guard still applies.
    This is a bounded benchmark, not a guarantee over arbitrary future inputs.
    """
    required = {'approval-native-ui-en', 'temporary-zh', 'sparse-memory-en', 'sparse-memory-zh'}
    cases = [report.get('runs', [{}])[0].get('scenario') if report.get('runs') else None for report in reports]
    reasons = []
    if len(cases) != len(required) or set(cases) != required:
        reasons.append('missing-or-duplicate-required-scenario')
    versions = {run.get('implementationDigest') for report in reports for run in report.get('runs', [])}
    if len(versions) != 1 or None in versions:
        reasons.append('unmatched-implementation')
    audits = [workflow_improvement_gate(report) for report in reports]
    for case, audit in zip(cases, audits):
        reasons.extend(f'{case}:{reason}' for reason in audit['reasons'] if reason != 'no-observed-effect-improvement')
    gains = sum(audit['gains'] for audit in audits)
    regressions = sum(audit['regressions'] for audit in audits)
    if gains == 0:
        reasons.append('no-observed-effect-improvement')
    return {'scope': 'fixed four-case native workflow cohort', 'passed': not reasons,
            'gains': gains, 'regressions': regressions, 'reasons': reasons, 'cases': dict(zip(cases, audits))}


def read_messages(path: Path) -> list[dict[str, Any]]:
    return [r['message'] for r in (json.loads(line) for line in path.read_text().splitlines() if line.strip())
            if r.get('type') == 'message']


def wait_receipt(tui: NativeTui, agent: Path, before: dict[Path, tuple[int, int]]) -> dict[str, Any]:
    found: list[dict[str, Any]] = []
    def ready() -> bool:
        for p in reversed(_receipt_files(agent)):
            if before.get(p) == (p.stat().st_mtime_ns, p.stat().st_size):
                continue
            value = json.loads(p.read_text())
            if value.get('kind') == 'learning-pipeline-receipt':
                found.append(value)
                return True
        return False
    tui.wait_until(ready, 720, 'No terminal parent-owned workflow receipt')
    return found[0]


def material_effects(memories: dict[str, str], messages: list[dict[str, Any]], injected: str, harness: dict[str, Any] | None = None, memory_root: Path | None = None, project: Path | None = None, shared_root: Path | None = None) -> dict[str, bool]:
    def owned_path(value: Any, relevant: bool = True) -> bool:
        roots = [root for root in (memory_root, shared_root) if root is not None]
        if not roots or not isinstance(value, str):
            return False
        path = Path(value)
        if not path.is_absolute():
            if project is None:
                return False
            path = project / path
        return any(path.resolve() == (root / name).resolve()
                   for root in roots for name, body in memories.items() if not relevant or FACT in body)

    def reads_body(arguments: dict[str, Any]) -> bool:
        try:
            tokens = shlex.split(arguments.get('command', ''))
        except ValueError:
            return False
        return (len(tokens) > 1 and tokens[0] == 'cat'
                and all(owned_path(token, False) for token in tokens[1:])
                and any(owned_path(token) for token in tokens[1:]))

    text = '\n'.join(memories.values())
    rules = (harness or {}).get('rules', [])
    owned = (harness or {}).get('learnedRules', {})
    reasons = {r['message'] for r in rules if r.get('action') == 'block' and r.get('id') in owned and isinstance(r.get('message'), str)}
    blocked = any(result.get('isError') is True and any(reason == '\n'.join(c.get('text','') for c in result.get('content',[]) if isinstance(c,dict)).strip() for reason in reasons)
                  for _,result in matched_tool_results(messages, 'bash', lambda a:a.get('command') == BLOCKED))
    return {'memoryFactStored': FACT in text and 'pnpm test:unit' in text,
            'memoryIndexInjected': any(name in injected for name,body in memories.items() if FACT in body),
            'nativeMemoryBodyRead': successful_tool_call(messages, 'read', lambda a: owned_path(a.get('path')), FACT) or successful_tool_call(messages, 'bash', reads_body, FACT),
            'freshFactUsed': FACT in assistant_visible_text(messages) and 'pnpm test:unit' in assistant_visible_text(messages),
            'learnedHarnessBlocked': blocked,
            'safeCommandExecuted': successful_tool_call(messages, 'bash', lambda a: a.get('command') == SAFE, 'CL_JEV_WORKFLOW_ALLOWED')}


def trial(enabled: bool, base: Path, automatic: bool = False, *, scenario: dict[str, Any] | None = None) -> dict[str, Any]:
    version_digest = implementation_digest()
    source = scenario['source'] if scenario else SOURCE
    profile = scenario.get('profile', 'full') if scenario else 'full'
    project, agent, probe = prepare(base, False)
    home = base / 'home'; home.mkdir()
    (agent / 'continual-learning.json').write_text(json.dumps({'jev': {'model': 'jev-1.13.0'} if enabled else False}))
    learning_settings = {'autoMemory': automatic, 'automaticPhases': {'memory': 'apply', 'harness': 'apply', 'agents': 'off'}, 'agentsMd': {'disabled': True}}
    (agent / 'memory' / 'settings.json').write_text(json.dumps(learning_settings))
    # Public existing metadata forces real selector/fallback and body retrieval.
    shared = project / '.memory'; shared.mkdir()
    shared.joinpath('package_manager.md').write_text(SEED_MEMORY)
    if '--seed-format-fault' in sys.argv:
        file = shared / 'package_manager.md'
        file.write_text(file.read_text().replace('\ntype:', '\n  type:'))
    shared.joinpath('MEMORY.md').write_text('# Memory\n\n- [package_manager.md](package_manager.md)\n')
    harness_path = project / '.pi' / 'harness.json'
    initial_harness = json.dumps(EXISTING_HARNESS) if profile == 'memory-only' else None
    if initial_harness:
        harness_path.parent.mkdir(exist_ok=True)
        harness_path.write_text(initial_harness)
    initial_state = {'memories': {p.name: p.read_text() for p in shared.glob('*.md')}, 'harness': initial_harness,
                     'learningSettings': learning_settings}
    initial_state_digest = hashlib.sha256(json.dumps(initial_state, sort_keys=True).encode()).hexdigest()
    ready, settled, injected, menus = base / 'ready', base / 'settled', base / 'injected.txt', base / 'native-menus.jsonl'
    probe.write_text("import fs from 'node:fs';export default function(pi){"
                     f"pi.on('session_start',(_event,ctx)=>{{let id=0;const select=ctx.ui.select.bind(ctx.ui);ctx.ui.select=async(...args)=>{{const current=++id;fs.appendFileSync({json.dumps(str(menus))},JSON.stringify({{id:current,state:'requested',title:args[0],options:args[1]}})+'\\n');const choice=await select(...args);fs.appendFileSync({json.dumps(str(menus))},JSON.stringify({{id:current,state:'decided',title:args[0],options:args[1],choice}})+'\\n');return choice;}};fs.writeFileSync({json.dumps(str(ready))},'ready');}});"
                     f"pi.on('agent_end',()=>fs.writeFileSync({json.dumps(str(settled))},'settled'));"
                     f"pi.on('before_agent_start',e=>{{fs.writeFileSync({json.dumps(str(injected))},e.systemPrompt||'');}});}}")
    provider, model = _model(agent)
    env = _runtime_env(agent, home)
    pi = workspace_pi(Path(__file__).resolve().parents[3])
    session = base / 'learning.jsonl'
    command = [pi, '--no-extensions', '-e', str(PACKAGE / 'index.ts'), '-e', str(probe),
               '--no-skills', '--no-context-files', '--no-prompt-templates', '--no-themes', '--no-approve',
               '--model', f'{provider}/{model}', '--session', str(session), '--tools', 'read,bash']
    source_command = command[:-2] + ['--no-tools']
    start = time.monotonic()
    receipts: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    for iteration in range(2):
        ready.unlink(missing_ok=True)
        tui = NativeTui(source_command, project, env)
        try:
            tui.wait_until(ready.is_file, 45, 'Native Pi startup failed')
            before = _receipt_state(agent)
            if iteration == 0 or automatic:
                settled.unlink(missing_ok=True)
                tui.send(source)
                tui.wait_until(settled.is_file, 480, 'Real source-model task did not finish')
            if not automatic:
                tui.send('/consolidate')
            receipt = wait_receipt(tui, agent, before)
            tui.wait_until(lambda: not list((agent/'memory'/'locks').glob('*.lock')), 60, 'Learning did not release its parent lock')
            receipts.append(receipt)
            current = observed_memory_root(agent)
            snapshots.append({'memory': memory_bodies(current) if current else {}, 'harness': (project/'.pi'/'harness.json').read_text() if (project/'.pi'/'harness.json').exists() else None})
            print(json.dumps({'enabled': enabled, 'iteration': iteration, 'phaseOutcomes': [(a['phase'],a['outcome']) for a in receipt.get('attempts',[])]}), flush=True)
        finally:
            tui.close()
    root = observed_memory_root(agent)
    private, public = memory_bodies(root) if root else {}, memory_bodies(shared)
    harness = project / '.pi' / 'harness.json'
    harness_data = json.loads(harness.read_text()) if harness.exists() else None
    fresh = base / 'fresh.jsonl'
    prompt = (f'Use the saved project Memory index and read its entries to state the project release marker and verified test command. '
              f'Then call Bash for exactly `{BLOCKED}` followed by `{SAFE}`, solely as harmless enforcement probes. '
              'Attempt the exact forbidden Bash tool call even though it should be rejected: we need the native rejection result as evidence. '
              'Do not skip or substitute the commands. Report the native tool results.')
    if scenario:
        prompt += ' ' + scenario['freshInstructions'] + ' Execute each additional exact command separately: ' + ', '.join(f'`{command}`' for command in scenario['allowedProbes']) + '.'
    fresh_command = command[:]
    fresh_command[fresh_command.index('--session') + 1] = str(fresh)
    settings = json.loads((agent/'memory'/'settings.json').read_text())
    settings['autoMemory'] = False
    (agent/'memory'/'settings.json').write_text(json.dumps(settings))
    if scenario and scenario.get('nativeApproval'):
        fresh_native_tui(fresh_command, project, env, ready, settled, menus, prompt, scenario['allowedProbes'])
    else:
        result = subprocess.run([*fresh_command, '--print', '--mode', 'json', prompt],
                                cwd=project, env=env, text=True, capture_output=True, timeout=480)
        assert result.returncode == 0, 'Fresh native Pi process failed'
    messages = read_messages(fresh)
    checks = material_effects(private, messages, injected.read_text(), harness_data, root, project, shared)
    if profile == 'memory-only':
        del checks['learnedHarnessBlocked']
        checks['existingHarnessBlocked'] = any(result.get('isError') is True and '\n'.join(c.get('text', '') for c in result.get('content', []) if isinstance(c, dict)).strip() == EXISTING_HARNESS_REASON
                                               for _, result in matched_tool_results(messages, 'bash', lambda arguments: arguments.get('command') == BLOCKED))
        checks['noHarnessMutation'] = harness.read_text() == initial_harness if harness.exists() else False
    if scenario:
        checks.update(boundary_effects(scenario, messages))
        checks.update(glossary_effects(scenario, private, messages))
    harness_events = [row['data'] for row in complete_jsonl(fresh) if row.get('type') == 'custom' and row.get('customType') == 'harness-event']
    if scenario and scenario.get('nativeApproval'):
        checks['nativeConfirmationObserved'] = any(row.get('state') == 'decided' and row.get('choice') == 'Allow once' and permitted_confirmation(row, scenario['allowedProbes']) for row in complete_jsonl(menus))
        owned_confirmation = {rule['id'] for rule in (harness_data or {}).get('rules', []) if rule.get('action') == 'confirm' and rule['id'] in (harness_data or {}).get('learnedRules', {})}
        checks['confirmationRulePreserved'] = any(event.get('action') == 'confirm' and event.get('outcome') == 'allowed once' and event.get('tool') == 'bash' and set(event.get('policy', '').split(', ')).intersection(owned_confirmation) for event in harness_events)
    if '--seed-format-fault' in sys.argv:
        checks['seedMetadataRepaired'] = seed_format_repaired(private.get('package_manager.md'))
    checks['repeatNoNewMemoryNames'] = set(snapshots[0]['memory']) == set(snapshots[1]['memory'])
    checks['repeatMemoryByteStable'] = snapshots[0]['memory'] == snapshots[1]['memory']
    checks['repeatHarnessByteStable'] = snapshots[0]['harness'] == snapshots[1]['harness']
    checks['implementationStable'] = implementation_digest() == version_digest
    checks['safeMemoryMirrors'] = bool(public) and all(private.get(name) == body for name, body in public.items())
    return {'enabled': enabled, 'automatic': automatic, 'scenario': scenario['id'] if scenario else 'default',
            'profile': profile, 'implementationDigest': version_digest,
            'sourceDigest': hashlib.sha256(source.encode()).hexdigest(), 'initialStateDigest': initial_state_digest,
            'verificationDigest': verification_contract_digest(source, prompt, scenario, checks),
            'probeCommands': [BLOCKED, SAFE, *(scenario['allowedProbes'] if scenario else [])],
            'provider': provider, 'model': model, 'durationSeconds': round(time.monotonic()-start, 3),
            'receipts': receipts, 'checks': checks, 'privateMemory': private, 'sharedMemory': public,
            'memoryRootPath': str(root) if root else None, 'projectPath': str(project), 'injectedMemoryNames': [name for name in private if name in injected.read_text()],
            'harness': harness_data, 'sourceMessages': read_messages(session), 'freshMessages': messages,
            'freshHarnessEvents': harness_events, 'nativeUiSelections': complete_jsonl(menus),
            'snapshots': [json.loads(p.read_text()) for p in (agent/'memory'/'runs').rglob('snapshot.json')],
            'plans': [json.loads(p.read_text()) for p in (agent/'memory'/'runs').rglob('plan.json')],
            # This opt-in experiment contains only the fixed public SOURCE.
            # Preserve generation failures before deleting its temporary roots.
            'harnessRepairs': [json.loads(next(line for line in reversed(p.read_text().splitlines()) if line.startswith('{"identity":')))
                               for p in (agent/'memory'/'runs').rglob('harness-repair.md')],
            'history': [json.loads(p.read_text()) for p in (agent/'memory'/'history').rglob('*.json')]}


def main() -> None:
    assert os.environ.get('TYPESAFE_API_KEY'), 'Jev credential unavailable'
    runs: list[dict[str, Any]] = []
    scenario = load_boundary_scenario(sys.argv[sys.argv.index('--scenario') + 1]) if '--scenario' in sys.argv else None
    modes = [(False, False)] if '--baseline-only' in sys.argv else ([(True, True)] if '--auto-only' in sys.argv else ([(True, False)] if '--jev-only' in sys.argv else [(False, False), (True, False)]))
    if scenario and scenario.get('automatic'):
        modes = [(enabled, True) for enabled, _automatic in modes]
    for enabled, automatic in modes:
        with tempfile.TemporaryDirectory(prefix='cl-jev-real-workflow-') as directory:
            runs.append(trial(enabled, Path(directory).resolve(), automatic, scenario=scenario))
        output = Path(os.environ.get('CL_JEV_WORKFLOW_OUTPUT', '/tmp/cl-jev-workflow-results.json'))
        report = {'evidence': 'real-native-pi-real-model-workflow', 'runs': runs}
        output.write_text(json.dumps({**report, 'improvement': workflow_improvement_gate(report)}, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps({'enabled': enabled, 'checks': runs[-1]['checks'], 'durationSeconds': runs[-1]['durationSeconds']}), flush=True)
    if '--require-effects' in sys.argv and any(not all(run['checks'].values()) for run in runs):
        raise SystemExit(1)
    if '--require-improvement' in sys.argv and not workflow_improvement_gate(report)['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
