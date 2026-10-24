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
      const knowledge={sourceCitations:evidence,units:[{sourceCitationIndex:0}]};
      const accepted=[{...project,kind:'preference',classification:'private'},
        {name:'new.md',kind:'project',classification:'safe',description:'Source',knowledge},
        {name:'excerpt.md',kind:'project',classification:'private',sourceExcerpt:{ref:'e0.b0.l1'},evidence}];
      const rejected=[project,{name:'bad.md',kind:'project',classification:'safe',sourceExcerpt:{ref:'e0.b0.l1'},evidence},
        {...project,knowledge},{name:'both.md',kind:'project',classification:'private',knowledge,sourceExcerpt:{ref:'e0.b0.l1'},evidence}];
      const passed=accepted.map(item=>{assertFreshMemoryProjectOutput({newMemories:[item]});return true});
      const errors=rejected.map(item=>{try{assertFreshMemoryProjectOutput({newMemories:[item]});return null}catch(error){return error.message}});
      const legacy={operations:[],newMemories:[project]},out=await materializeSourceExcerptPlan({manifest:{cwd:'/unused'}},legacy,{entries:[]});
      console.log(JSON.stringify({passed,errors,legacyUnchanged:JSON.stringify(legacy)===JSON.stringify(out)}));
    ''')
    assert all(value['passed']) and value['legacyUnchanged']
    assert all(error == 'Fresh Memory project output is invalid: newMemories[0] requires knowledge or a private sourceExcerpt'
               for error in value['errors']), value


def test_fresh_project_raw_rejection_uses_one_existing_repair_before_source_materialization() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import {mock} from 'bun:test';
      import {assertFreshMemoryProjectOutput} from './packages/continual-learning/extensions/planner-output-schema.ts';
      import {materializeSourceExcerptPlan} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const kit=await import('./packages/kit/src/index.ts');let calls=0,reply;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{calls++;return {exitCode:0,stderr:'',text:JSON.stringify(reply),
        usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:0},usageComplete:true};}}));
      const {repairIncrementalMemoryPlan,semanticMemoryRepairCandidates,retainOriginalMemoryGenerationPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'fresh-project-contract-')));
      try {
        const source=path.join(root,'api.ts'),text='export interface Pool { flush(): void; }\nexport function makePool(): Pool;';fs.writeFileSync(source,text);
        const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'read',name:'read',arguments:{path:source}}]},
          {role:'toolResult',toolName:'read',toolCallId:'read',isError:false,content:text}]};
        const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
        const item={name:'pool.md',kind:'project',classification:'safe',content:'---\nname: pool\ndescription: Pool\ntype: project\n---\nProse.',evidence:[{ref:'e1.b0.l1'}]};
        const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[item]},before=JSON.stringify(original);
        await retainOriginalMemoryGenerationPlan(root,identity,original);
        const originalArtifact=JSON.parse(fs.readFileSync(path.join(root,'generation-original-plan.json'),'utf8'));
        let rejection;try{assertFreshMemoryProjectOutput(original)}catch(error){rejection=error.message}
        const corrected={name:item.name,kind:'project',classification:'safe',description:'The inspected Pool declares flush.',knowledge:{
          sourceCitations:[{ref:'e1.b0.l1',endRef:'e1.b0.l2'}],units:[{sourceCitationIndex:0}]}};
        reply={...original,newMemories:[corrected]};
        const options={identity,rejectedPlan:original,selectedNames:[],errors:[rejection],structuralCorrection:true,requireNewProjectKnowledge:true};
        const repaired=await repairIncrementalMemoryPlan(options);
        const raw=JSON.stringify(repaired.plan);const materialized=await materializeSourceExcerptPlan({manifest:{cwd:root}},repaired.plan,snapshot);
        const badOutput=path.join(root,'bad-response');fs.mkdirSync(badOutput);reply=original;
        const failed=await repairIncrementalMemoryPlan({...options,outputDir:badOutput});
        const artifact=JSON.parse(fs.readFileSync(path.join(badOutput,'structural-repair-response.json'),'utf8'));
        const legacy=await repairIncrementalMemoryPlan({...options,requireNewProjectKnowledge:undefined});
        const candidateId=semanticMemoryRepairCandidates(materialized)[0].candidateId;
        reply={kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId,evidence:[{ref:'e1.b0.l1',endRef:'e1.b0.l2'}]}]};
        const internal=await repairIncrementalMemoryPlan({...options,rejectedPlan:materialized,citationOnly:true,
          semanticContext:{frozenEvidence:snapshot,existingMemories:[]}});
        console.log(JSON.stringify({rejection,repaired,materialized,rawRetained:raw===JSON.stringify(repaired.plan),failed,legacy,internal,originalArtifact,calls,
          originalUnchanged:before===JSON.stringify(original),badRawRetained:JSON.parse(artifact.output).newMemories[0].content===item.content,
          memoryWrite:fs.existsSync(path.join(root,'.memory')),sourceUnchanged:fs.readFileSync(source,'utf8')===text}));
      }finally{fs.rmSync(root,{recursive:true,force:true})}
    ''')
    assert value['rejection'].startswith('Fresh Memory project output is invalid:'), value
    assert value['repaired']['outcome'] == 'repaired', value
    assert value['repaired']['plan']['newMemories'][0]['knowledge']['units'] == [{'sourceCitationIndex': 0}]
    body = value['materialized']['newMemories'][0]['content']
    assert 'export interface Pool { flush(): void; }\nexport function makePool(): Pool;' in body
    assert 'knowledge' not in value['materialized']['newMemories'][0]
    assert value['failed']['outcome'] == 'failed' and value['failed']['failureKind'] == 'framing'
    assert value['legacy']['outcome'] == 'repaired'
    assert value['internal']['outcome'] == 'repaired', value['internal']
    assert value['internal']['plan']['newMemories'][0]['content'] == body
    assert value['originalArtifact']['originalPlan']['newMemories'][0]['content'].endswith('Prose.')
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
