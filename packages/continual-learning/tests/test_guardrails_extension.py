from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

PKG_DIR = Path(__file__).resolve().parents[1]
REPO = PKG_DIR.parents[1]
ENGINE = './packages/continual-learning/extensions/guardrail-engine.ts'


def run_bun(source: str):
    with tempfile.TemporaryDirectory(prefix='harness-test-agent-') as agent_dir:
        result = subprocess.run(['bun', '-e', source], cwd=REPO, env={**os.environ, 'PI_CODING_AGENT_DIR': agent_dir}, capture_output=True, text=True, check=False, timeout=120)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_default_rules_block_auth_and_otp_but_allow_normal_calls() -> None:
    result = run_bun(f'''
      import {{DEFAULT_RULES,mergeLayers,evaluateBash}} from '{ENGINE}';
      const config=mergeLayers([{{source:'defaults',rules:DEFAULT_RULES}}]);
      console.log(JSON.stringify(['npm login','pnpm adduser','printf otp > /tmp/code','pnpm test'].map(command=>evaluateBash(config,command))));
    ''')
    assert [r['decision'] for r in result] == ['block', 'block', 'block', 'execute']
    assert 'their own terminal' in result[0]['reason']


def test_nearest_rule_completely_replaces_same_id_and_ids_are_exact() -> None:
    result = run_bun(f'''
      import {{mergeLayers,evaluateBash}} from '{ENGINE}';
      const config=mergeLayers([{{source:'user',rules:[{{id:'a',bash:'alpha',action:'block',message:'outer'}},{{id:' a ',bash:'gamma',message:'distinct'}}]}},{{source:'project',rules:[{{id:'a',bash:'beta',message:'inner'}}]}}]);
      console.log(JSON.stringify({{config,alpha:evaluateBash(config,'alpha'),beta:evaluateBash(config,'beta')}}));
    ''')
    assert result['alpha']['matchedRules'] == []
    assert result['beta']['decision'] == 'execute'
    assert result['beta']['messages'] == ['inner']
    assert [r['id'] for r in result['config']['rules']] == [' a ', 'a']


def test_harness_target_resolution_defaults_and_flags() -> None:
    result = run_bun('''
      import {resolveHarnessTarget} from './packages/continual-learning/extensions/guardrails.ts';
      console.log(JSON.stringify(['x','--global x','-g x','--shared x','--project x','--repo x','--local x','--user x'].map(args=>resolveHarnessTarget(args,'/tmp/project','/tmp/agent'))));
    ''')
    assert [r['scope'] for r in result] == ['project','user','user','project','project','project','project.local','user']
    assert result[0]['targetFile'] == '/tmp/project/.pi/harness.json'
    assert result[1]['targetFile'] == '/tmp/agent/harness.json'
    assert all(r['request'] == 'x' for r in result)


def test_exact_three_layers_and_no_mtime_cache_blind_spot(tmp_path: Path) -> None:
    agent = tmp_path / 'agent'
    project = tmp_path / 'project'
    (project / '.pi/agent').mkdir(parents=True)
    agent.mkdir()
    def config(message: str) -> str:
        return json.dumps({'rules':[{'id':'layered','bash':'fixture','message':message}]})
    for target, text in [(agent/'harness.json','user'), (agent/'harness.local.json','ignored'), (project/'.pi/harness.json','project'), (project/'.pi/harness.local.json','local'), (project/'.pi/agent/harness.json','ignored')]:
        target.write_text(config(text))
    result = run_bun(f'''
      import fs from 'node:fs';
      import {{loadLayers,resolveHarnessConfig,configPaths}} from './packages/continual-learning/extensions/guardrail-config.ts';
      const cwd={json.dumps(str(project))}, agent={json.dumps(str(agent))};
      const first=resolveHarnessConfig(cwd,agent); const file=first.paths.projectLocal;
      const stat=fs.statSync(file);fs.writeFileSync(file,{json.dumps(config('newer'))});fs.utimesSync(file,stat.atime,stat.mtime);
      const second=resolveHarnessConfig(cwd,agent);
      console.log(JSON.stringify({{keys:Object.keys(configPaths(cwd,agent)),sources:loadLayers(cwd,agent).map(l=>l.source),first:first.config.rules.find(r=>r.id==='layered').message,second:second.config.rules.find(r=>r.id==='layered').message}}));
    ''')
    assert result == {'keys':['user','project','projectLocal'],'sources':['user','project','project.local'],'first':'local','second':'newer'}


@pytest.mark.parametrize('malformed', ['{broken', '{"rules":[{"id":"same","bash":"x","message":"x"},{"id":"same","enabled":false}]}', '{"rules":[],"policies":{}}'])
def test_structural_errors_use_last_identity_unambiguous_snapshot(tmp_path: Path, malformed: str) -> None:
    (tmp_path / '.pi').mkdir()
    file = tmp_path / '.pi/harness.json'
    file.write_text(json.dumps({'rules':[{'id':'kept','bash':'fixture','action':'block','message':'keep'}]}))
    result = run_bun(f'''
      import fs from 'node:fs';
      import {{resolveHarnessConfig}} from './packages/continual-learning/extensions/guardrail-config.ts';
      import {{evaluateBash}} from '{ENGINE}';
      const cwd={json.dumps(str(tmp_path))}, agent={json.dumps(str(tmp_path/'agent'))};
      resolveHarnessConfig(cwd,agent);fs.writeFileSync({json.dumps(str(file))},{json.dumps(malformed)});
      const {{config}}=resolveHarnessConfig(cwd,agent);
      console.log(JSON.stringify({{config,decision:evaluateBash(config,'fixture'),bytes:fs.readFileSync({json.dumps(str(file))},'utf8')}}));
    ''')
    assert result['config']['configReadIncomplete']
    assert result['decision']['decision'] == 'block'
    assert result['bytes'] == malformed


@pytest.mark.parametrize('symlink_parent', [False, True])
def test_tool_gate_rejects_symlinked_target_or_parent(tmp_path: Path, symlink_parent: bool) -> None:
    project = tmp_path / 'project'; project.mkdir()
    outside = tmp_path / 'outside'; outside.mkdir()
    target = project / '.pi/harness.json'
    if symlink_parent:
        (project / '.pi').symlink_to(outside, target_is_directory=True)
    else:
        target.parent.mkdir(); (outside/'harness.json').write_text('{"rules":[]}'); target.symlink_to(outside/'harness.json')
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks={{}};register({{on:(n,f)=>hooks[n]=f,registerEntryRenderer(){{}},registerCommand(){{}},getCommands:()=>[]}});
      console.log(JSON.stringify(await hooks.tool_call({{toolName:'write',input:{{path:{json.dumps(str(target))},content:'{{"rules":[]}}'}}}},{{cwd:{json.dumps(str(project))}}})));
    ''')
    assert result['block'] and 'Unsafe' in result['reason']
