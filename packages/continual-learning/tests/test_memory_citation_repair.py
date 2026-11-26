from __future__ import annotations

# --- Merged from test_memory_citation_repair.py ---
from support import REPO, isolated_run_bun


def test_knowledge_citation_amendment_preserves_units_metadata_and_catalog_positions() -> None:
    value = isolated_run_bun(r'''
      import {bindMemoryCitationAmendment,semanticMemoryRepairCandidates} from './packages/continual-learning/extensions/inject-memory.ts';
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const knowledge={sourceCitations:[{ref:'e1.b0.l1',endRef:'e1.b0.l99'},{ref:'e2.b0.l1'}],
        units:[{sourceCitationIndex:0},{text:'Why: Keep the declared owner. How to apply: Inspect that receiver.',citationIndexes:[0,1]}]};
      const item={name:'contract.md',kind:'project',classification:'safe',description:'The source declares the receiver.',knowledge};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[item]};
      const before=JSON.stringify(original),id=semanticMemoryRepairCandidates(original)[0].candidateId;
      const patch={candidateId:id,evidence:[{ref:'e1.b0.l3'},{ref:'e2.b0.l1'}]};
      const amendment={kind:'incremental-memory-amendment',version:1,...identity,replacements:[patch]};
      const result=bindMemoryCitationAmendment(original,amendment,identity),after=result.newMemories[0];
      const rejected={};
      const mutations={body:{...patch,content:'Lossy prose'},units:{...patch,knowledge:{...knowledge,units:[]}},
        description:{...patch,description:'Other'},privacy:{...patch,classification:'private'},
        dropCatalog:{...patch,evidence:patch.evidence.slice(0,1)},addCatalog:{...patch,evidence:[...patch.evidence,{ref:'e3.b0.l1'}]},
        emptyCatalog:{...patch,evidence:[]},foreignId:{...patch,candidateId:id+'x'}};
      for(const [name,p] of Object.entries(mutations)){try{bindMemoryCitationAmendment(original,{...amendment,replacements:[p]},identity);rejected[name]=false}catch{rejected[name]=true}}
      console.log(JSON.stringify({after,unitsPreserved:JSON.stringify(after.knowledge.units)===JSON.stringify(knowledge.units),
        unchanged:before===JSON.stringify(original),rejected}));
    ''')
    assert value['unitsPreserved'] and value['unchanged']
    assert value['after']['knowledge']['sourceCitations'] == [{'ref': 'e1.b0.l3'}, {'ref': 'e2.b0.l1'}]
    assert 'content' not in value['after'] and 'evidence' not in value['after']
    assert value['after']['classification'] == 'safe'
    assert all(value['rejected'].values()), value


def test_knowledge_catalog_failure_retains_typed_citation_cause_and_original_bound() -> None:
    value = isolated_run_bun(r'''
      import {materializeMemoryKnowledge,MemoryKnowledgeCitationError,MemoryCitationLocationError} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const snapshot={entries:[{role:'toolResult',content:'x'.repeat(1990)+'\nexport const owner = 1;'}]};
      const knowledge={sourceCitations:[{ref:'e0.b0.l2'},{ref:'e0.b0.l2'},{ref:'e0.b0.l1',endRef:'e0.b0.l2'}],units:[{text:'The source has an owner.',citationIndexes:[2]}]};
      let result;try{materializeMemoryKnowledge('---\nname: owner\ndescription: Source\ntype: project\n---\n',knowledge,snapshot)}catch(error){
        result={knowledgeError:error instanceof MemoryKnowledgeCitationError,citationCause:error.cause instanceof MemoryCitationLocationError,
          cause:error.cause?.message,message:error.message};}
      console.log(JSON.stringify(result));
    ''')
    assert value['knowledgeError'] and value['citationCause'], value
    assert 'maximumCharacters=2000' in value['cause']
    assert 'knowledge.sourceCitations[2]' in value['message'], value
    assert 'maximumCharacters=2000' in value['message'], value
    assert 'newMemories[0].evidence' not in value['message']
    assert 'export const owner' not in value['message']


def test_knowledge_catalog_unexpected_failure_keeps_untrusted_error_text_private() -> None:
    value = isolated_run_bun(r'''
      import {materializeMemoryKnowledge,MemoryKnowledgeCitationError} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const secret='private source must not enter diagnostics';
      const ref=new Proxy({}, {ownKeys(){throw new Error(secret)}});
      let result;try{materializeMemoryKnowledge('---\nname: owner\ndescription: Source\ntype: project\n---\n',
        {sourceCitations:[ref],units:[{text:'Source fact.',citationIndexes:[0]}]},{entries:[]})}catch(error){
          result={knowledgeError:error instanceof MemoryKnowledgeCitationError,message:error.message};}
      console.log(JSON.stringify(result));
    ''')
    assert value['knowledgeError']
    assert value['message'] == 'Atomic Memory source catalog has an invalid original-source citation'


def test_knowledge_citation_worker_keeps_source_units_and_usage_in_existing_single_slot() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let options,calls=0;
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const {materializeMemoryKnowledge}=await import('./packages/continual-learning/extensions/memory-citation-locations.ts');
      const snapshot={entries:[{role:'toolResult',content:'export const receiver = 1;\n'+'x'.repeat(1990)+'\nexport const owner = 1;'}]};
      const knowledge={sourceCitations:[{ref:'e0.b0.l1'},{ref:'e0.b0.l3'},{ref:'e0.b0.l2',endRef:'e0.b0.l3'}],units:[{sourceCitationIndex:0},
        {text:'Why: Retain the contract. How to apply: Check the exact receiver.',citationIndexes:[0,1,2]}]};
      let diagnostic;try{materializeMemoryKnowledge('---\nname: owner\ndescription: Source\ntype: project\n---\n',knowledge,snapshot)}catch(error){diagnostic=error.message}
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[
        {name:'contract.md',kind:'project',classification:'safe',description:'The source declares a receiver.',knowledge}]};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{calls++;options=input;const data=JSON.parse(input.prompt.split('\n').at(-1));
        return {exitCode:0,stderr:'',text:JSON.stringify({kind:'incremental-memory-amendment',version:1,...identity,
          replacements:[{candidateId:data.repairCandidates[0].candidateId,evidence:[{ref:'e0.b0.l1'},{ref:'e0.b0.l3'},{ref:'e0.b0.l3'}]}]}),
          usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:0},usageComplete:true};}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,selectedNames:[],structuralCorrection:true,citationOnly:true,
        errors:[diagnostic],
        semanticContext:{frozenEvidence:snapshot,existingMemories:[]}});
      console.log(JSON.stringify({result,calls,tools:options.tools,args:options.extraArgs,
        context:JSON.parse(options.prompt.split('\n').at(-1)),catalogContract:options.prompt.includes('same-length ordered source catalog')}));
    ''')
    assert value['result']['outcome'] == 'repaired', value['result']
    item = value['result']['plan']['newMemories'][0]
    assert item['knowledge']['sourceCitations'] == [{'ref': 'e0.b0.l1'}, {'ref': 'e0.b0.l3'}, {'ref': 'e0.b0.l3'}]
    assert item['knowledge']['units'][0] == {'sourceCitationIndex': 0}
    assert item['knowledge']['units'][1]['text'].startswith('Why: Retain the contract.')
    assert 'content' not in item and 'evidence' not in item
    assert value['calls'] == 1 and value['tools'] == [] and value['catalogContract']
    assert any('knowledge.sourceCitations[2]' in item and 'maximumCharacters=2000' in item
               for item in value['context']['errors']), value['context']
    assert 'memory-amendment' in value['args']
    assert value['result']['usage']['totalTokens'] == 2


def test_structural_project_example_uses_the_current_knowledge_producer_contract() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let prompt;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        prompt=input.prompt;return {exitCode:0,stderr:'',text:'{}',cancelled:false};}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      await repairIncrementalMemoryPlan({identity,rejectedPlan:{kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,
        operations:[],newMemories:[]},selectedNames:[],structuralCorrection:true,errors:['Invalid body unit'],
        semanticContext:{frozenEvidence:{entries:[]},existingMemories:[]}});
      const marker='The repaired output MUST follow this exact incremental delta schema:\n';
      const start=prompt.indexOf(marker)+marker.length;
      const end=prompt.indexOf('\nThe schema example is not evidence:',start);
      const example=JSON.parse(prompt.slice(start,end)).newMemories[0];
      console.log(JSON.stringify({example,legacyRequirement:prompt.includes('Each newMemories item requires name, kind, content, and non-empty evidence')}));
    ''')
    assert value['example']['kind'] == 'project'
    assert 'knowledge' in value['example'] and 'description' in value['example']
    assert 'content' not in value['example'] and 'evidence' not in value['example']
    assert not value['legacyRequirement']


def test_citation_amendment_locks_every_non_evidence_field_and_preserves_omitted_candidates() -> None:
    value = isolated_run_bun(r'''
      import {bindMemoryCitationAmendment,semanticMemoryRepairCandidates} from './packages/continual-learning/extensions/inject-memory.ts';
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[{name:'old.md',kind:'rewrite',classification:'private',content:'Complete old body',observations:[{path:'src.ts',status:'found'}],evidence:[{index:0,lines:{block:0,start:999,end:999}}]}],newMemories:[{name:'new.md',kind:'project',classification:'safe',content:'New fact',evidence:[{index:0,quote:'Current source'}]}]};
      const before=JSON.stringify(original),ids=semanticMemoryRepairCandidates(original),patch={candidateId:ids[0].candidateId,evidence:[{ref:'e0.b0.l1'}]};
      const amendment={kind:'incremental-memory-amendment',version:1,...identity,replacements:[patch]};
      const result=bindMemoryCitationAmendment(original,amendment,identity);const invalid=[{...amendment,runId:'other'},{...amendment,replacements:[]},{...amendment,replacements:[patch,patch]},...[
        {...patch,content:'Changed body'},{...patch,name:'other.md'},{...patch,candidateId:ids[1].candidateId+'changed'},{...patch,evidence:[{index:0,quote:'Current source'}]},
      ].map(p=>({...amendment,replacements:[p]}))];
      const denied=invalid.map(v=>{try{bindMemoryCitationAmendment(original,v,identity);return false}catch{return true}});
      const {evidence:a,...old}=original.operations[0],{evidence:b,...next}=result.operations[0];
      console.log(JSON.stringify({sameBodyAndIntent:JSON.stringify(old)===JSON.stringify(next),omitted:JSON.stringify(result.newMemories)===JSON.stringify(original.newMemories),unchanged:before===JSON.stringify(original),evidence:b,denied}));
    ''')
    assert value['sameBodyAndIntent'] and value['omitted'] and value['unchanged']
    assert value['evidence'] == [{'ref': 'e0.b0.l1'}]
    assert all(value['denied'])


def test_structural_citation_worker_returns_only_refs_and_parent_restores_complete_body() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let options;
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[{name:'old.md',kind:'rewrite',classification:'private',content:'Locked body',evidence:[{index:0,lines:{block:0,start:999,end:999}}]}],newMemories:[]};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{options=input;const context=JSON.parse(input.prompt.split('\n').at(-1));return {exitCode:0,stderr:'',text:JSON.stringify({kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:context.repairCandidates[0].candidateId,evidence:[{ref:'e0.b0.l1'}]}]}),usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:0}}}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,selectedNames:['old.md'],structuralCorrection:true,citationOnly:true,errors:['Memory citation locations are invalid'],semanticContext:{frozenEvidence:{entries:[{role:'toolResult',content:'Current source'}]},existingMemories:[{name:'old.md',classification:'private',content:'Predecessor body'}]}});
      console.log(JSON.stringify({result,tools:options.tools,args:options.extraArgs,context:JSON.parse(options.prompt.split('\n').at(-1)),locked:options.prompt.includes('Do not output content'),knowledgeContract:options.prompt.includes('Knowledge output contract:')}));
    ''')
    assert value['result']['outcome'] == 'repaired'
    assert value['result']['plan']['operations'][0]['content'] == 'Locked body'
    assert value['result']['plan']['operations'][0]['evidence'][0]['quote'] == 'Current source'
    assert value['tools'] == [] and value['locked']
    assert not value['knowledgeContract']
    assert 'memory-amendment' in value['args']
    assert value['context']['semanticContext']['existingMemories'][0]['content'] == 'Predecessor body'


def test_citation_failure_with_unvalidated_delete_uses_full_existing_correction_slot() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let options;
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const existingContent='---\ndescription: Existing source\ntype: project\n---\nStill required predecessor';
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[{name:'old.md',kind:'delete',classification:'private',verdict:'SUPERSEDED',preservedIn:['nonexistent.md'],evidence:[{ref:'e0.b0.l999'}]}],newMemories:[]};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{options=input;const context=JSON.parse(input.prompt.split('\n').at(-1));return {exitCode:0,stderr:'',text:JSON.stringify({kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:context.repairCandidates[0].candidateId,content:existingContent+'\nCurrent source',evidence:[{ref:'e0.b0.l1'}]}]}),usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:0}}}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,selectedNames:['old.md'],structuralCorrection:true,citationOnly:true,allowDeleteReconsideration:true,errors:['Memory citation locations are invalid'],semanticContext:{frozenEvidence:{entries:[{role:'toolResult',content:'Current source'}]},existingMemories:[{name:'old.md',classification:'private',content:existingContent}]}});
      console.log(JSON.stringify({result,existingContent,example:JSON.parse(options.prompt.split('\n').at(-1)).outputSchema.replacements[0].content,tools:options.tools,locked:options.prompt.includes('Do not output content'),knowledgeContract:options.prompt.includes('Knowledge output contract:'),reconsideration:options.prompt.includes('delete to rewrite')}));
    ''')
    assert value['result']['outcome'] == 'repaired'
    assert value['result']['plan']['operations'][0]['kind'] == 'rewrite'
    assert value['result']['plan']['operations'][0]['classification'] == 'private'
    assert value['tools'] == [] and not value['locked'] and value['reconsideration']
    assert value['knowledgeContract']

    assert value['example'].split('---')[1] == value['existingContent'].split('---')[1]
    assert value['result']['plan']['operations'][0]['content'].startswith(value['existingContent'])


def test_recoverable_indentation_does_not_consume_unvalidated_delete_correction() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let options;
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[{name:'old.md',kind:'delete',classification:'private',verdict:'SUPERSEDED',preservedIn:['nonexistent.md'],evidence:[{index:0,quote:'Note: pending only.\n\nWhen enabled, reject.'}]}],newMemories:[]};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{options=input;const context=JSON.parse(input.prompt.split('\n').at(-1));return {exitCode:0,stderr:'',text:JSON.stringify({kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:context.repairCandidates[0].candidateId,content:'Current source',evidence:[{ref:'e0.b0.l1'}]}]}),usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:0}}}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,selectedNames:['old.md'],structuralCorrection:true,citationOnly:true,allowDeleteReconsideration:true,errors:['quote is not present in the cited snapshot entry'],semanticContext:{frozenEvidence:{entries:[{role:'toolResult',content:'\tNote: pending only.\n\n\tWhen enabled, reject.'}]},existingMemories:[{name:'old.md',classification:'private',content:'Still required predecessor'}]}});
      console.log(JSON.stringify({result,tools:options.tools,locked:options.prompt.includes('Do not output content'),knowledgeContract:options.prompt.includes('Knowledge output contract:'),reconsideration:options.prompt.includes('delete to rewrite')}));
    ''')
    assert value['result']['outcome'] == 'repaired'
    assert value['result']['plan']['operations'][0]['kind'] == 'rewrite'
    assert value['result']['plan']['operations'][0]['classification'] == 'private'
    assert value['tools'] == [] and not value['locked'] and value['reconsideration']
    assert value['knowledgeContract']


def test_bound_delete_citation_amendment_preserves_every_unaffected_candidate() -> None:
    value = isolated_run_bun(r'''
      import {bindMemoryCitationAmendment,semanticMemoryRepairCandidates} from './packages/continual-learning/extensions/inject-memory.ts';
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const old={name:'old.md',kind:'delete',classification:'private',verdict:'SUPERSEDED',preservedIn:['absent.md'],evidence:[{ref:'e0.b0.l999'}]};
      const other={name:'other.md',kind:'rewrite',classification:'safe',content:'Locked peer',evidence:[{ref:'e0.b0.l1'}]};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[old,other],newMemories:[{name:'new.md',kind:'project',content:'Locked new fact',evidence:[{ref:'e0.b0.l1'}]}]};
      const ids=semanticMemoryRepairCandidates(original);const patch={candidateId:ids[0].candidateId,content:'Complete preserved knowledge',evidence:[{ref:'e0.b0.l1'}]};const amendment={kind:'incremental-memory-amendment',version:1,...identity,replacements:[patch]};
      const before=JSON.stringify(original);const result=bindMemoryCitationAmendment(original,amendment,identity,{'old.md':'private'});
      const invalid=[()=>bindMemoryCitationAmendment(original,amendment,identity),()=>bindMemoryCitationAmendment(original,amendment,identity,{'old.md':'safe'}),()=>bindMemoryCitationAmendment(original,{...amendment,replacements:[{...patch,candidateId:ids[1].candidateId}]},identity,{'other.md':'safe'}),()=>bindMemoryCitationAmendment(original,{...amendment,replacements:[patch,patch]},identity,{'old.md':'private'}),()=>bindMemoryCitationAmendment(original,{...amendment,runId:'foreign'},identity,{'old.md':'private'}),()=>bindMemoryCitationAmendment(original,{...amendment,replacements:[{...patch,kind:'rewrite'}]},identity,{'old.md':'private'})].map(f=>{try{f();return false}catch{return true}});
      console.log(JSON.stringify({result,unchanged:before===JSON.stringify(original),peer:JSON.stringify(result.operations[1])===JSON.stringify(other),newSame:JSON.stringify(result.newMemories)===JSON.stringify(original.newMemories),invalid}));
    ''')
    operation = value['result']['operations'][0]
    assert operation['name'] == 'old.md' and operation['kind'] == 'rewrite'
    assert operation['classification'] == 'private'
    assert operation['content'] == 'Complete preserved knowledge'
    assert 'preservedIn' not in operation and 'verdict' not in operation
    assert value['unchanged'] and value['peer'] and value['newSame']
    assert all(value['invalid'])


def test_fresh_project_output_contract_preserves_preference_excerpt_and_legacy_reader() -> None:
    value = isolated_run_bun(r'''
      import {assertFreshMemoryProjectOutput} from './packages/continual-learning/extensions/planner-output-schema.ts';
      import {materializeSourceExcerptPlan} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const evidence=[{ref:'e0.b0.l1'}],content='---\nname: old\ndescription: Source\ntype: project\n---\nLegacy knowledge.';
      const project={name:'old.md',kind:'project',classification:'safe',content,evidence};
      const knowledge={sourceCitations:evidence,units:[{text:'Observed source.',citationIndexes:[0]}]};
      const accepted=[{...project,kind:'preference',classification:'private'},
        {name:'new.md',kind:'project',classification:'safe',description:'Source',knowledge}];
      const rejected=[project,{name:'excerpt.md',kind:'project',classification:'private',sourceExcerpt:{ref:'e0.b0.l1'},evidence},{name:'bad.md',kind:'project',classification:'safe',sourceExcerpt:{ref:'e0.b0.l1'},evidence},
        {...project,knowledge},{name:'both.md',kind:'project',classification:'private',knowledge,sourceExcerpt:{ref:'e0.b0.l1'},evidence}];
      const passed=accepted.map(item=>{assertFreshMemoryProjectOutput({newMemories:[item]});return true});
      const errors=rejected.map(item=>{try{assertFreshMemoryProjectOutput({newMemories:[item]});return null}catch(error){return error.message}});
      const legacy={operations:[],newMemories:[project]},out=await materializeSourceExcerptPlan({manifest:{cwd:'/unused'}},legacy,{entries:[]});
      console.log(JSON.stringify({passed,errors,legacyUnchanged:JSON.stringify(legacy)===JSON.stringify(out)}));
    ''')
    assert all(value['passed']) and value['legacyUnchanged']
    assert all(error == 'Fresh Memory project output is invalid: newMemories[0] requires knowledge'
               for error in value['errors']), value


def test_fresh_project_raw_rejection_uses_one_existing_repair_before_source_materialization() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import {mock} from 'bun:test';
      import {assertFreshMemoryProjectOutput} from './packages/continual-learning/extensions/planner-output-schema.ts';
      import {materializeSourceExcerptPlan} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const kit=await import('./packages/kit/src/index.ts');let calls=0,reply,prompts=[];
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async(input)=>{calls++;prompts.push(input.prompt);return {exitCode:0,stderr:'',text:JSON.stringify(reply),
        usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:0},usageComplete:true};}}));
      const {repairIncrementalMemoryPlan,semanticMemoryRepairCandidates,retainOriginalMemoryGenerationPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'fresh-project-contract-')));
      try {
        const source=path.join(root,'api.d.ts'),text='export interface Pool { flush(): void; }\nexport function makePool(): Pool;';fs.writeFileSync(source,text);
        const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'read',name:'read',arguments:{path:source}}]},
          {role:'toolResult',toolName:'read',toolCallId:'read',isError:false,content:text}]};
        const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
        const item={name:'pool.md',kind:'project',classification:'safe',content:'---\nname: pool\ndescription: Pool\ntype: project\n---\nProse.',evidence:[{ref:'e1.b0.l1'}]};
        const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[item]},before=JSON.stringify(original);
        await retainOriginalMemoryGenerationPlan(root,identity,original);
        const originalArtifact=JSON.parse(fs.readFileSync(path.join(root,'generation-original-plan.json'),'utf8'));
        let rejection;try{assertFreshMemoryProjectOutput(original)}catch(error){rejection=error.message}
        const corrected={name:item.name,kind:'project',classification:'safe',description:'The inspected Pool declares flush.',knowledge:{
          sourceCitations:[{ref:'e1.b0.l1',endRef:'e1.b0.l2'}],units:[{kind:'declared-api-relation',factory:{ref:'e1.b0.l2'},owner:{ref:'e1.b0.l1'},member:{ref:'e1.b0.l1'}}]}};
        reply={...original,newMemories:[corrected]};
        const options={identity,rejectedPlan:original,selectedNames:[],errors:[rejection],structuralCorrection:true,requireNewProjectKnowledge:true,fileSourcesFromCwd:root,semanticContext:{frozenEvidence:snapshot,existingMemories:[]}};
        const repaired=await repairIncrementalMemoryPlan(options);
        const raw=JSON.stringify(repaired.plan);const materialized=await materializeSourceExcerptPlan({manifest:{cwd:root}},repaired.plan,snapshot,undefined,{retainSelectedDeclarations:true});
        const badOutput=path.join(root,'bad-response');fs.mkdirSync(badOutput);reply=original;
        const failed=await repairIncrementalMemoryPlan({...options,outputDir:badOutput});
        const artifact=JSON.parse(fs.readFileSync(path.join(badOutput,'structural-repair-response.json'),'utf8'));
        const legacy=await repairIncrementalMemoryPlan({...options,requireNewProjectKnowledge:undefined});
        const candidateId=semanticMemoryRepairCandidates(materialized)[0].candidateId;
        reply={kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId,evidence:[{ref:'e1.b0.l1',endRef:'e1.b0.l2'}]}]};
        const internal=await repairIncrementalMemoryPlan({...options,rejectedPlan:materialized,citationOnly:true,
          semanticContext:{frozenEvidence:snapshot,existingMemories:[]}});
        console.log(JSON.stringify({rejection,repaired,materialized,rawRetained:raw===JSON.stringify(repaired.plan),failed,legacy,internal,originalArtifact,calls,promptTextCatalog:prompts[0].includes('citationIndexes')&&!prompts[0].includes('declared-api-relation')&&!prompts[0].includes('"sourceCitationIndex":'),
          originalUnchanged:before===JSON.stringify(original),badRawRetained:JSON.parse(artifact.output).newMemories[0].content===item.content,
          memoryWrite:fs.existsSync(path.join(root,'.memory')),sourceUnchanged:fs.readFileSync(source,'utf8')===text}));
      }finally{fs.rmSync(root,{recursive:true,force:true})}
    ''')
    assert value['rejection'].startswith('Fresh Memory project output is invalid:'), value
    assert value['repaired']['outcome'] == 'repaired', value
    assert value['repaired']['plan']['newMemories'][0]['knowledge']['units'] == [{'kind':'declared-api-relation','factory':{'ref':'e1.b0.l2'},'owner':{'ref':'e1.b0.l1'},'member':{'ref':'e1.b0.l1'}}]
    body = value['materialized']['newMemories'][0]['content']
    assert 'export interface Pool { flush(): void; }' in body and 'export function makePool(): Pool;' in body
    assert 'knowledge' not in value['materialized']['newMemories'][0]
    assert value['failed']['outcome'] == 'failed' and value['failed']['failureKind'] == 'framing'
    assert value['legacy']['outcome'] == 'repaired'
    assert value['internal']['outcome'] == 'repaired', value['internal']
    assert value['internal']['plan']['newMemories'][0]['content'] == body
    assert value['originalArtifact']['originalPlan']['newMemories'][0]['content'].endswith('Prose.')
    assert value['promptTextCatalog']
    assert value['calls'] == 4 and value['originalUnchanged'] and value['badRawRetained'] and value['rawRetained']
    assert value['sourceUnchanged'] and not value['memoryWrite']


def test_initial_generation_archive_keeps_only_parsed_plan_and_hashes_sensitive_content() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {retainOriginalMemoryGenerationPlan} from './packages/continual-learning/extensions/inject-memory.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'initial-plan-archive-')));
      try {
        const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'h',snapshotDigest:'h'};
        const raw={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[
          {name:'pool.md',kind:'project',classification:'safe',description:'Pool contract',knowledge:{sourceCitations:[{ref:'e1.b0.l1'}],units:[{sourceCitationIndex:0}]}}]};
        await retainOriginalMemoryGenerationPlan(root,identity,raw);
        const file=path.join(root,'generation-original-plan.json'),plain=JSON.parse(fs.readFileSync(file,'utf8'));
        const secret={...raw,newMemories:[{name:'secret.md',kind:'project',classification:'private',content:'api_key = "real_credential_value_123456789"'}]};
        const other=path.join(root,'other');fs.mkdirSync(other);await retainOriginalMemoryGenerationPlan(other,identity,secret);
        const hiddenText=fs.readFileSync(path.join(other,'generation-original-plan.json'),'utf8'),hidden=JSON.parse(hiddenText);
        console.log(JSON.stringify({plain,hidden,plainDigest:sha256Digest(JSON.stringify(raw)),secretDigest:sha256Digest(JSON.stringify(secret)),
          privateMode:(fs.statSync(file).mode&0o777)===0o600,secretAbsent:!hiddenText.includes('real_credential_value'),rawUnchanged:!!raw.newMemories[0].knowledge,
          keys:Object.keys(plain)}));
      }finally{fs.rmSync(root,{recursive:true,force:true})}
    ''')
    assert value['plain']['originalPlan']['newMemories'][0]['knowledge']['units'] == [{'sourceCitationIndex': 0}]
    assert value['plain']['originalPlanDigest'] == value['plainDigest']
    assert value['plain']['snapshotDigest'] == value['plain']['artifactHash'] == 'h'
    assert value['plain']['originalPlanRetained'] and not value['plain']['sensitive']
    assert 'originalPlan' not in value['hidden'] and value['hidden']['sensitive']
    assert not value['hidden']['originalPlanRetained'] and value['hidden']['originalPlanDigest'] == value['secretDigest']
    assert value['secretAbsent'] and value['privateMode'] and value['rawUnchanged']
    assert set(value['keys']) == {'version', 'runId', 'scopeKey', 'scopeDigest', 'artifactHash', 'snapshotDigest',
                                  'originalPlanDigest', 'originalPlanBytes', 'sensitive', 'originalPlanRetained', 'originalPlan'}


def test_fresh_contract_gate_ends_at_successful_initial_materialization() -> None:
    # The parent owns this boundary; materialized plans use the existing repair
    # contract rather than being mistaken for a second raw producer response.
    source = (REPO / "packages/continual-learning/extensions/inject-memory.ts").read_text()
    start = source.index("        let originalIncrementalError: string | undefined = incrementalError;")
    end = source.index("          repairAttempt = {", start)
    boundary = source[start:end]
    materialize = boundary.index("rawPlan = await materializeSourceMemoryPlan")
    settled = boundary.index("freshProjectOutputPending = false;", materialize)
    expanded = boundary.index("plan = await expandCitedIncrementalMemoryPlan", materialize)
    assert materialize < settled < expanded
    assert "...(freshProjectOutputPending ? {requireNewProjectKnowledge: true as const} : {})" in boundary


def test_fresh_structural_repair_delivers_file_contract_as_data_without_provider_schema_support():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let captured;
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const content='---\nname: source\ndescription: Observed\ntype: project\n---\nObserved source.';
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[{name:'source.md',kind:'project',classification:'private',content,evidence:[{ref:'e2.b0.l1'}]}]};
      const reply={...original,newMemories:[{name:'source.md',kind:'project',classification:'private',description:'Observed source.',knowledge:{sourceCitations:[{ref:'e2.b0.l1'}],units:[{text:'Observed source.',citationIndexes:[0]}]}}]};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async(input)=>{captured=input;return {exitCode:0,stderr:'',text:JSON.stringify(reply),usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:0},usageComplete:true}}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'repair-contract-data-')));
      try {
        fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json'),JSON.stringify({plannerStructuredOutput:false}));
        const snapshot={entries:[{role:'user',content:'Keep this observation.'},{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:path.join(root,'source.ts')}}]},
          {role:'toolResult',toolName:'read',toolCallId:'r',isError:false,content:'export const observed = true;'},
          {role:'toolResult',toolName:'bash',toolCallId:'b',isError:false,content:'observed true'}]};
        const before=JSON.stringify(snapshot);
        const result=await repairIncrementalMemoryPlan({outputDir:root,identity,rejectedPlan:original,selectedNames:[],errors:['shape'],structuralCorrection:true,requireNewProjectKnowledge:true,fileSourcesFromCwd:root,semanticContext:{frozenEvidence:snapshot,existingMemories:[]},model:'gpt-6-luna'});
        const text=captured.prompt;const data=JSON.parse(text.slice(text.lastIndexOf('\n{')+1));
        console.log(JSON.stringify({outcome:result.outcome,contract:data.memoryOutputContract,unchanged:before===JSON.stringify(snapshot),hasHiddenSchemaFlag:captured.extraArgs.includes('--learning-citation-domain')}));
      }finally{fs.rmSync(root,{recursive:true,force:true})}
    ''', temp_dirs=('PI_CODING_AGENT_DIR',))
    assert value['outcome'] == 'repaired' and value['unchanged'] and not value['hasHiddenSchemaFlag']
    assert value['contract']['kind'] == 'fresh-memory-file-source-contract'
    assert 'e2.b0.l1' in value['contract']['schema']['$defs']['memorySourceReference']['enum']
    assert 'memoryFileSourceReference' not in value['contract']['schema']['$defs']
    assert len(value['contract']['domainDigest']) == len(value['contract']['fileDomainDigest']) == 64


def test_native_fresh_plan_repair_reaches_parent_source_materialization_and_private_apply():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import os from 'node:os';import {execFileSync} from 'node:child_process';import {mock} from 'bun:test';import {Value} from 'typebox/value';
      import extension from './packages/continual-learning/extensions/planner-json-output.ts';
      const kit=await import('./packages/kit/src/index.ts');let next,schema,binding;const shape=[];
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        const args=input.extraArgs,flags={};for(let i=0;i<args.length-1;i++)if(args[i].startsWith('--learning-'))flags[args[i]]=args[i+1];
        binding=flags['--learning-native-fresh-binding']?JSON.parse(flags['--learning-native-fresh-binding']):undefined;
        let hook;extension({registerFlag:()=>{},getFlag:n=>flags['--'+n],getActiveTools:()=>[],on:(e,fn)=>{if(e==='before_provider_request')hook=fn}});
        schema=hook({payload:{input:[{role:'user',content:'New authored source fixture.'}]}},{model:{api:'openai-responses',id:'gpt-6-luna'}})?.text?.format?.schema;
        shape.push(schema?Value.Check(schema,next):null);
        return {exitCode:0,stderr:'',text:JSON.stringify(next),usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:0},usageComplete:true};
      }}));
      const {repairIncrementalMemoryPlan,expandCitedIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {createConsolidationRun,releaseConsolidationRun,applyConsolidationPlan}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const {materializeSourceExcerptPlan,assertSourceExcerptBindings}=await import('./packages/continual-learning/extensions/source-excerpt-memory.ts');
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'fresh-native-parent-'))),repo=path.join(root,'project');fs.mkdirSync(repo);execFileSync('git',['init','-q',repo]);
      const agent=path.join(root,'agent');fs.mkdirSync(agent);process.env.PI_CODING_AGENT_DIR=agent;fs.writeFileSync(path.join(agent,'continual-learning.json'),JSON.stringify({plannerStructuredOutput:true}));
      const source='export interface Pool { flush(): void; }\nexport function allocatePool(): Pool;';fs.writeFileSync(path.join(repo,'api.d.ts'),source);
      const entries=[{message:{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:'api.d.ts'}}]}},{message:{role:'toolResult',toolName:'read',toolCallId:'r',isError:false,content:source}}];
      const run=await createConsolidationRun({cwd:repo,sessionManager:{getBranch:()=>entries,buildContextEntries:()=>entries}},repo,false);
      try{
        const snapshot=JSON.parse(fs.readFileSync(run.paths.snapshotFile,'utf8')),m=run.manifest,identity={runId:m.runId,scopeKey:m.scopeKey,scopeDigest:m.scopeDigest,artifactHash:m.snapshotDigest,snapshotDigest:m.snapshotDigest};
        const proposal={name:'pool.md',kind:'project',classification:'private',description:'The observed declaration returns Pool.',knowledge:{sourceCitations:[{ref:'e1.b0.l1'},{ref:'e1.b0.l2'}],units:[{text:'Why: The declaration returns Pool. How to apply: Inspect the declared return before using flush; runtime behavior is unverified.',citationIndexes:[0,1]}]}};
        const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[{...proposal,description:'x'.repeat(401)}]};
        const input={identity,rejectedPlan:original,selectedNames:[],errors:['Controlled metadata bound'],structuralCorrection:true,requireNewProjectKnowledge:true,fileSourcesFromCwd:repo,semanticContext:{frozenEvidence:snapshot,existingMemories:[]}};
        const good={...original,newMemories:[proposal]},before=JSON.stringify(original);next=good;const repaired=await repairIncrementalMemoryPlan(input),actualBinding=binding;
        const materialized=await materializeSourceExcerptPlan(run,repaired.plan,snapshot,undefined,{retainSelectedDeclarations:true});
        const expanded=await expandCitedIncrementalMemoryPlan(run,[],materialized);await applyConsolidationPlan(run,expanded,()=>true,()=>assertSourceExcerptBindings(run));
        const stored=fs.readFileSync(path.join(m.harnessDir,'pool.md'),'utf8');const bad={};
        for(const [label,change] of Object.entries({wrongId:p=>p.runId+='x',tooLong:p=>p.newMemories[0].description='x'.repeat(401),foreign:p=>p.newMemories[0].knowledge.sourceCitations[0]={ref:'e1.b0.l99'},privacy:p=>p.newMemories[0].classification='safe',zero:p=>p.newMemories=[],operation:p=>p.operations=[{}]})){
          next=structuredClone(good);change(next);try{const r=await repairIncrementalMemoryPlan(input);if(r.outcome==='repaired'){const body=await materializeSourceExcerptPlan(run,r.plan,snapshot,undefined,{retainSelectedDeclarations:true});await expandCitedIncrementalMemoryPlan(run,[],body);}bad[label]=r.outcome==='failed'}catch{bad[label]=true}
        }
        next=good;await repairIncrementalMemoryPlan({...input,selectedNames:['existing.md']});const nonemptyBinding=binding;
        console.log(JSON.stringify({repaired:repaired.outcome,stored,privateOnly:!fs.existsSync(path.join(m.publicDir,'pool.md')),sourceUnchanged:fs.readFileSync(path.join(repo,'api.d.ts'),'utf8')===source,unchanged:before===JSON.stringify(original),actualBinding,nonemptyBinding:nonemptyBinding??null,bad,shape}));
      }finally{await releaseConsolidationRun(run);fs.rmSync(root,{recursive:true,force:true})}
    ''')
    assert value['repaired'] == 'repaired', value
    assert 'allocatePool' in value['stored'] and 'Pool' in value['stored']
    assert value['privateOnly'] and value['sourceUnchanged'] and value['unchanged']
    assert value['actualBinding']['selectedNames'] == [] and value['nonemptyBinding'] is None
    assert all(value['bad'].values()), value['bad']
    assert value['shape'][0] is True and value['shape'][1:3] == [False, False]


def test_complete_source_review_uses_actual_parent_projection_for_raw_reference_candidates():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import {execFileSync} from 'node:child_process';import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let calls=0,next;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{calls++;return {exitCode:0,stderr:'',text:JSON.stringify(next),usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:0},usageComplete:true}}}));
      const {createConsolidationRun,releaseConsolidationRun,applyConsolidationPlan,sha256Digest}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const {repairIncrementalMemoryPlan,expandCitedIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {createJevJudge}=await import('./packages/continual-learning/extensions/jev-learning.ts');
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'canonical-source-review-'))),repo=path.join(root,'project');fs.mkdirSync(repo);execFileSync('git',['init','-q',repo]);process.env.PI_CODING_AGENT_DIR=path.join(root,'agent');
      const entries=[{message:{role:'user',content:'The project callable has an observed old interface.\nThe project callable has an observed new interface.'}}];const run=await createConsolidationRun({cwd:repo,sessionManager:{getBranch:()=>entries,buildContextEntries:()=>entries}},repo,false);
      try{
        const frozen=JSON.parse(fs.readFileSync(run.paths.snapshotFile,'utf8')),m=run.manifest,identity={runId:m.runId,scopeKey:m.scopeKey,scopeDigest:m.scopeDigest,artifactHash:m.snapshotDigest,snapshotDigest:m.snapshotDigest};
        const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[{name:'interface.md',kind:'project',classification:'private',content:'---\nname: interface\ndescription: Observed old interface\ntype: project\n---\nThe project callable has an observed old interface.',evidence:[{ref:'e0.b0.l1'}]}]},before=JSON.stringify(original);
        const projected=await expandCitedIncrementalMemoryPlan(run,[],original),candidates=projected.newMemories;
        const judge=createJevJudge({enabled:true,apiKey:'controlled-fixture',independentMemoryApplication:true,requestConcurrency:1,fetch:async(_u,init)=>{
          const q=JSON.parse(String(init.body));return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(q.questions).map(([key,v])=>{const labels=Object.keys(v.criteria),choice=['grounded','compatible','unrelated'].find(x=>labels.includes(x))??labels[0];return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(labels.map(x=>[x,+(x===choice)]))}]}))}));
        }});const review=(await judge.validate('memory',frozen,candidates,[])).candidateReview;
        next={kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateRef:'newMemories:0',knowledge:{sourceCitations:[{ref:'e0.b0.l1'},{ref:'e0.b0.l2'}],units:[{text:'The project callable has an observed old interface. The project callable also has an observed new interface.',citationIndexes:[0,1]}]},description:'Observed old and new callable interfaces'}]};
        const input={identity,rejectedPlan:original,selectedNames:[],repairableNames:['interface.md'],repairableFields:{'interface.md':['body','description']},atomicBodyEvidence:true,errors:['Controlled coverage hold'],sourceReview:review,sourceExcerptRun:run,semanticContext:{frozenEvidence:frozen,existingMemories:[]}};
        const foreignOriginal=structuredClone(original);foreignOriginal.newMemories[0].evidence=[{ref:'e0.b0.l99'}];
        const foreign=await repairIncrementalMemoryPlan({...input,rejectedPlan:foreignOriginal});
        const snapshotBytes=fs.readFileSync(run.paths.snapshotFile);fs.writeFileSync(run.paths.snapshotFile,Buffer.concat([snapshotBytes,Buffer.from(' ')]));
        const raced=await repairIncrementalMemoryPlan(input),negativeCalls=calls,negativeNoWrite=!fs.existsSync(path.join(m.harnessDir,'interface.md'));fs.writeFileSync(run.paths.snapshotFile,snapshotBytes);
        const repaired=await repairIncrementalMemoryPlan(input);let stored=false;if(repaired.outcome==='repaired'){const plan=await expandCitedIncrementalMemoryPlan(run,[],repaired.plan);await applyConsolidationPlan(run,plan,()=>true);stored=fs.readFileSync(path.join(m.harnessDir,'interface.md'),'utf8').includes('new interface');}
        const count=calls,wrong=await repairIncrementalMemoryPlan({...input,sourceReview:{...review,candidatesDigest:sha256Digest('foreign')}});
        console.log(JSON.stringify({outcome:repaired.outcome,error:repaired.error,foreign:foreign.outcome,raced:raced.outcome,negativeCalls,negativeNoWrite,stored,calls,count,wrong:wrong.outcome,unchanged:before===JSON.stringify(original),rawEvidence:original.newMemories[0].evidence,projectedEvidence:candidates[0].evidence,digestsDiffer:sha256Digest(JSON.stringify(original.newMemories))!==review.candidatesDigest}));
      }finally{await releaseConsolidationRun(run);fs.rmSync(root,{recursive:true,force:true})}
    ''')
    assert value['digestsDiffer'] and value['rawEvidence'] == [{'ref': 'e0.b0.l1'}]
    assert value['projectedEvidence'][0]['index'] == 0
    assert value['outcome'] == 'repaired' and value['stored'], value
    assert value['wrong'] == 'failed' and value['calls'] == value['count']
    assert value['foreign'] == value['raced'] == 'failed' and value['negativeCalls'] == 0 and value['negativeNoWrite']
    assert value['unchanged']


# --- Merged from test_field_repair_citation_overflow.py ---
from support import isolated_run_bun


def test_actual_correction_preserves_all_quote_bytes_within_original_citation_bound() -> None:
    # Given the real four-citation proposal and eight-citation correction, When
    # the parent preserves an accepted description, Then a larger verified quote
    # may represent an original contained quote without losing either's bytes.
    result = isolated_run_bun(r'''
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-field-repair-citation-overflow.json').json();
      const {resolveMemoryPlanCitations}=await import('./packages/continual-learning/extensions/memory-citation-locations.ts');
      const {mergeSemanticMemoryRepairDelta}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {normalizeNewMemoryProposals,normalizeSnapshotEvidence}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const before=resolveMemoryPlanCitations(f.originalPlan,f.snapshot),delta=resolveMemoryPlanCitations(f.repairResponse,f.snapshot);
      const fields=Object.fromEntries(before.newMemories.map(x=>[x.name,['body']]));
      const merged=mergeSemanticMemoryRepairDelta(before,delta,before.newMemories.map(x=>x.name),fields,f.snapshot);
      const candidates=normalizeNewMemoryProposals(merged,f.snapshot,[]);
      const old=before.newMemories[0],replacement=delta.newMemories[0],next=merged.newMemories[0];
      const covered=x=>next.evidence.some(y=>x.index===y.index&&x.role===y.role&&y.quote.includes(x.quote));
      console.log(JSON.stringify({oldCount:old.evidence.length,repairedCount:replacement.evidence.length,mergedCount:next.evidence.length,
        oldCovered:old.evidence.every(covered),repairCovered:replacement.evidence.every(covered),
        quotesValid:normalizeSnapshotEvidence(next.evidence,f.snapshot).length===next.evidence.length,
        bodyCorrect:next.content.split('\n---\n')[1]===replacement.content.split('\n---\n')[1],
        headerPreserved:next.content.split('\n---\n')[0]===old.content.split('\n---\n')[0],candidates:candidates.length}));
    ''')
    assert result == {
        'oldCount': 4, 'repairedCount': 8, 'mergedCount': 8,
        'oldCovered': True, 'repairCovered': True, 'quotesValid': True,
        'bodyCorrect': True, 'headerPreserved': True, 'candidates': 2,
    }


def test_citation_enlargement_needs_verified_same_source_and_role() -> None:
    result = isolated_run_bun(r'''
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-field-repair-citation-overflow.json').json();
      const {resolveMemoryPlanCitations}=await import('./packages/continual-learning/extensions/memory-citation-locations.ts');
      const {mergeSemanticMemoryRepairDelta}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const a=resolveMemoryPlanCitations(f.originalPlan,f.snapshot),b=resolveMemoryPlanCitations(f.repairResponse,f.snapshot);
      const old=a.newMemories[0].evidence[2];
      const larger=b.newMemories[0].evidence.find(x=>x.index===old.index&&x.quote!==old.quote&&x.quote.includes(old.quote));
      const rows=[];
      for(const mode of ['valid','different-index','forged-role','fabricated','no-snapshot']){
        const snapshot=structuredClone(f.snapshot),citation=structuredClone(larger);
        if(mode==='different-index'){citation.index=snapshot.entries.length;snapshot.entries.push(structuredClone(snapshot.entries[old.index]));}
        if(mode==='forged-role')citation.role='user';
        if(mode==='fabricated')citation.quote='fabricated '+citation.quote;
        const before={...a,newMemories:[{...a.newMemories[0],evidence:[old]}]},delta={...b,newMemories:[{...b.newMemories[0],evidence:[citation]}]};
        const merged=mergeSemanticMemoryRepairDelta(before,delta,[a.newMemories[0].name],{[a.newMemories[0].name]:['body']},mode==='no-snapshot'?undefined:snapshot);
        rows.push({mode,count:merged.newMemories[0].evidence.length,oldUnchanged:JSON.stringify(merged.newMemories[0].evidence[0])===JSON.stringify(old)});
      }
      console.log(JSON.stringify(rows));
    ''')
    assert result[0] == {'mode': 'valid', 'count': 1, 'oldUnchanged': False}
    assert all(row['count'] == 2 and row['oldUnchanged'] for row in result[1:])


# --- Merged from test_memory_citation_domain.py ---
from support import isolated_run_bun


def test_citation_domain_excludes_memory_self_evidence_but_preserves_source_choices() -> None:
    result = isolated_run_bun(r'''
      import {memoryCitationDomain,locatedMemoryEvidence} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      import {Value} from 'typebox/value';
      const snapshot={entries:[{role:'user',content:'Please correct the old record.'},
        {role:'assistant',content:[{type:'toolCall',id:'old',name:'read',arguments:{path:'.memory/old.md'}}]},
        {role:'toolResult',toolCallId:'old',toolName:'read',content:[{type:'text',text:'Old unverified fact.'}]},
        {role:'assistant',content:[{type:'toolCall',id:'source',name:'read',arguments:{path:'src/runtime.ts'}}]},
        {role:'toolResult',toolCallId:'source',toolName:'read',content:[{type:'text',text:'Current source\nSecond line'}]}]};
      const before=JSON.stringify(snapshot);const domain=memoryCitationDomain(snapshot);
      const schema=learningOutputSchema('memory-delta',domain);
      const plan={kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'x',operations:[],newMemories:[{name:'project_fact.md',kind:'project',classification:'safe',description:'Current source',knowledge:{sourceCitations:[],units:[{text:'Current source',citationIndexes:[0]}]}}]};
      const check=e=>{plan.newMemories[0].knowledge.sourceCitations=[e];return Value.Check(schema,plan)};
      console.log(JSON.stringify({domain,good:check({ref:'e4.b0.l1'}),invented:check({ref:'e4.b0.l99'}),self:check({ref:'e2.b0.l1'}),legacySelf:check({index:2,quote:'Old unverified fact.'}),coordinateSelf:check({index:2,lines:{block:0,start:1,end:1}}),goodQuote:check({index:4,quote:'Current source'}),unchanged:before===JSON.stringify(snapshot),context:JSON.stringify(locatedMemoryEvidence(snapshot)).includes('Old unverified fact.')}));
    ''')
    assert result['domain'] == {'indices': [0, 4], 'refs': ['e0.b0.l1', 'e4.b0.l1', 'e4.b0.l2']}
    assert result['good'] and result['unchanged'] and result['context']
    assert not result['goodQuote']
    assert not any(result[k] for k in ['invented', 'self', 'legacySelf', 'coordinateSelf'])


def test_domain_is_complete_for_long_chunks_and_patch_and_never_silently_trims() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {memoryCitationDomain,locatedMemoryEvidence} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      import {learningPlannerArgs} from './packages/continual-learning/extensions/planner-prompts.ts';
      const snapshot={entries:[{role:'toolResult',content:[{type:'text',text:'x'.repeat(2500)}, {type:'image',data:'context'}],details:{patch:'-old\n+new'}}]};
      const domain=memoryCitationDomain(snapshot); const projected=locatedMemoryEvidence(snapshot);
      const collect=x=>x&&typeof x==='object'?Object.entries(x).flatMap(([key,value])=>key==='ref'&&typeof value==='string'?[value]:collect(value)):[];
      const file=path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json');
      const huge={entries:[{role:'user',content:'line\n'.repeat(20000)}]};
      fs.writeFileSync(file,JSON.stringify({plannerStructuredOutput:false}));const off=learningPlannerArgs('memory-delta',huge);
      fs.writeFileSync(file,JSON.stringify({plannerStructuredOutput:true}));const args=learningPlannerArgs('memory-delta',snapshot);
      const hugeArgs=learningPlannerArgs('memory-delta',huge);const bounded=hugeArgs[hugeArgs.indexOf('--learning-citation-domain')+1]==='complete-catalog-overflow';
      console.log(JSON.stringify({domain,projected:collect(projected),encoded:JSON.parse(args[args.indexOf('--learning-citation-domain')+1]),off:off.includes('--learning-citation-domain'),bounded,sourceUnchanged:snapshot.entries[0].content[0].text.length===2500}));
    ''', temp_dirs=('PI_CODING_AGENT_DIR',))
    assert result['domain']['refs'] == result['projected']
    assert result['encoded'] == result['domain'] and result['bounded'] and result['sourceUnchanged']
    assert not result['off']


def test_bad_domains_fail_before_service_and_empty_domain_allows_only_abstention() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import extension from './packages/continual-learning/extensions/planner-json-output.ts';
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      import {Value} from 'typebox/value';
      fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json'),JSON.stringify({plannerStructuredOutput:true,plannerJsonOutput:true}));
      let handler,domain;extension({registerFlag:()=>{},getFlag:name=>name==='learning-output-schema'?'memory-delta':name==='learning-citation-domain'?domain:undefined,getActiveTools:()=>[],on:(name,fn)=>handler=fn});
      const payload={messages:[]};const ctx={model:{id:'qwen3.8-flash',api:'openai-completions'}};
      const errors=[];for(const v of ['damaged','complete-catalog-overflow','{"indices":[0],"refs":[]}','{"indices":[0],"refs":["e2.b0.l1"]}','{"indices":[0,0],"refs":["e0.b0.l1"]}','{"indices":[],"refs":"bad"}']){domain=v;try{handler({payload},ctx);errors.push(false)}catch{errors.push(true)}}
      domain='complete-catalog-overflow';const unsupported=handler({payload},{model:{id:'unknown',api:'openai-completions'}});
      const caller=handler({payload:{...payload,response_format:{type:'caller'}}},ctx);
      domain='{"indices":[],"refs":[]}';const request=handler({payload},ctx);
      const schema=request.response_format.json_schema.schema;
      const empty={kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'x',operations:[],newMemories:[]};
      const proposal={name:'p.md',kind:'project',classification:'safe',description:'Unverified candidate',knowledge:{sourceCitations:[{ref:'e0.b0.l1'}],units:[{text:'Unsupported',citationIndexes:[0]}]}};
      console.log(JSON.stringify({errors,unsupported,caller,empty:Value.Check(schema,empty),invented:Value.Check(schema,{...empty,newMemories:[proposal]}),nonemptyDomainAccepts:Value.Check(learningOutputSchema('memory-delta',{indices:[0],refs:['e0.b0.l1']}),{...empty,newMemories:[proposal]})}));
    ''', temp_dirs=('PI_CODING_AGENT_DIR',))
    assert all(result['errors'])
    assert result.get('unsupported') is None and result.get('caller') is None
    assert result['empty'] and not result['invented'] and result['nonemptyDomainAccepts']


def test_complete_domain_requires_catalog_references_instead_of_free_coordinates_or_quotes() -> None:
    value = isolated_run_bun(r'''
      import {Value} from 'typebox/value';
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      const domain={indices:[0],refs:['e0.b0.l1','e0.b0.l2']};
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'x'};
      const base={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[{name:'p.md',kind:'project',classification:'safe',description:'Unverified candidate',knowledge:{sourceCitations:[],units:[{text:'Unverified candidate',citationIndexes:[0]}]}}]};
      const values=[{ref:'e0.b0.l1'},{ref:'e0.b0.l1',endRef:'e0.b0.l2'},
        {index:0,quote:'Verbatim but freely generated'},
        {index:0,lines:{block:0,start:999,end:999}},
        {index:0,lines:{block:0,start:1,end:2}},
        {ref:'e0.b0.l999'},{ref:'e0.b0.l1',quote:'Mixed identity'}];
      const check=(schema,e)=>Value.Check(schema,{...base,newMemories:[{...base.newMemories[0],knowledge:{...base.newMemories[0].knowledge,sourceCitations:[e]}}]});
      console.log(JSON.stringify({strict:values.map(e=>check(learningOutputSchema('memory-delta',domain),e)),legacy:check(learningOutputSchema('memory-delta'),values[2]),amendment:values.map(e=>Value.Check(learningOutputSchema('memory-amendment',domain),{kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:'id',content:'---\nname: candidate\ndescription: Unverified candidate.\ntype: project\n---\nCandidate',evidence:[e]}]}))}));
    ''')
    assert value['strict'] == [True, True, False, False, False, False, False]
    assert value['amendment'] == value['strict']
    assert value['legacy']


def test_whitespace_is_lossless_context_but_not_a_selectable_source_fragment() -> None:
    value = isolated_run_bun(r'''
      import {memoryCitationDomain,locatedMemoryEvidence,resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      import {Value} from 'typebox/value';
      const long='Start '+ ' '.repeat(2100)+'finish';
      const snapshot={entries:[{role:'toolResult',content:'First condition.\n\n \t\nLast exception.'},{role:'user',content:' \n\t'},{role:'toolResult',content:long}]};
      const before=JSON.stringify(snapshot),domain=memoryCitationDomain(snapshot),shown=locatedMemoryEvidence(snapshot);
      const lines=shown.entries[0].entry.content.citationLines.lines,chunks=shown.entries[2].entry.content.citationLines.lines[0].chunks;
      const full=resolveMemoryPlanCitations({operations:[{evidence:[{ref:'e0.b0.l1',endRef:'e0.b0.l4'}]}]},snapshot);
      const legacy=resolveMemoryPlanCitations({operations:[{evidence:[{ref:'e0.b0.l2',endRef:'e0.b0.l4'}]}]},snapshot);
      let emptyRejected=false;try{resolveMemoryPlanCitations({operations:[{evidence:[{ref:'e0.b0.l2'}]}]},snapshot)}catch{emptyRejected=true}
      const base={kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'x',operations:[],newMemories:[{name:'fact.md',kind:'project',classification:'safe',description:'Unverified candidate',knowledge:{sourceCitations:[{ref:'e0.b0.l2'}],units:[{text:'Claim',citationIndexes:[0]}]}}]};
      console.log(JSON.stringify({domain,blankLabels:lines.slice(1,3).some(x=>x.ref!==undefined),blankChunkLabels:chunks.filter(c=>!c.text.trim()).some(c=>c.ref!==undefined),reconstructed:lines.map(l=>l.text).join('\n')===snapshot.entries[0].content&&chunks.map(c=>c.text).join('')===long,unchanged:before===JSON.stringify(snapshot),full:full.operations[0].evidence[0].quote,legacy:legacy.operations[0].evidence[0].quote,emptyRejected,schemaAcceptsSource:Value.Check(learningOutputSchema('memory-delta',domain),{...base,newMemories:[{...base.newMemories[0],knowledge:{...base.newMemories[0].knowledge,sourceCitations:[{ref:'e0.b0.l1'}]}}]}),schemaRejectsBlank:!Value.Check(learningOutputSchema('memory-delta',domain),base)}));
    ''')
    assert value['domain']['indices'] == [0, 2]
    assert value['domain']['refs'][:2] == ['e0.b0.l1', 'e0.b0.l4']
    assert not value['blankLabels'] and not value['blankChunkLabels']
    assert value['reconstructed'] and value['unchanged'] and value['emptyRejected']
    assert value['schemaRejectsBlank'] and value['schemaAcceptsSource']
    assert value['full'] == 'First condition.\n\n \t\nLast exception.'
    assert value['legacy'] == '\n \t\nLast exception.'


# --- Merged from test_memory_correction_citations.py ---
from support import run_bun


def test_cited_rewrite_survives_expansion_and_parent_citation_validation():
    value = run_bun('''
      import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
      import {expandIncrementalMemoryPlan} from './packages/continual-learning/extensions/incremental-memory-plan.ts';
      import {candidateCitationProblems,expandCitedIncrementalMemoryPlan} from './packages/continual-learning/extensions/inject-memory.ts';
      const root=await fs.mkdtemp(path.join(os.tmpdir(),'cl-cited-update-'));
      await fs.writeFile(path.join(root,'MEMORY.md'),'# Memory\\n- [fact.md](fact.md)\\n');
      await fs.writeFile(path.join(root,'fact.md'),'The old value.');
      const publicDir=path.join(root,'public');await fs.mkdir(publicDir);
      await fs.writeFile(path.join(publicDir,'fact.md'),'The old value.');
      const snapshot={schemaVersion:1,runId:'run_update',scopeKey:'k',entries:[{message:{role:'user',content:'Correction: the current value is new.'}}]};
      const text=JSON.stringify(snapshot);const digest=new Bun.CryptoHasher('sha256').update(text).digest('hex');
      const snapshotFile=path.join(root,'snapshot.json');await fs.writeFile(snapshotFile,text);
      const manifest={runId:'run_update',scopeKey:'k',scopeDigest:'d',snapshotDigest:digest,harnessDir:root,publicDir,cwd:root};
      const evidence=[{index:0,quote:'Correction: the current value is new.',role:'user'}];
      const delta={kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:'run_update',scopeKey:'k',scopeDigest:'d',artifactHash:manifest.snapshotDigest,snapshotDigest:manifest.snapshotDigest,
        operations:[{name:'fact.md',kind:'rewrite',classification:'safe',content:'The current value is new.',evidence}],newMemories:[]};
      try {
        const run={manifest,paths:{snapshotFile}};
        const plan=await expandCitedIncrementalMemoryPlan(run,['fact.md'],delta);
        const uncited=structuredClone(delta);delete uncited.operations[0].evidence;
        let rejected=false;try{await expandCitedIncrementalMemoryPlan(run,['fact.md'],uncited)}catch(e){rejected=e.message.includes('no citation')}
        if(!rejected)throw Error('Uncited corrected plan accepted');
        console.log(JSON.stringify({evidence:plan.operations[0].evidence,problems:candidateCitationProblems(snapshot,plan.operations)}));
      } finally {await fs.rm(root,{recursive:true,force:true})}
    ''')
    assert value['evidence'] == [{'index':0,'quote':'Correction: the current value is new.','role':'user'}]
    assert value['problems'] == []


def test_assistant_claim_cannot_authorize_memory_correction():
    value = run_bun('''
      import {candidateCitationProblems} from './packages/continual-learning/extensions/inject-memory.ts';
      console.log(JSON.stringify(candidateCitationProblems({entries:[{message:{role:'assistant',content:'A made-up fact.'}}]},
        [{evidence:[{index:0,quote:'A made-up fact.'}]}])));
    ''')
    assert value and 'user or tool' in value[0]


# --- Merged from test_memory_correction_relations.py ---
import hashlib

from support import isolated_run_bun


def test_real_failed_correction_never_compares_a_proposal_with_itself() -> None:
    value = isolated_run_bun(r'''
      const {createJevJudge}=await import(process.env.CL_RELATION_MODULE??'./packages/continual-learning/extensions/jev-learning.ts');
      import {normalizeNewMemoryProposals,containsSensitiveMemoryMaterial} from './packages/continual-learning/extensions/consolidation-run.ts';
      const {snapshot,plan,existing}=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-correction-relations.json').json();
      const candidates=[...plan.operations,...normalizeNewMemoryProposals(plan,snapshot,plan.selected)];
      const requests=[];
      await createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const request=JSON.parse(init.body);requests.push(request);
        const answers=Object.fromEntries(Object.entries(request.questions).map(([key,q])=>{
          const choice=key.startsWith('coherence_')?'compatible':key.startsWith('counter_')?'compatible':key.startsWith('relation_')?'unrelated':'grounded';
          return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}];
        }));return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:0,output_tokens:0}}));
      }}).validate('memory',snapshot,candidates,existing);
      const relation=requests.filter(r=>Object.keys(r.questions).some(k=>k.startsWith('relation_')));
      const rows=relation.map(r=>{const state=(typeof r.state === "string" ? JSON.parse(r.state) : r.state);return {keys:Object.keys(r.questions),hasProposals:Object.hasOwn(state,'proposedMemoryOperations'),comparatorsExact:JSON.stringify(state.existingMemories)===JSON.stringify(existing)}});
      const counter=requests.flatMap(r=>(typeof r.state === "string" ? JSON.parse(r.state) : r.state).reviewEvidence?.entries.map(e=>e.index)??[]);
      console.log(JSON.stringify({rows,counter:[...new Set(counter)].sort((a,b)=>a-b),entries:snapshot.entries.length,existing,sensitive:containsSensitiveMemoryMaterial(JSON.stringify({snapshot,plan,existing}))}));
    ''')
    assert value['rows']
    assert not value['sensitive']
    for row in value['rows']:
        assert all(key.startswith('relation_') for key in row['keys'])
        assert 'relation_0' not in row['keys'] and 'relation_description_0' not in row['keys']
        assert not row['hasProposals']
        assert row['comparatorsExact']
    # Preserve raw indexes while excluding only this frozen fixture's own injected reference.
    assert value['entries'] == 42
    assert value['counter'] == [i for i in range(42) if i != 1]


def test_rewrite_excludes_only_its_predecessor_and_preserves_mutation_checks() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const body=(name,text)=>`---\nname: ${name}\ndescription: ${text}\ntype: project\n---\n${text}`;
      const existing=[{name:'contract.md',classification:'safe',content:body('contract','The wrapper has clearQueue.')},{name:'other.md',classification:'safe',content:body('other','Use FIFO.') }];
      const snapshot={contextEnabled:true,entries:[{role:'user',content:'Correct contract.md: the wrapper now also exposes onIdle; keep FIFO.'},{role:'toolResult',content:'onIdle and clearQueue are declared; FIFO remains.'}]};
      const candidate={name:'contract.md',kind:'rewrite',classification:'safe',content:body('contract','The wrapper declares onIdle and clearQueue.'),evidence:[{index:0,quote:snapshot.entries[0].content},{index:1,quote:snapshot.entries[1].content}]};
      const requests=[];let mode='compatible';
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const req=JSON.parse(init.body);requests.push(req);
        const answers=Object.fromEntries(Object.entries(req.questions).map(([key,q])=>{
          const choice=key.startsWith('coherence_')?'compatible':key.startsWith('counter_')?mode:key.startsWith('relation_')?'unrelated':'grounded';
          return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}];
        }));return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:0,output_tokens:0}}));
      }});
      const allowed=await judge.validate('memory',snapshot,[candidate],existing);
      const original=requests.splice(0);mode='contradicts';const refused=await judge.validate('memory',snapshot,[candidate],existing);
      const relations=original.filter(r=>r.questions.relation_0).map(r=>({state:(typeof r.state === "string" ? JSON.parse(r.state) : r.state),names:r.questions.relation_0.instructions.comparisonNames}));
      const support=original.find(r=>r.questions.supported_0);const counters=original.filter(r=>Object.keys(r.questions).some(k=>k.startsWith('counter_')));
      console.log(JSON.stringify({allowed:allowed.decision,refused:refused.decision,relations,original:existing,candidate,
        support:(typeof support.state === "string" ? JSON.parse(support.state) : support.state),counterStates:counters.map(r=>(typeof r.state === "string" ? JSON.parse(r.state) : r.state)),review:allowed.candidateReview}));
    ''')
    assert value['allowed'] == 'allow' and value['refused'] == 'propose'
    assert value['relations'][0]['names'] == ['other.md']
    assert value['relations'][0]['state']['existingMemories'] == [value['original'][1]]
    # Factual source support sees the full new record, not its old reference.
    # Preservation and permission still review the exact predecessor below.
    assert 'existingMemories' not in value['support']
    assert 'mutationComparison' not in value['support']
    assert 'historicalMemoryOrigins' not in value['support']
    expected = {key: item for key, item in value['candidate'].items() if key != 'evidence'}
    expected.update(candidateIndex=0, originalCitationSources=[
        {'snapshotIndex': citation['index'], 'role': role,
         'quoteSha256': hashlib.sha256(citation['quote'].encode()).hexdigest()}
        for citation, role in zip(value['candidate']['evidence'], ['user', 'toolResult'], strict=True)
    ])
    assert value['support']['proposedMemoryOperations'] == [expected]
    assert [{key: item[key] for key in ('index', 'quote', 'role')}
            for item in value['support']['originalCitationsByCandidate']['0']] == [
        {**citation, 'role': role}
        for citation, role in zip(value['candidate']['evidence'], ['user', 'toolResult'], strict=True)
    ]
    for state in value['counterStates']:
        assert state['existingMemories'] == [value['original'][0]]
        assert state['proposedMemoryOperations'] == [expected]
    assert value['review']['complete']


def test_deletion_has_preservation_checks_without_a_novelty_question() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:'Delete obsolete.md; its claim is wrong.'}]};
      const old={name:'obsolete.md',classification:'safe',content:'---\nname: obsolete\ndescription: Wrong claim\ntype: project\n---\nWrong claim.'};
      const candidate={name:'obsolete.md',kind:'delete',classification:'safe',evidence:[{index:0,quote:snapshot.entries[0].content}]};
      const keys=[];let preservation=false;
      const result=await createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const req=JSON.parse(init.body);keys.push(...Object.keys(req.questions));const state=(typeof req.state === "string" ? JSON.parse(req.state) : req.state);
        if(req.questions.counter_0_0)preservation=state.existingMemories[0].content===old.content && state.proposedMemoryOperations[0].kind==='delete';
        const answers=Object.fromEntries(Object.entries(req.questions).map(([key,q])=>{const choice=key.startsWith('coherence_')?'compatible':key.startsWith('counter_')?'contradicts':'grounded';return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}];}));
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:0,output_tokens:0}}));
      }}).validate('memory',snapshot,[candidate],[old]);
      console.log(JSON.stringify({keys,preservation,decision:result.decision}));
    ''')
    assert not any(key.startswith('relation_') for key in value['keys'])
    assert 'supported_0' in value['keys'] and 'counter_0_0' in value['keys']
    assert value['preservation'] and value['decision'] == 'propose'


# --- Merged from test_memory_filename_repair.py ---
from support import isolated_run_bun


def test_real_missing_suffix_repair_preserves_identity_and_privacy() -> None:
    # Given real new proposal names without .md, When structural repair adds
    # exactly the missing suffix, Then retain intent and reject scope changes.
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let next;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>({text:JSON.stringify(next),exitCode:0,stderr:'',cancelled:false})}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-missing-memory-suffix.json').json();
      const input={identity:f.original,rejectedPlan:f.original,selectedNames:f.selected,structuralCorrection:true,errors:['Consolidation plan contains an invalid memory filename']};
      next=f.corrected;const good=await repairIncrementalMemoryPlan(input);
      const errors=[];
      for(const kind of ['rename','privacy','drop','collision','selected','existing_target','semantic']) {
        next=structuredClone(f.corrected);const original=structuredClone(f.original);
        if(kind==='rename')next.newMemories[0].name='unrelated.md';
        if(kind==='privacy')next.newMemories[0].classification=next.newMemories[0].classification==='safe'?'private':'safe';
        if(kind==='drop')next.newMemories=[];
        if(kind==='existing_target')original.operations[0].name=original.operations[0].name.slice(0,-3);
        if(kind==='collision')original.newMemories.push({...original.newMemories[0],name:next.newMemories[0].name});
        if(kind==='selected'){original.newMemories[0].name='limit_function_type_contract';next.newMemories[0].name='limit_function_type_contract.md';}
        errors.push({kind,result:await repairIncrementalMemoryPlan({...input,rejectedPlan:original,structuralCorrection:kind!=='semantic'})});
      }
      console.log(JSON.stringify({good,errors,expected:f.corrected.newMemories.map(v=>v.name)}));
    ''')
    assert result['good']['outcome'] == 'repaired'
    assert [v['name'] for v in result['good']['plan']['newMemories']] == result['expected']
    assert all(row['result']['outcome'] == 'failed' for row in result['errors'])


def test_repeated_extension_is_a_parent_bound_new_proposal_spelling_correction() -> None:
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let next,prompt='';
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{prompt=input.prompt;return {text:JSON.stringify(next),exitCode:0,stderr:'',cancelled:false};}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-repeated-memory-extension.json').json();
      const input={identity:f.original,rejectedPlan:f.original,selectedNames:f.selected,structuralCorrection:true,errors:['Consolidation plan contains an invalid memory filename']};
      next=f.corrected;const good=await repairIncrementalMemoryPlan(input);const parentMapping=prompt.includes('newProposalNameCorrections')&&prompt.includes('pnpm_test_node20_skip.md_keep_note.md')&&prompt.includes('pnpm_test_node20_skip_keep_note.md');
      const bad=[];
      for(const kind of ['rename','privacy','drop','duplicate','selected','path','other_extension','semantic','existing_target']) {
        next=structuredClone(f.corrected);const original=structuredClone(f.original);let selected=[...f.selected];
        if(kind==='rename')next.newMemories[1].name='unrelated.md';
        if(kind==='privacy')next.newMemories[1].classification='private';
        if(kind==='drop')next.newMemories.pop();
        if(kind==='duplicate')original.newMemories.push({...original.newMemories[1],name:next.newMemories[1].name});
        if(kind==='selected')selected.push(next.newMemories[1].name);
        if(kind==='path')original.newMemories[1].name='../pnpm_test_node20_skip.md_keep_note.md';
        if(kind==='other_extension')original.newMemories[1].name='pnpm_test_node20_skip.txt_keep_note.md';
        if(kind==='existing_target')original.operations[0].name='package_test_scripts.md_note.md';
        bad.push({kind,result:await repairIncrementalMemoryPlan({...input,rejectedPlan:original,selectedNames:selected,structuralCorrection:kind!=='semantic'})});
      }
      console.log(JSON.stringify({good,parentMapping,bad}));
    ''')
    assert result['good']['outcome'] == 'repaired'
    assert result['parentMapping']
    assert all(row['result']['outcome'] == 'failed' for row in result['bad'])


# --- Merged from test_memory_incomplete_replan.py ---
from pathlib import Path

from support import run_bun_script


def test_explicit_maintenance_independently_replans_one_incomplete_response() -> None:
    fixture = Path(__file__).with_name('learning-policy-harness.ts')
    recovered = run_bun_script(fixture, 'remember-existing-maintenance', env={'CL_MEMORY_PREFIX_FAILURE': 'first'})
    assert recovered['planners'] == ['memory', 'memory']
    assert recovered['maintenanceClaimChecks'] == 3
    assert recovered['selectors'] == 1
    assert all(row['completeInline'] and row['noTools'] for row in recovered['initialMemoryInputs'])
    assert len({row['inlineDossierSha256'] for row in recovered['initialMemoryInputs']}) == 1
    attempts = [row for row in recovered['registryReceipt']['attempts'] if row['phase'] == 'memory' and row.get('usage')]
    assert [(row['attempt'], row['outcome']) for row in attempts] == [(0, 'failed'), (1, 'applied')]
    assert sum(row['usage']['cost'] for row in attempts) == .02
    assert attempts[0]['diagnostic'] == 'Incomplete Memory planner response; independent maintenance replan requested.'
    assert recovered['registryReceipt']['operations'] == 1
    assert not recovered['lock']
    failed = run_bun_script(fixture, 'remember-existing-maintenance', env={'CL_MEMORY_PREFIX_FAILURE': 'always'})
    assert failed['planners'] == ['memory', 'memory']
    assert failed['registryReceipt']['operations'] == 0
    ordinary = run_bun_script(fixture, 'remember-shared', env={'CL_MEMORY_PREFIX_FAILURE': 'first'})
    assert ordinary['planners'] == ['memory']
    assert ordinary['registryReceipt']['operations'] == 0


# --- Merged from test_memory_patch_evidence.py ---
from support import isolated_run_bun


def test_real_successful_edit_patch_can_ground_changed_knowledge() -> None:
    result = isolated_run_bun(r'''
      import {locatedMemoryEvidence,resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      import {normalizeSnapshotEvidence,normalizeNewMemoryProposals} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {candidateCitationProblems} from './packages/continual-learning/extensions/inject-memory.ts';
      const {snapshot}=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-correction-relations.json').json();
      const before=JSON.stringify(snapshot),patch=snapshot.entries[33].message.details.patch;
      const rows=patch.split('\n'),line=rows.findIndex(s=>s.startsWith('+')&&s.includes("Pick<LimitFunction, 'clearQueue' | 'onIdle'>"))+1;
      const raw={operations:[],newMemories:[{name:'changed-contract.md',kind:'project',classification:'safe',content:'---\nname: changed-contract\ndescription: Declared wrapper members include onIdle.\ntype: project\n---\nThe edited declaration includes onIdle.',evidence:[{index:33,role:'toolResult',lines:{source:'patch',block:0,start:line,end:line}}]}]};
      let resolved,error;try{resolved=resolveMemoryPlanCitations(raw,snapshot);}catch(e){error=e.message;}
      const shown=locatedMemoryEvidence(snapshot).entries[33].entry.message;
      console.log(JSON.stringify({error,line,quote:rows[line-1],resolved,patch,
        numbered:shown.details.patch.citationLines,unchanged:before===JSON.stringify(snapshot),
        problems:resolved?candidateCitationProblems(snapshot,resolved.newMemories):null,
        normalized:resolved?normalizeNewMemoryProposals(resolved,snapshot):null}));
    ''')
    assert result.get('error') is None
    assert result['resolved']['newMemories'][0]['evidence'] == [
        {'index': 33, 'quote': result['quote'], 'role': 'toolResult'}]
    assert result['quote'].startswith('+')
    assert result['numbered']['source'] == 'patch'
    assert '\n'.join(row['text'] for row in result['numbered']['lines']) == result['patch']
    assert result['unchanged'] and not result['problems']
    assert result['normalized'][0]['evidence'][0]['quote'] == result['quote']


def test_patch_locations_do_not_promote_failed_edits_assistant_arguments_or_other_details() -> None:
    value = isolated_run_bun(r'''
      import {resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      import {normalizeSnapshotEvidence} from './packages/continual-learning/extensions/consolidation-run.ts';
      const good={role:'toolResult',toolName:'edit',isError:false,content:'Edit completed',details:{patch:'-old\r\n+new\r\n'}};
      const snapshot={entries:[good,{...good,role:'assistant'},{...good,isError:true},{...good,isError:undefined},{...good,toolName:'read'},{...good,details:{proposedPatch:good.details.patch}},{...good,details:{patch:'+API_KEY=sk-'+'a'.repeat(48)}},{...good,details:{patch:'x'.repeat(2001)}}]};
      const resolve=(index,lines={source:'patch',block:0,start:2,end:2},role='toolResult')=>{try{return resolveMemoryPlanCitations({operations:[{evidence:[{index,lines,role}]}]},snapshot).operations[0].evidence[0];}catch{return false;}};
      const bad=[...Array.from({length:5},(_,i)=>resolve(i+1)),resolve(6,{source:'patch',block:0,start:1,end:1}),resolve(7,{source:'patch',block:0,start:1,end:1}),resolve(0,{source:'patch',block:1,start:1,end:1}),resolve(0,{source:'arguments',block:0,start:1,end:1}),resolve(0,undefined,'user')];
      let stripped=false;try{normalizeSnapshotEvidence([{index:0,quote:'old\r\nnew'}],snapshot);stripped=true;}catch{}
      console.log(JSON.stringify({good:resolve(0),bad,stripped}));
    ''')
    assert value['good'] == {'index': 0, 'quote': '+new\r', 'role': 'toolResult'}
    assert not any(value['bad']) and not value['stripped']


def test_patch_citations_follow_initial_and_repaired_parent_mutation_paths() -> None:
    from pathlib import Path
    from support import run_bun_script
    fixture = Path(__file__).with_name('learning-policy-harness.ts')
    for reason in ('patch-supported', 'patch-repair'):
        value = run_bun_script(fixture, 'remember-shared', env={'CL_JEV_FIXTURE': reason})
        assert value['registryReceipt']['operations'] == 1
        assert value['memoryMirrored'] and not value['lock']
        assert value['semanticRepairs'] == (1 if reason == 'patch-repair' else 0)
        assert any(attempt['phase'] == 'memory' and attempt['outcome'] == 'applied'
                   for attempt in value['registryReceipt']['attempts'])


# --- Merged from test_memory_proof_attribution.py ---
import json
from pathlib import Path

from support import isolated_run_bun


def test_real_rewrite_preserves_contract_without_inheriting_unobserved_proof() -> None:
    # Given the complete v20 failure, the test exists in source but was never
    # observed in this slice. Old Memory is not evidence of that test assertion.
    fixture = json.loads((Path(__file__).parent / 'fixtures/real-memory-proof-attribution-gap.json').read_text())
    entries = fixture['dossier']['taskSlice']['entries']
    assert len(entries) == 63
    results = [entry['message'] for entry in entries if entry.get('message', {}).get('role') == 'toolResult']
    assert not any('expectError(limitFunction' in json.dumps(result) for result in results)
    assert 'expectError(limitFunction' in fixture['repaired']['operations'][0]['content']
    assert 'PromiseLike<ReturnType>' in json.dumps(results)
    assert 'pLimit(1,{rejectOnClear:true})' in json.dumps(entries)
    assert 'queued.isFulfilled===undefined' in json.dumps(entries)

    # When either initial planning or the existing bounded repair runs, Then
    # both retain original-source attribution and predecessor preservation.
    # Initial generation uses its refs-only template; repair retains the
    # detailed legacy guidance. This tests delivery, not learning benefit.
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let captured;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        captured=input.prompt;return {text:'{}',exitCode:0,stderr:'',cancelled:false};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {buildIncrementalMemoryConsolidatorPrompt}=await import('./packages/continual-learning/extensions/planner-prompts.ts');
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-proof-attribution-gap.json').json();
      await repairIncrementalMemoryPlan({identity:f.original,rejectedPlan:f.original,
        errors:['support uncertainty'],selectedNames:f.dossier.selectedMemories.map(x=>x.name),
        repairableNames:f.original.operations.map(x=>x.name),
        repairableFields:Object.fromEntries(f.original.operations.map(x=>[x.name,['body','description']])),
        semanticContext:{existingMemories:f.dossier.selectedMemories,frozenEvidence:{entries:f.dossier.taskSlice.entries}}});
      const initial=buildIncrementalMemoryConsolidatorPrompt({runId:'run',scopeKey:'scope',scopeDigest:'digest',artifactHash:'artifact',snapshotDigest:'snapshot',dossierPath:'/tmp/dossier.json'});
      const payload=JSON.parse(captured.split('\n').at(-1));
      console.log(JSON.stringify({initial,repair:captured.slice(0,captured.lastIndexOf('\n')),
        completeEvidence:payload.semanticContext.frozenEvidence.entries.length===63,
        predecessorPreserved:JSON.stringify(payload.semanticContext.existingMemories)===JSON.stringify(f.dossier.selectedMemories)}));
    ''')
    assert result['completeEvidence'] and result['predecessorPreserved']
    initial, repair = result['initial'], result['repair']
    for prompt in (initial, repair):
        assert 'Select original spans for each factual clause and its premises' in prompt
        assert 'Preserve still-valid predecessor knowledge and explicit restrictions' in prompt
    assert 'only eligible\nuser/toolResult text can be cited' in initial
    assert 'Current explicit corrections and verified changed project behavior supersede' in initial
    assert 'A claimed fix requires its actual successful verification' in initial
    assert 'Read a diagnostic\'s executed operations before interpreting its printed labels' in initial
    assert 'Preserve supported knowledge, not unsupported proof attribution' not in initial
    assert 'Preserve supported knowledge, not unsupported proof attribution' in repair
    assert 'A test assertion copied from existing Memory is not an observed test' in repair
    assert 'pair the actual invocation with its result' in repair
    assert 'deadlock, unawaited Promise, nonexistent property' in repair


# --- Merged from test_memory_reference_provenance.py ---
from support import isolated_run_bun


def test_parent_rejects_memory_readback_as_independent_support_for_all_citation_forms() -> None:
    value = isolated_run_bun(r'''
      import {normalizeSnapshotEvidence} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {locatedMemoryEvidence,resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const body='The device still runs the old deployment.';
      const calls=[{name:'codemode',arguments:{code:String.raw`const root="C:\\isolated-agent\\memory\\--project--"; await tools.read({path:root+"\\deployment.md"});`}},{name:'bash',arguments:{command:'cat .memory/deployment.md'}},{name:'codemode',arguments:{code:'await tools.read({path:".memory/deployment.md"})'}},...['.memory/deployment.md','memory/--project--/deployment.md',String.raw`C:\Users\test\.pi\agent\memory\--project--\deployment.md`,String.raw`C:\isolated-agent\memory\--project--\deployment.md`].map(path=>({name:'read',arguments:{path}})),{name:'read',arguments:{path:'/project/.memory/deployment.md'}},
        {name:'read',arguments:{path:'/home/.pi/agent/memory/--project--/deployment.md'}},
        {name:'codemode',arguments:{code:'const pub="/project/.memory"; const har="/home/.pi/agent/memory/--project--"; await tools.read({path:pub+"/deployment.md"}); await tools.read({path:"/project/runtime/shell/main.js"});'}},
        {name:'bash',arguments:{command:'cat /project/.memory/deployment.md; cat /project/runtime/shell/main.js'}}];
      const rows=calls.map((call,index)=>{
        const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'read-memory',...call}]},{role:'toolResult',toolCallId:'read-memory',toolName:call.name,isError:false,content:body}]};
        const before=JSON.stringify(snapshot);const shown=locatedMemoryEvidence(snapshot);
        const rejected=[];
        for(const citation of [{index:1,quote:body},{index:1,lines:{block:0,start:1,end:1}},{ref:'e1.b0.l1'}]){
          try{const plan=resolveMemoryPlanCitations({operations:[{evidence:[citation]}]},snapshot);normalizeSnapshotEvidence(plan.operations[0].evidence,snapshot);rejected.push(false);}catch{rejected.push(true);}
        }
        return {rejected,eligible:shown.entries[1].citationEligible,context:shown.entries[1].entry.content,unchanged:JSON.stringify(snapshot)===before};
      });console.log(JSON.stringify(rows));
    ''')
    assert all(all(row['rejected']) for row in value)
    assert all(row['eligible'] is False for row in value)
    assert all(row['context'] == 'The device still runs the old deployment.' and row['unchanged'] for row in value)


def test_project_source_user_correction_and_observed_read_failure_keep_their_evidence() -> None:
    value = isolated_run_bun(r'''
      import {normalizeSnapshotEvidence} from './packages/continual-learning/extensions/consolidation-run.ts';
      const body='The current source uses ODK_WORKSPACE.';
      const snapshots=[{entries:[{role:'assistant',content:[{type:'toolCall',id:'source',name:'write',arguments:{path:'/project/README.md',content:'Read .memory/deployment.md'}}]},{role:'toolResult',toolName:'write',toolCallId:'source',isError:false,content:body}]},{entries:[{role:'user',content:body}]},
        {entries:[{role:'assistant',content:[{type:'toolCall',id:'source',name:'read',arguments:{path:'/project/src/memory-reader.ts'}}]},{role:'toolResult',toolName:'read',toolCallId:'source',isError:false,content:body}]},
        {entries:[{role:'assistant',content:[{type:'toolCall',id:'source',name:'read',arguments:{path:'/project/README.md'}}]},{role:'toolResult',toolName:'read',toolCallId:'source',isError:false,content:'The project indexes .memory files.'}]},
        {entries:[{role:'assistant',content:[{type:'toolCall',id:'source',name:'read',arguments:{path:'/project/.memory/missing.md'}}]},{role:'toolResult',toolName:'read',toolCallId:'source',isError:true,content:'ENOENT: observation failed'}]}];
      const accepted=snapshots.map(snapshot=>{const index=snapshot.entries.length-1;try{return normalizeSnapshotEvidence([{index,quote:snapshot.entries[index].content}],snapshot).length===1;}catch{return false;}});
      console.log(JSON.stringify({accepted}));
    ''')
    assert all(value['accepted'])


def test_python_memory_provenance_matches_paths_and_actual_call_identity() -> None:
    import runpy
    from pathlib import Path

    namespace = runpy.run_path(str(Path(__file__).parents[1] / 'scripts' / 'validate-consolidate.py'))
    classify = namespace['memory_reference_results']
    paths = ['.memory/deployment.md', 'memory/--project--/deployment.md',
             r'C:\Users\test\.pi\agent\memory\--project--\deployment.md',
             r'C:\isolated-agent\memory\--project--\deployment.md',
             'file:///project/.memory/deployment.md', r'const root="C:\\isolated-agent\\memory\\--project--";']
    for path in paths:
        call = {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 'm', 'name': 'read', 'arguments': {'path': path}}]}
        result = {'role': 'toolResult', 'toolName': 'read', 'toolCallId': 'm', 'isError': False, 'content': 'old claim'}
        assert classify([call, result]) == {1}
        assert classify([result, call]) == set()
        assert classify([call, {**result, 'toolCallId': 'another'}]) == set()
        assert classify([call, {**result, 'toolName': 'bash'}]) == set()
        assert classify([call, {**result, 'isError': True}]) == set()
    source_write = {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 's', 'name': 'write', 'arguments': {'path': '/project/README.md', 'content': 'Read .memory/deployment.md'}}]}
    assert classify([source_write, {'role': 'toolResult', 'toolName': 'write', 'toolCallId': 's', 'content': 'Success'}]) == set()


# --- Merged from test_memory_reference_reuse.py ---
import json
from support import run_bun


def test_unchanged_discovery_is_structured_and_bodies_are_never_injected(tmp_path) -> None:
    result = run_bun(f'''
      import fs from 'node:fs/promises';
      import {{execFileSync}} from 'node:child_process';
      import register from './packages/continual-learning/extensions/inject-memory.ts';
      import {{resolveMemoryPaths}} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd={json.dumps(str(tmp_path / 'project'))};await fs.mkdir(cwd);execFileSync('git',['init','-q',cwd]);
      const p=resolveMemoryPaths(cwd);await fs.mkdir(p.harnessDir,{{recursive:true}});
      await fs.writeFile(p.harnessDir+'/test.md','---\\nname: test\\ndescription: Unique routing description\\ntype: project\\n---\\nSECRET_BODY_MARKER');
      await fs.writeFile(p.agentDir+'/continual-learning.json',JSON.stringify({{autoSettledLearning:false,autoContinualLearning:false}}));
      const hooks={{}};register({{on:(n,f)=>hooks[n]=f,registerCommand(){{}},sendMessage(){{}},appendEntry(){{}},getCommands:()=>[]}});
      const ctx={{cwd,ui:{{notify(){{}}}}}};
      await fs.mkdir(cwd+'/.memory');await fs.writeFile(cwd+'/.memory/TEST.md','---\\nname: test\\ndescription: STALE_PUBLIC_DESCRIPTION\\n---\\nPUBLIC_BODY');
      const start=async()=>{{const options={{sections:{{}}}};const returned=await hooks.before_agent_start({{systemPromptOptions:options,prompt:'task'}},ctx);return {{options,returned:returned??null}};}};
      const first=await start(),second=await start();
      const old={{role:'custom',customType:'continual-learning-memory-reference',content:'old',details:{{retrieved:[{{filename:'test.md'}}]}}}};
      const filtered=await hooks.context({{messages:[old,{{role:'user',content:'next'}}]}});
      await fs.writeFile(p.harnessDir+'/test.md','---\\nname: test\\ndescription: Corrected description\\ntype: project\\n---\\nNEW_BODY');
      const changed=await start();await fs.unlink(p.harnessDir+'/test.md');await fs.unlink(cwd+'/.memory/TEST.md');
      const deleted=await start();
      console.log(JSON.stringify({{first,second,filtered,changed,deleted}}));
    ''', env={'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    block = result['first']['options']['sections']['project_memory_discovery']
    assert 'SECRET_BODY_MARKER' not in block and 'STALE_PUBLIC_DESCRIPTION' not in block
    assert block.count('- test.md') == 1
    assert result['first'] == result['second']
    assert result['first']['returned'] is None
    assert result['filtered']['messages'] == [{'role': 'user', 'content': 'next'}]
    assert 'Corrected description' in result['changed']['options']['sections']['project_memory_discovery']
    assert 'project_memory_discovery' not in result['deleted']['options']['sections']


# --- Merged from test_memory_repair_deadline.py ---
import pytest

from support import isolated_run_bun


def test_unresponsive_repair_is_terminated_and_partial_usage_is_retained() -> None:
    # Given a repair child that reports known usage then never finishes,
    # When the recorded Memory correction budget expires, Then terminate it,
    # preserve partial cost, and retain the rejected plan without admitting it.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
      import {repairIncrementalMemoryPlan} from './packages/continual-learning/extensions/inject-memory.ts';
      import {MEMORY_CORRECTION_WORKER_DEADLINE_MS} from './packages/continual-learning/extensions/memory-body-review.ts';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'repair-deadline-')),pkg=path.join(root,'fake-package');fs.mkdirSync(pkg);
      fs.writeFileSync(path.join(pkg,'package.json'),JSON.stringify({name:'@earendil-works/pi-coding-agent'}));
      const cli=path.join(pkg,'cli.mjs'),marker=path.join(root,'pid');process.argv[1]=cli;
      fs.writeFileSync(cli,`import fs from 'node:fs';fs.writeFileSync(${JSON.stringify(marker)},String(process.pid));console.log(JSON.stringify({type:'message_end',message:{role:'assistant',stopReason:'toolUse',content:[],usage:{input:2,output:3,cacheRead:0,cacheWrite:0,totalTokens:5,cost:{total:0.25}}}}));setInterval(()=>{},1000);`);
      const timer=globalThis.setTimeout;let bound;
      // Accelerate only the production deadline after observing child readiness.
      globalThis.setTimeout=(fn,ms,...args)=>ms===MEMORY_CORRECTION_WORKER_DEADLINE_MS?(bound=ms,timer(function check(){if(fs.existsSync(marker))timer(fn,50,...args);else timer(check,10)},10)):timer(fn,ms,...args);
      const controller=new AbortController();let removed=0;
      const remove=controller.signal.removeEventListener.bind(controller.signal);controller.signal.removeEventListener=(...args)=>{removed++;return remove(...args)};
      const out=await repairIncrementalMemoryPlan({rejectedPlan:{operations:[],newMemories:[]},errors:['held'],selectedNames:[],identity:{runId:'r',scopeKey:'s',scopeDigest:'s',artifactHash:'a',snapshotDigest:'a'},signal:controller.signal,outputDir:root});
      let alive=true;try{process.kill(Number(fs.readFileSync(marker,'utf8')),0)}catch{alive=false}
      const ledgers=fs.readdirSync(root).filter(x=>x.startsWith('memory-repair-usage-')).map(x=>JSON.parse(fs.readFileSync(path.join(root,x),'utf8')));
      console.log(JSON.stringify({out,bound,recorded:MEMORY_CORRECTION_WORKER_DEADLINE_MS,alive,removed,parentAborted:controller.signal.aborted,ledgers}));
    ''', timeout=15)
    assert result['recorded'] == 600000
    assert result['bound'] == result['recorded']
    assert result['out']['outcome'] == 'failed'
    assert result['out']['failureKind'] == 'timeout'
    assert 'plan' not in result['out']
    assert not result['alive'] and not result['parentAborted']
    assert result['removed'] == 1
    assert len(result['ledgers']) == 1
    assert result['ledgers'][0]['knownUsage']['cost'] == 0.25


def test_parent_cancellation_is_not_relabelled_as_timeout() -> None:
    result = isolated_run_bun(r'''
      import {repairIncrementalMemoryPlan} from './packages/continual-learning/extensions/inject-memory.ts';
      const controller=new AbortController();controller.abort();
      const out=await repairIncrementalMemoryPlan({rejectedPlan:{operations:[],newMemories:[]},errors:['held'],selectedNames:[],identity:{runId:'r',scopeKey:'s',scopeDigest:'s',artifactHash:'a',snapshotDigest:'a'},signal:controller.signal});
      console.log(JSON.stringify(out));
    ''')
    assert result['outcome'] == 'cancelled'
    assert 'failureKind' not in result and 'plan' not in result


def test_actual_workspace_pi_repair_cancels_an_unresponsive_local_provider() -> None:
    # Actual selected workspace Pi and loopback transport; accelerate only the
    # parent deadline. Historical study copies keep their original Pi 1.0 pin.
    # This proves worker cancellation, not remote learning or semantic benefit.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
      import {repairIncrementalMemoryPlan} from './packages/continual-learning/extensions/inject-memory.ts';
      import {MEMORY_CORRECTION_WORKER_DEADLINE_MS} from './packages/continual-learning/extensions/memory-body-review.ts';
      const agent=process.env.PI_CODING_AGENT_DIR;let calls=0,expire;
      const server=Bun.serve({hostname:'127.0.0.1',port:0,idleTimeout:0,fetch:async request=>{
        calls++;await request.text();expire();return new Promise(()=>{});
      }});
      fs.writeFileSync(path.join(agent,'models.json'),JSON.stringify({providers:{fixture:{baseUrl:`http://127.0.0.1:${server.port}/v1`,api:'openai-completions',apiKey:'public-test-placeholder',models:[{id:'hang',name:'hang',reasoning:false,input:['text'],contextWindow:1000000,maxTokens:64,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}]}}}));
      fs.writeFileSync(path.join(agent,'settings.json'),JSON.stringify({packages:[],extensions:[],skills:[],retry:{enabled:false}}));
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'native-repair-cancel-'));process.env.HOME=root;process.env.PI_OFFLINE='1';
      const cli=fs.realpathSync('./node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js');process.argv[1]=cli;process.execPath=Bun.which('node');
      const expectedVersion=JSON.parse(fs.readFileSync('./node_modules/@earendil-works/pi-coding-agent/package.json','utf8')).version;
      const version=Bun.spawnSync([process.execPath,cli,'--version'],{env:process.env}).stdout.toString().trim();
      const timer=globalThis.setTimeout;let bound;
      globalThis.setTimeout=(fn,ms,...args)=>ms===MEMORY_CORRECTION_WORKER_DEADLINE_MS?(bound=ms,expire=()=>timer(fn,0,...args),timer(()=>{throw Error('No local provider request')},10000)):timer(fn,ms,...args);
      try{
        const out=await repairIncrementalMemoryPlan({rejectedPlan:{operations:[],newMemories:[]},errors:['held'],selectedNames:[],identity:{runId:'r',scopeKey:'s',scopeDigest:'s',artifactHash:'a',snapshotDigest:'a'},model:'fixture/hang',outputDir:root});
        const event=JSON.parse(fs.readFileSync(path.join(root,fs.readdirSync(root).find(x=>x.endsWith('-closed.json'))),'utf8'));
        console.log(JSON.stringify({out,event,bound,recorded:MEMORY_CORRECTION_WORKER_DEADLINE_MS,calls,version,expectedVersion,externalRequests:0}));
      }finally{server.stop(true)}
    ''', timeout=20)
    assert result['expectedVersion'] and result['version'] == result['expectedVersion']
    assert result['calls'] == 1 and result['externalRequests'] == 0
    assert result['bound'] == result['recorded'] == 600000
    assert result['out']['outcome'] == 'failed' and result['out']['failureKind'] == 'timeout'
    assert result['event']['stage'] == 'closed' and result['event']['timedOut'] is True


def test_active_parent_cancel_wins_a_deadline_during_child_cleanup() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
      import {repairIncrementalMemoryPlan} from './packages/continual-learning/extensions/inject-memory.ts';
      import {MEMORY_CORRECTION_WORKER_DEADLINE_MS} from './packages/continual-learning/extensions/memory-body-review.ts';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'repair-parent-cancel-')),pkg=path.join(root,'fake-package');fs.mkdirSync(pkg);
      fs.writeFileSync(path.join(pkg,'package.json'),JSON.stringify({name:'@earendil-works/pi-coding-agent'}));
      const cli=path.join(pkg,'cli.mjs'),marker=path.join(root,'pid');process.argv[1]=cli;
      fs.writeFileSync(cli,`import fs from 'node:fs';fs.writeFileSync(${JSON.stringify(marker)},String(process.pid));setInterval(()=>{},1000);`);
      const controller=new AbortController(),timer=globalThis.setTimeout;
      globalThis.setTimeout=(fn,ms,...args)=>ms===MEMORY_CORRECTION_WORKER_DEADLINE_MS?timer(function check(){
        if(fs.existsSync(marker)){controller.abort();fn(...args)}else timer(check,10)
      },10):timer(fn,ms,...args);
      const out=await repairIncrementalMemoryPlan({rejectedPlan:{operations:[],newMemories:[]},errors:['held'],selectedNames:[],identity:{runId:'r',scopeKey:'s',scopeDigest:'s',artifactHash:'a',snapshotDigest:'a'},signal:controller.signal});
      console.log(JSON.stringify(out));
    ''')
    assert result['outcome'] == 'cancelled'
    assert 'failureKind' not in result and 'plan' not in result


def test_recorded_correction_budget_admits_a_repair_that_outlives_the_historical_bound() -> None:
    # Given a held Memory repair that needs longer than the historical 230-second
    # bound, When it completes inside the recorded correction budget, Then the
    # complete response is accepted and the parent records the recorded deadline.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
      import {repairIncrementalMemoryPlan} from './packages/continual-learning/extensions/inject-memory.ts';
      import {MEMORY_CORRECTION_WORKER_DEADLINE_MS} from './packages/continual-learning/extensions/memory-body-review.ts';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'repair-budget-')),pkg=path.join(root,'fake-package');fs.mkdirSync(pkg);
      fs.writeFileSync(path.join(pkg,'package.json'),JSON.stringify({name:'@earendil-works/pi-coding-agent'}));
      const cli=path.join(pkg,'cli.mjs'),sentinel=path.join(root,'go');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'s',artifactHash:'a',snapshotDigest:'a'};
      const plan={kind:'incremental-memory-plan',version:1,...identity,operations:[],newMemories:[]};
      fs.writeFileSync(cli,`import fs from 'node:fs';const plan=${JSON.stringify(plan)};
        const wait=()=>{if(fs.existsSync(${JSON.stringify(sentinel)})){
          console.log(JSON.stringify({type:'message_end',message:{role:'assistant',stopReason:'stop',content:[{type:'text',text:JSON.stringify(plan)}],usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:{total:0.01}}}}));process.exit(0)}
          setTimeout(wait,5)};wait();`);
      process.argv[1]=cli;
      const timer=globalThis.setTimeout,SCALE=200;
      let bound=null;
      globalThis.setTimeout=(fn,ms,...args)=>{if(ms===MEMORY_CORRECTION_WORKER_DEADLINE_MS){bound=ms;return timer(fn,ms/SCALE,...args)}return timer(fn,ms,...args)};
      // A repair needing 300 of the recorded seconds still arrives before the deadline.
      timer(()=>fs.writeFileSync(sentinel,'1'),300_000/SCALE);
      const out=await repairIncrementalMemoryPlan({rejectedPlan:{operations:[],newMemories:[]},errors:['held'],selectedNames:[],identity,outputDir:root});
      const lifecycles=fs.readdirSync(root).filter(x=>x.startsWith('memory-repair-lifecycle-')).map(x=>JSON.parse(fs.readFileSync(path.join(root,x),'utf8')));
      const lifecycle=lifecycles.find(x=>x.stage==='started'),closed=lifecycles.find(x=>x.stage==='closed');
      console.log(JSON.stringify({outcome:out.outcome,failureKind:out.failureKind??null,hasPlan:!!out.plan,bound,recorded:MEMORY_CORRECTION_WORKER_DEADLINE_MS,lifecycle,closed}));
    ''', timeout=20)
    assert result['recorded'] == 600000
    assert result['recorded'] > 230000
    assert result['bound'] == result['recorded']
    assert result['outcome'] == 'repaired' and result['hasPlan']
    assert result['lifecycle']['deadlineMs'] == result['recorded']
    assert result['closed']['stage'] == 'closed' and result['closed']['timedOut'] is False and result['closed']['exitCode'] == 0


@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize("failed_artifact", ["closed", "usage", "both"])
def test_closed_marker_failure_retains_completed_worker_usage_without_admitting_plan(failed_artifact: str, partial: bool) -> None:
    # Given a paid worker result and a failing close marker, When retaining it,
    # Then keep known usage and fail closed instead of throwing away the costs.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import os from 'node:os';import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');
      const run=await import('./packages/continual-learning/extensions/consolidation-run.ts');const write=run.writeFileAtomic;
      const usage={input:2,output:3,cacheRead:0,cacheWrite:0,totalTokens:5,cost:0.25};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{input.onUpdate?.({text:'body',liveThinking:'fixture reasoning',turns:0});return {exitCode:__PARTIAL__?143:0,cancelled:__PARTIAL__,stderr:'',text:'{}',...(__PARTIAL__?{}:{usage}),usageLedger:{knownUsage:usage,assistantMessages:1,complete:!__PARTIAL__}}}}));
      mock.module('./packages/continual-learning/extensions/consolidation-run.ts',()=>({...run,writeFileAtomic:async(file,body)=>{
        if(('__FAILED_ARTIFACT__'!=='usage'&&file.endsWith('-closed.json'))||('__FAILED_ARTIFACT__'!=='closed'&&file.includes('memory-repair-usage-')))throw Error('fixture artifact write failed');
        return write(file,body);
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'repair-marker-failure-'));let out,error;
      try{out=await repairIncrementalMemoryPlan({rejectedPlan:{operations:[],newMemories:[]},errors:['held'],selectedNames:[],identity:{runId:'r',scopeKey:'s',scopeDigest:'s',artifactHash:'a',snapshotDigest:'a'},outputDir:root})}catch(e){error=e.message}
      const ledgers=fs.readdirSync(root).filter(x=>x.startsWith('memory-repair-usage-')).map(x=>JSON.parse(fs.readFileSync(path.join(root,x),'utf8')));
      const close=fs.readdirSync(root).find(x=>x.endsWith('-closed.json'));
      console.log(JSON.stringify({out,error:error??null,ledgers,closed:!!close,closedRecord:close?JSON.parse(fs.readFileSync(path.join(root,close),'utf8')):null}));
    '''.replace('__FAILED_ARTIFACT__', failed_artifact).replace('__PARTIAL__', str(partial).lower()))
    assert result['error'] is None
    assert result['out']['outcome'] == 'failed' and 'plan' not in result['out']
    assert result['out']['usage']['cost'] == 0.25
    assert result['out']['usageComplete'] is (not partial)
    assert result['out']['failureKind'] == 'artifact'
    assert len(result['ledgers']) == (1 if failed_artifact == 'closed' else 0)
    if result['ledgers']:
        assert result['ledgers'][0]['knownUsage']['cost'] == 0.25
    assert result['closed'] is (failed_artifact == 'usage')
    if result['closedRecord']:
        progress = result['closedRecord']['progress']
        assert progress['updates'] == 1 and progress['thinkingCharacters'] == 17
        assert progress['textCharacters'] == 4 and progress['completedTurns'] == 0
        assert progress['firstUpdateMs'] <= progress['lastUpdateMs']
        assert 'fixture reasoning' not in str(result['closedRecord'])


# --- Merged from test_memory_repair_effort.py ---
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


# --- Merged from test_memory_repair_grounding.py ---
from support import isolated_run_bun


def test_real_field_repair_preserves_parent_validated_observations() -> None:
    # Given the actual v10 rewrite, When only its held body is repaired,
    # Then original source observations survive omitted or forged metadata.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {mergeSemanticMemoryRepairDelta} from './packages/continual-learning/extensions/inject-memory.ts';
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-grounding.json','utf8'));
      const original={operations:[fixture.original],newMemories:[]};
      const rows=[];
      for(const fields of [['body'],['description'],['body','description']]) {
        for(const extra of [{},{observations:[{path:'invented.ts',status:'found'}]}]) {
          const corrected={...fixture.corrected,...extra};
          const merged=mergeSemanticMemoryRepairDelta(original,{operations:[corrected],newMemories:[]},[fixture.original.name],{[fixture.original.name]:fields});
          rows.push({observations:merged.operations[0].observations,body:merged.operations[0].content});
        }
      }
      console.log(JSON.stringify({expected:fixture.original.observations,rows}));
    ''')
    assert result['expected']
    assert all(row.get('observations') == result['expected'] for row in result['rows'])


def test_unobserved_grounding_never_infers_claim_kind_from_filename() -> None:
    # Given project facts and preferences without observations, When expanded,
    # Then all are honestly unverified rather than classified by filename.
    result = isolated_run_bun(r'''
      import fs from 'node:fs/promises'; import path from 'node:path';
      import {expandIncrementalMemoryPlan} from './packages/continual-learning/extensions/incremental-memory-plan.ts';
      const root=process.env.PI_CODING_AGENT_DIR;
      const names=['project_fact.md','limit_function_type_contract.md','preference_style.md'];
      const harness=path.join(root,'memory'),pub=path.join(root,'public');await fs.mkdir(harness);await fs.mkdir(pub);
      await fs.writeFile(path.join(harness,'MEMORY.md'),names.map(name=>`- [${name}](${name})`).join('\n'));
      for(const name of names)await fs.writeFile(path.join(harness,name),'---\ntype: project\n---\nRepository source claim.\n');
      const run={manifest:{runId:'r',scopeKey:'s',scopeDigest:'d',snapshotDigest:'h',cwd:root,harnessDir:harness,publicDir:pub,sourceHashes:{harness:{},public:{}}}};
      const plan=await expandIncrementalMemoryPlan(run,names,{kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'h',snapshotDigest:'h',operations:[],newMemories:[]});
      console.log(JSON.stringify(plan.grounding));
    ''', temp_dirs=('PI_CODING_AGENT_DIR',))
    assert {row['status'] for row in result} == {'UNVERIFIABLE'}
    assert len({row['reason'] for row in result}) == 1
    assert all('does not make a repository claim' not in row['reason'] for row in result)


def test_parent_recomputes_optional_content_hash_after_field_repair() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs'; import {createHash} from 'node:crypto';
      import {mergeSemanticMemoryRepairDelta} from './packages/continual-learning/extensions/inject-memory.ts';
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-grounding.json','utf8'));
      const hash=text=>createHash('sha256').update(text).digest('hex');
      const prior={...fixture.original,contentSha256:hash(fixture.original.content)};
      const rows=[];
      for(const fields of [['body'],['description'],['body','description']]) {
        const corrected={...fixture.corrected,content:fixture.corrected.content.replace(/description: [^\n]+/,'description: A corrected declared contract'),contentSha256:'0'.repeat(64)};
        const result=mergeSemanticMemoryRepairDelta({operations:[prior],newMemories:[]},{operations:[corrected],newMemories:[]},[prior.name],{[prior.name]:fields}).operations[0];
        rows.push({actual:result.contentSha256,expected:hash(result.content),observations:result.observations});
      }
      console.log(JSON.stringify({rows,observations:prior.observations}));
    ''')
    assert all(row['actual'] == row['expected'] for row in result['rows'])
    assert all(row['observations'] == result['observations'] for row in result['rows'])


def test_bounds_repair_preserves_observations_without_field_checklist() -> None:
    # Given bounds refused review before producing a checklist, When a semantic
    # replacement omits or forges observations, Then parent observations survive.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {mergeSemanticMemoryRepairDelta} from './packages/continual-learning/extensions/inject-memory.ts';
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-grounding.json','utf8'));
      const rows=[];
      for(const extra of [{},{observations:[{path:'invented.ts',status:'found'}]}]) {
        const result=mergeSemanticMemoryRepairDelta({operations:[fixture.original],newMemories:[]},{operations:[{...fixture.corrected,...extra}],newMemories:[]},[fixture.original.name]);
        rows.push(result.operations[0].observations);
      }
      console.log(JSON.stringify({expected:fixture.original.observations,rows}));
    ''')
    assert all(row == result['expected'] for row in result['rows'])


# --- Merged from test_memory_repair_inventory_classification.py ---
from support import isolated_run_bun


def test_structural_repair_uses_parent_inventory_not_rejected_classification() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let response,prompt;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{prompt=input.prompt;return {exitCode:0,stderr:'',text:JSON.stringify(response)}}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const outcomes=[];
      for(const classification of ['safe','private']) {
        const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[{name:'known.md',kind:'rewrite',classification:classification==='safe'?'private':'safe',content:'Observed source fact.',evidence:[{index:0,quote:'Observed source fact.'}]}],newMemories:[]};
        response=structuredClone(original);response.operations[0].classification=classification;
        const input={identity,rejectedPlan:original,errors:['citation too long'],selectedNames:['known.md'],structuralCorrection:true,semanticContext:{frozenEvidence:{entries:[{role:'toolResult',content:'Observed source fact.'}]},existingMemories:[{name:'known.md',classification,content:'Earlier source fact.',type:'project',description:'Source fact.'}]}};
        const result=await repairIncrementalMemoryPlan(input);
        const framing=JSON.parse(prompt.split('\n').at(-1));
        outcomes.push({classification,outcome:result.outcome,table:framing.selectedClassifications,errors:framing.errors});
        response.operations[0].classification=original.operations[0].classification;
        const wrong=await repairIncrementalMemoryPlan(input);outcomes.push({wrong:wrong.outcome});
        response.operations[0].classification=classification;
        const semantic=await repairIncrementalMemoryPlan({...input,structuralCorrection:false});outcomes.push({semantic:semantic.outcome});
      }
      console.log(JSON.stringify(outcomes));
    ''')
    for index, classification in ((0, 'safe'), (3, 'private')):
        assert value[index]['outcome'] == 'repaired'
        assert value[index]['table'] == {'known.md': classification}
        assert any('parent-derived inventory' in error for error in value[index]['errors'])
        assert value[index + 1]['wrong'] == 'failed'
        assert value[index + 2]['semantic'] == 'failed'


# --- Merged from test_memory_repair_knowledge_preservation.py ---
from support import isolated_run_bun


def test_real_lossy_correction_does_not_instruct_rewrite_bodies_to_be_one_fact() -> None:
    # Given v13's actual multi-fact predecessor and lossy repair, When another
    # semantic correction is requested, Then the worker gets the complete
    # predecessor and a preservation contract, not a one-sentence body contract.
    # Capturing this request proves the contract only, not real model compliance.
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let prompt;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        prompt=input.prompt;return {text:'{}',exitCode:0,stderr:'',cancelled:false};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-repair-knowledge-loss.json').json();
      await repairIncrementalMemoryPlan({identity:f.original,rejectedPlan:f.original,
        errors:['counterevidence uncertainty'],selectedNames:f.existingMemories.map(x=>x.name),
        repairableNames:f.original.operations.map(x=>x.name),
        repairableFields:Object.fromEntries(f.original.operations.map(x=>[x.name,['body']])),
        semanticContext:{existingMemories:f.existingMemories,frozenEvidence:{entries:[]}}});
      const payload=JSON.parse(prompt.split('\n').at(-1));
      console.log(JSON.stringify({prompt:prompt.slice(0,prompt.lastIndexOf('\n')),
        predecessorPreserved:JSON.stringify(payload.semanticContext.existingMemories)===JSON.stringify(f.existingMemories),
        originalBodies:f.original.operations.map(x=>({name:x.name,content:x.content})),
        correctedBodies:f.corrected.operations.map(x=>({name:x.name,content:x.content}))}));
    ''')
    before = {row['name']: row['content'] for row in result['originalBodies']}
    after = {row['name']: row['content'] for row in result['correctedBodies']}
    assert 'Promise.all' in before['clear_queue_pending_only.md']
    assert 'Promise.all' not in after['clear_queue_pending_only.md']
    assert 'PromiseLike<ReturnType> | ReturnType' in before['limit_function_type_contract.md']
    assert 'PromiseLike<ReturnType> | ReturnType' not in after['limit_function_type_contract.md']
    assert result['predecessorPreserved']
    prompt = result['prompt']
    assert 'Use the shortest directly supported fact;' not in prompt
    assert 'Preserve still-valid predecessor facts, conditions, unresolved observations and usage guidance' in prompt
    assert 'does not authorize compressing an already correct record or discarding still-valid predecessor knowledge' in prompt
    assert 'Preserve a supported unresolved failure instead of inventing a mechanism or discarding the observation' in prompt


# --- Merged from test_memory_schema_references.py ---
from support import isolated_run_bun


def test_complete_citation_catalog_is_encoded_once_without_weakening_schema() -> None:
    result = isolated_run_bun(r'''
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      import {Value} from 'typebox/value';
      const domain={indices:[0],refs:Array.from({length:2000},(_,i)=>`e0.b0.l${i+1}`)};
      const schema=learningOutputSchema('memory-delta',domain),encoded=JSON.stringify(schema);
      const occurrences=encoded.split('"e0.b0.l2000"').length-1;
      const content='---\nname: p\ndescription: Unverified candidate\ntype: project\n---\nClaim';
      const base={kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'x',operations:[],newMemories:[{name:'p.md',kind:'preference',content,evidence:[{ref:domain.refs.at(-1)}]}]};
      const valid=Value.Check(schema,base),invalid=Value.Check(schema,{...base,newMemories:[{...base.newMemories[0],evidence:[{ref:'e0.b0.l2001'}]}]});
      console.log(JSON.stringify({occurrences,complete:schema.$defs?.memorySourceReference.enum.length===domain.refs.length,valid,invalid,bytes:Buffer.byteLength(encoded)}));
    ''')
    assert result['occurrences'] == 1
    assert result['complete'] and result['valid'] and not result['invalid']


def test_real_generation_schema_expansion_retains_every_legacy_constraint_and_reference() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      const old=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-generation-schema.json','utf8')).schema;
      const refs=old.properties.operations.items.anyOf[0].properties.evidence.items.properties.ref.enum;
      const domain={indices:[...new Set(refs.map(ref=>Number(/^e(\d+)/.exec(ref)[1])))],refs,fileRefs:refs};
      const current=learningOutputSchema('memory-delta',domain);
      // When every synthetic catalog position is file-capable, the original two
      // branches remain equivalent after expansion. Real fileRefs is a strict
      // parent-derived subset; the new producer source unit is a distinct capability.
      const legacy=structuredClone(current);
      const added=legacy.properties.newMemories.items.anyOf.splice(1);
      // Fresh project source excerpts moved to atomic knowledge; legacy remains unchanged.
      legacy.properties.newMemories.items.anyOf.push(old.properties.newMemories.items.anyOf[1]);
      const projectProducerMoved=JSON.stringify(legacy.properties.newMemories.items.anyOf[0].properties.kind.enum)==='["preference"]';
      // Only the initial producer's project representation moves to knowledge.
      // Restore this declared difference for the exact legacy constraint check.
      legacy.properties.newMemories.items.anyOf[0].properties.kind=old.properties.newMemories.items.anyOf[0].properties.kind;
      const expand=value=>{
        if(Array.isArray(value))return value.map(expand);
        if(!value||typeof value!=='object')return value;
        if(value.$ref){const key=value.$ref.slice('#/$defs/'.length);if(!['memorySourceReference','memoryFileSourceReference'].includes(key))throw Error('Unexpected ref');return current.$defs[key];}
        return Object.fromEntries(Object.entries(value).filter(([key])=>key!=='$defs').map(([key,item])=>[key,expand(item)]));
      };
      const sort=value=>Array.isArray(value)?value.map(sort):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,sort(value[key])])):value;
      console.log(JSON.stringify({equivalent:JSON.stringify(sort(expand(legacy)))===JSON.stringify(sort(old)),
        projectProducerMoved,addedProjectSourceBranch:added.length===1&&JSON.stringify(added[0].properties.classification.enum)==='["safe","private"]'
          &&added[0].properties.kind.const==='project'&&added[0].required.includes('knowledge'),
        refs:refs.length,oldBytes:Buffer.byteLength(JSON.stringify(old)),newBytes:Buffer.byteLength(JSON.stringify(current)),
        occurrences:JSON.stringify(current).split(JSON.stringify(refs.at(-1))).length-1}));
    ''')
    assert result['equivalent'] and result['projectProducerMoved'] and result['addedProjectSourceBranch'] and result['refs'] > 0
    assert result['occurrences'] == 1
    assert result['newBytes'] < result['oldBytes'] / 2


# --- Merged from test_memory_source_identity.py ---
from support import isolated_run_bun


def test_memory_start_ignores_hash_key_order_but_rejects_actual_source_changes():
    # Given the real Memory startup path and a bound selection, When the same
    # hashes arrive in another traversal order, Then reach spawn; changed bytes
    # still stop before any worker. No model or network request is admitted.
    result = isolated_run_bun(r'''
      import {plugin} from 'bun';import {mock} from 'bun:test';
      import fs from 'node:fs';import path from 'node:path';
      plugin({name:'private-startup-test',setup(build){build.onLoad({filter:/[/]inject-memory\.ts$/},args=>({contents:fs.readFileSync(args.path,'utf8')+'\nexport {spawnAsyncConsolidation};',loader:'ts'}));}});
      const original=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const kit=await import('./packages/kit/index.ts');const root=process.env.PI_CODING_AGENT_DIR;
      const dossierPath=path.join(root,'dossier.json');fs.writeFileSync(dossierPath,JSON.stringify({kind:'incremental-learning-dossier',taskSlice:{entries:[]},selectedMemories:[]}));
      const selected={harness:{'a.md':'a'.repeat(64),'b.md':'b'.repeat(64)},public:{}};
      let current={harness:{'b.md':'b'.repeat(64),'a.md':'a'.repeat(64)},public:{}},spawns=0;
      mock.module('./packages/continual-learning/extensions/consolidation-run.ts',()=>({...original,
        createConsolidationRun:async()=>({manifest:{cwd:root,runId:'test',scopeKey:'s',scopeDigest:'d',snapshotDigest:'d',runDir:root,harnessDir:'private',publicDir:'public',sourceHashes:current},normalization:{repaired:[],removed:[]}}),
        hashMemoryRoot:async root=>root==='private'?current.harness:current.public,releaseConsolidationRun:async()=>{}}));
      mock.module('./packages/kit/index.ts',()=>({...kit,resolvePiCli:()=>({command:'forbidden',args:[]}),spawnPiChild:()=>{spawns++;throw Error('OFFLINE_SPAWN_BOUNDARY');}}));
      const module=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const source=fs.readFileSync('./packages/continual-learning/extensions/inject-memory.ts','utf8');
      // Compute the selected identity with the exact production selection expression.
      const expression=source.match(/selectedSourceDigest = ([^;]+selectorRun\.manifest\.sourceHashes[^;]+);/)[1];
      const selectedDigest=new Function('selectorRun','sha256Digest','digest',`return ${expression}`)({manifest:{sourceHashes:selected}},original.sha256Digest,original.digest);
      const outcomes=[];for(const change of ['order','changed','added','removed']){current={harness:{'b.md':'b'.repeat(64),'a.md':'a'.repeat(64)},public:{}};if(change==='changed')current.harness['a.md']='c'.repeat(64);if(change==='added')current.harness['c.md']='c'.repeat(64);if(change==='removed')delete current.harness['a.md'];let error;const notices=[];
        try{await module.spawnAsyncConsolidation({ui:{notify:m=>notices.push(m)}},{active:false,cancelled:false,generation:0},{cwd:root,pkgDir:root,reason:'test',mode:'automatic',dossierPath,dossierDigest:original.sha256Digest(fs.readFileSync(dossierPath)),selectedSourceDigest:selectedDigest,selectedScope:['a.md'],applyChanges:false});}catch(e){error=e.message}
        outcomes.push({spawns,error,notices});}
      console.log(JSON.stringify({outcomes,externalRequests:0}));
    ''')
    assert result['outcomes'][0]['spawns'] == 1, result
    assert 'OFFLINE_SPAWN_BOUNDARY' in str(result['outcomes'][0]['notices'])
    for outcome in result['outcomes'][1:]:
        assert outcome['spawns'] == 1, result
        assert outcome['error'] == 'selected Memory changed after incremental selection'
