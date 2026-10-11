"""Manually run the frozen eight-pair post-draft study; no work on import."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import uuid
import run


def sha(file: Path) -> str:
    return hashlib.sha256(file.read_bytes()).hexdigest()


def runtime_tree(root: Path) -> str:
    """Bind exported files and symlink targets to the verified runtime image."""
    digest=hashlib.sha256()
    for file in sorted(root.rglob('*')):
        relative=str(file.relative_to(root))
        if file.is_symlink(): value='link:'+os.readlink(file)
        elif file.is_file(): value='file:'+sha(file)
        elif file.is_dir(): value='directory'
        else: raise ValueError(f'Unexpected runtime entry: {relative}')
        digest.update(json.dumps([relative,value]).encode())
    return digest.hexdigest()


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    args=parser.parse_args(); root=args.root.resolve()
    manifest=json.loads((root/'manifest.json').read_text())
    if manifest['status'] not in {'frozen_before_postfix_inference','running'}:
        raise ValueError('Unexpected experiment state')
    assert sha(run.HERE/manifest.get('protocolFile','POSTFIX.md'))==manifest['protocolSha256']
    for relative,digest in manifest['sourceSha256'].items():
        assert sha(run.REPO/relative)==digest,relative
    for filename,digest in manifest['packageSha256'].items():
        assert sha(root/filename)==digest,filename
    for filename,digest in manifest['inputSha256'].items():
        assert sha(root/filename)==digest,filename
    actual=json.loads(run.command(['docker','image','inspect',manifest['runtimeImage']]).stdout)[0]
    assert actual['Id']==manifest['runtimeId']
    run.RUNTIME_IMAGE=manifest['runtimeId']
    runtime=root/'runtime'
    runtime_receipt=root/'runtime-export.json'
    if runtime.exists():
        exported=json.loads(runtime_receipt.read_text())
        assert exported['runtimeId']==manifest['runtimeId']
        assert exported['treeSha256']==runtime_tree(runtime)
    else:
        name='postfix-runtime-export-'+uuid.uuid4().hex[:8]
        temporary=root/('runtime-export-'+uuid.uuid4().hex[:8])
        run.command(['docker','create','--name',name,run.RUNTIME_IMAGE])
        try:
            run.command(['docker','cp',f'{name}:/opt/pilot-runtime',str(temporary)],timeout=180)
            tree=runtime_tree(temporary)
            temporary.rename(runtime)
            run.save(runtime_receipt,{'runtimeId':manifest['runtimeId'],'treeSha256':tree})
        finally: run.command(['docker','rm',name])
    rows=json.loads((root/'sample-private.json').read_text())
    scripts=json.loads((root/'eval-private.json').read_text())
    results_file=root/'results.json'
    results=json.loads(results_file.read_text()) if results_file.exists() else []
    manifest['status']='running';run.save(root/'manifest.json',manifest)
    for index in manifest['executionOrder']:
        row=dict(rows[index]);frozen=manifest['tasks'][index];task=row['instance_id']
        assert task==frozen['task']
        seed=root/'inputs'/task/'draft.patch'; assert sha(seed)==frozen['draftSha256']
        row['image_name']=frozen['image']['id']
        pair=root/'pairs'/task;pair.mkdir(parents=True,exist_ok=True)
        existing=run.command(['docker','image','inspect',row['image_name']],check=False)
        pulled=existing.returncode!=0
        if pulled:
            print(f'PULL {task} {frozen["image"]["digest"]}',flush=True)
            fetched=run.command(['docker','pull','--platform','linux/amd64',frozen['image']['digest']],timeout=1800)
            (pair/'pull.log').write_text(fetched.stdout+fetched.stderr)
        observed=json.loads(run.command(['docker','image','inspect',row['image_name']]).stdout)[0]
        assert observed['Id']==frozen['image']['id'] and frozen['image']['digest'] in observed['RepoDigests']
        run.save(pair/'image-provenance.json',observed)
        try:
            for arm in (('baseline','e2e') if index%2==0 else ('e2e','baseline')):
                output=pair/arm
                receipt=output/'attempt.json'
                if output.exists() and not receipt.exists():
                    raise RuntimeError(f'Interrupted start needs explicit audit, never silent retry: {output}')
                if receipt.exists():
                    attempt=json.loads(receipt.read_text())
                else:
                    print(f'RUN {task} {arm}',flush=True)
                    attempt=run.run_arm(row,arm,runtime,root/'pairs',seed_patch=seed,postfix_strategy='e2e' if arm=='e2e' else 'review',workflow_version=manifest.get('workflowVersion',1),resume_from=(root/frozen["resumeFrom"]) if arm=="baseline" and frozen.get("resumeFrom") else None)
                if manifest.get('workflowVersion') == 2:
                    assert attempt.get('workflowVersion') == 2, 'V2 did not reach model result capture; audit infrastructure failure'
                patch=output/'model.patch'
                # Grade captured final work even when a shared budget yielded no
                # repair response. Keep workflow completion separate from patch score.
                if attempt.get('patchCaptured') and patch.exists():
                    assert sha(patch)==attempt['patchSha256']
                    grade_receipt=output/'grade/result.json'
                    if not grade_receipt.exists():
                        print(f'GRADE {task} {arm}',flush=True)
                        attempt['grade']=run.grade(row,scripts[task]['eval_script'],patch.read_text(),output/'grade')
                    else: attempt['grade']=json.loads(grade_receipt.read_text())
                run.save(receipt,attempt)
                results=[r for r in results if (r['instance_id'],r['arm'])!=(task,arm)]
                results.append({'instance_id':task,**attempt});run.save(results_file,results)
                print(json.dumps({'task':task,'arm':arm,'validRepair':attempt.get('validInference'),'requests':attempt.get('inferenceRequests'),'grade':attempt.get('grade'),'workflowIncomplete':attempt.get('workflowIncomplete'),'infrastructureError':attempt.get('infrastructureError')}),flush=True)
            attempts=[json.loads((pair/a/'attempt.json').read_text()) for a in ('baseline','e2e')]
            starts=[a.get('startingDraftSha256') for a in attempts]
            run.save(pair/'pair-validity.json',{'sameCapturedStart':bool(starts[0]) and starts[0]==starts[1],'hashes':starts,'frozenSeedSha256':frozen['draftSha256']})
            if not starts[0] or starts[0]!=starts[1]:
                raise RuntimeError(f'Starting draft mismatch or incomplete setup: {task}')
        finally:
            # Only an exact image newly pulled by this study is a disposable
            # artifact; never prune, force deletion, or remove preexisting images.
            if pulled:
                removed=run.command(['docker','image','rm',frozen['image']['digest']],check=False)
                (pair/'own-image-cleanup.log').write_text(removed.stdout+removed.stderr)
    manifest['status']='attempts_and_grades_finished';run.save(root/'manifest.json',manifest)
    print(f'ALL_{len(manifest["executionOrder"])}_PAIRS_FINISHED',flush=True)


if __name__=='__main__':
    main()
