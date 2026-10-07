"""Once-only EN/ZH whole/subset study; fixed main generation, real bounded Jev."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import threading
import time


def run_child(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    # uv may spawn Python, which may spawn Docker. Own the entire local group.
    child=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    try:
        stdout,stderr=child.communicate(timeout=150)
        return subprocess.CompletedProcess(command,child.returncode,stdout,stderr)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid,signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.communicate(timeout=10)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--mock-endpoint')
    parser.add_argument('--request-proof',type=Path)
    parser.add_argument('--study', choices=['whole-subset','composed'], default='whole-subset')
    options = parser.parse_args()
    root = options.root.resolve();root.mkdir(parents=True,exist_ok=False)
    key = 'host-only-fixture' if options.mock_endpoint else os.environ.get('TYPESAFE_API_KEY','').strip()
    assert key, 'No TypeSafe host credential; do not substitute fixture inference'
    native = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location('jev_proxy',native/'jev-proxy.py');assert spec and spec.loader
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    owner_spec=importlib.util.spec_from_file_location('owned_containers',native/'owned-containers.py');assert owner_spec and owner_spec.loader
    owned=importlib.util.module_from_spec(owner_spec);owner_spec.loader.exec_module(owned)
    token = secrets.token_urlsafe(32)
    composed = options.study == 'composed'
    budget = 40 if composed else 24
    arms = ['jev-composed-original','jev-composed'] if composed else ['jev-whole','jev-subset']
    allowed_requests = None
    request_proof_hash = None
    if composed and not options.mock_endpoint:
        assert options.request_proof, 'Real composed study requires prior public request proof'
        preflight_manifest_file = options.request_proof.parent/'real-study-manifest.json'
        preflight_manifest = json.loads(preflight_manifest_file.read_text())
        assert preflight_manifest.get('realJev') is False and preflight_manifest.get('study') == 'composed'
        assert preflight_manifest.get('model') == 'jev-1.13.0' and preflight_manifest.get('sdkVersion') == '0.6.0'
        assert preflight_manifest.get('codeHashes') and all(hashlib.sha256(Path(file).read_bytes()).hexdigest()==digest for file,digest in preflight_manifest['codeHashes'].items()), 'Preflight source bytes changed'
        proof_bytes = options.request_proof.read_bytes()
        proof = json.loads(proof_bytes)
        assert isinstance(proof.get('requests'),list) and proof['requests']
        allowed_requests = {row['canonicalRequestSha256'] for row in proof['requests']}
        assert len(allowed_requests) <= 40 and all(isinstance(value,str) and module.re.fullmatch(r'[a-f0-9]{64}',value) for value in allowed_requests)
        assert all(row.get('status') == 200 and row.get('actualModel') == 'jev-1.13.0' for row in proof['requests'])
        request_proof_hash = hashlib.sha256(proof_bytes).hexdigest()
    proxy = module.BoundedJevProxy(key,token,options.mock_endpoint or 'https://api.typesafe.ai/v1/systemone', max_requests=budget, allow_readiness=composed, allowed_requests=allowed_requests)
    server = proxy.create_server()
    repo = native.parents[3]
    package = native.parents[1]
    kit = repo/'packages/kit'
    sdk = package/'node_modules/@typesafe-ai/sdk'
    assert json.loads((sdk/'package.json').read_text())['version'] == '0.6.0'
    image = json.loads(subprocess.run(['docker','image','inspect','continual-learning-projects:df60a6123748956b'],capture_output=True,text=True,check=True,timeout=10).stdout)[0]['Id']
    if allowed_requests is not None:
        assert preflight_manifest['imageId'] == image, 'Preflight image changed'
    files = [package/'index.ts',package/'package.json',*sorted((package/'extensions').glob('*.ts')),
        *sorted(file for folder in ['prompts','scripts'] for file in (package/folder).rglob('*') if file.is_file()),
        package/'tests/composed-native-real-study-plan.md',kit/'index.ts',kit/'package.json',*sorted(file for file in (kit/'src').rglob('*') if file.is_file()),
        *sorted(file for file in native.glob('*') if file.is_file()),sdk/'package.json',sdk/'dist/index.mjs',repo/'pnpm-lock.yaml']
    code_hashes = {str(file):hashlib.sha256(file.read_bytes()).hexdigest() for file in files}
    def verify_frozen() -> None:
        assert all(hashlib.sha256(Path(file).read_bytes()).hexdigest()==digest for file,digest in code_hashes.items()), 'Frozen native study sources changed'
        if options.request_proof:
            assert hashlib.sha256(options.request_proof.read_bytes()).hexdigest()==request_proof_hash, 'Frozen request proof changed'
    manifest = {'createdAtUtc':datetime.now(timezone.utc).isoformat(),'model':'jev-1.13.0','sdkVersion':'0.6.0',
        'mainGeneration':'fixed; no main model inference','realJev':not bool(options.mock_endpoint),
        'codeHashes':code_hashes,'imageId':image,'requestProofSha256':request_proof_hash,'allowedRequestHashes':sorted(allowed_requests or []),
        'study':options.study,'arms':[language+'-'+arm for language in ['en','zh'] for arm in arms],'maxRequests':budget,'retry':0,
        'maximumInputTokens':budget*64000,'estimatedMaximumUsd':budget*64000*.042/1000000,'pricingSource':'https://docs.typesafe.ai/models',
        'labels':{'eligible':['tools.md','license.md'],'ineligible':['cache.md']},'labelAuthority':'author-defined synthetic fixture; not independent or unseen evaluation',
        'fixtureHashes':{file.name:hashlib.sha256(file.read_bytes()).hexdigest() for file in native.glob('*') if file.is_file()},
        'ordinaryConfigGateRemainsOff':True,'completeGoalEvidence':False}
    (root/'real-study-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    threading.Thread(target=server.serve_forever,daemon=True).start()
    rows=[]
    study_started=time.monotonic()
    env={**os.environ,'CL_NATIVE_REAL_JEV_PROXY_URL':f'http://host.docker.internal:{server.server_port}/v1/systemone','CL_NATIVE_PROXY_TOKEN':token}
    try:
        for language in ['en','zh']:
            for arm in arms:
                verify_frozen()
                case=root/(language+'-'+arm)
                case_started=time.monotonic()
                timed_out=False
                try:
                    result=run_child(['uv','run','--no-project','python',str(native/'run-independent-memory.py'),'--root',str(case),'--arms',arm,'--language',language,'--real-jev','--image',image],env)
                except subprocess.TimeoutExpired:
                    timed_out=True
                    result=subprocess.CompletedProcess([],124,'','Native runner timed out; parent ownership cleanup required')
                finally:
                    cleanup=owned.cleanup_manifest(case)
                    creation_unknown=timed_out or any(json.loads(file.read_text()).get('creationOutcomeUnknown') for file in case.glob('*/cleanup.json'))
                    # A runner failure before recording create completion is also uncertain.
                    creation_unknown=creation_unknown or (result.returncode!=0 and any(not (Path(plan['evidenceRoot'])/'launch-inspect.json').exists() for plan in cleanup))
                    (root/(case.name+'-parent-cleanup.json')).write_text(json.dumps({'timedOut':timed_out,'containers':cleanup,
                        'lateDaemonCreationUnverified':creation_unknown,'finalAbsenceProven':not creation_unknown},indent=2)+'\n')
                (root/(case.name+'-launch.json')).write_text(json.dumps({'exitCode':result.returncode,'stdout':result.stdout,'stderr':result.stderr},indent=2)+'\n')
                row={'language':language,'arm':arm,'exitCode':result.returncode,'wallDurationMs':round((time.monotonic()-case_started)*1000)}
                result_path=case/arm/'result.json'
                if result_path.exists():
                    value=json.loads(result_path.read_text());pipeline=value['pipeline'];written=set(pipeline['privateFiles'])-{'MEMORY.md'}
                    row.update({'applied':sorted(written),'eligibleApplied':len(written&{'tools.md','license.md'}),'ineligibleApplied':len(written&{'cache.md'}),
                        'eligibleHeld':len({'tools.md','license.md'}-written),'operations':pipeline['receipt']['operations'],
                        'attempts':pipeline['receipt']['attempts'],'pipelineContextInjectionVerified':json.loads((case/'study-result.json').read_text())['rows'][0]['parentAssertionsPassed']})
                rows.append(row);print(json.dumps({key:value for key,value in row.items() if key!='attempts'}),flush=True)
    finally:
        server.shutdown()
        deadline=time.monotonic()+12
        while proxy.active and time.monotonic()<deadline:time.sleep(.05)
        server.server_close()
        (root/'proxy-result.json').write_text(json.dumps({'requests':proxy.rows,'active':proxy.active,'capRejected':proxy.rejected},indent=2)+'\n')
    verify_frozen()
    summary={'manifestSha256':hashlib.sha256((root/'real-study-manifest.json').read_bytes()).hexdigest(),'rows':rows,
        'proxyRequests':len(proxy.rows),'realJev':not bool(options.mock_endpoint),'mainInference':False,'fullPluginQualityImprovementProven':False,
        'inputTokensKnown':sum((row.get('usage') or {}).get('input_tokens') or 0 for row in proxy.rows),
        'usageComplete':all(type((row.get('usage') or {}).get(key)) is int for row in proxy.rows for key in ['input_tokens','output_tokens']),
        'realInferenceResponses':0 if options.mock_endpoint else sum(row.get('status')==200 and row.get('actualModel')=='jev-1.13.0' for row in proxy.rows),
        'actualModels':sorted({row['actualModel'] for row in proxy.rows if row.get('actualModel')}),
        'durationMs':sum(row.get('durationMs',0) for row in proxy.rows),'capRejected':proxy.rejected,'remoteCompletionUnknown':proxy.active > 0 or any(not row.get('completed') or row.get('remoteCompletionUnknown') for row in proxy.rows),'wallDurationMs':round((time.monotonic()-study_started)*1000)}
    summary['pricedInputTokensKnown']=sum((row.get('usage') or {}).get('input_tokens') or 0 for row in proxy.rows if row.get('actualModel')=='jev-1.13.0')
    summary['unpricedInputTokensKnown']=summary['inputTokensKnown']-summary['pricedInputTokensKnown']
    summary['estimatedKnownInputCostUsd']=summary['pricedInputTokensKnown']*.042/1000000
    (root/'real-study-result.json').write_text(json.dumps(summary,indent=2)+'\n')
    assert all(row['exitCode']==0 and row.get('pipelineContextInjectionVerified') for row in rows), 'Native workflow failed; preserve original cases'


if __name__=='__main__':main()
