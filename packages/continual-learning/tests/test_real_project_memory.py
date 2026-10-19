"""Regression checks for invalid-training and check-integrity study gates."""
import json
import subprocess
import pytest
import live_real_project_memory as study


def test_original_root_type_tests_and_new_config_are_detected(tmp_path, monkeypatch):
    (tmp_path/'index.test-d.ts').write_text('original assertions')
    (tmp_path/'index.js').write_text('original production')
    (tmp_path/'tox.ini').write_text('[pytest]\ntestpaths=testing')
    monkeypatch.setattr(study,'checked',lambda args,**kw:subprocess.check_output(
        ['python3','-c',args[-2],str(tmp_path)]))
    before=study.protected('disposable','p-limit')
    assert 'index.js' not in before
    assert 'index.js' in study.protected('disposable','p-limit',include_source=True)
    (tmp_path/'index.test-d.ts').write_text('weakened assertions')
    assert study.protected('disposable','p-limit')['index.test-d.ts'] != before['index.test-d.ts']
    (tmp_path/'index.test-d.ts').write_text('original assertions')
    (tmp_path/'ava.config.js').write_text('export default {files: []}')
    assert study.protected('disposable','p-limit')['__configuration_paths__'] != before['__configuration_paths__']


def test_invalid_training_prevents_every_downstream_model_call(tmp_path, monkeypatch):
    class Proxy:
        selection={'provider':'test','model':'test'}
        def __init__(self,*a,**kw): pass
        def __enter__(self): return self
        def __exit__(self,*a): pass
    calls=[]
    monkeypatch.setenv('TYPESAFE_API_KEY','synthetic-test-key')
    monkeypatch.setattr(study,'InferenceProxy',Proxy)
    monkeypatch.setattr(study,'runtime_image',lambda:'test-image')
    monkeypatch.setattr(study,'checked',lambda *a,**kw:b'test-digest')
    monkeypatch.setattr(study,'prepare',lambda name,*a,**kw:{'project':name,'valid':False})
    monkeypatch.setattr(study,'candidate',lambda *a,**kw:calls.append(a))
    with pytest.raises(RuntimeError,match='Training gate failed'):
        study.run(tmp_path/'evidence',tmp_path,2)
    assert calls==[]
    manifest=json.loads(next((tmp_path/'evidence').glob('*/manifest.json')).read_text())
    assert manifest['status']=='failed'
    assert manifest['candidates']==[]


def test_resume_requires_matching_real_source_session_and_successful_source_checks(tmp_path):
    root=tmp_path/'prior';root.mkdir()
    (root/'manifest.json').write_text(json.dumps({'sourceUnchanged':True}))
    (root/'protocol.json').write_text(json.dumps({'projects':study.PROJECTS}))
    selection={'provider':'test','model':'real-model'}
    for project in study.PROJECTS:
        target=root/project; (target/'training').mkdir(parents=True)
        (target/'preparation.json').write_text(json.dumps({'training':{'exitCode':0,'modelErrors':0,'timedOut':False},'existingChecksPreserved':True,'trainingUpstreamPassed':True}))
        rows=[{'type':'session','cwd':'/work/'+project},{'type':'model_change','provider':'test','modelId':'real-model'},
              {'type':'message','message':{'role':'user','content':[{'type':'text','text':study.COMMON+study.PROJECTS[project]['training']}]}}]
        (target/'training/session.jsonl').write_text('\n'.join(map(json.dumps,rows))+'\n')
    resumed=study.resume_training(root,selection)
    assert set(resumed)==set(study.PROJECTS)
    assert all(len(row['digest'])==64 and row['session'] for row in resumed.values())
    session=root/'pluggy/training/session.jsonl'
    session.write_text(session.read_text()+json.dumps({'type':'message','message':{'role':'user','content':'future feature'}})+'\n')
    with pytest.raises(ValueError,match='source orientation'):
        study.resume_training(root,selection)


def test_resume_rejects_failed_source_integrity_and_changed_project_commit(tmp_path):
    root=tmp_path/'prior';root.mkdir()
    (root/'manifest.json').write_text(json.dumps({'sourceUnchanged':False}))
    (root/'protocol.json').write_text(json.dumps({'projects':study.PROJECTS}))
    with pytest.raises(ValueError,match='source'):
        study.resume_training(root,{'provider':'test','model':'test'})
    (root/'manifest.json').write_text(json.dumps({'sourceUnchanged':True}))
    (root/'protocol.json').write_text(json.dumps({'projects':{}}))
    with pytest.raises(ValueError,match='protocol'):
        study.resume_training(root,{'provider':'test','model':'test'})


def test_resume_turn_keeps_original_tool_evidence_in_product_task_slice():
    from support import run_bun
    arguments=study.model_prompt_arguments('Summarize the completed source orientation.',continuation=True)
    assert arguments[-1]=='continue'
    assert arguments[:1]==['--append-system-prompt']
    result=run_bun('''
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      const message=(role,content)=>({message:{role,content}});
      const slice=currentTaskSlice([message('user','Inspect actual source'),message('assistant',[{type:'toolCall',id:'read1',name:'read',arguments:{path:'src.py'}}]),
        message('toolResult','ORIGINAL_VERIFIED_SOURCE'),message('assistant','done'),message('user',%s),message('assistant','summary')]);
      console.log(JSON.stringify({count:slice.entries.length,hasSource:slice.entries.some(e=>e.message.content==='ORIGINAL_VERIFIED_SOURCE')}));
    ''' % json.dumps(arguments[-1]))
    assert result=={'count':6,'hasSource':True}


def test_resumed_learning_requires_original_tool_observations_in_one_dossier():
    user={'type':'message','message':{'role':'user','content':'inspect source'}}
    tool={'type':'message','message':{'role':'toolResult','content':'ACTUAL_SOURCE'}}
    session=('\n'.join(map(json.dumps,[user,tool]))+'\n').encode()
    dossier=lambda entries: {'taskSlice':{'entries':entries}}
    assert study.original_observations_preserved(session,[dossier([user,tool])])
    assert not study.original_observations_preserved(session,[dossier([user]),dossier([tool])])
    assert not study.original_observations_preserved(session,[dossier([user,{'type':'message','message':{'role':'assistant','content':'ACTUAL_SOURCE'}}])])


def test_continuation_summary_has_no_parent_tools_but_fresh_tasks_keep_tools(tmp_path, monkeypatch):
    # Given verified original observations, when only a final summary is needed,
    # then parent tool access is disabled rather than merely discouraged.
    class Proxy:
        selection={'provider':'test','model':'test'}
        key=jev_key=token=''
        def jev_environment(self): return {}
    captured=[]
    def execute(args, **kwargs):
        captured.append(args)
        return subprocess.CompletedProcess(args,0,b'',b'')
    monkeypatch.setattr(study,'process',execute)
    monkeypatch.setattr(study,'get',lambda *args:b'')
    study.run_model('disposable','pluggy','summary',Proxy(),tmp_path/'summary','training',continuation=True)
    assert '--no-tools' in captured[0]
    assert '--tools' not in captured[0]
    assert captured[0][-1]=='continue'
    study.run_model('disposable','pluggy','feature',Proxy(),tmp_path/'feature','task')
    assert '--no-tools' not in captured[1]
    index=captured[1].index('--tools')
    assert captured[1][index+1]=='read,bash,edit,write'


def test_documentation_updates_are_allowed_but_existing_type_tests_stay_protected(tmp_path, monkeypatch):
    # Given the feature contract allows documentation updates, when a model
    # updates another Markdown document, do not misclassify it as a test change.
    (tmp_path/'recipes.md').write_text('existing recipes')
    (tmp_path/'AGENTS.md').write_text('existing agent instructions')
    (tmp_path/'index.test-d.ts').write_text('original assertions')
    monkeypatch.setattr(study,'checked',lambda args,**kw:subprocess.check_output(
        ['python3','-c',args[-2],str(tmp_path)]))
    before=study.protected('disposable','p-limit')
    assert 'recipes.md' not in before
    assert 'AGENTS.md' in before and 'index.test-d.ts' in before
    assert 'recipes.md' in study.protected('disposable','p-limit',include_source=True)


def test_runtime_image_upgrades_cached_dependencies_to_pi13_before_admission(monkeypatch):
    # Given an old cached project image, When building a fresh cohort runtime,
    # Then install the pinned requested Pi before the study's version guard.
    from pathlib import Path
    files=[]
    def checked(args, **kwargs):
        if args[:2] == ['docker','build']:
            files.append({'dockerfile':(Path(args[-1])/'Dockerfile').read_text(), 'workspace':(Path(args[-1])/'pnpm-workspace.yaml').read_text()})
        return b'fixture-image'
    monkeypatch.setattr(study, 'checked', checked)
    study.runtime_image('historical-pi10-cache')
    assert len(files) == 1
    assert 'pnpm add --workspace-root --save-exact @earendil-works/pi-coding-agent@1.3.0 @earendil-works/pi-tui@1.3.0' in files[0]['dockerfile']
    assert files[0]['dockerfile'].index('COPY pnpm-workspace.yaml ./') < files[0]['dockerfile'].index('RUN pnpm add')
    assert '"@earendil-works/pi-coding-agent": 1.3.0' in files[0]['workspace']
    assert '"@earendil-works/pi-tui": 1.3.0' in files[0]['workspace']
    assert '1.0.0' not in files[0]['workspace']
    assert '"@earendil-works/pi-ai": 1.3.0' in files[0]['workspace']
    for package in ('pi-agent-core', 'pi-codemode', 'pi-mcp', 'pi-telemetry'):
        assert f'"@earendil-works/{package}": 1.3.0' in files[0]['workspace']
    baseline = (Path(study.__file__).parent/'docker/real-task.Dockerfile').read_text()
    assert '1.0.0' not in baseline
    assert '"@earendil-works/pi-ai":"1.3.0"' in baseline
    for package in ('pi-agent-core', 'pi-codemode', 'pi-mcp', 'pi-telemetry'):
        assert f'\\"@earendil-works/{package}\\": 1.3.0' in baseline
    import docker_experiment
    builds=[]
    def build(args, **kwargs):
        builds.append({'manifest':json.loads((Path(args[-1])/'package.json').read_text()),
                       'workspace':(Path(args[-1])/'pnpm-workspace.yaml').read_text()})
    monkeypatch.setattr(docker_experiment, 'command', build)
    original_copy = docker_experiment.shutil.copytree
    scratch_ignored = []
    def checked_copy(source, target, *args, **kwargs):
        if Path(source).name in {'kit', 'continual-learning'}:
            ignored = kwargs['ignore'](str(source), ['.jev-bound-scope-active', '.jev-description-active', 'jev-bound-scope-shadow.ts'])
            scratch_ignored.append(set(ignored))
        return original_copy(source, target, *args, **kwargs)
    monkeypatch.setattr(docker_experiment.shutil, 'copytree', checked_copy)
    docker_experiment.build_image()
    assert scratch_ignored and all(ignored == {'.jev-bound-scope-active', '.jev-description-active'} for ignored in scratch_ignored)

    for package in ('pi-coding-agent','pi-ai','pi-tui'):
        name='@earendil-works/'+package
        assert builds[0]['manifest']['dependencies'][name]=='1.3.0'
        assert f'"{name}": 1.3.0' in builds[0]['workspace']
    for package in ('pi-agent-core', 'pi-codemode', 'pi-mcp', 'pi-telemetry'):
        assert f'"@earendil-works/{package}": 1.3.0' in builds[0]['workspace']


def test_configuration_prepares_empty_session_root_before_any_model_task(tmp_path, monkeypatch):
    # Given a fresh disposable agent, when configuration succeeds before any
    # model task, then failure retention can archive an empty sessions root.
    # Reconfiguration must preserve existing session bytes.
    agent = tmp_path / 'agent'

    class Proxy:
        def write_agent_config(self, root):
            root.mkdir()
            (root / 'settings.json').write_text('{}')

    def put(_container, file, data):
        target = agent / file.removeprefix(study.AGENT + '/')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def shell(_container, command):
        return subprocess.check_output(['sh', '-c', command.replace(study.AGENT, str(agent))])

    monkeypatch.setattr(study, 'put', put)
    monkeypatch.setattr(study, 'shell', shell)
    study.configuration('owned-disposable', Proxy())
    assert (agent / 'sessions').is_dir()
    assert list((agent / 'sessions').iterdir()) == []
    session = agent / 'sessions' / 'existing.jsonl'
    session.write_bytes(b'original session\n')
    study.configuration('owned-disposable', Proxy())
    assert session.read_bytes() == b'original session\n'
