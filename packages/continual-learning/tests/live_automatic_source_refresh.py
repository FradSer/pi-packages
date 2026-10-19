"""Actual isolated Pi: old read -> edit -> automatic current-source collection.

Loopback judgments are controlled framing/mechanics evidence, never model learning
or semantic accuracy evidence. No external credentials or services are admitted.
"""
from __future__ import annotations
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import shlex
import threading

from live_acceptance_support import isolated_environment, workspace_pi
from live_learning_loop import field, message_text, stream_response
from support import REPO


def run(output: Path, case: str = 'applied') -> dict:
    is_mixed=case.startswith('mixed-noop')
    output.mkdir(parents=True, exist_ok=False)
    project, agent = output/'project', output/'agent'
    project.mkdir(); agent.mkdir()
    if is_mixed:subprocess.run(['git','init','-q',str(project)],check=True,capture_output=True,timeout=10)
    source = project/('packages/a/src/nested/runtime.ts' if case=='deep' else 'runtime.ts')
    source.parent.mkdir(parents=True,exist_ok=True)
    source.write_text('export const mode = "old";\n')
    tracked = [REPO/'packages/continual-learning/extensions'/name for name in ('incremental-learning.ts','memory-maintenance-audit.ts','inject-memory.ts','learning-history.ts','jev-learning.ts','memory-review-consent.ts','consolidation-run.ts','independent-memory-partition.ts','jev-memory-predecessors.ts','jev-memory-relations.ts','jev-memory-readiness.ts','planner-prompts.ts')] + [Path(__file__),Path(__file__).with_name('memory-origin-harness.ts')]
    source_hashes = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
    report = {'status':'failed','case':case,'outputDir':str(output),'sourceHashes':source_hashes,
        'externalRequests':0,'paidRequests':0,'semanticOrLearningBenefitEstablished':False}
    kinds: list[str] = []; requests: list[dict] = []; failures: list[str] = []
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
                        if question['type']=='noul':answers[key]={'type':'noul','noul':0.99 if key=='memory' else 0.01}
                        elif question['type']=='score':answers[key]={'type':'score','score':3,'confidence':1,'legend':{str(i):str(i) for i in range(4)},'probabilities':{str(i):int(i==3) for i in range(4)}}
                        else:
                            labels=list(question['criteria']); label=next((x for x in ('independent','selfContained','compatible','grounded','consistent','unrelated') if x in labels),labels[0])
                            if case=='mixed-noop-uncertain' and key=='relation':label='unclear'
                            if is_mixed and key=='coherence_0' and len(data.get('state',{}).get('proposedMemoryOperations',[]))==2:label='unclear'
                            if (case=='held-later' or case=='origin-repair' and 'origin-repair' not in kinds) and key.startswith('supported_'):label='unsupported'
                            answers[key]={'type':'choice','choice':label,'confidence':1,'probabilities':{x:int(x==label) for x in labels}}
                    body=json.dumps({'model':'jev-1.13.0','answers':answers,'usage':{'input_tokens':1,'output_tokens':1}}).encode()
                    self.send_response(200); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
                text = message_text(data)
                if 'Task: inspect current project source' in text:
                    user = next(m for m in data['messages'] if m.get('role')=='user')
                    content = user['content']
                    prompt = content if isinstance(content,str) else '\n'.join(b['text'] for b in content if b.get('type')=='text')
                    payload=json.loads(prompt.split('\n')[-1])
                    assert payload['memoryFiles']==[] and payload['memoryIndex']==[] and payload['untrustedMemoryClaims']==[]
                    assert payload['sourceIndex']['paths']==[str(source.relative_to(project))]
                    assert payload['readScope']['roots']==[]
                    if not any(m.get('role')=='tool' for m in data['messages']):
                        kinds.append('source-read')
                        path=str(memory/'runtime.md') if case=='collector-refused' else str(source)
                        stream_response(self,[{'id':'source','name':'learning_read','arguments':{'path':path,'offset':1,'limit':200}}])
                    else:kinds.append('source-complete'); stream_response(self,'Current source observed.')
                elif '# Incremental Memory selector' in text:
                    kinds.append('selector'); stream_response(self,json.dumps({'kind':'incremental-memory-selection','version':1,'contextDigest':field(text,'Context digest'),'selected':[] if case=='read-review' else ['runtime.md'],'memory':case!='read-review','harness':False,'agents':False,'reason':'Controlled source topic'}))
                elif 'harness-consolidation-plan' in text:
                    kinds.append('harness-noop')
                    stream_response(self,json.dumps({'kind':'harness-consolidation-plan','version':1,'schemaVersion':1,**{k:field(text,k) for k in ('runId','scopeDigest','artifactHash')},'operations':[],'evidence':[],'report':[]}))
                elif 'Task: repair one rejected incremental Memory delta plan.' in text:
                    payload=json.loads(text.split('\n')[-1])
                    patches=[]
                    if case=='origin-repair':
                        kinds.append('origin-repair')
                        assert payload['historicalMemoryOrigins'][0]['transactions'][0]['snapshot']['entries'][0]['content'][0]['text']=='Remember the currently observed contract for future maintenance.'
                        snapshot=payload['semanticContext']['frozenEvidence']
                        refs=[line['ref'] for e in snapshot['entries'] for block in e.get('entry',{}).get('message',{}).get('content',[])
                            for line in block.get('citationLines',{}).get('lines',[]) if line.get('text')=='export const mode = "new";' and line.get('ref')]
                        assert len(refs)==1,refs
                        content='---\nname: runtime\ndescription: runtime.ts declares mode new\ntype: project\n---\nObserved source in runtime.ts: `export const mode = "new";`.\n'
                        patches=[{'candidateId':payload['repairCandidates'][0]['candidateId'],'content':content,'evidence':[{'ref':refs[0]}]}]
                    else:kinds.append('repair-no-correction')
                    stream_response(self,json.dumps({'kind':'incremental-memory-amendment','version':1,**payload['identity'],'replacements':patches}))
                elif 'incremental-memory-plan' in text:
                    kinds.append('plan')
                    snapshots=[json.loads(p.read_text()) for p in runs.glob('*/snapshot.json')]
                    snapshot=next(s for s in reversed(snapshots) if any(e.get('message',{}).get('details',{}).get('readOnlyMaintenanceAudit') for e in s['entries']))
                    index=next(i for i,e in enumerate(snapshot['entries']) if e.get('message',{}).get('details',{}).get('readOnlyMaintenanceAudit'))
                    if case in ('source-changed','mixed-noop-source-race'):source.write_text('export const mode = "raced";\n')
                    content='---\nname: runtime\ndescription: runtime.ts declares mode new\ntype: project\n---\nObserved source in runtime.ts: `export const mode = "new";`.\n'
                    if case=='origin-repair':content=content.replace('mode new','mode old').replace('mode = "new"','mode = "old"')
                    plan={'kind':'incremental-memory-plan','version':1,'schemaVersion':1,**{k:field(text,k) for k in ('runId','scopeKey','scopeDigest','artifactHash','snapshotDigest')},'operations':[{'name':'runtime.md','kind':'rewrite','classification':'safe','content':content,'evidence':[{'ref':f'e{index}.b0.l1'}]}],'newMemories':[]}
                    if is_mixed:
                        plan['operations'][0]['content']=before
                        plan['newMemories']=[{'name':'mode-value.md','kind':'project','classification':'safe','content':content.replace('name: runtime','name: mode-value'),'evidence':[{'ref':f'e{index}.b0.l1'}]}]
                    stream_response(self,json.dumps(plan))
                elif 'Review each complete candidate Memory below' in text:
                    kinds.append('body')
                    targets=json.loads(text.split('\n')[-1])['targets'] if is_mixed else [{'targetIndex':0}]
                    stream_response(self,json.dumps({'reviews':{str(t['targetIndex']):{'verdict':'consistent','conflictingQuotes':[],'reason':'Controlled framing only'} for t in targets}}))
                else:
                    tools=[m for m in data['messages'] if m.get('role')=='tool']
                    if case=='read-review' and not tools:
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
    env.update(TYPESAFE_BASE_URL=f'http://127.0.0.1:{server.server_port}/jev',TYPESAFE_API_KEY='offline-fixture')
    (agent/'settings.json').write_text(json.dumps({'packages':[],'quietStartup':True,'defaultThinkingLevel':'off','retry':{'enabled':False}}))
    (agent/'memory').mkdir(); (agent/'memory/settings.json').write_text(json.dumps({'autoMemory':True,'automaticPhases':{'memory':'apply','harness':'apply' if case in ('legacy','held-later','mixed-noop') else 'off','agents':'off'}}))
    (agent/'continual-learning.json').write_text(json.dumps({'jev':{'enabled':case!='legacy','model':'jev-1.13.0','allowPrivateMemory':True,'requestConcurrency':1,**({'scopes':['memory']} if case=='read-review' else {})}}))
    (agent/'memory.json').write_text('{"provider":"fixture","model":"scripted"}')
    (agent/'models.json').write_text(json.dumps({'providers':{'fixture':{'baseUrl':f'http://127.0.0.1:{server.server_port}/v1','api':'openai-completions','apiKey':'offline-fixture','models':[{'id':'scripted','reasoning':False,'input':['text'],'contextWindow':200000,'maxTokens':4096,'cost':{'input':0,'output':0,'cacheRead':0,'cacheWrite':0}}]}}}))
    code='import {resolveMemoryPaths} from '+json.dumps(str(REPO/'packages/continual-learning/extensions/memory-paths.ts'))+';console.log(JSON.stringify(resolveMemoryPaths(process.argv[1])));'
    paths=json.loads(subprocess.check_output(['node','--import','tsx','--input-type=module','-e',code,str(project)],cwd=REPO,env=env,text=True))
    runs=Path(paths['runsDir']); memory=Path(paths['harnessDir']); memory.mkdir(parents=True)
    before='---\nname: runtime\ndescription: runtime.ts declares mode old\ntype: project\n---\nObserved source in runtime.ts: `export const mode = "old";`.\n'
    if is_mixed:before='---\nname: runtime\ndescription: runtime.ts exports a mode constant\ntype: project\n---\nruntime.ts exports a mode constant.\n'
    if case in ('origin','origin-repair'):
        code='import {fixture} from '+json.dumps(str(REPO/'packages/continual-learning/tests/memory-origin-harness.ts'))+';await fixture("native-origin",1,"safe",false,false,JSON.parse(process.argv[1]));'
        subprocess.run(['bun','-e',code,json.dumps({'cwd':str(project),'name':'runtime.md','content':before,'sourceText':source.read_text()})],cwd=REPO,env=env,check=True,capture_output=True,timeout=30)
    else:(memory/'runtime.md').write_text(before)
    if is_mixed:
        (project/'.memory').mkdir()
        (project/'.memory/runtime.md').write_text(before)
    noop_before={str(p):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'inode':p.stat().st_ino,'mtimeNs':p.stat().st_mtime_ns} for p in [memory/'runtime.md',project/'.memory/runtime.md'] if p.exists()}
    (memory/'MEMORY.md').write_text('# Project memories\n\n- runtime.md — runtime.ts declares mode old\n')
    session=output/'session.jsonl'
    command=[workspace_pi(REPO),'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-approve','--thinking','off','--tools','read,edit,write,bash' if case=='renamed' else 'read,edit','-e',str(REPO/'packages/continual-learning/index.ts'),'--model','fixture/scripted','--session',str(session),'--print','--mode','json','Update runtime.ts mode from old to new.'+(' Add a regression test for onIdle.' if case=='legacy' else ' Never run the retired compiler in future tasks.' if case in ('held-later','mixed-noop') else '')]
    try:
        report['piVersion']=subprocess.check_output([workspace_pi(REPO),'--version'],cwd=project,env=env,text=True,timeout=10).strip()
        assert report['piVersion']=='1.3.0',report['piVersion']
        result=subprocess.run(command,cwd=project,env=env,capture_output=True,timeout=90)
        (output/'stdout.jsonl').write_bytes(result.stdout); (output/'stderr.txt').write_bytes(result.stderr)
        assert result.returncode==0,result.stderr.decode()
        assert not failures,failures
        receipts=list(runs.rglob('learning-pipeline-receipt.json'))
        assert len(receipts)==1,(kinds,receipts)
        receipt=json.loads(receipts[0].read_text())
        rows=[json.loads(line) for line in session.read_text().splitlines() if line.strip()]
        delivered=[r['details'] for r in rows if r.get('type')=='custom_message' and r.get('customType')=='continual-learning-result']
        assert delivered and delivered[-1]==receipt, 'Receipt identity differs from actual session result'
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
            if case=='held-later':
                assert (memory/'runtime.md').read_text()==before
                assert receipt['operations']==0 and any(a['phase']=='memory' and a['outcome']=='proposed' for a in receipt['attempts'])
                assert 'repair-no-correction' in kinds
                assert receipt['screen']['harness'] is True
                assert 'harness-noop' not in kinds, 'Held Memory launched a later model worker'
                assert not any(a['phase']=='harness' for a in receipt['attempts'])
                assert not (project/'.pi/harness.json').exists()
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
    parser=argparse.ArgumentParser(); parser.add_argument('output',type=Path); parser.add_argument('--case',choices=('applied','legacy','deep','renamed','source-changed','collector-refused','read-review','held-later','origin','origin-repair','mixed-noop','mixed-noop-uncertain','mixed-noop-source-race'),default='applied')
    args=parser.parse_args(); print(json.dumps(run(args.output.resolve(),args.case)))
