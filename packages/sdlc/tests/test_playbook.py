"""Observable full-playbook behavior through the packaged CLI and real processes."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/sdlc.py'
ASSETS = SCRIPT.parents[1] / 'templates'

class PlaybookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix='sdlc-playbook-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.cwd = self.base / 'project'
        self.cwd.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@localhost')
        (self.cwd / 'code.txt').write_text('before\n')
        self.commit()
        self.adapter = self.base / 'adapter.py'
        self.adapter.write_text('''import json,sys,pathlib
request=json.load(sys.stdin)
kind=sys.argv[1]
if kind=='approve':
 print(json.dumps({**request,'approved':True,'approver':'independent human fixture','reference':'PR-123'}))
elif kind=='review':
 print(json.dumps({'digest':request['digest'],'passes':request['passes'],'important':0,'findings':[]}))
elif kind=='status': print('{"healthy":true}')
elif kind=='bad-status': print('{"healthy":false}')
elif kind=='diagnose': print(json.dumps({'intent':'# Intent: Incident\\nAuthor: Monitor. Status: draft.\\n\\n## Problem\\nFailure rate rose.\\n\\n## Proposed outcome\\nRestore baseline.\\n\\n## Affected users and systems\\nAPI users.\\n\\n## Constraints\\nExisting auth.\\n\\n## Open questions\\nCause unknown.\\n'}))
else:
 pathlib.Path(sys.argv[2]).write_text(kind)
 print('{}')
''')
        self.status_adapter = self.base / 'status'
        self.status_adapter.write_text('#!' + sys.executable + '\nimport json,pathlib\nprint(json.dumps({"healthy":not pathlib.Path(' + repr(str(self.base/'unhealthy')) + ').exists()}))\n')
        self.status_adapter.chmod(0o700)
        self.policy = self.base / 'policy.json'
        commands = lambda kind: [sys.executable, str(self.adapter), kind]
        self.policy_value = {'version':1, 'approve':commands('approve'), 'review':commands('review'), 'diagnose':commands('diagnose'),
            'environments':{env:{'release':commands('release')+[str(self.base/'released')], 'status':[str(self.status_adapter)], 'rollback':commands('rollback')+[str(self.base/'rolled-back')]} for env in ('dev','staging','production')}}
        self.policy.write_text(json.dumps(self.policy_value))
        self.env = {**os.environ, 'SDLC_POLICY_FILE':str(self.policy)}
        self.suite = self.base / 'evals.json'
        runner = self.base / 'runner.py'
        runner.write_text("import pathlib; pathlib.Path('code.txt').write_text('accepted\\n')")
        grader = self.base / 'grader.py'
        grader.write_text("import pathlib; assert pathlib.Path('code.txt').read_text() == 'accepted\\n'")
        self.suite_value = [{'name':'historical-change', 'from':self.git('rev-parse','HEAD'), 'prompt':'Update the fixture file.', 'mayChange':['code.txt'], 'runner':[sys.executable,str(runner)], 'checks':[[sys.executable,str(grader)]]}]
        self.suite.write_text(json.dumps(self.suite_value))

    def git(self, *args: str) -> str:
        result = subprocess.run(['git', *args], cwd=self.cwd, text=True, capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        return result.stdout.strip()

    def commit(self) -> None:
        self.git('add','-A'); self.git('commit','--allow-empty','-qm','fixture')

    def cli(self, action: str, args: dict | None=None, passed: bool=True) -> dict:
        result = subprocess.run([sys.executable,str(SCRIPT),action,'--cwd',str(self.cwd),'--args',json.dumps(args or {})], env=self.env, text=True,capture_output=True,timeout=30)
        if passed:
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
        return json.loads(result.stderr or result.stdout)

    def prepare(self) -> None:
        self.cli('init',{'task':'fixture'})
        (self.cwd/'INTENT.md').write_text('# Intent: Example\nAuthor: A. User. Status: draft.\n\n'+'\n\n'.join('## '+s+'\nEstablished requirement.' for s in ['Problem','Proposed outcome','Affected users and systems','Constraints','Open questions'])+'\n')
        (self.cwd/'HANDOFF.md').write_text((ASSETS/'HANDOFF.md').read_text().replace('No task progress has been recorded. The task outcome is unknown.','In progress: artifacts reviewed.').replace('Not assessed.','No known blocker.'))
        (self.cwd/'SPEC.md').write_text((ASSETS/'SPEC.md').read_text().replace('[REQUIRED]','Concrete reviewed decision.'))
        (self.cwd/'PLAN.md').write_text((ASSETS/'PLAN.md').read_text().replace('[REQUIRED]','Concrete reviewed step.'))
        shutil.copyfile(ASSETS/'REVIEW.md',self.cwd/'REVIEW.md')
        config = {'version':1,'checks':[{'name':'fixture','argv':[sys.executable,'-c','print("verified")']}],'agentFiles':[],'evalSuite':str(self.suite)}
        (self.cwd/'.sdlc/config.json').write_text(json.dumps(config))

    def build(self) -> None:
        self.prepare()
        for expected in ['design','plan','build']:
            self.assertEqual(self.cli('advance')['stage'],expected)
        self.commit()

    def deploy_stage(self) -> None:
        self.build(); self.cli('advance')
        self.cli('check'); self.cli('eval'); self.cli('advance'); self.cli('review'); self.cli('advance')

    def test_initialization_preserves_existing_intent(self) -> None:
        (self.cwd/'INTENT.md').write_text('Human source\n')
        self.assertEqual(self.cli('init')['stage'],'intent')
        self.assertEqual((self.cwd/'INTENT.md').read_text(),'Human source\n')
        self.cli('advance',passed=False)

    def test_full_chain_records_actual_evidence_and_archives(self) -> None:
        self.deploy_stage()
        self.assertFalse((self.base/'released').exists())
        result=self.cli('deploy',{'environment':'production'})
        self.assertTrue(result['receipts']['deploy']['passed'])
        self.assertTrue((self.base/'released').exists())
        self.assertEqual(self.cli('advance')['stage'],'maintain')
        result=self.cli('archive')
        self.assertTrue((Path(result['archived'])/'INTENT.md').is_file())
        self.assertTrue((self.cwd/'INTENT.md').is_file())

    def test_missing_approval_cannot_advance(self) -> None:
        self.prepare(); self.env.pop('SDLC_POLICY_FILE')
        self.assertIn('SDLC_POLICY_FILE',self.cli('advance',passed=False)['error'])
        self.assertEqual(self.cli('status')['stage'],'intent')

    def test_wrong_role_or_digest_cannot_approve(self) -> None:
        self.prepare()
        self.adapter.write_text("print('{\"approved\":true,\"role\":\"engineer\",\"digest\":\"wrong\"}')")
        self.cli('advance',passed=False)

    def test_correction_invalidates_approval(self) -> None:
        self.prepare(); self.cli('advance')
        path=self.cwd/'INTENT.md'; path.write_text(path.read_text().replace('Established requirement.','Corrected requirement.',1))
        self.assertIn('stale',self.cli('advance',passed=False)['error'])
        self.cli('rewind',{'stage':'intent'}); self.assertEqual(self.cli('advance')['stage'],'design')

    def test_code_change_invalidates_verification(self) -> None:
        self.build(); self.cli('advance'); self.cli('check'); self.cli('eval')
        (self.cwd/'code.txt').write_text('changed after checks\n')
        self.assertIn('stale',self.cli('advance',passed=False)['error'])

    def test_config_change_requires_new_plan_approval(self) -> None:
        self.build()
        path=self.cwd/'.sdlc/config.json'; value=json.loads(path.read_text());value['checks']=[];path.write_text(json.dumps(value))
        self.assertIn('stale',self.cli('check',passed=False)['error'])

    def test_failed_check_receipt_is_not_success(self) -> None:
        self.prepare()
        path=self.cwd/'.sdlc/config.json';value=json.loads(path.read_text());value['checks'][0]['argv']=[sys.executable,'-c','raise SystemExit(3)'];path.write_text(json.dumps(value))
        for _ in range(3): self.cli('advance')
        result=self.cli('check',passed=False)
        self.assertFalse(result['receipts']['check']['passed'])

    def test_eval_detects_committed_out_of_scope_edits(self) -> None:
        self.build()
        runner=self.base/'runner.py'
        runner.write_text("import subprocess,pathlib; pathlib.Path('outside.txt').write_text('stray'); subprocess.run(['git','add','-A'],check=True); subprocess.run(['git','-c','user.name=fixture','-c','user.email=f@local','commit','-qm','stray'],check=True)")
        result=self.cli('eval',passed=False)
        self.assertIn('outside.txt',result['receipts']['eval']['results'][0]['stray'])

    def test_eval_rejects_historical_parent_symlink(self) -> None:
        outside=self.base/'outside';outside.mkdir();(outside/'AGENTS.md').write_text('preserve')
        (self.cwd/'agent').symlink_to(outside,target_is_directory=True)
        self.commit(); historical=self.git('rev-parse','HEAD')
        (self.cwd/'agent').unlink();(self.cwd/'agent').mkdir();(self.cwd/'agent/AGENTS.md').write_text('current config')
        self.prepare()
        path=self.cwd/'.sdlc/config.json';value=json.loads(path.read_text());value['agentFiles']=['agent/AGENTS.md'];path.write_text(json.dumps(value))
        self.suite_value[0]['from']=historical;self.suite.write_text(json.dumps(self.suite_value))
        for _ in range(3): self.cli('advance')
        self.cli('eval',passed=False)
        self.assertEqual((outside/'AGENTS.md').read_text(),'preserve')

    def test_guard_checks_patch_move_destination(self) -> None:
        self.prepare()
        self.cli('guard',{'tool':'apply_patch','input':{'command':'*** Update File: HANDOFF.md\n*** Move to: code.txt\n'}},passed=False)

    def test_eval_start_failure_invalidates_older_receipt(self) -> None:
        self.build();self.cli('eval')
        (self.base/'runner.py').unlink()
        self.cli('eval',passed=False)
        self.assertFalse(self.cli('status')['receipts']['eval']['passed'])

    def test_eval_rejects_ignored_out_of_scope_writes(self) -> None:
        (self.cwd/'.gitignore').write_text('private/\n')
        self.commit()
        self.suite_value[0]['from']=self.git('rev-parse','HEAD');self.suite.write_text(json.dumps(self.suite_value))
        self.build()
        (self.base/'runner.py').write_text("import pathlib; pathlib.Path('code.txt').write_text('accepted\\n'); pathlib.Path('private').mkdir(); pathlib.Path('private/secret.txt').write_text('stray')")
        result=self.cli('eval',passed=False)
        self.assertIn('private/secret.txt',result['receipts']['eval']['results'][0]['stray'])

    def test_important_review_finding_blocks_progress(self) -> None:
        self.build(); self.cli('advance'); self.cli('check');self.cli('eval');self.cli('advance')
        self.adapter.write_text(self.adapter.read_text().replace("'important':0","'important':1"))
        self.cli('review',passed=False);self.cli('advance',passed=False)

    def test_unhealthy_release_rolls_back_and_stays_failed(self) -> None:
        self.deploy_stage()
        (self.base/'unhealthy').write_text('failure')
        result=self.cli('deploy',{'environment':'staging'},passed=False)
        self.assertEqual(result['receipts']['deploy']['rollbackExit'],0)
        self.assertTrue((self.base/'rolled-back').exists())
        self.cli('advance',passed=False)

    def test_status_start_error_rolls_back_and_clears_old_success(self) -> None:
        self.deploy_stage()
        self.cli('deploy')
        self.status_adapter.unlink()
        result=self.cli('deploy',passed=False)
        self.assertFalse(result['receipts']['deploy']['passed'])
        self.assertTrue((self.base/'rolled-back').exists())
        self.cli('advance',passed=False)

    def test_approval_race_cannot_release_new_revision(self) -> None:
        self.deploy_stage()
        script=self.adapter.read_text()
        script=script.replace("if kind=='approve':", "if kind=='approve':\n if request['stage']=='deploy':\n  import subprocess\n  pathlib.Path('code.txt').write_text('racing change')\n  subprocess.run(['git','add','code.txt'],check=True)\n  subprocess.run(['git','-c','user.name=Other','-c','user.email=other@local','commit','-qm','racing change'],check=True,stdout=sys.stderr)")
        self.adapter.write_text(script)
        self.cli('deploy',{'environment':'production'},passed=False)
        self.assertFalse((self.base/'released').exists())
        self.assertFalse(self.cli('status')['receipts']['deploy']['passed'])

    def test_failed_rerun_invalidates_downstream_release(self) -> None:
        self.deploy_stage();self.cli('deploy')
        (self.base/'runner.py').unlink()
        self.cli('eval',passed=False)
        self.cli('advance',passed=False)
        self.assertNotIn('deploy',self.cli('status')['receipts'])

    def test_status_timeout_rolls_back_and_fails(self) -> None:
        self.policy_value['environments']['dev']['timeout']=1
        self.policy.write_text(json.dumps(self.policy_value))
        self.deploy_stage()
        self.status_adapter.write_text('#!' + sys.executable + '\nimport time\ntime.sleep(3)\n')
        result=self.cli('deploy',passed=False)
        self.assertFalse(result['receipts']['deploy']['passed'])
        self.assertTrue((self.base/'rolled-back').exists())

    def test_metric_creates_deduplicated_new_intent_without_releasing(self) -> None:
        self.prepare()
        values=[1.0]*24+[2.0]
        result=self.cli('metric',{'event':'incident-1','readings':values,'evidence':'hourly fixture'})
        self.assertEqual(result['tier'],3)
        self.assertFalse(result['actionsExecuted'])
        self.assertTrue((self.cwd/'.sdlc/inbox/incident-1.md').exists())
        self.assertEqual(result,self.cli('metric',{'event':'incident-1','readings':values}))
        self.assertFalse((self.base/'released').exists())
        self.cli('metric',{'event':'../escape','readings':values},passed=False)

    def test_monitoring_is_stateless_and_needs_no_active_task(self) -> None:
        result=self.cli('metric',{'event':'stateless-incident','readings':[1]*24+[2]})
        self.assertEqual(result['tier'],3)
        self.assertFalse((self.cwd/'.sdlc/state.json').exists())
        self.assertTrue((self.cwd/'.sdlc/inbox/stateless-incident.md').exists())

    def test_metric_rejects_short_or_nonfinite_readings(self) -> None:
        self.prepare()
        self.cli('metric',{'readings':[1]*24},passed=False)
        self.cli('metric',{'readings':[1]*24+[float('nan')]},passed=False)

    def test_native_edit_guard_requires_plan_and_allows_artifacts(self) -> None:
        self.prepare()
        self.cli('guard',{'tool':'write','input':{'path':'code.txt'}},passed=False)
        self.cli('guard',{'tool':'write','input':{'path':'SPEC.md'}})
        self.cli('guard',{'tool':'mcp__prod__release','input':{}},passed=False)
        for _ in range(3): self.cli('advance')
        self.cli('guard',{'tool':'edit','input':{'path':'code.txt'}})

    def test_handoff_checkpoint_does_not_rewrite_plan_or_invalidate_checks(self) -> None:
        self.build();self.cli('advance');self.cli('check');self.cli('eval')
        plan=(self.cwd/'PLAN.md').read_text()
        state=self.cli('status')
        handoff=self.cwd/'HANDOFF.md'
        handoff.write_text(handoff.read_text().replace('In progress: artifacts reviewed.','In progress: PLAN.md step 2; fixture check passed.'))
        advanced=self.cli('advance')
        self.assertEqual(advanced['stage'],'review')
        self.assertEqual((self.cwd/'PLAN.md').read_text(),plan)
        self.assertEqual(advanced['approvals']['plan'],state['approvals']['plan'])
        self.assertEqual(advanced['receipts']['check'],state['receipts']['check'])

    def test_handoff_missing_or_oversized_fails(self) -> None:
        self.prepare()
        path=self.cwd/'HANDOFF.md';path.write_text(path.read_text()+'\n'*200)
        self.cli('handoff',passed=False)

    def test_codex_native_hook_protocol_denies_unapproved_patch(self) -> None:
        hook = SCRIPT.parents[3] / 'hooks/record.py'
        if not hook.exists():
            self.skipTest('Codex adapter belongs to the Codex package')
        self.prepare()
        payload={'hook_event_name':'PreToolUse','cwd':str(self.cwd),'tool_name':'apply_patch','tool_input':{'command':'*** Update File: HANDOFF.md\n*** Move to: code.txt\n'}}
        result=subprocess.run([sys.executable,str(hook)],input=json.dumps(payload),text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['hookSpecificOutput']['permissionDecision'],'deny')

    def test_real_host_runner_preserves_prompt_and_current_configuration(self) -> None:
        fake=self.base/'bin';fake.mkdir()
        capture=self.base/'host-input.json'
        executable=fake/'codex'
        executable.write_text('#!' + sys.executable + '\nimport json,sys,pathlib\npathlib.Path(' + repr(str(capture)) + ').write_text(json.dumps({"argv":sys.argv[1:],"prompt":sys.stdin.read()}))\n')
        executable.chmod(0o700)
        env={**self.env,'PATH':str(fake)+os.pathsep+os.environ['PATH']}
        result=subprocess.run([sys.executable,str(SCRIPT.with_name('run_agent.py')),'codex'],input=json.dumps({'cwd':str(self.cwd),'prompt':'Original eval task'}),env=env,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        invocation=json.loads(capture.read_text())
        self.assertEqual(invocation['prompt'],'Original eval task')
        self.assertIn('workspace-write',invocation['argv'])
        self.assertNotIn('--dangerously-bypass-hook-trust',invocation['argv'])

    def test_github_adapter_requires_current_independent_role_approval(self) -> None:
        self.build()
        fake=self.base/'bin';fake.mkdir()
        head=self.git('rev-parse','HEAD')
        pr={'head':{'sha':head},'state':'open','user':{'login':'author'}}
        reviews=[[{'id':1,'state':'APPROVED','commit_id':head,'html_url':'https://github.example/review/1','user':{'login':'reviewer'}}]]
        executable=fake/'gh'
        executable.write_text('#!' + sys.executable + '\nimport json,sys\nprint(json.dumps(' + repr(reviews) + ' if sys.argv[-1].endswith("/reviews") else ' + repr(pr) + '))\n')
        executable.chmod(0o700)
        roles=self.base/'roles.json';roles.write_text(json.dumps({'code-owner':['reviewer']}))
        request={'task':'fixture','stage':'review','role':'code-owner','digest':self.cli('status')['currentDigest']}
        command=[sys.executable,str(SCRIPT.with_name('github_approval.py')),'--repo','owner/repo','--pr','1','--roles',str(roles)]
        result=subprocess.run(command,cwd=self.cwd,input=json.dumps(request),env={**self.env,'PATH':str(fake)+os.pathsep+os.environ['PATH']},text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout)['approver'],'reviewer')
        roles.write_text(json.dumps({'code-owner':['author']}))
        denied=subprocess.run(command,cwd=self.cwd,input=json.dumps(request),env={**self.env,'PATH':str(fake)+os.pathsep+os.environ['PATH']},text=True,capture_output=True)
        self.assertNotEqual(denied.returncode,0)

    def test_symlinked_state_directory_does_not_write_outside(self) -> None:
        outside=self.base/'outside';outside.mkdir();(self.cwd/'.sdlc').symlink_to(outside,target_is_directory=True)
        self.cli('init',passed=False)
        self.assertEqual(list(outside.iterdir()),[])

if __name__=='__main__': unittest.main()
