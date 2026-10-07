from support import isolated_run_bun


def test_generation_prompts_require_claim_specific_original_citations() -> None:
    value = isolated_run_bun(r'''
      import {buildIncrementalMemoryConsolidatorPrompt,buildMemoryConsolidatorPrompt,MEMORY_CITATION_GUIDANCE} from './packages/continual-learning/extensions/planner-prompts.ts';
      const bindings={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h',dossierPath:'d.json',pkgDir:'pkg',runDir:'run',snapshotPath:'s.json',harnessDir:'private',publicDir:'public',repoRoot:'repo'};
      const prompts=[buildIncrementalMemoryConsolidatorPrompt(bindings),buildMemoryConsolidatorPrompt(bindings)];
      console.log(JSON.stringify({guidance:MEMORY_CITATION_GUIDANCE,prompts}));
    ''')
    guidance = value['guidance']
    assert 'future-task instruction does not prove a verified current state' in guidance
    assert 'each body and description claim' in guidance
    assert 'later corrections, revocations and exceptions' in guidance
    assert 'Do not attach all entries' in guidance
    assert '8 evidence items' in guidance and '2,000 characters' in guidance
    assert 'Preserve privacy classifications' in guidance
    assert all(guidance in prompt for prompt in value['prompts'])


def test_actual_semantic_worker_receives_guidance_without_new_write_authority() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');const inputs=[];
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{inputs.push(input);return {exitCode:0,stderr:'',text:JSON.stringify(payload),cancelled:false}}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {MEMORY_CITATION_GUIDANCE}=await import('./packages/continual-learning/extensions/planner-prompts.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const payload={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[{name:'fact.md',kind:'project',classification:'safe',content:'Project uses Vitest.',evidence:[{index:1,quote:'Verified migration to Vitest.',role:'toolResult'}]}]};
      const context={frozenEvidence:{contextEnabled:true,entries:[{role:'user',content:'Use Vitest for future tasks.'},{role:'toolResult',content:'Verified migration to Vitest.'}]},existingMemories:[]};
      const semantic=await repairIncrementalMemoryPlan({identity,rejectedPlan:payload,errors:['uncertain'],selectedNames:[],semanticContext:context});
      const structural=await repairIncrementalMemoryPlan({identity,rejectedPlan:payload,errors:['schema'],selectedNames:[]});
      console.log(JSON.stringify({semantic,structural,semanticGuidance:inputs[0].prompt.includes(MEMORY_CITATION_GUIDANCE),structuralGuidance:inputs[1].prompt.includes(MEMORY_CITATION_GUIDANCE),tools:inputs.map(i=>i.tools),contextUnchanged:JSON.stringify(JSON.parse(inputs[0].prompt.split('\n').at(-1)).semanticContext)===JSON.stringify(context)}));
    ''')
    assert value['semanticGuidance'] and not value['structuralGuidance']
    assert value['semantic']['outcome'] == 'repaired'
    assert value['contextUnchanged']
    assert all(tools == [] for tools in value['tools'])


def test_repair_schema_demonstrates_a_fact_without_authorizing_example_copy() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let prompt='';
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{prompt=input.prompt;return {exitCode:0,stderr:'',text:JSON.stringify(payload),cancelled:false}}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const payload={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[]};
      await repairIncrementalMemoryPlan({identity,rejectedPlan:payload,errors:['description unsupported'],selectedNames:[]});
      const start=prompt.indexOf('{\n'),end=prompt.indexOf('\n}\n',start)+2;
      const example=JSON.parse(prompt.slice(start,end)).newMemories[0].content;
      const description=/^description: (.+)$/m.exec(example)[1];const body=example.split('\n---\n')[1].trim();
      console.log(JSON.stringify({description,body,exampleIsNotEvidence:prompt.includes('The schema example is not evidence'),tools:[]}));
    ''')
    assert value['description'] == value['body']
    assert value['exampleIsNotEvidence']
