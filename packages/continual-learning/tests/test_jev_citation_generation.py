from support import isolated_run_bun


def test_generation_prompts_require_claim_specific_original_citations() -> None:
    value = isolated_run_bun(r'''
      import {buildIncrementalMemoryConsolidatorPrompt,buildMemoryConsolidatorPrompt,MEMORY_CITATION_GUIDANCE,MEMORY_KNOWLEDGE_GUIDANCE} from './packages/continual-learning/extensions/planner-prompts.ts';
      const bindings={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h',dossierPath:'d.json',pkgDir:'pkg',runDir:'run',snapshotPath:'s.json',harnessDir:'private',publicDir:'public',repoRoot:'repo'};
      const prompts=[buildIncrementalMemoryConsolidatorPrompt(bindings),buildMemoryConsolidatorPrompt(bindings)];
      console.log(JSON.stringify({guidance:MEMORY_CITATION_GUIDANCE,knowledge:MEMORY_KNOWLEDGE_GUIDANCE,prompts}));
    ''')
    guidance = value['guidance']
    assert 'future-task instruction does not prove a verified current state' in guidance
    assert 'each body and description claim' in guidance
    assert 'later corrections, revocations and exceptions' in guidance
    assert 'Do not attach all entries' in guidance
    assert '8 evidence items' in guidance and '2,000 characters' in guidance
    assert 'Preserve privacy classifications' in guidance
    assert 'controlling branch conditions' in guidance
    assert 'before shortening' in guidance
    assert 'removed lines establish the predecessor state' in guidance
    assert 'A patch is a transition' in guidance
    assert 'latest observed state is incomplete' in guidance
    assert 'work already queued at the inspected completion check' in guidance
    assert 'caller-facing Promise continuations' in guidance
    assert 'instantaneous empty state' in guidance
    assert 'pipeline or output filter does not establish' in guidance
    assert 'upstream command' in guidance
    # V95 treated an assertion label as the actual outstanding work.
    # This checks delivery only; real generation and later tasks remain required.
    assert 'failure message is an observed label, not proof of its named mechanism' in guidance
    assert 'trace the awaited reactions, completed callbacks and unreleased work' in guidance
    assert 'identify only that missing condition as unresolved' in guidance
    assert 'keep the actual blocking state unresolved' not in guidance
    # An unknown cause does not erase an independently observed state.
    assert 'Unknown cause does not make an observed state unknown' in guidance
    assert 'Do not generalize uncertainty about one missing condition' in guidance
    # Given stateful knowledge, generation receives an explicit relation contract.
    # This checks input delivery, not factual correctness or later task benefit.
    for relation in ('whose resource or result is involved', 'which event changes its state',
                     'what stays unchanged', 'material default or selected branch'):
        assert value['knowledge'].count(relation) == 1
    assert len(value['knowledge']) <= 5768
    assert 'source-scoped observation' in value['knowledge']
    assert 'unsupported or obsolete draft claims' in value['knowledge']
    assert '**Conditions**' in value['knowledge'] and '**Revisit**' in value['knowledge']
    assert 'a reached failed check' in value['knowledge']
    assert 'not a permanent instruction to keep the failure unresolved' in value['knowledge']
    assert 'do not create a durable task log' in value['knowledge']
    # Initial generation uses the parent-ref contract. Legacy quote/index and
    # repair-specific guidance remain in maintenance and semantic correction.
    initial, maintenance = value['prompts']
    assert guidance not in initial
    assert guidance in maintenance
    assert 'Quotes must be verbatim with their original snapshot indexes.' not in initial
    assert 'During semantic repair,' not in initial
    assert 'Copy existing labels; never invent labels, calculate coordinates' in initial
    assert 'never invent or truncate away a condition' not in initial
    assert 'preserve the complete statement\'s' in initial
    assert 'Reserved existing Memory filenames' in initial
    assert 'memoryReplayFeedback' in initial
    assert 'diagnosticsStatus is bound to that exact plan' in initial
    assert all(value['knowledge'] in prompt for prompt in value['prompts'])
    assert 'Within a new record body, state each supported fact once' in value['knowledge']
    assert 'Keep independent named-type requirements' in value['knowledge']
    assert 'an index description may repeat one supported body fact for discovery' in value['knowledge']
    assert 'not a hard length limit' in value['knowledge']
    assert 'does not authorize compressing an already correct record' in value['knowledge']
    # Given a maintenance fact or failure observation, When choosing its format,
    # Then keep its purpose without requiring an unrelated declaration dump.
    # Exact declared-API records retain the original complete-declaration rule.
    # This proves framing only, not model compliance or learning benefit.
    initial = value['prompts'][0]
    assert 'use `description` plus `knowledge` instead of `content` and `evidence`' in initial
    assert '"sourceCitationIndex":0' in initial
    assert 'classification justified by the evidence; source copying grants no sharing permission' in initial
    assert 'generate new project proposals with `knowledge`' in initial
    assert 'exact copying does not make a partial selection complete' in initial
    assert '**Why** and **How to apply**' in initial
    assert 'Keep the complete exact declaration inline' in initial
    assert 'When the knowledge is an inspected declared API contract' in initial
    # Given the real record mixes runtime observations and a declared return
    # claim, a behavior-record exemption must not erase its type obligations.
    # Pure observations keep the existing conditional declaration requirement.
    import json
    from pathlib import Path
    fixture = json.loads((Path(__file__).parent / 'fixtures/real-description-body-conflict.json').read_text())['hybridDeclarationCase']
    assert fixture['sourceVersion'] in fixture['content']
    assert 'was `undefined`' in fixture['content']
    assert 'The `limitFunction` declaration types its returned value' in fixture['content']
    assert fixture['formalFactoryDeclaration'] not in fixture['content']
    assert fixture['missingNamedTypeBridge'] and not fixture['candidateReviewForwarded']
    assert not fixture['learningAccepted']
    assert 'Behavior and failure observations do not require a declaration excerpt' not in initial
    assert 'Keep the subject, dependencies and applicable conditions explicit' in initial
    assert 'Do not invent a purpose, currentness guarantee or runtime behavior' in initial


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
      const original=JSON.stringify(context);
      const semantic=await repairIncrementalMemoryPlan({identity,rejectedPlan:payload,errors:['uncertain'],selectedNames:[],semanticContext:context});
      const structural=await repairIncrementalMemoryPlan({identity,rejectedPlan:payload,errors:['schema'],selectedNames:[]});
      console.log(JSON.stringify({semantic,structural,semanticGuidance:inputs[0].prompt.includes(MEMORY_CITATION_GUIDANCE),structuralGuidance:inputs[1].prompt.includes(MEMORY_CITATION_GUIDANCE),tools:inputs.map(i=>i.tools),contextUnchanged:JSON.stringify(context)===original,shownContext:JSON.parse(inputs[0].prompt.split('\n').at(-1)).semanticContext}));
    ''')
    assert value['semanticGuidance'] and not value['structuralGuidance']
    # An unchanged semantic answer cannot resample the original held review.
    assert value['semantic']['outcome'] == 'failed' and value['semantic']['failureKind'] == 'no-correction'
    assert 'plan' not in value['semantic'] and value['structural']['outcome'] == 'repaired'
    assert value['contextUnchanged']
    shown = value['shownContext']['frozenEvidence']['entries']
    assert [entry['snapshotIndex'] for entry in shown] == [0, 1]
    assert [entry['entry']['role'] for entry in shown] == ['user', 'toolResult']
    assert [entry['entry']['content']['citationLines'] for entry in shown] == [
        {'block': 0, 'lines': [{'line': 1, 'text': 'Use Vitest for future tasks.', 'ref': 'e0.b0.l1'}]},
        {'block': 0, 'lines': [{'line': 1, 'text': 'Verified migration to Vitest.', 'ref': 'e1.b0.l1'}]},
    ]
    assert value['shownContext']['existingMemories'] == []
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


def test_initial_and_repair_generation_examples_do_not_reintroduce_legacy_citation_fields() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let prompt;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{prompt=input.prompt;return {exitCode:0,stderr:'',text:'{}'}}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      await repairIncrementalMemoryPlan({identity:{runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'},rejectedPlan:{operations:[],newMemories:[]},errors:['citation'],selectedNames:[],structuralCorrection:true,semanticContext:{frozenEvidence:{entries:[{role:'user',content:'Observed fact'}]},existingMemories:[]}});
      const template=fs.readFileSync('./packages/continual-learning/prompts/incremental-memory-consolidator.md','utf8');const instructions=prompt.slice(0,prompt.lastIndexOf('\n'));
      console.log(JSON.stringify({examples:[template,instructions].map(text=>Array.from(text.matchAll(/(?:"evidence"|evidence:)\s*:?\s*\[\s*\{\s*(?:"?)(\w+)/g),m=>m[1])),copyQuotes:instructions.includes('Copy those exact quotes'),legacyInstruction:template.includes('each evidence item has a snapshot `index`')}));
    ''')
    assert all(examples and set(examples) == {'ref'} for examples in value['examples'])
    assert not value['copyQuotes'] and not value['legacyInstruction']
