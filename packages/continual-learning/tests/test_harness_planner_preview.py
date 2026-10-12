from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path
from support import run_bun

FIXTURE = Path(__file__).parent / 'fixtures/real-harness-case-rejections.json'


def test_real_rejected_cases_are_executable_inside_read_only_planner() -> None:
    frozen = json.loads(FIXTURE.read_text())
    result = run_bun(f'''
      import {{previewHarnessRuleCases}} from './packages/continual-learning/extensions/harness-consolidation.ts';
      console.log(JSON.stringify({json.dumps(frozen)}.map(x=>previewHarnessRuleCases(x.rule,x.cases))));
    ''')
    for actual, original in zip(result, frozen):
        assert actual['passed'] is False
        assert actual['errors'] == original['parentErrors']


def test_planner_preview_is_bounded_read_only_and_does_not_authorize_mutation() -> None:
    result = run_bun('''
      import {registerHarnessPlannerPreview} from './packages/continual-learning/extensions/harness-planner-preview.ts';
      const hooks={},tools={};let active=['learning_read'];
      registerHarnessPlannerPreview({on:(n,f)=>hooks[n]=f,registerTool:t=>tools[t.name]=t,getActiveTools:()=>active,setActiveTools:t=>active=t});
      await hooks.session_start();
      const params={rule:{id:'r',bash:'^npm(?:[ \\t]|$)',action:'block',message:'use pnpm'},cases:{positive:[{bash:'npm test',expected:'block'}],negative:[{bash:'pnpm test'}]}};
      const results=[];for(let i=0;i<9;i++)results.push(await tools.harness_check_cases.execute(String(i),params));
      console.log(JSON.stringify({results,active}));
    ''')
    assert all(not r.get('isError') and r['details']['passed'] for r in result['results'][:8])
    assert result['results'][8]['isError']
    assert result['active'] == ['learning_read']
    assert all(r['details']['authorizesMutation'] is False for r in result['results'])


def test_actual_pi_worker_exposes_case_preview_and_repairs_real_mismatch(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[3]
    args = run_bun(f'''
      import {{plannerReadArgs}} from './packages/continual-learning/extensions/planner-read-scope.ts';
      import {{harnessPlannerPreviewArgs}} from './packages/continual-learning/extensions/harness-planner-preview.ts';
      const root={json.dumps(str(tmp_path))};
      console.log(JSON.stringify([...await plannerReadArgs(root,{{cwd:root,files:[],roots:[]}}),...await harnessPlannerPreviewArgs(root)]));
    ''')
    env = {k: v for k, v in os.environ.items() if k in ('PATH', 'LANG', 'LC_ALL')}
    env.update(HOME=str(tmp_path), PI_CODING_AGENT_DIR=str(tmp_path / 'agent'), PI_OFFLINE='1')
    result = subprocess.run(['node', str(repo / 'node_modules/@earendil-works/pi-coding-agent/dist/cli.js'),
        '--offline', '--no-extensions', '--no-context-files', '--no-skills', '--no-prompt-templates', '--no-themes',
        '--tools', 'learning_read,harness_check_cases', *args, '-e', str(Path(__file__).with_name('harness-planner-preview-live-fixture.ts')),
        '--provider', 'preview-fixture', '--model', 'fixed', '--thinking', 'off', '--no-session', '--print', '--mode', 'json', 'Check proposed cases.'],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=40)
    (tmp_path / 'native-pi-output.jsonl').write_text(result.stdout)
    assert result.returncode == 0, result.stderr
    assert 'preview-correction-verified' in result.stdout
    assert 'matched but must remain unmatched' in result.stdout
    assert not (tmp_path / '.pi/harness.json').exists()


def test_real_string_argument_failure_has_explicit_object_transport_contract() -> None:
    frozen = json.loads(FIXTURE.with_name('real-harness-preview-string-arguments.json').read_text())
    result = run_bun(f'''
      import {{registerHarnessPlannerPreview}} from './packages/continual-learning/extensions/harness-planner-preview.ts';
      import {{Value}} from 'typebox/value';
      let tool;registerHarnessPlannerPreview({{on:()=>{{}},registerTool:t=>tool=t}});
      const original={json.dumps(frozen['arguments'])};
      const objects=Object.fromEntries(Object.entries(original).map(([k,v])=>[k,JSON.parse(v)]));
      console.log(JSON.stringify({{schema:tool.parameters,stringsValid:Value.Check(tool.parameters,original),objectsValid:Value.Check(tool.parameters,objects)}}));
    ''')
    schema = result['schema']['properties']
    assert schema['rule']['type'] == 'object'
    assert schema['cases']['type'] == 'object'
    assert schema['cases']['properties']['positive']['items']['type'] == 'object'
    assert not result['stringsValid']
    assert result['objectsValid']
