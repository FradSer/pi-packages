"""Native Pi Memory generation and retained-body correction, with no paid calls.

Run this explicit acceptance in a network-disabled Docker container. Loopback
generation and Jev answers test mechanics, not judgment accuracy or benefit.
The same project, native session and stored Memory survive every command.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading
import traceback

from continuous_failure_retention import deduplicate_receipt_views
from live_acceptance_support import isolated_environment, workspace_pi
from live_learning_loop import field, message_text, stream_response, controlled_body_reference as body_reference, controlled_knowledge_units
from support import REPO

RELATIONS = (
    'The voice worker requires the registry before boot.',
    'Ready means registry loaded; it does not mean microphone paired.',
    'The mode convention applies only to release checks.',
)
NAME = 'runtime.md'


def markdown(mode: str, *, complete: bool = True) -> str:
    body = f'Observed source in runtime.ts: `export const mode = "{mode}";`.\n'
    return ('---\nname: ' + json.dumps(NAME) + '\ndescription: ' + json.dumps('runtime.ts declares the release mode') + '\n'
            'type: project\n---\n' + body + ('\n'.join(RELATIONS) + '\n' if complete else ''))


def citation_lines(value: object) -> list[dict]:
    if isinstance(value, dict):
        return ([value] if isinstance(value.get('ref'), str) and isinstance(value.get('text'), str) else []) + [
            line for child in value.values() for line in citation_lines(child)]
    if isinstance(value, list):
        return [line for child in value for line in citation_lines(child)]
    return []


def run(output: Path, *, pi_version: str = '1.3.0') -> dict:
    output.mkdir(parents=True, exist_ok=False)
    project, agent = output / 'project', output / 'agent'
    project.mkdir(); agent.mkdir()
    subprocess.run(['git', 'init', '-q', str(project)], check=True, capture_output=True)
    source = project / 'runtime.ts'
    source.write_text('export const mode = "old";\n' + ''.join('// ' + fact + '\n' for fact in RELATIONS))
    report = {'status': 'failed', 'paidRequests': 0, 'externalRequests': 0,
              'learningBenefitEstablished': False, 'judgments': 'controlled loopback fixtures', 'stages': []}
    tracked = [Path(__file__), *REPO.joinpath('packages/continual-learning/extensions').rglob('*.ts'),
               *REPO.joinpath('packages/continual-learning/prompts').glob('*.md'),
               *REPO.joinpath('packages/kit/src').rglob('*.ts')]
    report['sourceHashes'] = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
    prompt_source = REPO.joinpath('packages/continual-learning/extensions/planner-prompts.ts').read_text()
    knowledge_contract = prompt_source.split('export const MEMORY_KNOWLEDGE_GUIDANCE = `', 1)[1].split('`;', 1)[0]
    phase = {'name': 'source-new'}
    requests: list[dict] = []
    errors: list[str] = []
    paths: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_POST(self) -> None:
            try:
                assert self.path in ('/v1/chat/completions', '/jev/v1/systemone')
                raw = self.rfile.read(int(self.headers['Content-Length']))
                data = json.loads(raw)
                assert len(requests) < 180, 'Unexpected fixture request loop'
                requests.append({'phase': phase['name'], 'path': self.path,
                                 'sha256': hashlib.sha256(raw).hexdigest(), 'body': data})
                if self.path.startswith('/jev/'):
                    state = data.get('state', {})
                    if isinstance(state, str):
                        state = json.loads(state)
                    plan = state.get('completeCurrentPlan', {})
                    records = [*plan.get('operations', []), *plan.get('newMemories', [])]
                    missing = any(fact not in record.get('content', '') for record in records for fact in RELATIONS)
                    if phase['name'] in ('description-only', 'body-correction'):
                        # A retained plan has no candidate. Its old body still
                        # lacks the requested current-source mode declaration.
                        missing = not records or any('mode = "corrected"' not in r.get('content', '') for r in records)
                    answers = {}
                    for key, question in data['questions'].items():
                        if question['type'] == 'noul':
                            answers[key] = {'type': 'noul', 'noul': .99 if key.startswith('supported_') or key == 'memory' else .01}
                        elif question['type'] == 'score':
                            answers[key] = {'type': 'score', 'score': 3, 'confidence': 1,
                                            'legend': {str(i): str(i) for i in range(4)},
                                            'probabilities': {str(i): int(i == 3) for i in range(4)}}
                        else:
                            labels = list(question['criteria'])
                            label = next((x for x in ('independent', 'selfContained', 'compatible', 'grounded', 'consistent', 'unrelated') if x in labels), labels[0])
                            if labels == ['true', 'false'] and key in ('memory', 'harness'):
                                label = 'true' if key == 'memory' else 'false'
                            if key.startswith('coverage_'):
                                label = ('material_missing' if missing else 'dismissed') if key.startswith('coverage_issue_') else ('missing' if missing else 'complete')
                            answers[key] = {'type': 'choice', 'choice': label, 'confidence': 1,
                                            'probabilities': {x: int(x == label) for x in labels}}
                    body = json.dumps({'model': 'jev-1.13.0', 'answers': answers,
                                       'usage': {'input_tokens': 1, 'output_tokens': 1}}).encode()
                    self.send_response(200); self.send_header('Content-Length', str(len(body)))
                    self.end_headers(); self.wfile.write(body)
                    return
                text = message_text(data)
                if 'Task: inspect current project source' in text:
                    if not any(m.get('role') == 'tool' for m in data['messages']):
                        stream_response(self, [{'id': 'source', 'name': 'learning_read',
                                                'arguments': {'path': str(source), 'offset': 1, 'limit': 100}}])
                    else:
                        stream_response(self, 'Current source observed.')
                elif '# Incremental Memory selector' in text:
                    stream_response(self, json.dumps({'kind': 'incremental-memory-selection', 'version': 1,
                        'contextDigest': field(text, 'Context digest'), 'selected': [] if phase['name'] == 'generation' else [NAME],
                        'memory': True, 'harness': False, 'agents': False, 'reason': 'Controlled source review'}))
                elif 'Task: repair one rejected incremental Memory delta plan.' in text or '"atomicKnowledgeContract"' in text:
                    payload = json.loads(text.split('\n')[-1])
                    if payload.get('atomicKnowledgeContract'):
                        assert text.count(knowledge_contract) == 1, 'Atomic repair lost or duplicated the shared knowledge contract'
                    assert payload['requiredTextChanges'][NAME] == ['body'], payload.get('requiredTextChanges')
                    refs = citation_lines(payload['semanticContext']['frozenEvidence'])
                    mode = 'new' if phase['name'] == 'generation' else 'corrected'
                    evidence = []
                    for needle in [f'export const mode = "{mode}";', *RELATIONS]:
                        matches = [line for line in refs if needle in line['text'] and '.l' in line['ref']]
                        assert matches, 'Complete source relations must reach correction: ' + needle
                        evidence.append({'ref': matches[-1]['ref']})
                    answer = {'kind': 'incremental-memory-amendment', 'version': 1, **payload['identity'], 'replacements': []}
                    if phase['name'] == 'generation':
                        answer['replacements'] = [{'candidateId': payload['repairCandidates'][0]['candidateId'],
                                                   **({'knowledge': controlled_knowledge_units(markdown(mode), evidence)}
                                                      if payload.get('atomicKnowledgeContract') else {'content': markdown(mode), 'evidence': evidence})}]
                    else:
                        assert payload['rejectedPlan']['operations'] == []
                        assert NAME in payload['retainedRepairNames']
                        predecessor = next(x for x in payload['semanticContext']['existingMemories'] if x['name'] == NAME)
                        content = (predecessor['content'].replace('description: ' + json.dumps('runtime.ts declares the release mode'),
                                   'description: ' + json.dumps('runtime.ts declares the corrected release mode'))
                                   if phase['name'] == 'description-only' else markdown(mode))
                        fields = ({'knowledge': controlled_knowledge_units(content, evidence)}
                                  if payload.get('atomicKnowledgeContract') and phase['name'] != 'description-only' else {'content': content, 'evidence': evidence})
                        answer = {**payload['rejectedPlan'], 'operations': [{
                            'name': NAME, 'kind': 'rewrite', 'classification': 'safe',
                            **fields}]}
                    stream_response(self, json.dumps(answer))
                elif 'Review knowledge coverage, separately from internal consistency and source truth.' in text:
                    payload = json.loads(text.split('\n')[-1])
                    refs = citation_lines(payload['frozenEvidence'])
                    assert refs
                    mode = 'new' if phase['name'] == 'generation' else 'corrected'
                    expected = [f'Observed source in runtime.ts: `export const mode = "{mode}";`.', *RELATIONS]
                    reviews, obligations = {}, []
                    for target in payload['targets']:
                        body = target['content'].split('\n---\n', 1)[-1]
                        claims, uncovered = [], []
                        for statement in expected:
                            needle = f'export const mode = "{mode}";' if statement == expected[0] else statement
                            matches = [line for line in refs if needle in line['text']]
                            assert matches, 'Source relation missing from frozen evidence: ' + needle
                            evidence = [{'ref': matches[-1]['ref']}]
                            if statement in body:
                                claims.append({'statement': statement, 'bodyQuote': body_reference(target['content'], statement, f'm{target["targetIndex"]}') if target.get('bodyLocations') else statement, 'evidence': evidence, 'conditions': []})
                            else:
                                uncovered.append({'statement': statement, 'evidence': evidence})
                                obligations.append({'basis': 'requested', 'statement': statement, 'evidence': [{'ref': refs[0]['ref']}],
                                                    'coveredBy': [], 'status': 'missing'})
                        scope = ({'basis': 'predecessor', 'statement': 'Existing release knowledge', 'evidence': [],
                                  'predecessorQuote': body.splitlines()[0]} if target['source'] == 'retained' else
                                 {'basis': 'optional', 'statement': 'Current release knowledge', 'evidence': [{'ref': refs[-1]['ref']}]})
                        if target['source'] == 'retained' and target.get('bodyLocations'):
                            index = next(i for i, prior in enumerate(payload['predecessors']) if prior['name'] == target['name'])
                            scope['predecessorQuote'] = body_reference(payload['predecessors'][index]['content'], body.splitlines()[0], f'p{index}')
                        reviews[str(target['targetIndex'])] = {'scope': scope, 'claims': claims, 'uncovered': uncovered,
                                                               'verdict': 'incomplete' if uncovered else 'covered'}
                    stream_response(self, json.dumps({'plan': {'verdict': 'incomplete' if obligations else 'covered',
                                                               'obligations': obligations}, 'reviews': reviews}))
                elif 'incremental-memory-plan' in text:
                    snapshot = json.loads((Path(paths['runsDir']) / field(text, 'runId') / 'snapshot.json').read_text())
                    audit_index = next(i for i, entry in enumerate(snapshot['entries'])
                                       if entry.get('message', {}).get('details', {}).get('readOnlyMaintenanceAudit'))
                    evidence = [{'ref': f'e{audit_index}.b0.l1'}]
                    answer = {'kind': 'incremental-memory-plan', 'version': 1, 'schemaVersion': 1,
                              **{k: field(text, k) for k in ('runId', 'scopeKey', 'scopeDigest', 'artifactHash', 'snapshotDigest')},
                              'operations': [], 'newMemories': []}
                    if phase['name'] == 'generation':
                        assert evidence
                        answer['newMemories'] = [{'name': NAME, 'kind': 'project', 'classification': 'safe',
                                                  'description': 'runtime.ts declares the release mode',
                                                  'knowledge': controlled_knowledge_units(markdown('new', complete=False), evidence)}]
                    stream_response(self, json.dumps(answer))
                elif 'Review each complete candidate Memory below' in text:
                    targets = json.loads(text.split('\n')[-1])['targets']
                    stream_response(self, json.dumps({'reviews': {str(t['targetIndex']): {
                        'verdict': 'consistent', 'conflictingQuotes': []} for t in targets}}))
                else:
                    current = max(i for i, m in enumerate(data['messages']) if m.get('role') == 'user')
                    tools = [m for m in data['messages'][current + 1:] if m.get('role') == 'tool']
                    if phase['name'] == 'retrieval':
                        if not tools:
                            assert NAME in text, 'Stored Memory is absent from discovery'
                            stream_response(self, [{'id': 'memory-read', 'name': 'read', 'arguments': {
                                'path': str(Path(paths['harnessDir']) / NAME), 'offset': 1, 'limit': 100}}])
                        else:
                            observed = message_text({'messages': tools})
                            assert all(fact in observed for fact in RELATIONS) and 'mode = "corrected"' in observed
                            assert 'mode = "new"' not in observed
                            stream_response(self, 'Observed the corrected mode and all three knowledge relations in the stored body.')
                    elif not tools:
                        stream_response(self, [{'id': 'source-read', 'name': 'read', 'arguments': {'path': str(source)}}])
                    elif len(tools) == 1 and phase['name'] in ('source-new', 'source-corrected'):
                        old, new = ('old', 'new') if phase['name'] == 'source-new' else ('new', 'corrected')
                        stream_response(self, [{'id': 'source-edit', 'name': 'edit', 'arguments': {
                            'path': str(source), 'oldText': f'export const mode = "{old}";',
                            'newText': f'export const mode = "{new}";'}}])
                    else:
                        stream_response(self, 'Observed the current release mode, registry dependency, readiness boundary and release-only scope.')
            except Exception as error:
                errors.append(traceback.format_exc())
                self.send_error(500, 'Controlled fixture failure')

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    env = isolated_environment(output / 'home', agent)
    env.update(TYPESAFE_BASE_URL=f'http://127.0.0.1:{server.server_port}/jev', TYPESAFE_API_KEY='offline-fixture')
    (agent / 'memory').mkdir()
    (agent / 'memory/settings.json').write_text(json.dumps({'autoMemory': False,
        'automaticPhases': {'memory': 'off', 'harness': 'off', 'agents': 'off'}}))
    (agent / 'settings.json').write_text(json.dumps({'packages': [], 'quietStartup': True, 'retry': {'enabled': False}}))
    (agent / 'continual-learning.json').write_text(json.dumps({'jev': {'model': 'jev-1.13.0', 'allowPrivateMemory': True, 'requestConcurrency': 1}}))
    (agent / 'memory.json').write_text('{"provider":"fixture","model":"scripted"}')
    (agent / 'models.json').write_text(json.dumps({'providers': {'fixture': {
        'baseUrl': f'http://127.0.0.1:{server.server_port}/v1', 'api': 'openai-completions', 'apiKey': 'offline-fixture',
        'models': [{'id': 'scripted', 'reasoning': False, 'input': ['text'], 'contextWindow': 200000,
                    'maxTokens': 4096, 'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0}}]}}}))
    code = 'import {resolveMemoryPaths} from ' + json.dumps(str(REPO / 'packages/continual-learning/extensions/memory-paths.ts')) + ';console.log(JSON.stringify(resolveMemoryPaths(process.argv[1])));'
    # Keep all roots parent-derived, including the native command session.
    paths.update(json.loads(subprocess.check_output(['node', '--import', 'tsx', '--input-type=module', '-e', code, str(project)], cwd=REPO, env=env, text=True)))
    session = agent / 'sessions/fixture/session.jsonl'
    session.parent.mkdir(parents=True)
    argv = [workspace_pi(REPO), '--offline', '--no-extensions', '--no-context-files', '--no-skills',
            '--no-prompt-templates', '--no-themes', '--no-approve', '--thinking', 'off', '--tools', 'read,edit',
            '-e', str(REPO / 'packages/continual-learning/index.ts'), '--model', 'fixture/scripted',
            '--session', str(session), '--print', '--mode', 'json']

    def invoke(name: str, prompt: str) -> None:
        phase['name'] = name
        previous = session.read_bytes() if session.exists() else b''
        result = subprocess.run([*argv, prompt], cwd=project, env=env, capture_output=True, timeout=120)
        (output / f'{name}-stdout.jsonl').write_bytes(result.stdout)
        (output / f'{name}-stderr.txt').write_bytes(result.stderr)
        assert result.returncode == 0, result.stderr.decode()
        assert not errors, errors
        assert session.read_bytes().startswith(previous), 'Native prefix changed'
        report['stages'].append(name)

    def receipts() -> list[dict]:
        return deduplicate_receipt_views([json.loads(p.read_text()) for p in Path(paths['runsDir']).rglob('learning-pipeline-receipt.json')])

    def body() -> str:
        private = Path(paths['harnessDir']) / NAME
        public = project / '.memory' / NAME
        assert private.read_bytes() == public.read_bytes(), 'Safe roots differ'
        return private.read_text()

    try:
        report['piVersion'] = subprocess.check_output([workspace_pi(REPO), '--version'], text=True).strip()
        assert report['piVersion'] == pi_version, 'Unexpected native Pi version'
        invoke('source-new', 'Update runtime.ts mode from old to new. Read and preserve its registry dependency, readiness boundary and release-only applicability.')
        assert not receipts()
        invoke('generation', '/memory 整理记忆')
        generated = body()
        assert generated == markdown('new') and receipts()[-1]['operations'] == 1
        (output / 'generated.md').write_text(generated)
        invoke('source-corrected', 'Correct runtime.ts mode from new to corrected. The registry dependency, readiness boundary and release-only applicability still apply.')
        assert source.read_text().splitlines()[0] == 'export const mode = "corrected";'
        assert body() == generated
        history = sorted((agent / 'memory/history' / paths['scopeKey']).glob('change_*.json'))
        before_history = {str(p): p.read_bytes() for p in history}
        invoke('description-only', '/memory 整理记忆')
        assert body() == generated, 'Description-only patch wrote stale knowledge'
        assert {str(p): p.read_bytes() for p in (agent / 'memory/history' / paths['scopeKey']).glob('change_*.json')} == before_history
        assert len(receipts()) == 2 and sum(r['operations'] for r in receipts()) == 1
        negative = [q for q in requests if q['phase'] == 'description-only']
        repairs = [i for i, q in enumerate(negative) if any(marker in message_text(q['body']) for marker in
                   ('Task: repair one rejected incremental Memory delta plan.', '"atomicKnowledgeContract"'))]
        assert len(repairs) == 1 and repairs[0] == len(negative) - 1, 'Unchanged body reached post-repair review'
        rejected = [json.loads(p.read_text()) for p in Path(paths['runsDir']).rglob('repair-response.json')]
        rejected = next(json.loads(item['output']) for item in rejected if 'corrected release mode' in item['output'])
        assert rejected['operations'][0]['content'].split('\n---\n', 1)[1] == generated.split('\n---\n', 1)[1]
        invoke('source-confirmation', 'Read runtime.ts again. Remember the corrected mode in the body, preserving the registry dependency, readiness boundary and release-only scope.')
        invoke('body-correction', '/memory 整理记忆')
        corrected = body()
        assert corrected == markdown('corrected') and corrected.split('\n---\n', 1)[1] != generated.split('\n---\n', 1)[1]
        assert all(fact in corrected for fact in RELATIONS) and 'mode = "new"' not in corrected
        assert len(receipts()) == 3 and sum(r['operations'] for r in receipts()) == 2
        (output / 'corrected.md').write_text(corrected)
        invoke('retrieval', 'Read the stored release knowledge. Report the current mode and the dependency, readiness boundary and applicability from its body.')
        assert body() == corrected and len(receipts()) == 3
        assert not (project / '.pi/harness.json').exists() and not (project / 'AGENTS.md').exists()
        report.update(status='passed', descriptionOnlyRejected=True, retainedBodyChanged=True,
                      relationsPreserved=list(RELATIONS), safeMirrorsEqual=True, laterNativeRead=True,
                      localRequests=len(requests), receipts=receipts())
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        report['sourceHashesAfter'] = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
        if report['sourceHashesAfter'] != report['sourceHashes']:
            report.update(status='failed', error='Source changed during native acceptance')
        report['localRequests'] = len(requests)
        report['fixtureErrors'] = errors
        report['receipts'] = receipts()
        (output / 'manifest.json').write_text(json.dumps(report, indent=2))
        (output / 'requests.json').write_text(json.dumps(requests, indent=2))
        server.shutdown(); server.server_close(); thread.join()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--pi-version', default='1.3.0')
    args = parser.parse_args()
    result = run(args.output.resolve(), pi_version=args.pi_version)
    print(json.dumps({key: result[key] for key in ('status', 'piVersion', 'stages', 'localRequests',
                                                 'paidRequests', 'externalRequests', 'learningBenefitEstablished')}))
