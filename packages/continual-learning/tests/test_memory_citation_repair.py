from support import isolated_run_bun


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
