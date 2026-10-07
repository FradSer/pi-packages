"""Network-disabled native parent workflow with fixed SDK/main responses only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

expected = json.loads(Path('/evidence/source-manifest.json').read_text())['sourceHashes']

def verify_sources() -> dict[str, str]:
    actual = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in expected}
    assert actual == expected, 'Native source hashes changed'
    return actual

before = verify_sources()
sdk_version = json.loads(Path('/opt/experiment/packages/continual-learning/node_modules/@typesafe-ai/sdk/package.json').read_text())['version']
assert sdk_version=='0.6.0', sdk_version
agent = Path('/tmp/agent'); agent.mkdir()
project = Path('/tmp/project'); project.mkdir()
subprocess.run(['git', 'init', '-q', str(project)], check=True)
(project / 'AGENTS.md').write_text('Keep existing instructions unchanged.\n')
(agent / 'settings.json').write_text(json.dumps({'packages': []}))
(agent / 'memory').mkdir()
(agent / 'memory/settings.json').write_text(json.dumps({'autoMemory': False, 'automaticPhases': {'memory':'off','harness':'off','agents':'off'}}))
arm = os.environ['CL_NATIVE_ARM']
(agent / 'continual-learning.json').write_text(json.dumps({'jev': False if arm == 'jev-off' else {'model':'jev-1.13.0','scopes':['memory']}}))
state: dict[str, Any] = {'requests': []}
language = os.environ.get('CL_NATIVE_LANGUAGE','en')
quote = '请记住：这个项目使用 pnpm，许可证是 MIT。一次缓存超时在重试后恢复了。' if language == 'zh' else 'Remember: this project uses pnpm. Its license is MIT. A cache timeout cleared on retry.'

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args: Any) -> None:
        pass

    def do_POST(self) -> None:
        request = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
        # The native worker identity is frozen by the parent, not synthesized by
        # the fixture server. Fixed candidate content never depends on arm.
        manifests = sorted((agent/'memory/runs').glob('*/run_*/manifest.json'))
        plan_request = any('incremental-memory-plan' in json.dumps(message) or 'repair one rejected incremental Memory delta plan' in json.dumps(message) for message in request['messages'])
        if plan_request:
            assert manifests, 'Planner has no parent manifest'
            manifest = json.loads(manifests[-1].read_text())
            facts = [('tools.md','这个项目使用 pnpm。'),('cache.md','缓存服务永久不可用。'),('license.md','许可证是 MIT。')] if language == 'zh' else [('tools.md','This project uses pnpm.'),('cache.md','Cache service is permanently unavailable.'),('license.md','Its license is MIT.')]
            content = json.dumps({'kind':'incremental-memory-plan','version':1,'schemaVersion':1,
                **{k:manifest[k] for k in ['runId','scopeKey','scopeDigest','snapshotDigest']},
                'artifactHash':manifest['snapshotDigest'],'operations':[],
                'newMemories':[{'name':name,'kind':'project','classification':'safe',
                    'content':f'---\nname: {name[:-3]}\ndescription: {body}\ntype: project\n---\n{body}\n',
                    'evidence':[{'index':0,'quote':quote}]} for name,body in facts]})
        else:
            content = 'Fixed native parent workflow complete.'
        request_text = json.dumps(request['messages'],ensure_ascii=False)
        state['requests'].append({'model':request.get('model'),'plannerFixture':plan_request,
            'containsPnpmMemory':('这个项目使用 pnpm。' if language == 'zh' else 'This project uses pnpm.') in request_text,
            'containsMITMemory':('许可证是 MIT。' if language == 'zh' else 'Its license is MIT.') in request_text,
            'containsPermanentFailureClaim':('缓存服务永久不可用。' if language == 'zh' else 'Cache service is permanently unavailable.') in request_text})
        values = [{'id':'fixture','object':'chat.completion.chunk','created':0,'model':'fixed','choices':[{'index':0,'delta':{'role':'assistant','content':content},'finish_reason':None}]},
                  {'id':'fixture','object':'chat.completion.chunk','created':0,'model':'fixed','choices':[{'index':0,'delta':{},'finish_reason':'stop'}]}]
        data = (''.join('data: '+json.dumps(value)+'\n\n' for value in values)+'data: [DONE]\n\n').encode()
        self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)

server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
(agent/'models.json').write_text(json.dumps({'providers':{'cl-fixture':{'baseUrl':f'http://127.0.0.1:{server.server_port}/v1','apiKey':'fixture-only','api':'openai-completions','models':[{'id':'fixed','name':'Fixed workflow responses','reasoning':False,'input':['text'],'cost':{'input':0,'output':0,'cacheRead':0,'cacheWrite':0},'contextWindow':64000,'maxTokens':1024}]}}}))
env = {**os.environ,'PI_CODING_AGENT_DIR':str(agent),'TYPESAFE_API_KEY':'fixture-only','HOME':'/tmp/home'}
Path(env['HOME']).mkdir()
pi = '/opt/experiment/node_modules/.bin/pi'
version = subprocess.run([pi,'--version'],env=env,capture_output=True,text=True,check=True).stdout.strip()
command = [pi,'--offline','--no-extensions','-e','/evidence/probe.ts','--no-skills','--no-prompt-templates','--no-themes','--no-context-files','--session','/evidence/session.jsonl','--model','cl-fixture/fixed','--print','--mode','json','What package manager and license does this project use?' ]
try:
    result = subprocess.run(command,cwd=project,env=env,capture_output=True,text=True,timeout=90)
finally:
    server.shutdown(); server.server_close()
Path('/evidence/pi-stdout.txt').write_text(result.stdout)
Path('/evidence/pi-stderr.txt').write_text(result.stderr)
assert result.returncode == 0, (result.returncode,result.stderr)
pipeline = json.loads(Path('/evidence/pipeline-result.json').read_text())
after = verify_sources()
report = {'arm':arm,'sdkVersion':sdk_version,'piVersion':version,'piExitCode':result.returncode,'sourceHashesBefore':before,'sourceHashesAfter':after,
          'mainFixtureRequests':state['requests'],'pipeline':pipeline,'externalMainRequests':0,'externalJevRequests':None if os.environ.get('CL_NATIVE_REAL_JEV_PROXY_URL') else 0,'realMainInference':False,'realJevTransportConfigured':bool(os.environ.get('CL_NATIVE_REAL_JEV_PROXY_URL')),'learningQualityEvidence':False}
Path('/evidence/result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'arm':arm,'operations':pipeline['receipt']['operations'],'requests':state['requests']}))
