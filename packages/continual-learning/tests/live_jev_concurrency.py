"""Offline actual Pi + loopback SDK configuration, complete-window and cancellation proof."""
from __future__ import annotations
import hashlib,json,os,shutil,subprocess,sys,tempfile,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
FIXTURE=Path(__file__).with_name('jev-concurrency-live-fixture.ts')
def main() -> None:
    output=Path(tempfile.mkdtemp(prefix='jev-native-concurrency-',dir=sys.argv[1] if len(sys.argv)>1 else None))
    source_files=[Path(__file__),FIXTURE,FIXTURE.parent.parent/'extensions/jev-learning.ts',FIXTURE.parent.parent/'extensions/config.ts']
    source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    pi=str(FIXTURE.parents[3]/'node_modules/.bin/pi')
    if not Path(pi).is_file():raise RuntimeError('Installed workspace Pi is required; do not substitute a global CLI')
    version=subprocess.run([pi,'--version'],capture_output=True,text=True,timeout=10,check=True).stdout.strip()
    observations=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args: object) -> None: pass
        def do_POST(self) -> None:
            if self.path!='/v1/systemone' or self.headers.get('Authorization')!='Bearer fixture':self.send_error(403);return
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<1_000_000:self.send_error(413);return
            body=self.rfile.read(size);r=json.loads(body)
            if r.get('model')!='jev-1.13.0':self.send_error(403);return
            observations.append({'wireHash':hashlib.sha256(body).hexdigest(),'questions':list(r['questions'])})
            answers={}
            for key,q in r['questions'].items():
                label='grounded' if key.startswith('supported') else 'compatible'
                answers[key]={'type':'choice','choice':label,'confidence':1,'probabilities':{x:int(x==label) for x in q['criteria']}}
            data=json.dumps({'model':'jev-1.13.0','answers':answers,'usage':{'input_tokens':1,'output_tokens':1}}).encode();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever);thread.start();rows=[]
    try:
        for concurrency,cancel in [(4,False),(1,False),(1,True)]:
            root=output/f'concurrency-{concurrency}-cancel-{cancel}';agent=root/'agent';agent.mkdir(parents=True);(agent/'continual-learning.json').write_text(json.dumps({'jev':{'requestConcurrency':concurrency}}));result=root/'result.json';start=len(observations)
            env={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL')};env.update(HOME=str(root),PI_CODING_AGENT_DIR=str(agent),PI_OFFLINE='1',JEV_FIXTURE_URL=f'http://127.0.0.1:{server.server_port}',JEV_FIXTURE_OUTPUT=str(result),JEV_FIXTURE_CANCEL=str(int(cancel)))
            command=[pi,'--no-session','--no-extensions','--no-skills','--no-prompt-templates','--no-themes','--no-context-files','--no-approve','--extension',str(FIXTURE),'--provider','jev-concurrency-fixture','--model','deterministic','--thinking','off','--no-builtin-tools','--print','Run offline fixture']
            run=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=60);(root/'stdout.txt').write_text(run.stdout);(root/'stderr.txt').write_text(run.stderr)
            assert run.returncode==0 and result.exists(),(run.returncode,run.stderr)
            row=json.loads(result.read_text());row.update(concurrency=concurrency,cancel=cancel,actualHttpRequests=len(observations)-start);rows.append(row)
            assert row['peak']<=concurrency and row['calls']==row['actualHttpRequests']
            telemetry=row['result']['telemetry']
            if cancel:assert row['calls']==1 and row['result']['decision']=='propose' and telemetry['reason']=='cancelled'
            else:assert row['result']['decision']=='allow' and telemetry['completedWindows']==telemetry['evidenceWindows']==2 and telemetry['coveredEntries']==telemetry['evidenceEntries']==2
        assert rows[0]['peak']>1 and rows[0]['calls']==rows[1]['calls']>=3
        assert source_hashes=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}, 'Fixture source changed'
        manifest={'status':'passed','piVersion':version,'sourceHashes':source_hashes,'externalRequests':0,'paidRequests':0,'rows':rows,'observations':observations,'learningBenefitEstablished':False};(output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps({'outputDir':str(output),'status':'passed','externalRequests':0}))
    finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':main()
