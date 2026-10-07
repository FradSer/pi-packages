import importlib.util
import json
from pathlib import Path
import subprocess
from typing import Any

import pytest

spec=importlib.util.spec_from_file_location('native_owned_containers',Path(__file__).parent/'native/owned-containers.py')
assert spec and spec.loader
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
PLAN={'name':'fixture-owned','owner':'frozen-study','imageId':'sha256:fixture','evidenceRoot':'/fixture/evidence'}


def test_parent_recovers_owned_container_without_child_cid_and_refuses_wrong_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path/'study-manifest.json').write_text(json.dumps({'containerPlans':[PLAN]}))
    calls: list[list[str]]=[]
    present=True
    owner='wrong-study'

    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal present
        assert kwargs['timeout']==10
        calls.append(args)
        if args[1]=='inspect':
            if not present:
                return subprocess.CompletedProcess(args,1,'','No such object')
            info={'Name':'/fixture-owned','Image':'sha256:fixture','Config':{'Labels':{'pi.continual-learning.study':owner},'Cmd':['python3','/evidence/native.py']},
                  'Mounts':[{'Source':'/fixture/evidence','Destination':'/evidence'}],'State':{'Running':True}}
            return subprocess.CompletedProcess(args,0,json.dumps([info]),'')
        if args[1]=='rm':
            present=False
        return subprocess.CompletedProcess(args,0,'','')

    monkeypatch.setattr(module.subprocess,'run',run)
    with pytest.raises(AssertionError,match='wrong study owner'):
        module.cleanup_manifest(tmp_path)
    assert [args[1] for args in calls]==['inspect'] and present
    owner='frozen-study';calls.clear()
    value=module.cleanup_manifest(tmp_path)
    assert value[0]['status']=='removed'
    assert [args[1] for args in calls]==['inspect','stop','rm','inspect'] and not present
    assert module.cleanup_manifest(tmp_path)[0]['status']=='absent'


def test_parent_without_prospective_manifest_never_attempts_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected(*args: Any, **kwargs: Any) -> None:
        raise AssertionError('No declared ownership')
    monkeypatch.setattr(module.subprocess,'run',unexpected)
    assert module.cleanup_manifest(tmp_path)==[]


def test_docker_lowercase_missing_object_is_confirmed_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module.subprocess,'run',lambda *args,**kwargs:subprocess.CompletedProcess(args,1,'[]','error: no such object: fixture-owned'))
    assert module.inspect('fixture-owned') is None


def test_timeout_terminates_runner_process_group_before_ownership_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    native=Path(__file__).parent/'native/run-real-jev-parent.py'
    spec=importlib.util.spec_from_file_location('native_real_parent',native);assert spec and spec.loader
    parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
    events: list[str]=[]

    class Child:
        pid=12345

        def communicate(self,timeout: int) -> tuple[str,str]:
            events.append('communicate-'+str(timeout))
            if timeout==150:
                raise subprocess.TimeoutExpired(['fixture'],timeout)
            return ('','')

    def launch(*args: Any, **kwargs: Any) -> Child:
        assert kwargs['start_new_session']
        return Child()

    monkeypatch.setattr(parent.subprocess,'Popen',launch)
    monkeypatch.setattr(parent.os,'killpg',lambda pid,signal:events.append('kill-group-'+str(pid)))
    with pytest.raises(subprocess.TimeoutExpired):
        parent.run_child(['fixture'],{})
    assert events==['communicate-150','kill-group-12345','communicate-10']
