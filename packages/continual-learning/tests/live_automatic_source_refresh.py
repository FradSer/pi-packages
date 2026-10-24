"""Actual isolated Pi: old read -> edit -> automatic current-source collection.

Loopback judgments are controlled framing/mechanics evidence, never model learning
or semantic accuracy evidence. No external credentials or services are admitted.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import shlex
import shutil
import threading
import time

from live_acceptance_support import isolated_environment, workspace_pi, workspace_pnpm
from continuous_project_evidence import command_session_prefix_count, initialization_closure_ready, policy_initialization_bridge
from continuous_failure_retention import deduplicate_receipt_views
from live_learning_loop import controlled_memory_coverage_response, controlled_body_reference, controlled_knowledge_units, field, message_text, stream_response
from support import REPO, rule
from recovery_integrity import collect_surface_metadata, verify_command_recovery_delta


def run(output: Path, case: str = 'applied') -> dict:
    is_mixed=case.startswith('mixed-noop')
    is_manual_replay=case=='manual-coverage-replay'
    is_coverage_correction=case in ('coverage-correction','manual-initialization-repair')
    is_knowledge=case in ('manual-initialization-knowledge','manual-initialization-knowledge-repair','manual-initialization-knowledge-contract-repair','manual-initialization-knowledge-materialized-repair','manual-initialization-knowledge-citation-repair','manual-initialization-knowledge-held')
    is_knowledge_contract=case=='manual-initialization-knowledge-contract-repair'
    is_materialized_repair=case=='manual-initialization-knowledge-materialized-repair'
    is_knowledge_citation=case=='manual-initialization-knowledge-citation-repair'
    is_excerpt=is_knowledge or case in ('manual-initialization-excerpt','manual-initialization-excerpt-repair')
    is_initialization=is_excerpt or case in ('manual-initialization','manual-initialization-held','manual-initialization-repair')
    is_manual=is_initialization or case in ('manual-maintenance','manual-maintenance-held','manual-coverage-replay','manual-phase','manual-phase-held')
    is_manual_held=is_manual and case.endswith('-held')
    phase={'policy':False}
    policy_text='Permanent project constraint: Bash commands whose first executable is npm must be blocked; use pnpm instead.'
    output.mkdir(parents=True, exist_ok=False)
    project, agent = output/'project', output/'agent'
    project.mkdir(); agent.mkdir()
    if is_mixed or is_manual or case=='coverage-replay':subprocess.run(['git','init','-q',str(project)],check=True,capture_output=True,timeout=10)
    harness=project/'.pi/harness.json'
    harness_before=None
    if is_manual:
        harness.parent.mkdir()
        harness_before=json.dumps({'rules':[rule('manual-fixture')]}).encode()
        harness.write_bytes(harness_before)
    source = project/('packages/a/src/nested/runtime.ts' if case=='deep' else 'runtime.ts')
    source.parent.mkdir(parents=True,exist_ok=True)
    source.write_text('export const mode = "old";\n')
    if is_knowledge_citation:
        source.write_text(source.read_text()+'// '+1200*'x'+'\n// '+1200*'y'+'\n')
    expected_edited_source=source.read_text().replace('export const mode = "old";', 'export const mode = "new";')
    tracked = [REPO/'packages/continual-learning/extensions'/name for name in ('incremental-learning.ts','memory-maintenance-audit.ts','inject-memory.ts','learning-history.ts','jev-learning.ts','memory-review-consent.ts','consolidation-run.ts','independent-memory-partition.ts','jev-memory-predecessors.ts','jev-memory-relations.ts','jev-memory-readiness.ts','planner-prompts.ts','memory-body-review.ts','memory-knowledge-coverage.ts','learning-replay-feedback.ts','learning-replay.ts','learning-backlog.ts','learning-input.ts','learning-efficiency.ts','planner-json-output.ts','planner-output-schema.ts','source-excerpt-memory.ts')] + [Path(__file__),Path(__file__).with_name('memory-origin-harness.ts'),Path(__file__).with_name('live_learning_loop.py')]
    tracked.extend([Path(__file__).with_name('continuous_project_evidence.py'),Path(__file__).with_name('continuous_failure_retention.py')])
    if is_initialization:tracked.extend([Path(__file__).with_name('continuous-command-proof.ts'),Path(__file__).with_name('continuous-dossier-proof.mjs'),Path(__file__).with_name('continuous_failure_retention.py'),Path(__file__).with_name('recovery_integrity.py')])
    if is_initialization:
        package=REPO/'packages/continual-learning'
        tracked=sorted(set([*tracked,package/'index.ts',package/'package.json',
            *package.joinpath('extensions').rglob('*.ts'),*package.joinpath('prompts').glob('*.md'),
            *REPO.joinpath('packages/kit/src').rglob('*.ts'),
            Path(__file__).with_name('support.py'),Path(__file__).with_name('live_acceptance_support.py')]))
    source_hashes = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
    report = {'status':'failed','case':case,'outputDir':str(output),'sourceHashes':source_hashes,
        'externalRequests':0,'paidRequests':0,'semanticOrLearningBenefitEstablished':False}
    kinds: list[str] = []; requests: list[dict] = []; failures: list[str] = []
    limit='Scope: This mode convention applies to release checks only.'
    memory: Path
    runs: Path
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None: pass
        def do_POST(self) -> None:
            try:
                assert self.path in ('/v1/chat/completions','/jev/v1/systemone')
                raw = self.rfile.read(int(self.headers['Content-Length']))
                data = json.loads(raw)
                requests.append({'path':self.path,'hash':hashlib.sha256(raw).hexdigest(),'body':data})
                if self.path.startswith('/jev/'):
                    answers = {}
                    for key, question in data['questions'].items():
                        if question['type']=='noul':answers[key]={'type':'noul','noul':0.99 if key.startswith('supported_') or key==('harness' if phase['policy'] else 'memory') else 0.01}
                        elif question['type']=='score':answers[key]={'type':'score','score':3,'confidence':1,'legend':{str(i):str(i) for i in range(4)},'probabilities':{str(i):int(i==3) for i in range(4)}}
                        else:
                            labels=list(question['criteria']); label=next((x for x in ('independent','selfContained','compatible','grounded','consistent','unrelated') if x in labels),labels[0])
                            if labels==['true','false'] and key in ('memory','harness'):
                                label='true' if key==('harness' if phase['policy'] else 'memory') else 'false'
                            if key.startswith('coverage_'):
                                state=data.get('state',{})
                                missing=case in ('coverage-correction','coverage-invalid-correction','coverage-replay','manual-coverage-replay','manual-initialization-repair') and any(limit not in item.get('content','') for item in [*state['completeCurrentPlan']['operations'],*state['completeCurrentPlan'].get('newMemories',[])])
                                label=('material_missing' if missing else 'dismissed') if key.startswith('coverage_issue_') else ('missing' if missing else 'complete')
                            if case=='coverage-invalid-correction' and key=='supported_0' and 'coverage-correction' not in kinds:label='unsupported'
                            if case=='mixed-noop-uncertain' and key=='relation':label='unclear'
                            if is_mixed and key=='coherence_0' and len(data.get('state',{}).get('proposedMemoryOperations',[]))==2:label='unclear'
                            if (case=='held-later' or case=='origin-repair' and 'origin-repair' not in kinds) and key.startswith('supported_'):label='unsupported'
                            answers[key]={'type':'choice','choice':label,'confidence':1,'probabilities':{x:int(x==label) for x in labels}}
                            if is_manual_held and key=='coverage_plan':answers[key]['confidence']=0.79
                            if case=='coverage-citation-only' and (key.startswith('coverage_') or key=='counter_0_0'):
                                label,score,confidence=('complete',.81,.72) if key.startswith('coverage_') else ('compatible',.89,.83)
                                answers[key]={'type':'choice','choice':label,'confidence':confidence,
                                    'probabilities':{x:score if x==label else 1-score if x=='unclear' else 0 for x in labels}}
                            if case=='manual-initialization-repair' and 'coverage-correction' not in kinds and key in ('coherence_0','supported_0'):
                                # Replay observed score shapes only on this new loopback fixture.
                                # These answers are not a rejudgment of the failed real cohort.
                                label,score,confidence=('compatible',.62,.43) if key=='coherence_0' else ('unsupported',.54,.42)
                                answers[key]={'type':'choice','choice':label,'confidence':confidence,
                                    'probabilities':{x:score if x==label else 1-score if x=='unclear' else 0 for x in labels}}

                    body=json.dumps({'model':'jev-1.13.0','answers':answers,'usage':{'input_tokens':1,'output_tokens':1}}).encode()
                    self.send_response(200); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
                text = message_text(data)
                if 'Task: inspect current project source' in text:
                    user = next(m for m in data['messages'] if m.get('role')=='user')
                    content = user['content']
                    prompt = content if isinstance(content,str) else '\n'.join(b['text'] for b in content if b.get('type')=='text')
                    payload=json.loads(prompt.split('\n')[-1])
                    if is_manual and (not phase.get('backfill') or is_manual_replay):
                        assert payload['request']=='整理记忆'
                        assert payload['untrustedMemoryClaims']==([] if is_initialization else [{'name':'runtime.md','path':str(memory/'runtime.md'),'content':before,'sha256':hashlib.sha256(before.encode()).hexdigest()}])
                        assert payload['readScope']['roots']==[str(project)]
                        assert str(agent/'memory') in payload['readScope']['excludedPaths']
                        assert '.memory' in payload['readScope']['excludedComponents']
                    else:
                        assert payload['memoryFiles']==[] and payload['memoryIndex']==[] and payload['untrustedMemoryClaims']==[]
                        assert payload['readScope']['roots']==[]
                    assert payload['sourceIndex']['paths']==[str(source.relative_to(project))]
                    if not any(m.get('role')=='tool' for m in data['messages']):
                        kinds.append('source-read')
                        path=str(memory/'runtime.md') if case=='collector-refused' else str(source)
                        stream_response(self,[{'id':'source','name':'learning_read','arguments':{'path':path,'offset':1,'limit':200}}])
                    else:kinds.append('source-complete'); stream_response(self,'Current source observed.')
                elif '# Incremental Memory selector' in text:
                    kinds.append('selector'); stream_response(self,json.dumps({'kind':'incremental-memory-selection','version':1,'contextDigest':field(text,'Context digest'),'selected':[] if (is_initialization and not phase.get('backfill')) or case=='read-review' else ['runtime.md'],'memory':not phase['policy'] and case!='read-review','harness':phase['policy'],'agents':False,'reason':'Controlled source topic'}))
                elif 'harness-consolidation-plan' in text:
                    plan={'kind':'harness-consolidation-plan','version':1,'schemaVersion':1,**{k:field(text,k) for k in ('runId','scopeDigest','artifactHash')},'operations':[],'evidence':[],'report':[]}
                    if phase['policy']:
                        snapshot=json.loads((runs/plan['runId']/'snapshot.json').read_text())
                        indexes=[i for i,e in enumerate(snapshot['entries']) if e.get('message',{}).get('role')=='user' and policy_text in str(e['message'].get('content'))]
                        assert len(indexes)<=1,indexes
                        if indexes:
                            kinds.append('harness-create')
                            learned={'id':'auto-npm','bash':r'^npm(?:\s|$)','action':'block','message':'Block Bash commands whose first executable is npm; use pnpm.'}
                            plan['operations']=[{'op':'addRule','rule':learned,'cases':{'positive':[{'bash':'npm --version','expected':'block'},{'bash':'npm test','expected':'block'}],'negative':[{'bash':'pnpm test'},{'bash':'printf npm test'}]}}]
                            plan['evidence']=[{'index':indexes[0],'source':'user','quote':policy_text,'count':1}]
                        else:kinds.append('harness-noop')
                    else:kinds.append('harness-noop')
                    stream_response(self,json.dumps(plan))
                elif 'Review knowledge coverage, separately from internal consistency and source truth.' in text:
                    kinds.append('coverage')
                    payload=json.loads(text.split('\n')[-1]); answer=controlled_memory_coverage_response(text)
                    if case in ('coverage-correction','coverage-invalid-correction','coverage-replay','manual-coverage-replay','manual-initialization-repair'):
                        missing=any(limit not in target['content'] for target in payload['targets'])
                        condition={'statement':limit,'evidence':[{'ref':'e0.b0.l1'}],'bodyQuote':None if missing else limit}
                        for key,item in answer['reviews'].items():
                            target=payload['targets'][int(key)]
                            selected={**condition,'bodyQuote':controlled_body_reference(target['content'],limit,f'm{key}')} if not missing and target.get('bodyLocations') else condition
                            item['claims'][0]['conditions']=[selected]
                            item['uncovered']=[{'statement':limit,'evidence':[{'ref':'e0.b0.l1'}]}] if missing else []
                            item['verdict']='incomplete' if missing and case!='coverage-invalid-correction' else 'covered'
                        if missing:answer['plan']={'verdict':'incomplete','obligations':[{'basis':'requested','statement':limit,'evidence':[{'ref':'e0.b0.l1'}],'coveredBy':[],'status':'missing'}]}
                    stream_response(self,json.dumps(answer))
                elif 'Task: correct source citations for a frozen Memory candidate plan.' in text:
                    assert is_knowledge_citation
                    payload=json.loads(text.split('\n')[-1])
                    original=payload['repairCandidates'][0]['original']
                    valid=phase['validExcerptPlan']['newMemories'][0]
                    assert original['knowledge']['units']==valid['knowledge']['units']
                    assert 'same-length ordered source catalog' in text
                    assert any('knowledge.sourceCitations[2]' in error and 'maximumCharacters=2000' in error
                        for error in payload['errors']), payload['errors']
                    kinds.append('excerpt-structural-correction')
                    stream_response(self,json.dumps({'kind':'incremental-memory-amendment','version':1,**payload['identity'],
                        'replacements':[{'candidateId':payload['repairCandidates'][0]['candidateId'],
                            'evidence':valid['knowledge']['sourceCitations']}]}))
                elif 'Task: repair one rejected incremental Memory delta plan.' in text or '"atomicKnowledgeContract"' in text:
                    payload=json.loads(text.split('\n')[-1])
                    patches=[]
                    if is_excerpt:
                        if is_knowledge_contract:
                            assert any('newMemories[0] requires knowledge or a private sourceExcerpt' in error
                                for error in payload['errors']), payload['errors']
                        kinds.append('excerpt-structural-correction')
                        corrected=phase['validExcerptPlan']
                        if is_materialized_repair:
                            corrected=json.loads(json.dumps(payload['rejectedPlan']))
                            assert 'content' in corrected['newMemories'][0] and 'knowledge' not in corrected['newMemories'][0]
                            assert corrected.pop('unsupportedControlledField') is True
                        stream_response(self,json.dumps(corrected))
                        return
                    if case=='manual-initialization-repair':
                        errors=payload['errors']
                        assert len(errors)<=16 and all(len(line)<=800 for line in errors)
                        joined='\n'.join(errors)
                        assert 'observed-check=coherence_0; choice=compatible; probability=0.62; confidence=0.43' in joined
                        assert 'observed-check=supported_0; choice=unsupported; probability=0.54; confidence=0.42' in joined
                        assert 'Check the original source before removing a draft condition that lacks a selected citation' in text
                        assert 'If that source establishes the condition, retain it and add the matching original source citation' in text
                        assert 'Correct or remove a condition when the original evidence establishes that it is false or obsolete' in text
                        assert 'Before emitting the patch, compare its applicability with the rejected record and the complete source' in text
                        assert 'Correct only unsupported claims' not in joined, 'Parent still instructs unsupported-only correction'
                        assert 'Remove uncited source-layout' not in joined, 'Parent still orders deletion for missing citations'
                        assert 'Source-supported missing conditions may be added' in joined, 'Missing enabled-field omission correction policy'
                        assert 'Missing selected citations alone do not make a claim false' in joined, 'Missing source-first citation policy'
                        report['scopeRepairParentDiagnosticsAgree']=True
                        report['sourceBoundScopeRepairGuidanceDelivered']=True
                        report['distinctRepairObservationsDelivered']=True
                    if case=='coverage-citation-only':
                        kinds.append('coverage-correction')
                        snapshot=payload['semanticContext']['frozenEvidence']
                        refs=[line['ref'] for e in snapshot['entries'] for block in e.get('entry',{}).get('message',{}).get('content',[]) if isinstance(block,dict)
                            for line in block.get('citationLines',{}).get('lines',[]) if line.get('text')=='export const mode = "new";' and line.get('ref')]
                        assert len(refs)==1,refs
                        patches=[{'candidateId':payload['repairCandidates'][0]['candidateId'],'evidence':[{'ref':refs[0]},{'ref':'e0.b0.l1'}]}]
                    elif case in ('coverage-correction','coverage-invalid-correction','coverage-replay','manual-coverage-replay','manual-initialization-repair'):
                        kinds.append('coverage-correction')
                        if case in ('coverage-correction','coverage-replay','manual-coverage-replay','manual-initialization-repair'):
                            assert payload['repairableFields']['runtime.md']==['body','description'],payload['repairableFields']
                            assert payload['requiredTextChanges']['runtime.md']==['body']
                            assert payload['independentKnowledgeCoverage']['independentSemanticChecks']['planPassed'] is False
                        else:
                            assert 'body' in payload['repairableFields']['runtime.md']
                            assert not payload.get('independentKnowledgeCoverage')
                        snapshot=payload['semanticContext']['frozenEvidence']
                        refs=[line['ref'] for e in snapshot['entries'] for block in e.get('entry',{}).get('message',{}).get('content',[]) if isinstance(block,dict)
                            for line in block.get('citationLines',{}).get('lines',[]) if line.get('text')=='export const mode = "new";' and line.get('ref')]
                        assert len(refs)==1,refs
                        content=[*payload['rejectedPlan']['operations'],*payload['rejectedPlan']['newMemories']][0]['content']+limit+'\n'
                        patches=[] if case in ('coverage-replay','manual-coverage-replay') else [{'candidateId':payload['repairCandidates'][0]['candidateId'],'content':content,'evidence':[{'ref':refs[0]},{'ref':'e0.b0.l1'}]}]
                    elif case=='origin-repair':
                        kinds.append('origin-repair')
                        assert payload['historicalMemoryOrigins'][0]['transactions'][0]['snapshot']['entries'][0]['content'][0]['text']=='Remember the currently observed contract for future maintenance.'
                        snapshot=payload['semanticContext']['frozenEvidence']
                        refs=[line['ref'] for e in snapshot['entries'] for block in e.get('entry',{}).get('message',{}).get('content',[]) if isinstance(block,dict)
                            for line in block.get('citationLines',{}).get('lines',[]) if line.get('text')=='export const mode = "new";' and line.get('ref')]
                        assert len(refs)==1,refs
                        content='---\nname: runtime\ndescription: runtime.ts declares mode new\ntype: project\n---\nObserved source in runtime.ts: `export const mode = "new";`.\n'
                        patches=[{'candidateId':payload['repairCandidates'][0]['candidateId'],'content':content,'evidence':[{'ref':refs[0]}]}]
                    else:kinds.append('repair-no-correction')
                    if payload.get('atomicKnowledgeContract'):
                        patches=[{**{k:v for k,v in patch.items() if k not in ('content','evidence')},
                                  'knowledge':controlled_knowledge_units(patch['content'],patch['evidence'])} if 'content' in patch else patch for patch in patches]
                    stream_response(self,json.dumps({'kind':'incremental-memory-amendment','version':1,**payload['identity'],'replacements':patches}))
                elif 'incremental-memory-plan' in text:
                    kinds.append('plan')
                    snapshot=json.loads((runs/field(text,'runId')/'snapshot.json').read_text())
                    index=next(i for i,e in enumerate(snapshot['entries']) if e.get('message',{}).get('details',{}).get('readOnlyMaintenanceAudit'))
                    if case in ('source-changed','mixed-noop-source-race'):source.write_text('export const mode = "raced";\n')
                    content='---\nname: runtime\ndescription: runtime.ts declares mode new\ntype: project\n---\nObserved source in runtime.ts: `export const mode = "new";`.\n'
                    if is_initialization and phase.get('backfill'):
                        content=(memory/'runtime.md').read_text()
                    if case=='manual-initialization-repair' and phase.get('backfill') and limit not in content:content+=limit+'\n'
                    if case in ('coverage-replay','manual-coverage-replay') and 'replay-start' in kinds:
                        dossiers=[json.loads(p.read_text()) for p in runs.glob('*/incremental-learning-dossier.json')]
                        dossier=next(d for d in dossiers if d.get('memoryReplayFeedback',{}).get('rejectedCoverageQuestions'))
                        feedback=dossier['memoryReplayFeedback']; questions=feedback['rejectedCoverageQuestions']
                        assert questions and all(q['purpose']=='rejected-questions-only' for q in questions)
                        assert all(q['checks'] and all('probabilities' in c for c in q['checks']) for q in questions)
                        assert any(limit in str(q['occurrences']) for q in questions)
                        assert all(q.get('planAccount') and q.get('recordAccounts') for q in questions)
                        assert any(claim.get('conditions') for q in questions for account in q['recordAccounts'] for claim in account['claims']), 'Parent-child condition relationships were dropped'
                        inline_start='Use every original indexed entry and selected predecessor body without repository exploration.\n\n'
                        wire_dossier=json.loads(text.split(inline_start,1)[1].split('\n\nEnd of complete Learning Dossier.',1)[0])
                        assert wire_dossier['memoryReplayFeedback']==feedback, 'Complete rejected account relationships did not reach actual wire'
                        assert limit in text, 'Historical omission did not reach the actual planner wire'
                        kinds.append('replay-questions-delivered')
                        content+=limit+'\n'
                    if case=='origin-repair':content=content.replace('mode new','mode old').replace('mode = "new"','mode = "old"')
                    plan={'kind':'incremental-memory-plan','version':1,'schemaVersion':1,**{k:field(text,k) for k in ('runId','scopeKey','scopeDigest','artifactHash','snapshotDigest')},'operations':[{'name':'runtime.md','kind':'rewrite','classification':'safe','content':content,'evidence':[{'ref':f'e{index}.b0.l1'}]}],'newMemories':[]}
                    if is_initialization and not phase.get('backfill'):
                        operation=plan['operations'].pop()
                        plan['newMemories']=[{'name':operation['name'],'kind':'project','classification':operation['classification'],
                            'description':'runtime.ts declares mode new',
                            'knowledge':controlled_knowledge_units(operation['content'],operation['evidence'])}]
                        if is_excerpt:
                            plan['newMemories']=[{'name':'runtime.md','kind':'project','classification':'private',
                                'sourceExcerpt':{'ref':f'e{index}.b0.l1'},'evidence':[{'ref':f'e{index}.b0.l1'}]}]
                            if is_knowledge:
                                assert 'sourceCitationIndex' in text
                                plan['newMemories']=[{'name':'runtime.md','kind':'project','classification':'safe',
                                    'description':'runtime.ts declares mode new','knowledge':{
                                        'sourceCitations':[{'ref':f'e{index}.b0.l1'}],
                                        'units':[{'sourceCitationIndex':0},{'text':'Why: Retain the inspected runtime mode.\n\nHow to apply: Refer to this source observation when maintaining runtime.ts.',
                                            'citationIndexes':[0]}]}}]
                            if is_knowledge_citation:
                                knowledge=plan['newMemories'][0]['knowledge']
                                knowledge['sourceCitations']=[dict(knowledge['sourceCitations'][0]) for _ in range(3)]
                                knowledge['units'][0]['sourceCitationIndex']=2
                                knowledge['units'][1]['citationIndexes']=[0,1,2]
                            phase['validExcerptPlan']=json.loads(json.dumps(plan))
                            if case.endswith('-repair'):
                                if is_materialized_repair:
                                    plan['unsupportedControlledField']=True
                                elif is_knowledge_contract:
                                    plan['newMemories']=[{**operation,'kind':'project'}]
                                elif is_knowledge_citation:
                                    plan['newMemories'][0]['knowledge']['sourceCitations'][2]['endRef']=f'e{index}.b0.l3'
                                elif is_knowledge:plan['newMemories'][0]['knowledge']['units'][0]['unknownField']='invalid controlled initial shape'
                                else:plan['newMemories'][0]['sourceExcerpt']['unknownField']='invalid controlled initial shape'
                    if is_mixed:
                        plan['operations'][0]['content']=before
                        plan['newMemories']=[{'name':'mode-value.md','kind':'project','classification':'safe',
                            'description':'runtime.ts declares mode new',
                            'knowledge':controlled_knowledge_units(content,[{'ref':f'e{index}.b0.l1'}])}]
                    stream_response(self,json.dumps(plan))
                elif 'Review each complete candidate Memory below' in text:
                    kinds.append('body')
                    targets=json.loads(text.split('\n')[-1])['targets'] if is_mixed else [{'targetIndex':0}]
                    stream_response(self,json.dumps({'reviews':{str(t['targetIndex']):{'verdict':'consistent','conflictingQuotes':[],'reason':'Controlled framing only'} for t in targets}}))
                else:
                    tools=[m for m in data['messages'] if m.get('role')=='tool']
                    if phase.get('probe'):
                        if not tools:stream_response(self,[{'id':'owned-npm-block','name':'bash','arguments':{'command':'npm --version'}}])
                        elif len(tools)==1:stream_response(self,[{'id':'pnpm-allowed','name':'bash','arguments':{'command':'pnpm --version'}}])
                        else:stream_response(self,'Policy execution observed.')
                    elif phase['policy']:kinds.append('policy-main-complete'); stream_response(self,'Policy noted.')
                    elif case=='read-review' and not tools:
                        kinds.append('main-memory-read'); stream_response(self,[{'id':'memory-read','name':'read','arguments':{'path':str(memory/'runtime.md')}}])
                    elif len(tools)==(1 if case=='read-review' else 0):kinds.append('main-old-read'); stream_response(self,[{'id':'old-read','name':'read','arguments':{'path':str(source)}}])
                    elif len(tools)==(2 if case=='read-review' else 1):kinds.append('main-edit'); stream_response(self,[{'id':'actual-edit','name':'edit','arguments':{'path':str(source),'oldText':'export const mode = "old";','newText':'export const mode = "new";'}}])
                    elif case=='renamed' and len(tools)==2:
                        kinds.append('main-write-temporary');stream_response(self,[{'id':'temporary-write','name':'write','arguments':{'path':str(project/'temporary.ts'),'content':'export const temporary = true;\n'}}])
                    elif case=='renamed' and len(tools)==3:
                        kinds.append('main-rename');stream_response(self,[{'id':'actual-rename','name':'bash','arguments':{'command':'mv -- '+shlex.quote(str(project/'temporary.ts'))+' '+shlex.quote(str(project/'renamed.ts'))}}])
                    else:kinds.append('main-complete'); stream_response(self,'Updated the declaration.')
            except Exception as error:
                failures.append(str(error)); self.send_error(500,'Controlled fixture failure')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    env=isolated_environment(output/'home',agent)
    if is_initialization:
        cli=workspace_pnpm(REPO)
        node=shutil.which('node')
        assert node, 'Workspace Node runtime is unavailable'
        fixture_bin=output/'bin';fixture_bin.mkdir()
        launcher=fixture_bin/'pnpm'
        launcher.write_text('#!/bin/sh\nCOREPACK_ENABLE_NETWORK=0 NODE_DISABLE_COMPILE_CACHE=1 exec '+shlex.quote(node)+' '+shlex.quote(cli)+' "$@"\n')
        launcher.chmod(0o700)
        env['PATH']=str(fixture_bin)+os.pathsep+env.get('PATH','')
    env.update(TYPESAFE_BASE_URL=f'http://127.0.0.1:{server.server_port}/jev',TYPESAFE_API_KEY='offline-fixture')
    (agent/'settings.json').write_text(json.dumps({'packages':[],'quietStartup':True,'defaultThinkingLevel':'off','retry':{'enabled':False}}))
    (agent/'memory').mkdir(); (agent/'memory/settings.json').write_text(json.dumps({'autoMemory':not is_manual,'automaticPhases':{'memory':'off' if is_manual else 'apply','harness':'apply' if case in ('legacy','held-later','mixed-noop') else 'off','agents':'off'}}))
    (agent/'continual-learning.json').write_text(json.dumps({'jev':{'enabled':case!='legacy','model':'jev-1.13.0','allowPrivateMemory':True,'requestConcurrency':1,**({'scopes':['memory']} if case=='read-review' else {})}}))
    (agent/'memory.json').write_text('{"provider":"fixture","model":"scripted"}')
    (agent/'models.json').write_text(json.dumps({'providers':{'fixture':{'baseUrl':f'http://127.0.0.1:{server.server_port}/v1','api':'openai-completions','apiKey':'offline-fixture','models':[{'id':'scripted','reasoning':False,'input':['text'],'contextWindow':200000,'maxTokens':4096,'cost':{'input':0,'output':0,'cacheRead':0,'cacheWrite':0}}]}}}))
    code='import {resolveMemoryPaths} from '+json.dumps(str(REPO/'packages/continual-learning/extensions/memory-paths.ts'))+';console.log(JSON.stringify(resolveMemoryPaths(process.argv[1])));'
    paths=json.loads(subprocess.check_output(['node','--import','tsx','--input-type=module','-e',code,str(project)],cwd=REPO,env=env,text=True))
    runs=Path(paths['runsDir']); memory=Path(paths['harnessDir']); memory.mkdir(parents=True)
    def history_state() -> dict:
        metadata=collect_surface_metadata(memory,project)
        surfaces={}
        for key,value in metadata.items():
            target=memory/key[len('private/'):] if key.startswith('private/') else project/key[len('project/'):]
            raw=target.read_bytes()
            assert hashlib.sha256(raw).hexdigest()==value['digest']
            surfaces[key]={**value,'bytes':base64.b64encode(raw).decode()}
        assert metadata==collect_surface_metadata(memory,project),'Surface identity changed during native capture'
        history=[json.loads(p.read_text()) for p in (agent/'memory/history'/paths['scopeKey']).glob('change_*.json')]
        receipts=deduplicate_receipt_views([json.loads(p.read_text()) for p in runs.rglob('learning-pipeline-receipt.json')])
        return {'surfaceSnapshots':surfaces,'history':history,'attempts':[],'receipts':receipts}
    before='---\nname: runtime\ndescription: runtime.ts declares mode old\ntype: project\n---\nObserved source in runtime.ts: `export const mode = "old";`.\n'
    if is_mixed:before='---\nname: runtime\ndescription: runtime.ts exports a mode constant\ntype: project\n---\nruntime.ts exports a mode constant.\n'
    if case in ('origin','origin-repair'):
        code='import {fixture} from '+json.dumps(str(REPO/'packages/continual-learning/tests/memory-origin-harness.ts'))+';await fixture("native-origin",1,"safe",false,false,JSON.parse(process.argv[1]));'
        subprocess.run(['bun','-e',code,json.dumps({'cwd':str(project),'name':'runtime.md','content':before,'sourceText':source.read_text()})],cwd=REPO,env=env,check=True,capture_output=True,timeout=30)
    elif not is_initialization:(memory/'runtime.md').write_text(before)
    if is_mixed or is_manual and not is_initialization:
        (project/'.memory').mkdir()
        (project/'.memory/runtime.md').write_text(before)
    noop_before={str(p):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'inode':p.stat().st_ino,'mtimeNs':p.stat().st_mtime_ns} for p in [memory/'runtime.md',project/'.memory/runtime.md'] if p.exists()}
    (memory/'MEMORY.md').write_text('# Project memories\n'+('' if is_initialization else '\n- runtime.md — runtime.ts declares mode old\n'))
    session=agent/'sessions'/'fixture'/'session.jsonl' if is_manual or case=='coverage-replay' else output/'session.jsonl'
    session.parent.mkdir(parents=True,exist_ok=True)
    command=[workspace_pi(REPO),'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-approve','--thinking','off','--tools','read,edit,write,bash' if case=='renamed' else 'read,edit','-e',str(REPO/'packages/continual-learning/index.ts'),'--model','fixture/scripted','--session',str(session),'--print','--mode','json','Update runtime.ts mode from old to new.'+(' Do not edit Memory directly; automatic learning owns it. Never remember temporary tokens.' if case.startswith('manual-phase') else '')+(' Keep the learned mode convention scoped to release checks.' if case in ('coverage-correction','coverage-invalid-correction','coverage-replay','manual-coverage-replay','manual-initialization-repair') else '')+(' Add a regression test for onIdle.' if case=='legacy' else ' Never run the retired compiler in future tasks.' if case in ('held-later','mixed-noop') else '')]
    backlog_code='import {backlogStatus,readBacklog,backlogIdentity} from '+json.dumps(str(REPO/'packages/continual-learning/extensions/learning-backlog.ts'))+';const read=readBacklog(process.argv[1],process.argv[2]);console.log(JSON.stringify({...backlogStatus(process.argv[1],process.argv[2]),pendingEntries:read.pendingEntries.map(({entry})=>({...entry,id:backlogIdentity(process.argv[3],entry)}))}));'
    def backlog_status() -> dict:
        return json.loads(subprocess.check_output(['node','--import','tsx','--input-type=module','-e',backlog_code,str(project),str(agent),paths['scopeKey']],cwd=REPO,env=env,text=True))
    try:
        report['piVersion']=subprocess.check_output([workspace_pi(REPO),'--version'],cwd=project,env=env,text=True,timeout=10).strip()
        assert report['piVersion']=='1.3.0',report['piVersion']
        result=subprocess.run(command,cwd=project,env=env,capture_output=True,timeout=90)
        (output/'stdout.jsonl').write_bytes(result.stdout); (output/'stderr.txt').write_bytes(result.stderr)
        assert result.returncode==0,result.stderr.decode()
        assert not failures,failures
        if is_manual:
            assert source.read_text()==expected_edited_source, 'Ordinary edit did not succeed'
            assert not list(runs.rglob('learning-pipeline-receipt.json')),kinds
            assert not any(k in kinds for k in ('source-read','selector','plan','body','coverage')),kinds
            assert (not (memory/'runtime.md').exists()) if is_initialization else (memory/'runtime.md').read_text()==before
            assert harness.read_bytes()==harness_before
            original_session=session.read_bytes()
            original_digest=hashlib.sha256(original_session).hexdigest()
            original_count=command_session_prefix_count(original_session,original_digest,str(project.resolve()))
            (output/'ordinary-session.jsonl').write_bytes(original_session)
            if is_manual_replay:
                ordinary_backlog=backlog_status()
                assert ordinary_backlog['pending']==1 and not ordinary_backlog['pendingEntries'][0].get('manualRequest'),ordinary_backlog
                (output/'ordinary-backlog.json').write_text(json.dumps(ordinary_backlog,indent=2))
            kinds.append('manual-maintenance-start')
            maintenance_command='/memory 整理记忆'
            maintenance_argv=[*command[:-1],maintenance_command]
            if is_initialization:
                owner={'kind':'native-memory-command','version':1,'argv':maintenance_argv,
                    'cwd':str(project.resolve()),'agentDir':str(agent.resolve()),'sessionPath':str(session.resolve()),
                    'model':'fixture/scripted','piVersion':report['piVersion'],'arguments':'整理记忆',
                    'priorSessionDigest':original_digest,'startedAt':time.time_ns()//1_000_000,
                    'sourceHashes':{str(source.relative_to(project)):hashlib.sha256(source.read_bytes()).hexdigest()},
                    'sourceFiles':{str(source.relative_to(project)):{'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'mode':source.stat().st_mode&0o777,'size':source.stat().st_size}}}
                owner_text=json.dumps(owner,ensure_ascii=False,separators=(',',':'))
                (output/'memory-command-started.json').write_text(owner_text)
                before_command=history_state()
                (output/'before-memory-command-state.json').write_text(json.dumps(before_command,indent=2))
            second=subprocess.run(maintenance_argv,cwd=project,env=env,capture_output=True,timeout=90)
            (output/'maintenance-stdout.jsonl').write_bytes(second.stdout)
            (output/'maintenance-stderr.txt').write_bytes(second.stderr)
            if is_initialization:
                completion={'ownerDigest':hashlib.sha256(owner_text.encode()).hexdigest(),'exitCode':second.returncode,
                    'cancelled':False,'timedOut':False,'settledAt':time.time_ns()//1_000_000,
                    'stdoutDigest':hashlib.sha256(second.stdout).hexdigest(),
                    'sessionDigest':hashlib.sha256(session.read_bytes()).hexdigest(),
                    'sourceHashes':{str(source.relative_to(project)):hashlib.sha256(source.read_bytes()).hexdigest()},
                    'sourceFiles':{str(source.relative_to(project)):{'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'mode':source.stat().st_mode&0o777,'size':source.stat().st_size}}}
                (output/'memory-command-closed.json').write_text(json.dumps(completion,indent=2))
            assert second.returncode==0,second.stderr.decode()
            assert not failures,failures
            assert session.read_bytes().startswith(original_session),'Explicit command changed original native session'
            assert harness.read_bytes()==harness_before
            assert 'harness-noop' not in kinds
            if case.startswith('manual-phase'):
                # Actual handler provenance, checked separately from controlled verdicts.
                native_rows=[json.loads(line) for line in session.read_text().splitlines() if line.strip()]
                markers=[row for row in native_rows if row.get('type')=='custom' and row.get('customType')=='continual-learning-memory-request']
                assert len(markers)==1,markers
                marker=markers[0]['data']
                snapshot_files=sorted(runs.glob('*/snapshot.json'))
                snapshots=[(path,json.loads(path.read_text())) for path in snapshot_files]
                bound=[(path,snapshot) for path,snapshot in snapshots if snapshot.get('currentMemoryCommandPhase')]
                assert len(bound)>=2,[(str(path),snapshot.get('runId')) for path,snapshot in snapshots]
                def js_digest(value: object) -> str:
                    return hashlib.sha256(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
                phases={}
                for path,snapshot in bound:
                    captured=snapshot['currentMemoryCommandPhase']; index=captured['requestEntryIndex']
                    assert captured['origin']=='current-handler' and captured['command']=='memory'
                    assert captured['invocationId']==marker['invocationId']
                    assert captured['sessionId']==marker['sessionId']
                    assert captured['scopeKey']==paths['scopeKey']==snapshot['scopeKey']
                    assert captured['runId']==snapshot['runId']
                    assert captured['arguments']==marker['request']=='整理记忆'
                    assert snapshot['entries'][index]=={'type':'message','message':{'role':'user','content':'整理记忆'}}
                    assert captured['requestEntryDigest']==js_digest(snapshot['entries'][index])
                    assert captured['taskEntriesDigest']==js_digest(snapshot['entries'][:index+1])
                    assert captured['sourceEntriesDigest']==js_digest(snapshot['entries'])
                    assert any('Do not edit Memory directly; automatic learning owns it.' in str(entry.get('message',{}).get('content')) for entry in snapshot['entries'][:index])
                    assert any('Never remember temporary tokens.' in str(entry.get('message',{}).get('content')) for entry in snapshot['entries'][:index])
                    phases[captured['runId']]=captured
                accounts=[];jev=[]
                for request in requests:
                    if request['path'].startswith('/jev/'):
                        body=request['body'];state=body.get('state',{})
                        if 'coverage_plan' in body.get('questions',{}):
                            captured=state['currentMemoryCommandPhase']
                            assert captured==phases[captured['runId']]
                            assert captured==state['originalEvidence']['currentMemoryCommandPhase']
                            assert all(q['instructions'].count('currentMemoryCommandPhase binds')==1 for q in body['questions'].values())
                            jev.append(request['hash'])
                    else:
                        text=message_text(request['body'])
                        if 'Review knowledge coverage, separately from internal consistency and source truth.' in text:
                            payload=json.loads(text.split('\n')[-1]);captured=payload['currentMemoryCommandPhase']
                            assert captured==phases[captured['runId']]
                            assert captured==payload['frozenEvidence']['currentMemoryCommandPhase']
                            assert 'Content-specific no-remember, temporary-only and privacy restrictions' in text
                            accounts.append(request['hash'])
                assert accounts and jev,(accounts,jev,kinds)
                report['nativeCommandPhaseProof']={'nativeMarkerEntryId':markers[0]['id'],'invocationId':marker['invocationId'],
                    'sessionId':marker['sessionId'],'snapshotBindings':[{'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'runId':snapshot['runId'],'phase':snapshot['currentMemoryCommandPhase']} for path,snapshot in bound],
                    'accountWireHashes':accounts,'jevCoverageWireHashes':jev,'originalNativePrefixPreserved':True,
                    'sourceRestrictionsPreserved':True,'automaticLearningEnabled':False,
                    'externalRequests':0,'paidRequests':0,'semanticOrLearningBenefitEstablished':False}
            report['manualMaintenance']={'command':maintenance_command,'automaticLearningEnabled':False,
                'ordinaryTaskLearningReceipts':0,'harnessUnchanged':True,
                'initialKnowledgeEntries':0 if is_initialization else 1,'dependentHarnessStarted':False,
                'originalSessionDigest':original_digest,'originalSessionEntryCount':original_count,
                'originalNativePrefixPreserved':True,
                'originalMemoryPreserved':not (memory/'runtime.md').exists() if is_initialization else (memory/'runtime.md').read_text()==before,
                'bothRootsMatch':(project/'.memory/runtime.md').is_file() and (memory/'runtime.md').read_bytes()==(project/'.memory/runtime.md').read_bytes()}
        receipts=deduplicate_receipt_views([json.loads(p.read_text()) for p in runs.rglob('learning-pipeline-receipt.json')])
        assert len(receipts)==1,(kinds,receipts)
        receipt=receipts[0]
        rows=[json.loads(line) for line in session.read_text().splitlines() if line.strip()]
        delivered=[r['details'] for r in rows if r.get('type')=='custom_message' and r.get('customType')=='continual-learning-result']
        assert delivered and delivered[-1]==receipt, 'Receipt identity differs from actual session result'
        if is_initialization:
            generation=[p for p in [*runs.rglob('memory-task-usage.json'),*runs.rglob('memory-repair-usage-*.json')] if json.loads(p.read_text())['ledgerId'] in
                {a.get('usageLedgerId') for a in receipt['attempts'] if a.get('phase')=='memory' and a.get('operations',0)>0}]
            # A held command intentionally has no approved generation binding.
            audit_receipts=list(runs.rglob('maintenance-audit-*/receipt.json'))
            assert len(audit_receipts)==1,audit_receipts
            audit_dir=audit_receipts[0].parent
            proof_input={'kind':'explicit-command-source-review','version':1,'owner':owner,'completion':completion,
                'originalSession':original_session.decode(),'nativeSession':session.read_text(),'stdout':second.stdout.decode(),
                'receipt':receipt,'sources':{str(source.relative_to(project)):source.read_text()}}
            if generation:
                assert len(generation)==1,generation
                root=generation[0].parent
                proof_input.update(plan=json.loads((root/'plan.json').read_text()),snapshotText=(root/'snapshot.json').read_text(),
                    reviewManifest=json.loads((root/'manifest.json').read_text()),usageLedger=json.loads(generation[0].read_text()),
                    initialUsageLedger=json.loads((root/'memory-task-usage.json').read_text()),appliedUsageLedgerFile=generation[0].name,
                    sourceAudit={'receipt':json.loads(audit_receipts[0].read_text()),
                        'usageLedger':json.loads((audit_dir/'source-audit-usage.json').read_text()),
                        'observations':[json.loads(line) for line in (audit_dir/'observations.jsonl').read_text().splitlines()]})
            proof_path=output/'command-source-input.json';proof_path.write_text(json.dumps(proof_input,ensure_ascii=False))
            code='import fs from "node:fs";import {createHash} from "node:crypto";import {commandMemorySourceProof as check} from '+json.dumps(str(REPO/'packages/continual-learning/tests/continuous-command-proof.ts'))+''';
const input=JSON.parse(fs.readFileSync(process.argv[1],"utf8"));const negative={};
const digest=v=>createHash("sha256").update(JSON.stringify(v)).digest("hex");
const mutate=(name,fn)=>{const changed=structuredClone(input);fn(changed);negative[name]=check(changed);};
mutate("foreign-kind",x=>x.kind="completed-replay");
mutate("missing-owner",x=>delete x.owner);
mutate("changed-prefix",x=>x.originalSession=x.originalSession.replace("Update runtime.ts","Changed runtime.ts"));
mutate("partial-jsonl",x=>x.originalSession=x.originalSession.slice(0,-1));
mutate("owner-args-drift",x=>x.owner.arguments="remember something else");
mutate("rehashed-args-drift",x=>{x.owner.arguments="remember something else";x.owner.argv[x.owner.argv.length-1]="/memory "+x.owner.arguments;x.completion.ownerDigest=digest(x.owner);});
mutate("receipt-drift",x=>x.receipt.batchId+="foreign");
mutate("cancelled",x=>x.completion.cancelled=true);
mutate("held",x=>x.receipt.operations=0);
if(input.plan){
 if(input.initialUsageLedger){
  mutate("original-generation-usage-drift",x=>x.initialUsageLedger.knownUsage.input+=1);
 }
 if(input.appliedUsageLedgerFile?.startsWith("memory-repair-usage-")){
  mutate("missing-original-generation-ledger",x=>delete x.initialUsageLedger);
  mutate("foreign-repair-ledger-file",x=>x.appliedUsageLedgerFile="memory-task-usage.json");
 }
 mutate("generation-usage-drift",x=>x.usageLedger.knownUsage.input+=1);
 mutate("source-usage-drift",x=>x.sourceAudit.usageLedger.knownUsage.input+=1);
 mutate("source-body-drift",x=>x.sources["runtime.ts"]+="// changed\\n");
 mutate("source-read-drift",x=>x.sourceAudit.observations[0].result+=" changed");
 mutate("source-outside-root",x=>x.sourceAudit.observations[0].path="/outside/runtime.ts");
 mutate("missing-native-receipt",x=>{x.nativeSession=x.originalSession;x.completion.sessionDigest=createHash("sha256").update(x.nativeSession).digest("hex");});
 mutate("rehashed-projection-drift",x=>{const s=JSON.parse(x.snapshotText);s.entries[0].message.content="Altered original task";x.snapshotText=JSON.stringify(s);const h=createHash("sha256").update(x.snapshotText).digest("hex");x.reviewManifest.snapshotDigest=h;x.plan.snapshotDigest=h;x.plan.artifactHash=h;});
}
console.log(JSON.stringify({proof:check(input),negative}));'''
            checked=json.loads(subprocess.check_output(['node','--import','tsx','--input-type=module','-e',code,str(proof_path)],cwd=REPO,env=env,text=True,timeout=30))
            report['commandSourceReview']=checked['proof'];report['commandSourceReviewNegatives']=checked['negative']
            assert checked['proof']['ready'] is (not is_manual_held),checked
            assert all(not result['ready'] for result in checked['negative'].values()),checked
            after_command=history_state()
            (output/'after-memory-command-state.json').write_text(json.dumps(after_command,indent=2))
            report['commandHistoryIntegrity']=verify_command_recovery_delta(before_command,after_command,receipt)
            assert report['commandHistoryIntegrity']['passed'] is (not is_manual_held),report['commandHistoryIntegrity']
            corpus_state={**after_command,'memoryEntries':[{'filename':p.name,'content':p.read_text(),
                'revision':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(memory.glob('*.md')) if p.name!='MEMORY.md']}
            corpus_path=output/'command-corpus-state.json';corpus_path.write_text(json.dumps({'prior':before_command,'current':corpus_state}))
            code='import fs from "node:fs";import {commandMemoryCorpusProof as check} from '+json.dumps(str(REPO/'packages/continual-learning/tests/continuous-command-proof.ts'))+''';
const input=JSON.parse(fs.readFileSync(process.argv[1],"utf8"));const state=JSON.parse(fs.readFileSync(process.argv[2],"utf8"));
const negative={};const mutate=(name,fn)=>{const i=structuredClone(input),s=structuredClone(state);fn(i,s);negative[name]=check(i,s.prior,s.current);};
if(state.current.memoryEntries.length){
 mutate("missing-corpus",(i,s)=>s.current.memoryEntries=[]);
 mutate("body-drift",(i,s)=>s.current.memoryEntries[0].content+=" changed");
 mutate("count-drift",i=>i.receipt.operations+=1);
 if(input.plan.newMemories[0].classification==='private'){
  mutate("private-public-copy",(i,s)=>s.current.surfaceSnapshots["project/.memory/runtime.md"]=structuredClone(s.current.surfaceSnapshots["private/runtime.md"]));
 }else{mutate("missing-public-copy",(i,s)=>delete s.current.surfaceSnapshots["project/.memory/runtime.md"]);}
 mutate("missing-history",(i,s)=>s.current.history=[]);
 mutate("foreign-history",(i,s)=>s.current.history[0].batchId="foreign");
 mutate("physical-identity-drift",(i,s)=>s.current.surfaceSnapshots["private/runtime.md"].revision="1:2:3:4:5");
 mutate("unlisted-corpus",(i,s)=>s.current.memoryEntries.push({...s.current.memoryEntries[0],filename:"foreign.md"}));
}
console.log(JSON.stringify({proof:check(input,state.prior,state.current),negative}));'''
            corpus_checked=json.loads(subprocess.check_output(['node','--import','tsx','--input-type=module','-e',code,str(proof_path),str(corpus_path)],cwd=REPO,env=env,text=True,timeout=30))
            report['commandCorpusProof']=corpus_checked['proof'];report['commandCorpusProofNegatives']=corpus_checked['negative']
            assert corpus_checked['proof']['ready'] is (not is_manual_held),corpus_checked
            assert all(not result['ready'] for result in corpus_checked['negative'].values()),corpus_checked
            if is_excerpt and not is_manual_held:
                entry=memory/'runtime.md'
                assert receipt['operations']==1 and entry.is_file(),receipt
                selected_source=source.read_text().splitlines()[0] if is_knowledge_citation else source.read_text().strip()
                assert selected_source in entry.read_text()
                if is_knowledge:
                    assert (project/'.memory/runtime.md').read_bytes()==entry.read_bytes()
                    assert proof_input['plan']['newMemories'][0]['classification']=='safe'
                else:
                    assert not (project/'.memory/runtime.md').exists()
                    assert proof_input['plan']['newMemories'][0]['classification']=='private'
                assert 'source-read' in kinds and 'coverage' in kinds and 'body' in kinds
                if is_knowledge:
                    assert 'Why: Retain the inspected runtime mode.' in entry.read_text()
                    assert 'How to apply:' in entry.read_text()
                    assert 'knowledge' not in proof_input['plan']['newMemories'][0]
                if case.endswith('-repair'):
                    assert kinds.count('excerpt-structural-correction')==1
                    assert list(runs.glob('*/structural-rejection.json'))
                if is_knowledge_contract:
                    rejection=json.loads(next(runs.glob('*/structural-rejection.json')).read_text())
                    assert rejection['category']=='plan'
                    assert 'content' in rejection['originalPlan']['newMemories'][0]
                    assert 'knowledge' not in rejection['originalPlan']['newMemories'][0]
                    original=json.loads(next(runs.glob('*/generation-original-plan.json')).read_text())
                    assert original['originalPlan']==rejection['originalPlan']
                    assert original['snapshotDigest']==rejection['snapshotDigest']
                    report['freshProjectContractCorrection']=True
                if is_materialized_repair:
                    rejection=json.loads(next(runs.glob('*/structural-rejection.json')).read_text())
                    assert 'content' in rejection['originalPlan']['newMemories'][0]
                    assert 'knowledge' not in rejection['originalPlan']['newMemories'][0]
                    original=json.loads(next(runs.glob('*/generation-original-plan.json')).read_text())
                    assert 'knowledge' in original['originalPlan']['newMemories'][0]
                    assert original['snapshotDigest']==rejection['snapshotDigest']
                    assert original['originalPlan']['unsupportedControlledField'] is True
                    report['materializedProjectCorrectionCompatible']=True
                if is_knowledge_citation:
                    rejection=json.loads(next(runs.glob('*/structural-rejection.json')).read_text())
                    assert rejection['category']=='citation'
                    assert rejection['originalPlan']['newMemories'][0]['knowledge']['units']==phase['validExcerptPlan']['newMemories'][0]['knowledge']['units']
                    repair=json.loads(next(runs.glob('*/structural-repair-response.json')).read_text())
                    patch=json.loads(repair['output'])
                    assert patch['kind']=='incremental-memory-amendment'
                    assert all(set(p)=={'candidateId','evidence'} for p in patch['replacements'])
                assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in source_hashes.items()),'Source drift'
                report.update(status='passed',kinds=kinds,receipt=receipt,
                    initialAuditExcerpt={'parentCopiedOriginalBytes':True,'freshParentAuditSource':True,
                        'privateOnly':not is_knowledge,'safeMirrorsEqual':is_knowledge,
                        'structuralCorrection':case.endswith('-repair'),
                        'citationOnlyStructuralCorrection':is_knowledge_citation,
                        'mixedContextCopied':is_knowledge,
                        'sourceBacklogClosureExercised':False,'HarnessExercised':False,
                        'externalRequests':0,'learningBenefitEstablished':False})
                return report
        if case=='renamed':
            audits=[json.loads(p.read_text()) for p in runs.rglob('maintenance-audit-*/receipt.json')]
            assert len(audits)==1 and audits[0]['unavailableEditPaths']==['temporary.ts'],audits
            assert not (project/'temporary.ts').exists() and (project/'renamed.ts').is_file()
            assert kinds.index('main-rename') < kinds.index('source-read')
        if case=='collector-refused':
            assert 'selector' not in kinds and 'plan' not in kinds
            assert (memory/'runtime.md').read_text()==before
            assert receipt['operations']==0 and any(a['outcome']=='failed' for a in receipt['attempts'])
        else:
            assert kinds.index('source-read') < kinds.index('plan')
            snapshots=[json.loads(p.read_text()) for p in runs.glob('*/snapshot.json')]
            snapshot=next(s for s in reversed(snapshots) if any(e.get('message',{}).get('details',{}).get('readOnlyMaintenanceAudit') for e in s['entries']))
            entries=snapshot['entries']; audit=next(i for i,e in enumerate(entries) if e.get('message',{}).get('details',{}).get('readOnlyMaintenanceAudit'))
            assert any(e.get('message',{}).get('toolName')=='edit' for e in entries[:audit-1])
            assert any('export const mode = "old";' in str(e.get('message',{}).get('content')) for e in entries[:audit-1])
            assert 'export const mode = "new";' in entries[audit]['message']['content'][0]['text']
            if is_manual_held:
                if is_initialization:
                    assert not (memory/'runtime.md').exists() and not (project/'.memory/runtime.md').exists()
                else:
                    assert (memory/'runtime.md').read_text()==before
                    assert (project/'.memory/runtime.md').read_text()==before
                assert receipt['operations']==0 and any(a['phase']=='memory' and a['outcome']=='proposed' for a in receipt['attempts']),receipt
                proofs=[json.loads(p.read_text()) for p in runs.rglob('memory-coverage-semantic-*.json')]
                assert proofs and all(not p['reviewed']['coverageReview']['planPassed'] and any(c['key']=='coverage_plan' and c['confidence']==0.79 for c in p['reviewed']['coverageReview']['checks']) for p in proofs),proofs
                assert not any(a['phase']=='harness' for a in receipt['attempts'])
            elif case=='coverage-citation-only':
                assert (memory/'runtime.md').read_text()==before
                assert receipt['operations']==0 and kinds.count('coverage')==1 and kinds.count('coverage-correction')==1 and kinds.count('body')==1,kinds
                proofs=[json.loads(p.read_text()) for p in runs.rglob('memory-coverage-semantic-*.json')]
                assert len(proofs)==1 and not proofs[0]['reviewed']['coverageReview']['planPassed']
                assert proofs[0]['reviewed']['candidateReview']['checkObservations']['counter_0_0']['probabilities']['compatible']==.89
                stopped=[json.loads(p.read_text()) for p in runs.rglob('semantic-repair-unchanged-coverage.json')]
                assert len(stopped)==1 and stopped[0]['independentCoverageHeld'] and not stopped[0]['writeAuthorized'],stopped
                original=json.loads(next(runs.glob('*/semantic-rejected-plan.json')).read_text())
                corrected=json.loads(next(runs.glob('*/semantic-repair-plan.json')).read_text())
                assert original['operations'][0]['content']==corrected['operations'][0]['content']
                assert original['operations'][0]['evidence']!=corrected['operations'][0]['evidence']
                assert not any(a['phase']=='harness' for a in receipt['attempts'])
                report['unchangedCoverageHold']={'initialHoldRetained':True,'independentCounterHoldRetained':True,
                    'citationOnlyRepairRetained':True,'secondCoverageDraw':False,'memoryOperations':0}
            elif case in ('held-later','coverage-replay','manual-coverage-replay'):
                assert (memory/'runtime.md').read_text()==before
                assert receipt['operations']==0 and any(a['phase']=='memory' and a['outcome']=='proposed' for a in receipt['attempts'])
                assert ('coverage-correction' if case in ('coverage-replay','manual-coverage-replay') else 'repair-no-correction') in kinds
                assert receipt['screen']['harness'] is (case=='held-later')
                assert 'harness-noop' not in kinds, 'Held Memory launched a later model worker'
                assert not any(a['phase']=='harness' for a in receipt['attempts'])
                assert harness.read_bytes()==harness_before if is_manual_replay else not harness.exists()
            elif is_mixed:
                if case!='mixed-noop':
                    assert receipt['operations']==0,receipt
                    assert not (memory/'mode-value.md').exists()
                    assert (memory/'runtime.md').read_text()==before
                    assert not any(a['phase']=='harness' for a in receipt['attempts'])
                    assert not (project/'.pi/harness.json').exists()
                    assert not (agent/'learning'/paths['scopeKey']/'backlog-completed.json').exists()
                    report['negativeAdmissionObserved']=True
                else:
                    assert (memory/'runtime.md').read_text()==before
                    assert (memory/'mode-value.md').read_bytes()==(project/'.memory/mode-value.md').read_bytes()
                    assert 'mode = \"new\"' in (memory/'mode-value.md').read_text()
                    assert receipt['operations']==1,receipt
                    assert any(a.get('outcome')=='applied' and a.get('pendingOperations')==1 for a in receipt['attempts']),receipt
                    assert not any(a['phase']=='harness' for a in receipt['attempts'])
                    assert not (project/'.pi/harness.json').exists()
                    audits=[json.loads(p.read_text())['proposal'] for p in (agent/'memory/history'/paths['scopeKey']).glob('change_*.json') if json.loads(p.read_text()).get('proposal',{}).get('kind')=='independent-memory-review']
                    assert len(audits)==1 and audits[0]['eligibleIndexes']==[1] and audits[0]['heldIndexes']==[0],audits
                    assert audits[0]['originalPlan']['operations'][0]['content']==before
                    noop_after={str(Path(p)):{'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest(),'inode':Path(p).stat().st_ino,'mtimeNs':Path(p).stat().st_mtime_ns} for p in noop_before}
                    assert noop_before==noop_after,(noop_before,noop_after)
                    assert not (agent/'learning'/paths['scopeKey']/'backlog-completed.json').exists()
                    report.update(partialPersistenceOnly=True,unchangedNoopFiles=noop_after)
            elif case=='source-changed':
                assert (memory/'runtime.md').read_text()==before
                assert receipt['operations']==0 and any(a['outcome']=='failed' for a in receipt['attempts'])
            else:
                assert 'mode = "new"' in (memory/'runtime.md').read_text()
                if case in ('coverage-correction','coverage-invalid-correction','coverage-replay','manual-coverage-replay','manual-initialization-repair'):
                    assert limit in (memory/'runtime.md').read_text()
                    assert kinds.count('coverage')==2 and kinds.count('coverage-correction')==1 and kinds.count('body')==2,kinds
                    coverage_proofs=[json.loads(p.read_text()) for p in runs.rglob('memory-coverage-semantic-*.json')]
                    assert len(coverage_proofs)==(2 if is_coverage_correction else 1) and all(p['proofAvailable'] and p['expectedContextDigest']==p['reviewed']['coverageReview']['contextDigest'] for p in coverage_proofs)
                    for proof in coverage_proofs:
                        assert proof['coverageContext']['questionContractVersion']==2
                        questions={q['key']:q for q in proof['coverageQuestions']}
                        assert questions['coverage_record_0']['criteria']!=questions['coverage_plan']['criteria']
                        wire=[r['body']['questions'] for r in requests if r['path'].startswith('/jev/')]
                        for key in ('coverage_plan','coverage_record_0'):
                            assert any(key in q and q[key]['criteria']==questions[key]['criteria'] for q in wire)

                    if is_coverage_correction:
                        assert {p['reviewed']['coverageReview']['planPassed'] for p in coverage_proofs}=={True,False}
                        assert any(check['choice']=='material_missing' for p in coverage_proofs for check in p['reviewed']['coverageReview']['checks'])
                    else:
                        accounts=[json.loads(p.read_text()) for p in runs.rglob('memory-coverage-review-*.json')]
                        assert sorted(p['status'] for p in accounts)==['invalid-response','reviewed']
                        rejected=next(p for p in accounts if p['status']=='invalid-response')
                        assert rejected['accounts']==[] and not rejected.get('plan')
                        assert rejected['diagnosticContinuation']['kind']=='complete-account-binding-rejection'
                        diagnostics=[json.loads(p.read_text()) for p in runs.rglob('memory-coverage-rejected-diagnostic-*.json')]
                        assert len(diagnostics)==1 and not diagnostics[0]['proofAvailable'] and not diagnostics[0]['writeAuthorized']
                        assert diagnostics[0]['rejectedAccount']==rejected['diagnosticContinuation']
                        assert diagnostics[0]['reviewed']['candidateReview']['checkObservations']['supported_0']['choice']=='unsupported'
                        assert all(p['reviewed']['coverageReview']['planPassed'] for p in coverage_proofs)
                    report['coverageCorrection']={'proofs':len(coverage_proofs),'initialHoldRetained':True,'repairedBody':True,'allSemanticThresholdsUnchanged':True}

                assert any(a.get('phase')=='memory' and a.get('outcome')=='applied' and a.get('operations')==1 for a in receipt['attempts'])
                history=[json.loads(p.read_text()) for p in (agent/'memory/history'/paths['scopeKey']).glob('change_*.json')]
                applied=[r for r in history if r['status']=='applied' and r['phase']=='memory' and any(c['target']['name']=='runtime.md' and c['target']['root']=='private' for c in r['changes'])]
                assert len(applied)==(2 if case in ('origin','origin-repair') else 1),applied
                current_digest=hashlib.sha256((memory/'runtime.md').read_bytes()).hexdigest()
                current=[r for r in applied if any(c['target']['name']=='runtime.md' and c['target']['root']=='private' and c['after']['digest']==current_digest for c in r['changes'])]
                assert len(current)==1,current
                origin=current[0]['origin']; assert origin['status']=='available',origin
                stat=(memory/'runtime.md').stat()
                revision=':'.join(str(n) for n in (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns))
                assert any(t['root']=='private' and t['name']=='runtime.md' and t['revision']==revision and t['digest']==hashlib.sha256((memory/'runtime.md').read_bytes()).hexdigest() for t in origin['targets']),origin
                report['memoryOrigin']=origin
                if case in ('origin','origin-repair'):
                    review_requests=[r['body'] for r in requests if r['path'].startswith('/jev/')]
                    states=[r['state'] for r in review_requests]
                    states=[json.loads(s) if isinstance(s,str) else s for s in states]
                    historical=[s['historicalMemoryOrigins'] for s in states if s.get('historicalMemoryOrigins')]
                    assert historical,'Historical task never reached actual SDK requests'
                    assert all(h[0]['transactions'][0]['kind']=='create' for h in historical)
                    assert all(h[0]['transactions'][0]['snapshot']['entries'][0]['content'][0]['text']=='Remember the currently observed contract for future maintenance.' for h in historical)
                    counter_requests=[(r,s) for r,s in zip(review_requests,states) if s.get('historicalMemoryOrigins') and s.get('reviewEvidence')]
                    assert counter_requests, 'Historical counter requests are missing'
                    assert all(s.get('supportEvidence') and all(
                        'complete supportEvidence and reviewEvidence' in q['instructions']['question']
                        and 'frozenEvidence' not in q['instructions']['question']
                        for q in r['questions'].values()) for r,s in counter_requests), 'Historical review refers to missing current evidence'
                    if case=='origin-repair':assert 'origin-repair' in kinds
                    report['historicalContextRequests']=len(historical)
                    report['historicalCurrentEvidenceFieldsBound']=True
        if case in ('coverage-replay','manual-coverage-replay'):
            kinds.append('replay-start')
            before_requests=len(requests)
            if is_manual_replay:
                held_backlog=backlog_status()
                manual_rows=[e for e in held_backlog['pendingEntries'] if e.get('manualRequest')]
                assert held_backlog['pending']==2 and len(manual_rows)==1,held_backlog
                manual_entry=manual_rows[0]
                assert receipt['input']['backlogId']==manual_entry['id']
                assert receipt['input']['manualRequest']==manual_entry['manualRequest']
                markers=[r for r in rows if r.get('type')=='custom' and r.get('customType')=='continual-learning-memory-request']
                assert len(markers)==1,markers
                marker=markers[0]
                assert marker['id']==manual_entry['manualRequest']['entryId']
                assert marker['data']['request']=='整理记忆'
                assert marker['data']['invocationId']==manual_entry['manualRequest']['invocationId']
                assert hashlib.sha256(marker['data']['request'].encode()).hexdigest()==manual_entry['manualRequest']['requestDigest']
                held_native_session=session.read_bytes()
                initial_snapshot=snapshot
                assert any(e.get('message',{}).get('content')=='整理记忆' for e in initial_snapshot['entries']),initial_snapshot
                learning=agent/'learning'/paths['scopeKey']
                initial_attempt=json.loads((learning/f"replay-{manual_entry['id']}.json").read_text())
                assert len(initial_attempt['attempts'])==1 and initial_attempt['attempts'][0]['receipt']==receipt,initial_attempt
                (output/'held-manual-backlog.json').write_text(json.dumps(held_backlog,indent=2))
                (output/'held-manual-attempt.json').write_text(json.dumps(initial_attempt,indent=2))
                (output/'native-memory-request.json').write_text(json.dumps(marker,indent=2,ensure_ascii=False))
                phase['backfill']=True
            second_command=[*command[:-1],'/consolidate backfill']
            if is_manual_replay:
                second_command[second_command.index('--session')+1]=str(agent/'sessions/fixture/manual-backfill.jsonl')
            second=subprocess.run(second_command,cwd=project,env=env,capture_output=True,timeout=90)
            (output/'replay-stdout.jsonl').write_bytes(second.stdout); (output/'replay-stderr.txt').write_bytes(second.stderr)
            assert second.returncode==0,second.stderr.decode()
            assert not failures,failures
            assert 'replay-questions-delivered' in kinds,kinds
            assert limit in (memory/'runtime.md').read_text()
            assert (memory/'runtime.md').read_bytes()==(project/'.memory/runtime.md').read_bytes()
            all_receipts=deduplicate_receipt_views([json.loads(p.read_text()) for p in runs.rglob('learning-pipeline-receipt.json')])
            applied=[r for r in all_receipts if r['batchId']!=receipt['batchId'] and r['operations']==1]
            assert len(applied)==1,all_receipts
            assert any(a.get('coverageReviewArtifact') for a in receipt['attempts'])
            assert 'source-complete' in kinds[kinds.index('replay-start'):],kinds
            assert requests[before_requests:], 'No actual native replay requests'
            if is_manual_replay:
                after_backlog=backlog_status()
                assert after_backlog['pending']==1 and after_backlog['pendingEntries']==ordinary_backlog['pendingEntries'],after_backlog
                assert applied[0]['input']['manualRequest']==manual_entry['manualRequest']
                assert applied[0]['input']['backlogId']==manual_entry['id']
                assert all(not a.get('phase') in ('harness','agents') for a in applied[0]['attempts'])
                assert not applied[0]['screen']['harness'] and not applied[0]['screen']['agents']
                assert session.read_bytes()==held_native_session,'Cross-session replay wrote the original source session'
                assert harness.read_bytes()==harness_before
                final_attempt=json.loads((learning/f"replay-{manual_entry['id']}.json").read_text())
                assert len(final_attempt['attempts'])==2
                assert final_attempt['attempts'][0]==initial_attempt['attempts'][0],'Initial failed attempt or costs changed'
                assert final_attempt['attempts'][-1]['receipt']==applied[0]
                completed=json.loads((learning/'backlog-completed.json').read_text())
                assert set(completed)=={manual_entry['id']},completed
                replay_snapshots=[json.loads(p.read_text()) for p in runs.glob('*/snapshot.json') if p.parent.name!=initial_snapshot['runId'] and (p.parent/'plan.json').is_file()]
                prefix=initial_snapshot['entries'][:audit-1]
                assert replay_snapshots and all(s['entries'][:len(prefix)]==prefix for s in replay_snapshots),'Original task/Memory command projection changed'
                assert (memory/'runtime.md').read_text()!=before and limit in (memory/'runtime.md').read_text()
                for name,value in [('replayed-manual-backlog',after_backlog),('replayed-manual-attempt',final_attempt),('manual-completed-references',completed)]:
                    (output/(name+'.json')).write_text(json.dumps(value,indent=2))
                report['manualCoverageReplay']={'nativeMarkerBound':True,'requestProjectionRestored':True,
                    'originalNativePrefixPreserved':True,'differentReplaySession':True,'memoryOnly':True,
                    'ordinaryBacklogStillPending':True,'manualReferenceOnlyAcknowledged':True,
                    'completeHistoricalAccountRelationshipsDelivered':True,'initialFailureAndUsageRetained':True,
                    'bodyCorrected':True,'externalRequests':0,'learningBenefitEstablished':False}
            report['failedLearningReplay']={'initialOperations':0,'initialReceipt':receipt,
                'replayReceipt':applied[0],'actualQuestionsDelivered':True,'freshSourceCollected':True,
                'independentFreshReview':True,'bothRootsMatch':True,'learningBenefitEstablished':False}
        if is_initialization and not is_manual_held:
            assert receipt['operations']==1 and report['manualMaintenance']['bothRootsMatch']
            def closure_state() -> dict:
                state=history_state();status=backlog_status()
                state.update(memoryEntries=[{'filename':p.name,'content':p.read_text(),'revision':hashlib.sha256(p.read_bytes()).hexdigest()}
                    for p in sorted(memory.glob('*.md')) if p.name!='MEMORY.md'],
                    pendingLearningJobs=status['pending'],backlogStatus=status)
                learning=agent/'learning'/paths['scopeKey']
                completed=learning/'backlog-completed.json'
                state['completedBacklog']=json.loads(completed.read_text()) if completed.exists() else {}
                state['attempts']=[attempt for p in sorted(learning.glob('replay-*.json'))
                    for attempt in json.loads(p.read_text()).get('attempts',[])]
                digest_code='import {dossierDigest} from '+json.dumps(str(REPO/'packages/continual-learning/tests/continuous-dossier-proof.mjs'))+';const state=JSON.parse(process.argv[1]);for(const attempt of state.attempts)attempt.receiptDigest=attempt.receipt?dossierDigest(attempt.receipt):null;console.log(JSON.stringify(state));'
                return json.loads(subprocess.check_output(['node','--input-type=module','-e',digest_code,json.dumps(state)],cwd=REPO,env=env,text=True))
            before_closure_state=closure_state()
            (output/'before-source-closure-state.json').write_text(json.dumps(before_closure_state,indent=2))
            closure_before=backlog_status()
            assert closure_before['pending']==1,closure_before
            phase['backfill']=True
            closure_command=command[:-1].copy()
            closure_command[closure_command.index('--session')+1]=str(agent/'sessions/fixture/source-backfill.jsonl')
            closure=subprocess.run([*closure_command,'/consolidate backfill'],cwd=project,env=env,capture_output=True,timeout=90)
            (output/'source-backfill-stdout.jsonl').write_bytes(closure.stdout);(output/'source-backfill-stderr.txt').write_bytes(closure.stderr)
            assert closure.returncode==0,closure.stderr.decode()
            assert not failures,failures
            closure_after=backlog_status()
            after_closure_state=closure_state()
            (output/'after-source-closure-state.json').write_text(json.dumps(after_closure_state,indent=2))
            report['sourceClosureIntegrity']=initialization_closure_ready(before_closure_state,after_closure_state,session.read_bytes(),str(session))
            assert report['sourceClosureIntegrity']['ready'],report['sourceClosureIntegrity']
            assert closure_after['pending']==0 and not any(closure_after.get(k) for k in ('error','malformed','unlearnable','unscoped')),closure_after
            closed=[r for r in deduplicate_receipt_views([json.loads(p.read_text()) for p in runs.rglob('learning-pipeline-receipt.json')]) if r['batchId']!=receipt['batchId']]
            assert len(closed)==1 and closed[0]['operations']==0,closed
            report['sourceBacklogClosure']={'before':closure_before,'after':closure_after,'receipt':closed[0],
                'command':'/consolidate backfill','countedAsNewLearning':False}
            phase['backfill']=False
            phase['policy']=True
            (agent/'memory/settings.json').write_text(json.dumps({'autoMemory':True,'automaticPhases':{'memory':'off','harness':'apply','agents':'off'}}))
            policy_session=agent/'sessions/fixture/policy.jsonl'
            policy_command=command[:-1].copy()
            tools_index=policy_command.index('--tools');policy_command[tools_index:tools_index+2]=['--no-tools']
            policy_command[policy_command.index('--session')+1]=str(policy_session)
            policy_source=lambda:{str(source.relative_to(project)):{'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'mode':source.stat().st_mode&0o777,'size':source.stat().st_size}}
            policy_owner={'kind':'native-automatic-harness-policy','version':1,'argv':[*policy_command,policy_text],
                'cwd':str(project.resolve()),'agentDir':str(agent.resolve()),'sessionPath':str(policy_session.resolve()),
                'piVersion':report['piVersion'],'prompt':policy_text,'sourceFiles':policy_source(),'startedAt':time.time_ns()//1_000_000}
            policy_owner_text=json.dumps(policy_owner,ensure_ascii=False,separators=(',',':'))
            (output/'policy-started.json').write_text(policy_owner_text)
            policy=subprocess.run([*policy_command,policy_text],cwd=project,env=env,capture_output=True,timeout=90)
            (output/'policy-stdout.jsonl').write_bytes(policy.stdout);(output/'policy-stderr.txt').write_bytes(policy.stderr)
            policy_completion={'ownerDigest':hashlib.sha256(policy_owner_text.encode()).hexdigest(),'exitCode':policy.returncode,
                'timedOut':False,'cancelled':False,'settledAt':time.time_ns()//1_000_000,
                'sessionDigest':hashlib.sha256(policy_session.read_bytes()).hexdigest(),
                'stdoutDigest':hashlib.sha256(policy.stdout).hexdigest(),'sourceFiles':policy_source()}
            (output/'policy-closed.json').write_text(json.dumps(policy_completion,ensure_ascii=False,separators=(',',':')))
            report['manualMaintenance']['dependentHarnessStarted']=True
            assert policy.returncode==0,policy.stderr.decode()
            assert not failures,failures
            document=json.loads(harness.read_text())
            assert next(r for r in document['rules'] if r['id']=='manual-fixture')==rule('manual-fixture')
            assert set(document['learnedRules'])=={'auto-npm'},document
            code='import {ruleRevision,evaluateBash} from '+json.dumps(str(REPO/'packages/continual-learning/extensions/guardrail-engine.ts'))+';import {resolveHarnessConfig} from '+json.dumps(str(REPO/'packages/continual-learning/extensions/guardrail-config.ts'))+';const document=JSON.parse(process.argv[1]);const rule=document.rules.find(r=>r.id==="auto-npm");const {config}=resolveHarnessConfig(process.argv[2],process.argv[3]);console.log(JSON.stringify({revisionVerified:document.learnedRules[rule.id].revision===ruleRevision(rule),decisions:Object.fromEntries(["npm --version","npm test","pnpm test","printf npm test"].map(command=>[command,evaluateBash(config,command).decision]))}));'
            probe=json.loads(subprocess.check_output(['node','--import','tsx','--input-type=module','-e',code,json.dumps(document),str(project),str(agent)],cwd=REPO,env=env,text=True))
            assert probe['revisionVerified'],probe
            all_receipts=deduplicate_receipt_views([json.loads(p.read_text()) for p in runs.rglob('learning-pipeline-receipt.json')])
            policy_receipts=[r for r in all_receipts if r['batchId'] not in (receipt['batchId'],closed[0]['batchId'])]
            applied=[r for r in policy_receipts if r['operations']==1]
            assert len(applied)==1 and applied[0]['mode']=='automatic',policy_receipts
            assert any(a['phase']=='harness' and a['outcome']=='applied' for a in applied[0]['attempts'])
            backlog_code='import {backlogStatus} from '+json.dumps(str(REPO/'packages/continual-learning/extensions/learning-backlog.ts'))+';console.log(JSON.stringify(backlogStatus(process.argv[1],process.argv[2])));'
            before_probe=json.loads(subprocess.check_output(['node','--import','tsx','--input-type=module','-e',backlog_code,str(project),str(agent)],cwd=REPO,env=env,text=True))
            assert before_probe['pending']==0 and not any(before_probe.get(k) for k in ('error','malformed','unlearnable','unscoped')),before_probe
            policy_attempt=next(a for a in applied[0]['attempts'] if a['phase']=='harness' and a['outcome']=='applied')
            policy_ledgers=[p for p in runs.rglob('harness-task-usage.json') if json.loads(p.read_text()).get('ledgerId')==policy_attempt['usageLedgerId']]
            assert len(policy_ledgers)==1,policy_ledgers
            policy_run=policy_ledgers[0].parent
            policy_input={'kind':'automatic-harness-policy-review','version':1,'owner':policy_owner,'completion':policy_completion,
                'nativeSession':policy_session.read_text(),'stdout':policy.stdout.decode(),'receipt':applied[0],
                'snapshotText':(policy_run/'snapshot.json').read_text(),'reviewManifest':json.loads((policy_run/'manifest.json').read_text()),
                'postReceipt':json.loads((policy_run/'harness-post-receipt.json').read_text()),'usageLedger':json.loads(policy_ledgers[0].read_text()),
                'usageLedgerPath':str(policy_ledgers[0])}
            policy_after=closure_state()
            policy_proof_file=output/'automatic-policy-input.json'
            policy_proof_file.write_text(json.dumps({'input':policy_input,'prior':after_closure_state,'current':policy_after},ensure_ascii=False))
            code='import fs from "node:fs";import {createHash} from "node:crypto";import {automaticHarnessPolicyProof as check} from '+json.dumps(str(REPO/'packages/continual-learning/tests/continuous-command-proof.ts'))+''';
const original=JSON.parse(fs.readFileSync(process.argv[1],"utf8")),negatives={};
const mutate=(name,change)=>{const x=structuredClone(original);change(x);negatives[name]=check(x.input,x.prior,x.current);};
mutate("different-user",x=>{x.input.owner.prompt+=" changed";x.input.owner.argv[x.input.owner.argv.length-1]=x.input.owner.prompt;x.input.completion.ownerDigest=createHash("sha256").update(JSON.stringify(x.input.owner)).digest("hex");});
mutate("ordinary-tools",x=>{x.input.owner.argv[x.input.owner.argv.indexOf("--no-tools")]="--tools";x.input.completion.ownerDigest=createHash("sha256").update(JSON.stringify(x.input.owner)).digest("hex");});
mutate("changed-source-mode",x=>Object.values(x.input.completion.sourceFiles)[0].mode^=1);
mutate("lost-prior-receipt",x=>x.current.receipts.shift());
mutate("lost-source-ack",x=>delete x.current.completedBacklog[x.input.receipt.input.backlogId]);
mutate("lost-prior-history",x=>x.current.history.shift());
mutate("foreign-history-owner",x=>x.current.history.find(r=>r.batchId===x.input.receipt.batchId).batchId="batch_"+"0".repeat(32));
mutate("changed-memory-revision",x=>{const key=Object.keys(x.current.surfaceSnapshots).find(k=>k.startsWith("private/")&&!k.endsWith("/MEMORY.md"));x.current.surfaceSnapshots[key].revision+="0";});
mutate("worker-cost-drift",x=>x.input.usageLedger.knownUsage.cost+=1);
mutate("different-snapshot",x=>{const snapshot=JSON.parse(x.input.snapshotText);snapshot.entries[0].message.content=[{type:"text",text:"different task"}];x.input.snapshotText=JSON.stringify(snapshot);x.input.reviewManifest.snapshotDigest=createHash("sha256").update(x.input.snapshotText).digest("hex");x.input.postReceipt.snapshotDigest=x.input.reviewManifest.snapshotDigest;});
const append=(x,message)=>{const rows=x.input.nativeSession.trimEnd().split("\\n").map(JSON.parse);rows.push({type:"message",id:"late-policy-message",parentId:rows.at(-1).id,message});x.input.nativeSession=rows.map(r=>JSON.stringify(r)).join("\\n")+"\\n";x.input.completion.sessionDigest=createHash("sha256").update(x.input.nativeSession).digest("hex");};
mutate("tool-after-receipt",x=>append(x,{role:"assistant",stopReason:"toolUse",content:[{type:"toolCall",id:"late-tool",name:"bash",arguments:{command:"npm --version"}}]}));
mutate("error-after-receipt",x=>append(x,{role:"assistant",stopReason:"error",content:[]}));
const receiptChange=(x,change)=>{
 const r=x.input.receipt;change(r);
 x.current.receipts=x.current.receipts.map(value=>value.batchId===r.batchId?r:value);
 const digest=createHash("sha256").update(JSON.stringify(r)).digest("hex");
 for(const attempt of x.current.attempts)if(attempt.receipt?.batchId===r.batchId){attempt.receipt=r;attempt.receiptDigest=digest;}
 x.current.completedBacklog[r.input.backlogId]=digest;
 const rows=x.input.nativeSession.trimEnd().split("\\n").map(JSON.parse);
 rows.find(row=>row.customType==="continual-learning-result").details=r;
 x.input.nativeSession=rows.map(row=>JSON.stringify(row)).join("\\n")+"\\n";
 const events=x.input.stdout.trimEnd().split("\\n").map(JSON.parse);
 events.find(row=>row.type==="message_end"&&row.message?.customType==="continual-learning-result").message.details=r;
 x.input.stdout=events.map(row=>JSON.stringify(row)).join("\\n")+"\\n";
 x.input.completion.sessionDigest=createHash("sha256").update(x.input.nativeSession).digest("hex");
 x.input.completion.stdoutDigest=createHash("sha256").update(x.input.stdout).digest("hex");
};
mutate("missing-worker-identity",x=>{delete x.input.usageLedger.ledgerId;receiptChange(x,r=>{delete r.attempts.find(a=>a.phase==="harness"&&a.outcome==="applied").usageLedgerId;});});
console.log(JSON.stringify({proof:check(original.input,original.prior,original.current),negatives}));'''
            policy_proofs=json.loads(subprocess.check_output(['bun','-e',code,str(policy_proof_file)],cwd=REPO,env=env,text=True))
            assert policy_proofs['proof']['ready'],policy_proofs
            assert all(not value['ready'] for value in policy_proofs['negatives'].values()),policy_proofs
            policy_bridge=policy_initialization_bridge(after_closure_state,policy_after,policy_input,source_files=owner['sourceFiles'])
            (output/'automatic-policy-bridge.json').write_text(json.dumps(policy_bridge,ensure_ascii=False,indent=2))
            report['automaticHarnessInitialization']={'receipt':applied[0],'additionalReceipts':[r for r in policy_receipts if r['batchId']!=applied[0]['batchId']],'origin':document['learnedRules']['auto-npm']['origin'],
                'nativePolicyProof':policy_proofs['proof'],'nativePolicyNegatives':policy_proofs['negatives'],
                'historyIntegrity':policy_bridge['historyIntegrity'],
                'backlogBeforeExecutionProbe':before_probe,
                'revisionVerified':probe['revisionVerified'],'manualRulePreserved':True,'preexistingManualFixtureOnly':True,
                'automaticRuleWasAbsent':set(json.loads(harness_before).get('learnedRules',{}))==set(),
                'decisions':probe['decisions'],'learningBenefitEstablished':False}
            phase['probe']=True
            (agent/'memory/settings.json').write_text(json.dumps({'autoMemory':False,'automaticPhases':{'memory':'off','harness':'off','agents':'off'}}))
            probe_command=command[:-1].copy()
            probe_command[probe_command.index('--tools')+1]='bash'
            probe_session=agent/'sessions/fixture/owned-execution.jsonl'
            probe_command[probe_command.index('--session')+1]=str(probe_session)
            persisted=harness.read_bytes()
            execution=subprocess.run([*probe_command,'Run npm --version once, then pnpm --version once. Report each actual outcome.'],cwd=project,env=env,capture_output=True,timeout=90)
            (output/'owned-execution-stdout.jsonl').write_bytes(execution.stdout);(output/'owned-execution-stderr.txt').write_bytes(execution.stderr)
            assert execution.returncode==0,execution.stderr.decode()
            events=[json.loads(line) for line in execution.stdout.splitlines() if line.strip()]
            ends={e['toolCallId']:e for e in events if e.get('type')=='tool_execution_end'}
            assert set(ends)=={'owned-npm-block','pnpm-allowed'},ends
            assert ends['owned-npm-block']['isError'] and not ends['pnpm-allowed']['isError'],ends
            pnpm_version=json.loads((REPO/'package.json').read_text())['packageManager'].split('@',1)[1].split('+',1)[0]
            pnpm_output=''.join(item.get('text','') for item in ends['pnpm-allowed']['result'].get('content',[]) if item.get('type')=='text')
            assert pnpm_output.strip()==pnpm_version,ends['pnpm-allowed']
            rows=[json.loads(line) for line in probe_session.read_text().splitlines() if line.strip()]
            decisions=[e['data'] for e in rows if e.get('customType')=='harness-behavior-observation' and e.get('data',{}).get('phase')=='decision']
            revision=document['learnedRules']['auto-npm']['revision']
            assert any(d['decision']=='block' and d['toolCallIdDigest']==hashlib.sha256(b'"owned-npm-block"').hexdigest() and any(r['idDigest']==hashlib.sha256(b'"auto-npm"').hexdigest() and r['revision']==revision and r['matched'] for r in d['rules']) for d in decisions),decisions
            assert any(d['decision']=='execute' and d['toolCallIdDigest']==hashlib.sha256(b'"pnpm-allowed"').hexdigest() for d in decisions),decisions
            assert harness.read_bytes()==persisted
            after_probe=json.loads(subprocess.check_output(['node','--import','tsx','--input-type=module','-e',backlog_code,str(project),str(agent)],cwd=REPO,env=env,text=True))
            assert after_probe['pending']==1,after_probe
            report['automaticHarnessInitialization']['nativeExecution']={'blockedByExactOwnedRevision':True,'nonNpmAllowed':True,'pnpmVersion':pnpm_version,'pnpmCli':cli,'unchangedPersistedRule':True,'automaticLearningEnabled':False}
            report['automaticHarnessInitialization']['backlogAfterDisabledLearningProbe']=after_probe
        assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in source_hashes.items()), 'Source drift'
        report.update(status='passed',kinds=kinds,receipt=receipt)
    except Exception as error:
        report.update(error=type(error).__name__+': '+str(error),kinds=kinds)
        raise
    finally:
        (output/'manifest.json').write_text(json.dumps(report,indent=2))
        (output/'requests.json').write_text(json.dumps(requests,indent=2)); server.shutdown(); server.server_close(); thread.join()
    (output/'manifest.json').write_text(json.dumps(report,indent=2)); return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('output',type=Path); parser.add_argument('--case',choices=('manual-initialization-knowledge-materialized-repair','manual-initialization-knowledge-contract-repair','manual-initialization-knowledge-citation-repair','manual-initialization-knowledge-held','manual-phase','manual-phase-held','manual-initialization-knowledge','manual-initialization-knowledge-repair','manual-initialization-excerpt','manual-initialization-excerpt-repair','manual-initialization','manual-initialization-held','manual-initialization-repair','manual-maintenance','manual-maintenance-held','manual-coverage-replay','coverage-replay','coverage-invalid-correction','coverage-correction','coverage-citation-only','applied','legacy','deep','renamed','source-changed','collector-refused','read-review','held-later','origin','origin-repair','mixed-noop','mixed-noop-uncertain','mixed-noop-source-race'),default='applied')
    args=parser.parse_args(); print(json.dumps(run(args.output.resolve(),args.case)))
