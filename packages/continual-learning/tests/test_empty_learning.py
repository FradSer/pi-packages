"""Merged tests from: test_empty_full_learning.py, test_empty_memory_discovery.py, test_empty_memory_routing.py."""

from __future__ import annotations

from support import run_bun_script, PKG_DIR, run_bun
import json
from support import run_bun
import tempfile
from support import isolated_run_bun

# --- Merged from test_empty_full_learning.py ---

def test_header_only_full_learning_launches_no_workers() -> None:
    result = run_bun_script(PKG_DIR / "tests" / "learning-policy-harness.ts", "empty-full")
    assert result["selectors"] == 0
    assert result["planners"] == []
    assert result["registryReceipt"]["attempts"] == []
    assert "no-learning-inputs" in result["registryReceipt"]["screen"]["reasons"]
    assert result["history"] == []
    assert result["lock"] is False


def test_empty_full_receipt_is_distinct_from_reviewed_noop() -> None:
    result = run_bun('''
      import {buildLearningReceipt, learningSummarySubject} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const screen = {memory:false,harness:false,agents:false,reasons:['manual-full','no-learning-inputs']};
      console.log(JSON.stringify(learningSummarySubject(buildLearningReceipt('full',screen,[]))));
    ''')
    assert result == "no learning input"


def test_harness_noop_protocol_is_complete_and_keeps_knowledge_in_memory() -> None:
    prompt = (PKG_DIR / "prompts" / "harness-consolidator.md").read_text()
    assert '"operations": [],' in prompt
    assert '"evidence": []' in prompt
    assert "Empty operations are required" in prompt
    assert "response sign-offs" in prompt


def test_new_user_fact_grounding_is_distinct_from_existing_repository_audit() -> None:
    prompt = (PKG_DIR / "prompts" / "memory-consolidator.md").read_text()
    assert "Repository verification above audits existing selected Memory" in prompt
    assert "Shareability and repository verification are separate" in prompt


def test_harness_noop_omits_optional_report_and_repair_targets_report_errors() -> None:
    prompt = (PKG_DIR / "prompts" / "harness-consolidator.md").read_text()
    source = (PKG_DIR / "extensions" / "harness-consolidation.ts").read_text()
    assert "For a no-op, omit report entirely" in prompt
    assert "If validation errors cite report" in source

# --- Merged from test_empty_memory_discovery.py ---

def test_empty_memory_discovery_is_explicit_with_or_without_an_empty_index(tmp_path):
    result = run_bun(f'''
      import fs from 'node:fs/promises';
      import register from './packages/continual-learning/extensions/inject-memory.ts';
      import {{resolveMemoryPaths}} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd={json.dumps(str(tmp_path / 'project'))}; await fs.mkdir(cwd);
      const paths=resolveMemoryPaths(cwd); await fs.mkdir(paths.harnessDir,{{recursive:true}});
      await fs.writeFile(path.join(paths.agentDir,'continual-learning.json'),JSON.stringify({{autoSettledLearning:false,autoContinualLearning:false}}));
      const hooks=new Map(); register({{on:(n,f)=>hooks.set(n,f),registerCommand:()=>{{}},sendMessage:()=>{{}},appendEntry:()=>{{}},getCommands:()=>[],exec:async()=>({{stdout:'',stderr:'',code:0}})}});
      const ctx={{cwd,ui:{{notify:()=>{{}}}}}};
      const options={{promptGuidelines:[],sections:{{project_memory_discovery:'STALE_DISCOVERY',project_memory_auto_learning:'STALE_AUTO',other:'KEEP'}}}};
      const missing=await hooks.get('before_agent_start')({{systemPrompt:'TRUSTED',systemPromptOptions:options}},ctx);
      await fs.writeFile(paths.harnessDir+'/MEMORY.md','# Memory Index\\n\\n');
      const emptyIndex=await hooks.get('before_agent_start')({{systemPrompt:'TRUSTED',systemPromptOptions:options}},ctx);
      console.log(JSON.stringify({{missing:{{...missing,guidance:Object.values(options.sections),sections:options.sections}},emptyIndex:{{...emptyIndex,guidance:Object.values(options.sections),sections:options.sections}}}}));
    ''',env={'PI_CODING_AGENT_DIR':str(tmp_path / 'agent')})
    for state in ('missing','emptyIndex'):
        assert result[state] is not None, 'Empty Memory discovery was omitted'
        assert 'message' not in result[state], 'Empty discovery must not append a placeholder reference'
        assert result[state]['sections']['other'] == 'KEEP'
        assert set(result[state]['sections']) == {'other', 'project_memory_protocol', 'project_memory_auto_learning'}
        assert 'If no established entries are available' in ' '.join(result[state]['guidance'])
        assert 'use the read tool to inspect relevant indexed Memory entries' in result[state]['sections']['project_memory_protocol']
        assert 'do not search guessed or alternative Memory locations' in ' '.join(result[state]['guidance'])
        protocol = result[state]['sections']['project_memory_protocol']
        assert "Respect the task's read and write scope" in protocol
        # The agent trigger is always on: the protocol advertises learn and
        # keeps the Pi-input note, never a retired slash command.
        assert 'uses the learn tool' in protocol
        assert 'slash commands are Pi input for the user' in protocol
        assert 'never a suggestion to type /memory' not in protocol
        assert 'The parent performs automatic maintenance when enabled' in protocol
        assert 'Memory retrieval alone does not authorize configuration discovery or launching another agent' in protocol
        assert 'those need separate task authorization' in protocol
        assert 'Maintain knowledge through /memory or /consolidate.' not in protocol
        assert '/memory or /consolidate' not in protocol
    assert result['missing'] == result['emptyIndex']


def test_automatic_learning_owns_durable_writes_and_remember_does_not_expand_task_scope(tmp_path):
    result = run_bun(f'''
      import fs from 'node:fs/promises';
      import register from './packages/continual-learning/extensions/inject-memory.ts';
      import {{resolveMemoryPaths}} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd={json.dumps(str(tmp_path / 'project'))};await fs.mkdir(cwd);
      const paths=resolveMemoryPaths(cwd);await fs.mkdir(paths.harnessDir,{{recursive:true}});
      await fs.writeFile(path.join(paths.agentDir,'continual-learning.json'),JSON.stringify({{autoSettledLearning:true,autoContinualLearning:false}}));
      const hooks=new Map();register({{on:(n,f)=>hooks.set(n,f),registerCommand(){{}},sendMessage(){{}},appendEntry(){{}},getCommands:()=>[]}});
      const options={{sections:{{}}}};await hooks.get('before_agent_start')({{systemPromptOptions:options}},{{cwd,ui:{{notify(){{}}}}}});
      console.log(JSON.stringify(options.sections));
    ''',env={'PI_CODING_AGENT_DIR':str(tmp_path / 'agent')})
    guidance = ' '.join(result['project_memory_auto_learning'].split())
    assert 'The parent validates and writes them' in guidance
    assert '"remember" does not authorize writing Memory, Harness, AGENTS.md' in guidance
    assert 'PI.md or agent configuration, or probing enforcement' in guidance
    assert 'explicit authoring requests take precedence' in guidance
    protocol = result['project_memory_protocol']
    assert "Respect the task's read and write scope" in protocol
    # The agent trigger is always on, so the protocol advertises learn.
    assert 'uses the learn tool' in protocol
    assert 'never a suggestion to type /memory' not in protocol

# --- Merged from test_empty_memory_routing.py ---

def test_empty_memory_routes_explicit_evidence_without_model_and_preserves_dossier() -> None:
    with tempfile.TemporaryDirectory(prefix='empty-memory-routing-') as temporary:
        result = isolated_run_bun(r'''
          import {mock} from 'bun:test';
          import fs from 'node:fs';
          import path from 'node:path';
          import {execFileSync} from 'node:child_process';
          const cwd=path.join(process.env.TEST_ROOT,'project');fs.mkdirSync(cwd);execFileSync('git',['init','-q',cwd]);
          let calls=0;
          const kit=await import('./packages/kit/src/index.ts');
          mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{
            calls++;return {text:'INVALID_SELECTOR',exitCode:0,stderr:'',cancelled:false};
          }}));
          const {selectIncrementalLearning}=await import('./packages/continual-learning/extensions/incremental-learning.ts');
          const slice={kind:'learning-task-slice',version:1,entries:[{message:{role:'user',content:
            'Remember for future tasks: the verified command is pnpm test. Never run git push.'}}]};
          const run=(name,taskSlice=slice,extra={})=>selectIncrementalLearning({cwd,taskSlice,contextDigest:'frozen-digest',
            outputDir:path.join(process.env.TEST_ROOT,name),allowEmptyIndexRouting:true,...extra});
          const cold=await run('cold');
          const dossier=cold.dossierPath?JSON.parse(fs.readFileSync(cold.dossierPath,'utf8')):null;
          const coldCalls=calls;
          const requested=await run('requested',{...slice,entries:[{message:{role:'user',content:'A means B.'}}]},{memoryOnly:true});
          const requestCalls=calls;
          const ambiguous=await run('ambiguous',{...slice,entries:[{message:{role:'user',content:'Inspect this task.'}}]});
          fs.mkdirSync(path.join(cwd,'.memory'));
          fs.writeFileSync(path.join(cwd,'.memory','known.md'),'---\nname: known\ndescription: Known project fact\ntype: project\n---\nBody\n');
          const existing=await run('existing');
          const rejected=JSON.parse(fs.readFileSync(path.join(process.env.TEST_ROOT,'ambiguous','selector-rejected.json'),'utf8'));
          const rejectedMode=fs.statSync(path.join(process.env.TEST_ROOT,'ambiguous','selector-rejected.json')).mode&0o777;
          const cancelled=await run('cancelled',slice,{signal:AbortSignal.abort()});
          console.log(JSON.stringify({cold:cold.outcome,coldCalls,dossier,coldUsage:cold.usage??null,
            diagnostic:cold.diagnostic,rejected,rejectedMode,requestCalls,requested:requested.selection,
            ambiguous:ambiguous.outcome,existing:existing.outcome,calls,cancelled:cancelled.outcome}));
        ''', {"TEST_ROOT": temporary})
    assert result['cold'] == 'selected'
    assert result['coldCalls'] == 0 and result['requestCalls'] == 0
    assert result['coldUsage'] is None
    assert result['dossier']['contextDigest'] == 'frozen-digest'
    assert result['dossier']['selectedMemories'] == []
    selection = result['dossier']['selection']
    assert selection['selected'] == [] and selection['memory'] and selection['harness'] and not selection['agents']
    assert result['requested']['memory'] and not result['requested']['harness'] and not result['requested']['agents']
    assert result['ambiguous'] == result['existing'] == 'failed'
    assert result['cancelled'] == 'cancelled' and result['calls'] == 2
    assert result['diagnostic'] == 'empty Memory index; parent-routed explicit evidence'

    assert result['rejected']['output'] == 'INVALID_SELECTOR'
    assert result['rejected']['contextDigest'] == 'frozen-digest'
    assert result['rejectedMode'] == 0o600
