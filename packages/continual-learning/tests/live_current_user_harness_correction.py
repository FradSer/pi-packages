"""Actual Pi/worker/semantic wire/parent mutation before Bash, loopback only."""
from __future__ import annotations
import hashlib,json,subprocess,sys,tempfile,threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from live_learning_loop import field,message_text,stream_response
from live_acceptance_support import isolated_environment,workspace_pi


def main() -> None:
    output=Path(tempfile.mkdtemp(prefix='early-harness-native-',dir=sys.argv[1] if len(sys.argv)>1 else None))
    package=Path(__file__).resolve().parents[1];repo=package.parents[1];fixture=Path(__file__).with_name('current-user-harness-live-fixture.ts')
    sources=[Path(__file__),fixture,Path(__file__).with_name('live_learning_loop.py'),Path(__file__).with_name('live_acceptance_support.py'),package/'index.ts',package/'package.json',repo/'pnpm-lock.yaml',*sorted((package/'extensions').rglob('*.ts')),*sorted((package/'prompts').rglob('*.md')),*sorted((repo/'packages/kit/src').rglob('*.ts'))]
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources};pi=workspace_pi(repo);version=subprocess.run([pi,'--version'],check=True,capture_output=True,text=True).stdout.strip();rows=[]
    for mode in ('correct','retire','held','ordinary-write','shadow-write','repair-read'):
        root=output/mode;cwd=root/'project';agent=root/'agent';(cwd/'.git').mkdir(parents=True);(cwd/'.pi').mkdir();(agent/'memory').mkdir(parents=True)
        prior={'id':'owned-npm','bash':r'^npm(?:\s|$)','action':'block','message':'Block Bash commands whose first executable is npm.'}
        revision=subprocess.run(['pnpm','exec','tsx','-e',"import {ruleRevision} from './packages/continual-learning/extensions/guardrail-engine.ts';console.log(ruleRevision("+json.dumps(prior)+"));"],cwd=repo,check=True,capture_output=True,text=True).stdout.strip()
        original={'rules':[prior],'learnedRules':{'owned-npm':{'origin':'consolidation','revision':revision}}};(cwd/'.pi/harness.json').write_text(json.dumps(original))
        text='Permanently retire the owned-npm rule: all npm commands are now allowed by project policy.' if mode=='retire' else 'Correction of the prior permanent project constraint: npm --version is now allowed; only Bash commands starting npm test must be blocked. Replace the old broad npm restriction permanently.'
        observations=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args: object) -> None:pass
            def do_POST(self) -> None:
                request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path=='/v1/systemone':
                    initial_repair_hold=mode=='repair-read' and not any(x['kind']=='semantic' for x in observations)
                    answers={}
                    for key,q in request['questions'].items():
                        if q['type']=='noul':answers[key]={'type':'noul','noul':1}
                        else:
                            label='unclear' if (mode=='held' or initial_repair_hold) and 'unclear' in q['criteria'] else next(x for x in ('compatible','same','grounded','authorized','faithful','lasting') if x in q['criteria'])
                            answers[key]={'type':'choice','choice':label,'confidence':1,'probabilities':{x:int(x==label) for x in q['criteria']}}
                    data=json.dumps({'model':'jev-1.13.0','answers':answers,'usage':{'input_tokens':1,'output_tokens':1}}).encode();observations.append({'kind':'semantic','wireSha256':hashlib.sha256(json.dumps(request).encode()).hexdigest()});self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
                if self.path!='/v1/chat/completions':self.send_error(403);return
                task=message_text(request)
                if 'harness-consolidation-plan' not in task:self.send_error(403);return
                if mode=='repair-read' and 'Task: repair ONE rejected harness consolidation plan.' in task:
                    tool_results={x.get('tool_call_id'):x for x in request['messages'] if x.get('role')=='tool'}
                    if 'repair-snapshot' not in tool_results:
                        snapshot=field(task,'snapshotPath')
                        observations.append({'kind':'repair-snapshot-request','pathSha256':hashlib.sha256(snapshot.encode()).hexdigest()})
                        stream_response(self,[{'id':'repair-snapshot','name':'learning_read','arguments':{'path':snapshot}}]);return
                    if 'repair-unrelated' not in tool_results:
                        content=json.dumps(tool_results['repair-snapshot'].get('content',''))
                        observations.append({'kind':'repair-snapshot-result','readOriginal':text in content and 'outside the parent-approved scope' not in content})
                        stream_response(self,[{'id':'repair-unrelated','name':'learning_read','arguments':{'path':str(agent/'unapproved.txt')}}]);return
                    content=json.dumps(tool_results['repair-unrelated'].get('content',''))
                    observations.append({'kind':'repair-unrelated-result','refused':'outside the parent-approved scope' in content})
                rule={**prior,'enabled':False} if mode=='retire' else {**prior,'bash':r'^npm\s+test(?:\s|$)','message':'Only npm test commands are prohibited; npm --version is allowed.'}
                answer={'kind':'harness-consolidation-plan','version':1,'schemaVersion':1,'runId':field(task,'runId'),'scopeDigest':field(task,'scopeDigest'),'artifactHash':field(task,'artifactHash'),'operations':[{'op':'updateRule','rule':rule,'correction':{'eventIndex':0,'quote':text,'priorRevision':revision},'cases':{'positive':[{'bash':'npm test','expected':'execute' if mode=='retire' else 'block'}],'negative':[{'bash':'pnpm test'},{'bash':'printf npm test'}]+([] if mode=='retire' else [{'bash':'npm --version'}])}}],'evidence':[{'index':0,'eventIndex':0,'source':'user','quote':text,'count':1}]}
                observations.append({'kind':'planner'});stream_response(self,json.dumps(answer))
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever);thread.start();url=f'http://127.0.0.1:{server.server_port}'
        try:
            (agent/'models.json').write_text(json.dumps({'providers':{'early-worker':{'baseUrl':url+'/v1','api':'openai-completions','apiKey':'offline-fixture','models':[{'id':'deterministic','name':'Offline worker','reasoning':False,'input':['text'],'contextWindow':1000000,'maxTokens':16000,'cost':{'input':0,'output':0,'cacheRead':0,'cacheWrite':0}}]}}}))
            (agent/'memory.json').write_text(json.dumps({'provider':'early-worker','model':'deterministic'}));(agent/'settings.json').write_text(json.dumps({'packages':[],'extensions':[],'skills':[],'retry':{'enabled':False}}));(agent/'continual-learning.json').write_text(json.dumps({'jev':{'apiKey':'offline-fixture','scopes':['harness']},'plannerJsonOutput':True}));(agent/'memory/settings.json').write_text(json.dumps({'autoMemory':True,'automaticPhases':{'memory':'off','harness':'apply','agents':'off'}}))
            env=isolated_environment(root,agent);env.update(CL_EARLY_FIXTURE_URL=url,CL_EARLY_FIXTURE_OUTPUT=str(root/'result.json'),CL_EARLY_FIXTURE_WRITE_PROBE='2' if mode=='shadow-write' else str(int(mode=='ordinary-write')))
            command=[pi,'--no-extensions','--no-skills','--no-prompt-templates','--no-themes','--no-context-files','--no-approve','--extension',str(fixture),'--provider','early-harness-native-fixture','--model','deterministic','--thinking','off','--tools','bash,write','--print','--mode','json',text]
            run=subprocess.run(command,cwd=cwd,env=env,capture_output=True,text=True,timeout=70);(root/'stdout.jsonl').write_text(run.stdout);(root/'stderr.txt').write_text(run.stderr)
            assert run.returncode==0 and (root/'result.json').exists(),(mode,run.returncode,run.stderr)
            result=json.loads((root/'result.json').read_text());(root/'wire-observations.json').write_text(json.dumps(observations,indent=2));assert any(x['kind']=='semantic' for x in observations),(mode,observations,result)
            at_main=result['atMain'];assert bool(result['results']),(mode,result);message=result['results'][-1]['message'];body=json.dumps(message['content']);executed=not message.get('isError',False) and __import__('re').search(r'\d+\.\d+\.\d+',body) is not None
            if mode=='held':assert at_main==original and not executed,(mode,result)
            else:assert at_main!=original and executed,(mode,result)
            if mode in ('ordinary-write','shadow-write'):assert len(result['writeResults'])==1 and result['writeResults'][0]['message']['isError'] is True,result
            if mode=='shadow-write':assert not (cwd/'.pi/harness.local.json').exists(),'Owned-rule shadow must not be written'
            if mode=='repair-read':
                assert any(x['kind']=='repair-snapshot-result' and x['readOriginal'] for x in observations),observations
                assert any(x['kind']=='repair-unrelated-result' and x['refused'] for x in observations),observations
            assert at_main==json.loads((cwd/'.pi/harness.json').read_text()),'No late policy change may substitute for pre-execution correction'
            receipts=[json.loads(x.read_text()) for x in agent.rglob('learning-pipeline-receipt.json')];assert len(receipts)==1 and receipts[0]['mode']=='automatic' and not receipts[0].get('input',{}).get('backlogId'),receipts
            rows.append({'mode':mode,'executedVersion':executed,'operations':receipts[0]['operations'],'httpRequests':len(observations),'externalRequests':0})
        finally:server.shutdown();server.server_close();thread.join()
    assert hashes=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'Source drift'
    (output/'manifest.json').write_text(json.dumps({'status':'passed','piVersion':version,'sourceHashes':hashes,'rows':rows,'externalRequests':0,'learningBenefitEstablished':False},indent=2));print(json.dumps({'outputDir':str(output),'status':'passed','rows':rows}))
if __name__=='__main__':main()
