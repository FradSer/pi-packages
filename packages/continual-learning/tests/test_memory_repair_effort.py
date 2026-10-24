import pytest

from support import isolated_run_bun


def test_preservation_repair_receives_exact_old_new_changes_without_forcing_body_rewrite():
    # Given a held rewrite, When the parent prepares its one repair slot,
    # Then expose exact changes and full records without granting preservation.
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      import {memoryRewriteTextComparisons} from './packages/continual-learning/extensions/jev-memory-predecessors.ts';
      const kit=await import('./packages/kit/src/index.ts');let prompt;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        prompt=input.prompt;return {exitCode:0,stderr:'',cancelled:false,text:'{}'};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'h',snapshotDigest:'h'};
      const markdown=description=>'---\nname: a.md\ndescription: '+description+'\ntype: project\n---\nObserved declaration.\n';
      const existing=[{name:'a.md',classification:'private',content:markdown('Historical declaration.')}];
      const candidate={name:'a.md',kind:'rewrite',classification:'private',content:markdown('Current declaration.'),evidence:[{index:0,quote:'Source'}]};
      const rejectedPlan={kind:'incremental-memory-plan',version:1,...identity,operations:[candidate],newMemories:[]};
      const frozenEvidence={entries:[{role:'user',content:'Source'}]},before=JSON.stringify({existing,rejectedPlan,frozenEvidence});
      const reply=await repairIncrementalMemoryPlan({identity,rejectedPlan,selectedNames:['a.md'],repairableNames:['a.md'],repairableFields:{'a.md':['body','description']},errors:['preservation held'],
        semanticContext:{frozenEvidence,existingMemories:existing}});
      const data=JSON.parse(prompt.split('\n').at(-1));
      // Actual final repair builder, after caller prefixes and retention hints.
      const errors=['Retained review index map: fixture', 'Semantic verification: uncertain',
        ...Array.from({length:18},(_,i)=>'Retained diagnostic '+i),
        'Candidate failures: 0:support:uncertain [observed-check=supported_0; choice=unsupported; probability=0.54; confidence=0.42]',
        'Candidate failures: 0:internal-consistency:uncertain [observed-check=coherence_0; choice=compatible; probability=0.62; confidence=0.43]'];
      await repairIncrementalMemoryPlan({identity,rejectedPlan,selectedNames:['a.md'],repairableNames:['a.md'],repairableFields:{'a.md':['body','description']},errors,
        boundedSemanticDiagnostics:true,semanticContext:{frozenEvidence,existingMemories:existing}});
      const finalErrors=JSON.parse(prompt.split('\n').at(-1)).errors;
      console.log(JSON.stringify({finalErrors,reply,comparison:data.semanticContext.preservationTextComparisons,
        expected:memoryRewriteTextComparisons(existing,[{...candidate,candidateIndex:0}]),
        completeRecords:JSON.stringify(data.semanticContext.existingMemories)===JSON.stringify(existing)&&JSON.stringify(data.rejectedPlan)===JSON.stringify(rejectedPlan),
        unchanged:before===JSON.stringify({existing,rejectedPlan,frozenEvidence}),
        guidance:prompt.includes('A description-only patch or selecting the same source excerpt does not by itself resolve a preservation hold'),
        noForcedBodyChange:prompt.includes('A supported description correction can resolve a real scope or condition error without changing an already correct body'),
        scopeRepair:prompt.includes('Check the original source before removing a draft condition that lacks a selected citation'),
        sourceCondition:prompt.includes('If that source establishes the condition, retain it and add the matching original source citation'),
        falseCondition:prompt.includes('Correct or remove a condition when the original evidence establishes that it is false or obsolete'),
        noDraftAuthority:prompt.includes('The draft and the review account are not evidence that a condition is true'),
        finalScopeCheck:prompt.includes('Before emitting the patch, compare its applicability with the rejected record and the complete source')}));
    ''')
    assert result.get('comparison') == result['expected']
    assert result['comparison']['writeAuthorized'] is False
    assert result['completeRecords'] and result['unchanged']
    assert result['guidance'] and result['noForcedBodyChange']
    assert all(result[key] for key in ('scopeRepair', 'sourceCondition', 'falseCondition', 'noDraftAuthority', 'finalScopeCheck'))
    assert result['reply']['outcome'] == 'failed' and 'plan' not in result['reply']
    errors = result['finalErrors']
    assert len(errors) <= 16 and max(map(len, errors)) <= 800
    assert errors[-1].startswith('Additional correction diagnostics omitted;')
    assert any('observed-check=supported_0' in line for line in errors)
    assert any('observed-check=coherence_0' in line for line in errors)
    assert errors[0] == 'Retained review index map: fixture'
    assert errors[1] == 'Semantic verification: uncertain'


def test_only_reviewed_description_patches_disable_reasoning_when_no_body_is_held():
    # Given a complete independent body review, When generating bounded patches,
    # Then spend the fixed worker budget on output while keeping fresh validation.
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let args;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        args=input.extraArgs;return {exitCode:0,stderr:'',cancelled:false,text:'{}'};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {prepareMemoryBodyTargets}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'h',snapshotDigest:'h'};
      const candidate={name:'a.md',kind:'project',classification:'private',content:'Original',evidence:[{index:0,quote:'Source'}]};
      const targets=prepareMemoryBodyTargets([candidate],[]),rows=[];
      for(const scope of ['body','description','unknown'])for(const status of ['absent','consistent','contradictory','uncertain']){
        const bodyReview=status==='absent'?undefined:{status:'reviewed',targets,
          judgments:targets.map(t=>({id:t.id,verdict:status,witnesses:[]})),calls:1,durationMs:1,usageComplete:true};
        const failure=await repairIncrementalMemoryPlan({identity,rejectedPlan:{kind:'incremental-memory-plan',version:1,...identity,operations:[],newMemories:[candidate]},
          selectedNames:[],repairableNames:['a.md'],...(scope==='unknown'?{}:{repairableFields:{'a.md':[scope]}}),errors:['held'],bodyReview,
          semanticContext:{frozenEvidence:{entries:[{role:'user',content:'Source'}]},existingMemories:[]}});
        const i=args.lastIndexOf('--thinking');rows.push({scope,status,thinking:i<0?null:args[i+1],failed:failure.outcome==='failed',plan:!!failure.plan});
      }
      console.log(JSON.stringify(rows));
    ''')
    for row in result:
        if row['scope'] in ('body', 'unknown') or row['status'] in ('contradictory', 'uncertain'):
            assert row['thinking'] == 'xhigh', row
        elif row['status'] == 'consistent':
            assert row['thinking'] == 'off', row
        else:
            assert row['thinking'] != 'off', row
    assert all(row['failed'] and not row['plan'] for row in result)


@pytest.mark.parametrize('scope', ['description', 'body', 'unknown'])
def test_actual_pi_preserves_reasoning_for_semantic_body_repairs(scope):
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {repairIncrementalMemoryPlan} from './packages/continual-learning/extensions/inject-memory.ts';
      import {prepareMemoryBodyTargets} from './packages/continual-learning/extensions/memory-body-review.ts';
      const agent=process.env.PI_CODING_AGENT_DIR;let calls=0,thinking,effort,tools;
      const server=Bun.serve({hostname:'127.0.0.1',port:0,fetch:async request=>{
        calls++;const wire=await request.json();thinking=wire.thinking;effort=wire.reasoning_effort;tools=wire.tools;
        const user=wire.messages.filter(m=>m.role==='user').at(-1);
        const text=typeof user.content==='string'?user.content:user.content.map(x=>x.text??'').join('\n');
        const data=JSON.parse(text.split('\n').at(-1));
        const reply=JSON.stringify({kind:'incremental-memory-amendment',version:1,...data.identity,
          replacements:[]});
        const chunk=(delta,finish_reason)=>'data: '+JSON.stringify({id:'fixture',object:'chat.completion.chunk',model:'deepseek',choices:[{index:0,delta,finish_reason}]})+'\n\n';
        return new Response(chunk({role:'assistant',content:reply},null)+chunk({},'stop')+'data: [DONE]\n\n',{headers:{'content-type':'text/event-stream'}});
      }});
      fs.writeFileSync(path.join(agent,'models.json'),JSON.stringify({providers:{fixture:{baseUrl:`http://127.0.0.1:${server.port}/v1`,api:'openai-completions',apiKey:'offline',models:[{id:'deepseek',name:'offline',reasoning:true,input:['text'],contextWindow:1000000,maxTokens:2048,cost:{input:0,output:0,cacheRead:0,cacheWrite:0},compat:{thinkingFormat:'deepseek',supportsReasoningEffort:true},thinkingLevelMap:{xhigh:'max'}}]}}}));
      fs.writeFileSync(path.join(agent,'settings.json'),JSON.stringify({packages:[],extensions:[],skills:[],retry:{enabled:false}}));
      fs.writeFileSync(path.join(agent,'continual-learning.json'),JSON.stringify({plannerThinkingLevel:'low'}));
      process.env.PI_OFFLINE='1';process.argv[1]=fs.realpathSync('./node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js');process.execPath=Bun.which('node');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'h',snapshotDigest:'h'};
      const candidate={name:'a.md',kind:'project',classification:'private',content:'Original',evidence:[{index:0,quote:'Source'}]},targets=prepareMemoryBodyTargets([candidate],[]);
      const original={kind:'incremental-memory-plan',version:1,...identity,operations:[],newMemories:[candidate]},before=JSON.stringify(original);
      try{
        const repaired=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,selectedNames:[],repairableNames:['a.md'],...('__SCOPE__'==='unknown'?{}:{repairableFields:{'a.md':['__SCOPE__']}}),errors:['held'],model:'fixture/deepseek',
          bodyReview:{status:'reviewed',targets,judgments:targets.map(t=>({id:t.id,verdict:'consistent',witnesses:[]})),calls:1,durationMs:1,usageComplete:true},
          semanticContext:{frozenEvidence:{entries:[{role:'user',content:'Source'}]},existingMemories:[]}});
        console.log(JSON.stringify({calls,thinking,effort:effort??null,tools:tools?.length??0,outcome:repaired.outcome,inputUnchanged:before===JSON.stringify(original),externalRequests:0}));
      }finally{server.stop(true)}
    '''.replace('__SCOPE__', scope), timeout=30)
    assert result['calls'] == 1 and result['tools'] == 0
    # An empty amendment is still failed learning, regardless of wire effort.
    assert result['outcome'] == 'failed' and result['inputUnchanged']
    assert result['externalRequests'] == 0
    if scope == 'description':
        assert result['thinking'] == {'type': 'disabled'} and result['effort'] is None
    else:
        assert result.get('thinking') != {'type': 'disabled'} and result['effort'] == 'max'
