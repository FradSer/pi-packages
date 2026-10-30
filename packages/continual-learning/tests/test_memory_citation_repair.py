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
        const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[{...proposal,description:'x'.repeat(123)}]};
        const input={identity,rejectedPlan:original,selectedNames:[],errors:['Controlled metadata bound'],structuralCorrection:true,requireNewProjectKnowledge:true,fileSourcesFromCwd:repo,semanticContext:{frozenEvidence:snapshot,existingMemories:[]}};
        const good={...original,newMemories:[proposal]},before=JSON.stringify(original);next=good;const repaired=await repairIncrementalMemoryPlan(input),actualBinding=binding;
        const materialized=await materializeSourceExcerptPlan(run,repaired.plan,snapshot,undefined,{retainSelectedDeclarations:true});
        const expanded=await expandCitedIncrementalMemoryPlan(run,[],materialized);await applyConsolidationPlan(run,expanded,()=>true,()=>assertSourceExcerptBindings(run));
        const stored=fs.readFileSync(path.join(m.harnessDir,'pool.md'),'utf8');const bad={};
        for(const [label,change] of Object.entries({wrongId:p=>p.runId+='x',tooLong:p=>p.newMemories[0].description='x'.repeat(123),foreign:p=>p.newMemories[0].knowledge.sourceCitations[0]={ref:'e1.b0.l99'},privacy:p=>p.newMemories[0].classification='safe',zero:p=>p.newMemories=[],operation:p=>p.operations=[{}]})){
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
        const judge=createJevJudge({enabled:true,apiKey:'controlled-fixture',allowPrivateMemory:true,independentMemoryApplication:true,requestConcurrency:1,fetch:async(_u,init)=>{
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
