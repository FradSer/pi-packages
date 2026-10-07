"""Prospectively hashed native Pi fixture workflow. No external inference."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any


def digest(file: Path) -> str:
    return hashlib.sha256(file.read_bytes()).hexdigest()


def invoke(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=10, **kwargs)


def verify_case(value: dict[str, Any], arm: str, real: bool = False) -> None:
    pipeline = value['pipeline']
    expected = {'jev-off': {'tools.md','cache.md','license.md'}, 'jev-subset': {'tools.md','license.md'},
                'jev-whole': set(), 'jev-unavailable': set(), 'jev-composed': {'tools.md','license.md'}, 'jev-composed-original': set()}[arm]
    if real:
        expected = set(pipeline['privateFiles']) - {'MEMORY.md'}
        assert expected <= {'tools.md','cache.md','license.md'}
    for key in ['privateFiles','publicFiles']:
        assert set(pipeline[key]) - {'MEMORY.md'} == expected, (arm,key,pipeline[key])
    assert set(pipeline['bodies']) == expected
    assert all(body['private'] == body['public'] for body in pipeline['bodies'].values())
    assert pipeline['boundRequests'] and all(pipeline['boundRequests']), (arm,'Explicit request not bound')
    assert pipeline['agents'] == 'Keep existing instructions unchanged.\n' and not pipeline['harnessFiles']
    assert pipeline['receipt']['screen']['memory'] and not pipeline['receipt']['screen']['harness'] and not pipeline['receipt']['screen']['agents']
    proposals = [record.get('proposal') for record in pipeline['history'] if record['status']=='proposed']
    if real:
        if not expected:
            assert any([item['name'] for item in proposal.get('newMemories',proposal.get('originalPlan',{}).get('newMemories',[]))]==['tools.md','cache.md','license.md'] for proposal in proposals)
    elif arm in ['jev-subset','jev-composed']:
        assert len(proposals)==1 and proposals[0]['kind']=='independent-memory-review'
        assert [item['name'] for item in proposals[0]['originalPlan']['newMemories']]==['tools.md','cache.md','license.md']
        assert proposals[0]['eligibleIndexes']==[0,2] and proposals[0]['heldIndexes']==[1]
        assert sum(attempt.get('pendingOperations',0) for attempt in pipeline['receipt']['attempts'])==1
        assert sum(request['questionIds']==['relation'] for request in pipeline['fixtureRequests'])==3
        if arm=='jev-composed':
            assert sum(request['questionIds']==['ready'] for request in pipeline['fixtureRequests'])==3
            assert any(attempt.get('jev',{}).get('strategy')=='standalone-memory' for attempt in pipeline['receipt']['attempts'])
    elif arm != 'jev-off':
        assert any([item['name'] for item in proposal.get('newMemories',[])]==['tools.md','cache.md','license.md'] for proposal in proposals)
    else:
        assert not pipeline['fixtureRequests']
    if arm=='jev-unavailable':
        assert all(request['unavailable'] and request['returnedModel'] is None for request in pipeline['fixtureRequests'])
        assert any(attempt.get('jev',{}).get('reason')=='unavailable' for attempt in pipeline['receipt']['attempts'])
    recall = [request for request in value['mainFixtureRequests'] if not request['plannerFixture']]
    assert len(recall)==1
    assert recall[0]['containsPnpmMemory'] == ('tools.md' in expected)
    assert recall[0]['containsMITMemory'] == ('license.md' in expected)
    assert recall[0]['containsPermanentFailureClaim'] == ('cache.md' in expected)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--arms', nargs='+', choices=['jev-off','jev-whole','jev-subset','jev-unavailable','jev-composed','jev-composed-original'], default=['jev-off','jev-whole','jev-subset','jev-unavailable'])
    parser.add_argument('--language',choices=['en','zh'],default='en')
    parser.add_argument('--real-jev',action='store_true')
    parser.add_argument('--image', default='continual-learning-projects:df60a6123748956b')
    options = parser.parse_args()
    repo = Path(__file__).resolve().parents[4]
    package = repo/'packages/continual-learning'
    root = options.root.resolve(); root.mkdir(parents=True, exist_ok=False)
    source = package/'extensions/inject-memory.ts'
    old = 'const jevJudge = createJevJudge();'
    new = 'const jevJudge = createJevJudge({ independentMemoryApplication: ["jev-subset", "jev-composed", "jev-composed-original"].includes(process.env.CL_NATIVE_ARM ?? ""), composedMemoryApplication: process.env.CL_NATIVE_ARM === "jev-composed" });'
    assert source.read_text().count(old) == 1
    instrumented = root/'inject-memory-instrumented.ts'
    instrumented.write_text(source.read_text().replace(old,new))
    paths = [package/'index.ts', *sorted((package/'extensions').glob('*.ts'))]
    original = {str(file.relative_to(package)):digest(file) for file in paths}
    container_hashes = {'/opt/experiment/packages/continual-learning/'+str(file.relative_to(package)):digest(instrumented if file == source else file) for file in paths}
    kit = repo/'packages/kit'
    kit_paths = [kit/'index.ts',kit/'package.json',*sorted(file for file in (kit/'src').rglob('*') if file.is_file())]
    kit_hashes = {str(file.relative_to(kit)):digest(file) for file in kit_paths}
    container_hashes.update({'/opt/experiment/packages/kit/'+str(file.relative_to(kit)):digest(file) for file in kit_paths})
    sdk = package/'node_modules/@typesafe-ai/sdk'
    assert json.loads((sdk/'package.json').read_text())['version']=='0.6.0'
    for relative in ['package.json','dist/index.mjs']:
        container_hashes['/opt/experiment/packages/continual-learning/node_modules/@typesafe-ai/sdk/'+relative] = digest(sdk/relative)
    fixtures = Path(__file__).resolve().parent
    spec=importlib.util.spec_from_file_location('owned_containers',fixtures/'owned-containers.py');assert spec and spec.loader
    owned=importlib.util.module_from_spec(spec);spec.loader.exec_module(owned)
    image_id=json.loads(invoke(['docker','image','inspect',options.image]).stdout)[0]['Id']
    owner=hashlib.sha256((str(root)+digest(instrumented)).encode()).hexdigest()
    plans=[{'name':'cl-parent-'+arm+'-'+root.name.lower(),'owner':owner,'imageId':image_id,'evidenceRoot':str(root/arm)} for arm in options.arms]
    manifest = {'containerPlans':plans,'kind':'native-fixed-response-parent-study','createdAtUtc':datetime.now(timezone.utc).isoformat(),
        'arms':options.arms,'language':options.language,'mainModelInference':False,'jevInference':options.real_jev,'learningQualityEvidence':False,
        'sourceHashes':original,'kitSourceHashes':kit_hashes,'containerSourceHashes':container_hashes,
        'instrumentation':{'path':'extensions/inject-memory.ts','originalSha256':digest(source),'instrumentedSha256':digest(instrumented),'old':old,'new':new},
        'fixtureHashes':{f:digest(fixtures/f) for f in ['independent-memory-probe.ts','independent-memory-container.py','run-independent-memory.py']},
        'expectedOperations':{'jev-off':3,'jev-whole':0,'jev-subset':2,'jev-unavailable':0,'jev-composed':2,'jev-composed-original':0},
        'expectedSubsetFiles':['tools.md','license.md'],'heldOriginalFile':'cache.md',
        'productionGateDefaultChanged':False,'requestedRealMainModel':{'provider':'cli-proxy','model':'opencode/space-bunny-free'}}
    (root/'study-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    rows = []
    for arm in options.arms:
        evidence = root/arm; evidence.mkdir()
        shutil.copyfile(fixtures/'independent-memory-probe.ts',evidence/'probe.ts')
        shutil.copyfile(fixtures/'independent-memory-container.py',evidence/'native.py')
        (evidence/'source-manifest.json').write_text(json.dumps({'sourceHashes':container_hashes},indent=2)+'\n')
        plan=next(plan for plan in plans if plan['evidenceRoot']==str(evidence))
        name=plan['name']
        command = ['docker','create','--network','bridge' if options.real_jev else 'none','--read-only','--tmpfs','/tmp:rw,size=256m','--name',name,'--label','pi.continual-learning.study='+owner,'-e','CL_NATIVE_ARM='+arm,'-e','CL_NATIVE_LANGUAGE='+options.language,'-v',str(evidence)+':/evidence']
        if options.real_jev:
            assert os.environ.get('CL_NATIVE_REAL_JEV_PROXY_URL') and os.environ.get('CL_NATIVE_PROXY_TOKEN')
            command += ['-e','CL_NATIVE_REAL_JEV_PROXY_URL','-e','CL_NATIVE_PROXY_TOKEN']
        for part in ['index.ts','extensions','prompts','scripts']:
            command += ['-v',str(package/part)+':/opt/experiment/packages/continual-learning/'+part+':ro']
        for part in ['index.ts','src','package.json']:
            command += ['-v',str(kit/part)+':/opt/experiment/packages/kit/'+part+':ro']
        command += ['-v',str(instrumented)+':/opt/experiment/packages/continual-learning/extensions/inject-memory.ts:ro',options.image,'python3','/evidence/native.py']
        creation_unknown=False
        try:
            try:
                cid = invoke(command).stdout.strip()
            except subprocess.TimeoutExpired:
                creation_unknown=True
                raise
            info = json.loads(invoke(['docker','inspect',cid]).stdout)[0]
            image = json.loads(invoke(['docker','image','inspect',info['Image']]).stdout)[0]
            launch = {'containerId':cid,'name':name,'created':info['Created'],'observedAtUtc':datetime.now(timezone.utc).isoformat(),'state':info['State'],
                'imageId':info['Image'],'platform':{key:image[key] for key in ['Os','Architecture']},'networkMode':info['HostConfig']['NetworkMode'],
                'readOnlyRootfs':info['HostConfig']['ReadonlyRootfs'],'mounts':info['Mounts'],'command':info['Config']['Cmd']}
            assert launch['state']['Status']=='created' and launch['networkMode']==('bridge' if options.real_jev else 'none') and launch['readOnlyRootfs']
            (evidence/'launch-inspect.json').write_text(json.dumps(launch,indent=2)+'\n')
            result = subprocess.run(['docker','start','-a',cid],capture_output=True,text=True,timeout=120)
            (evidence/'launch-result.json').write_text(json.dumps({'exitCode':result.returncode,'stdout':result.stdout,'stderr':result.stderr},indent=2)+'\n')
            row = {'arm':arm,'exitCode':result.returncode,'resultPresent':(evidence/'result.json').exists()}
            if row['resultPresent']:
                value = json.loads((evidence/'result.json').read_text())
                row['operations']=value['pipeline']['receipt']['operations']
                try:
                    verify_case(value,arm,options.real_jev)
                    row['parentAssertionsPassed']=True
                except AssertionError as error:
                    row['parentAssertionsPassed']=False
                    row['parentAssertionFailure']=str(error)
                row['matchesPredictedOperations']=row['operations']==manifest['expectedOperations'][arm]
            rows.append(row)
            print(json.dumps(row),flush=True)
        finally:
            status=owned.cleanup(plan)
            (evidence/'cleanup.json').write_text(json.dumps({'status':status,'creationOutcomeUnknown':creation_unknown},indent=2)+'\n')
            if creation_unknown and status=='absent':
                raise RuntimeError('Creation outcome unknown; retain declared ownership and recheck, do not claim cleanup')

    assert {str(file.relative_to(package)):digest(file) for file in paths} == original
    assert {str(file.relative_to(kit)):digest(file) for file in kit_paths} == kit_hashes
    (root/'study-result.json').write_text(json.dumps({'manifestSha256':digest(root/'study-manifest.json'),'rows':rows,'ownedContainersAbsent':True,'qualityEvidence':False},indent=2)+'\n')
    assert all((options.real_jev or row.get('matchesPredictedOperations')) and row.get('parentAssertionsPassed') and row['exitCode']==0 for row in rows), rows


if __name__ == '__main__':
    main()
