from support import isolated_run_bun


def test_semantic_candidate_reference_schema_is_exact_and_citation_only_stays_strict():
    value = isolated_run_bun(r'''
      import {Value} from 'typebox/value';import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      const ids=['newMemories:0:'+'a'.repeat(64),'operations:2:'+'b'.repeat(64)];
      const base={kind:'incremental-memory-amendment',version:1,runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const patch={candidateRef:'newMemories:0',content:'---\nname: a\ndescription: Candidate\ntype: project\n---\nUnverified proposal.',evidence:[{ref:'e0.b0.l1'}]};
      const semantic=learningOutputSchema('memory-semantic-amendment',undefined,ids),citation=learningOutputSchema('memory-amendment',undefined,ids);
      const check=p=>Value.Check(semantic,{...base,replacements:[p]});
      const {candidateRef,...body}=patch;
      console.log(JSON.stringify({refs:semantic.properties.replacements.items.properties.candidateRef.enum,
        valid:check(patch),legacy:check({...body,candidateId:ids[0]}),source:check({candidateRef:'operations:2',sourceExcerpt:{ref:'e0.b0.l1'},evidence:patch.evidence}),
        invalid:[{...patch,candidateId:ids[0]},{...patch,candidateRef:'newMemories:1'},body,{candidateRef:'newMemories:0'},
          {...patch,sourceExcerpt:{ref:'e0.b0.l1'}}].map(check),citation:Value.Check(citation,{...base,replacements:[patch]})}));
    ''')
    assert value['refs'] == ['newMemories:0', 'operations:2']
    assert value['valid'] and value['legacy'] and value['source']
    assert not any(value['invalid']) and not value['citation']


def test_memory_schema_constrains_delta_and_amendment_without_selecting_facts() -> None:
    value = isolated_run_bun(r'''
      import {Value} from 'typebox/value';
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      const delta=learningOutputSchema('memory-delta'),amendment=learningOutputSchema('memory-amendment');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'h',snapshotDigest:'h'};
      const rewrite={name:'existing.md',kind:'rewrite',classification:'private',content:'---\nname: existing\ndescription: Candidate, not truth.\ntype: project\n---\nCandidate, not truth.',evidence:[{ref:'e2.b0.l1',endRef:'e2.b0.l2'}]};
      const base={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[rewrite],newMemories:[]};
      const valid=[base,{...base,operations:[]},...[
        {index:2,quote:'Original source'},
        {index:2,lines:{block:0,start:1,end:2}},
        {index:2,lines:{source:'patch',block:0,start:1,end:1,characters:{start:0,end:20}}},
      ].map(e=>({...base,operations:[{...rewrite,evidence:[e]}]}))];
      const invalid=[[],{...base,scopeKey:undefined},...[
        {...rewrite,evidence:[]},{...rewrite,evidence:undefined},
        {...rewrite,kind:'project-fact'}, {...rewrite,evidence:[{ref:'e2.b0.l1',index:2}]},
        {name:'existing.md',kind:'delete',classification:'private',content:'Forbidden',verdict:'SUBSUMED',preservedIn:['replacement.md'],evidence:[{ref:'e2.b0.l1'}]},
      ].map(o=>({...base,operations:[o]}))];
      const sparse={kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:'parent-id',content:'---\nname: candidate\ndescription: Unverified candidate.\ntype: project\n---\nCandidate',evidence:[{ref:'e2.b0.l1'}]}]};
      console.log(JSON.stringify({valid:valid.map(v=>Value.Check(delta,v)),invalid:invalid.map(v=>Value.Check(delta,v)),sparse:Value.Check(amendment,sparse),missingEvidence:Value.Check(amendment,{...sparse,replacements:[{candidateId:'parent-id',content:'---\nname: candidate\ndescription: Unverified candidate.\ntype: project\n---\nCandidate'}]}),unknown:learningOutputSchema('unknown')}));
    ''')
    assert all(value['valid']) and not any(value['invalid'])
    assert value['sparse'] and not value['missingEvidence']
    assert value.get('unknown') is None


def test_combined_amendment_schema_and_candidate_domain_are_complete_and_fail_closed() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import {Value} from 'typebox/value';
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      import extension from './packages/continual-learning/extensions/planner-json-output.ts';import {learningPlannerArgs} from './packages/continual-learning/extensions/planner-prompts.ts';
      const id='newMemories:0:'+'a'.repeat(64);const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'h',snapshotDigest:'h'};
      const amendment={kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:id,content:'---\nname: candidate\ndescription: Unverified candidate.\ntype: project\n---\nCandidate',evidence:[{ref:'e0.b0.l1'}]}],operations:[{name:'retained.md',kind:'rewrite',classification:'private',content:'---\nname: retained\ndescription: Candidate\ntype: project\n---\nComplete corrected knowledge.',evidence:[{ref:'e0.b0.l1'}]}]};
      const schema=learningOutputSchema('memory-combined-amendment',{indices:[0],refs:['e0.b0.l1']},[id]);const emptySchema=learningOutputSchema('memory-combined-amendment',undefined,[]);
      fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json'),JSON.stringify({plannerStructuredOutput:true}));let encoded=JSON.stringify([id]),handler;
      extension({registerFlag:()=>{},getFlag:name=>name==='learning-output-schema'?'memory-combined-amendment':name==='learning-candidate-ids'?encoded:undefined,getActiveTools:()=>[],on:(name,fn)=>{if(name==='before_provider_request')handler=fn}});
      const payload={messages:[{role:'user',content:'Return JSON'}]};const ctx={model:{api:'openai-completions',id:'qwen3.8-flash'}};const wire=handler({payload},ctx);
      const refused=[];for(const input of [JSON.stringify([id,id]),JSON.stringify(['foreign']),JSON.stringify({id}),'{', 'complete-candidates-overflow','x'.repeat(64001)]){encoded=input;try{handler({payload},ctx);refused.push(false)}catch{refused.push(true)}}
      const unsupported=handler({payload},{model:{api:'openai-completions',id:'unknown'}});
      console.log(JSON.stringify({valid:Value.Check(schema,amendment),foreign:Value.Check(schema,{...amendment,replacements:[{...amendment.replacements[0],candidateId:'foreign'}]}),newNames:Value.Check(schema,{...amendment,newMemories:[]}),emptyValid:Value.Check(emptySchema,{...amendment,replacements:[],operations:[]}),partialProposal:Value.Check(schema,{...amendment,operations:[]}),partialRetained:Value.Check(schema,{...amendment,replacements:[]}),refusal:Value.Check(schema,{...amendment,operations:[],replacements:[]}),emptyRejectsPatch:!Value.Check(emptySchema,amendment),emptyItem:emptySchema.properties.replacements.items.properties.candidateId,wire,refused,unsupported,args:learningPlannerArgs('memory-combined-amendment',{entries:[{role:'user',content:'Source'}]},[id]),id}));
    ''', temp_dirs=('PI_CODING_AGENT_DIR',))
    assert value['valid'] and not value['foreign'] and not value['newNames']
    assert value['emptyValid'] and value['emptyRejectsPatch']
    assert not value['partialProposal'] and not value['partialRetained']
    assert value['refusal'], 'Unresolved source must allow an explicit complete refusal, never force invented operations'
    assert value['emptyItem'] == {'type': 'string'}
    assert all(value['refused']) and value.get('unsupported') is None
    assert value['wire']['response_format']['json_schema']['schema']['properties']['replacements']['items']['properties']['candidateId']['enum'] == [value['id']]
    assert '--learning-candidate-ids' in value['args']


def test_amendment_pattern_consumes_complete_markdown_and_rejects_metadata_only() -> None:
    # Given complete replacements, When a decoder uses whole-value matching,
    # Then it can generate the body, while normal JSON Schema search validation
    # also rejects metadata without a knowledge body. This is interoperability
    # coverage, not evidence of a particular service backend or learning benefit.
    value = isolated_run_bun(r'''
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      const legacy='^---\\r?\\n[\\s\\S]*?\\r?\\n---(?:\\r?\\n|$)';
      const header='---\nname: contract\ndescription: Observed declaration.\ntype: project\n---';
      const complete=[header+'\nFull declaration.',header+'\n\nWhy\n'+('A supported condition.\n'.repeat(100)),header+'\nBody\n---\nTail',header.replaceAll('\n','\r\n')+'\r\n完整正文\r\n'];
      const specimens=[...complete,header,header+'\n','A body-only paragraph.','prefix\n'+header,'---\nUnclosed header','---\nname: contract\n---suffix'];
      const results=['memory-amendment','memory-combined-amendment'].map(kind=>{
        const pattern=learningOutputSchema(kind).properties.replacements.items.properties.content.pattern;
        const search=new RegExp(pattern),full=new RegExp('^(?:'+pattern+')$');
        return {complete:complete.map(text=>full.test(text)),search:specimens.map(text=>search.test(text)),legacy:specimens.map(text=>new RegExp(legacy).test(text))};
      });console.log(JSON.stringify(results));
    ''')
    for result in value:
        assert all(result['complete']), 'Producer pattern prevents complete body generation under whole-value matching'
        assert result['search'] == [True] * 4 + [False] * 6
        assert result['legacy'][4:6] == [True, True], 'Original producer schema admitted metadata-only documents'


def test_semantic_patch_schema_distinguishes_source_reuse_from_citation_correction():
    value=isolated_run_bun(r'''
      import {Value}from'typebox/value';import{learningOutputSchema}from'./packages/continual-learning/extensions/planner-output-schema.ts';
      const id='operations:0:'+'a'.repeat(64),identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const base={kind:'incremental-memory-amendment',version:1,...identity};
      const content='---\nname: a\ndescription: Exact declaration\ntype: project\n---\nDeclared API contract.';
      const patch={candidateId:id,content},evidence=[{ref:'e0.b0.l1'}];
      const rows=['memory-semantic-amendment','memory-amendment'].map(kind=>{
        const schema=learningOutputSchema(kind,{indices:[0],refs:['e0.b0.l1']},[id]);
        const check=p=>Value.Check(schema,{...base,replacements:[p]});
        const excerpt={candidateId:id,sourceExcerpt:{ref:'e0.b0.l1'},evidence};
        return {kind,contentOnly:check(patch),citationOnly:check({candidateId:id,evidence}),excerpt:check(excerpt),mixed:check({...excerpt,content}),excerptWithoutEvidence:check({candidateId:id,sourceExcerpt:excerpt.sourceExcerpt}),outsideExcerpt:check({...excerpt,sourceExcerpt:{ref:'e0.b0.l2'}}),emptyPatch:check({candidateId:id}),emptyEvidence:check({...patch,evidence:[]}),foreign:check({...patch,candidateId:'other'}),bodyOnly:check({...patch,content:'No complete frontmatter'}),missingIdentity:Value.Check(schema,{kind:base.kind,version:1,replacements:[patch]})};
      });console.log(JSON.stringify(rows));
    ''')
    assert value[0]['contentOnly'] and not value[1]['contentOnly']
    assert value[0]['excerpt'] and not value[1]['excerpt']
    assert all(not row[key] for row in value for key in ['mixed', 'excerptWithoutEvidence', 'outsideExcerpt'])
    assert all(row['citationOnly'] for row in value)
    assert all(not row[key] for row in value for key in ['emptyPatch','emptyEvidence','foreign','bodyOnly','missingIdentity'])


def test_fresh_text_catalog_contract_omits_redundant_role_fields():
    value = isolated_run_bun(r'''
      import {Value} from 'typebox/value';
      import {learningOutputSchema,assertFreshMemoryProjectOutput} from './packages/continual-learning/extensions/planner-output-schema.ts';
      import {memoryCitationDomain} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const snapshot={entries:[{role:'user',content:'Keep observed behavior.'},{role:'assistant',content:[{type:'toolCall',id:'f',name:'read',arguments:{path:'/project/api.ts'}},{type:'toolCall',id:'b',name:'bash',arguments:{command:'node example.js'}}]},
        {role:'toolResult',toolName:'read',toolCallId:'f',isError:false,content:'export const enabled = true;\nexport const mode = 1;'},
        {role:'toolResult',toolName:'bash',toolCallId:'b',isError:false,content:'observed true'}]};
      const domain=memoryCitationDomain(snapshot,{fileSourcesFromCwd:'/project'}),schema=learningOutputSchema('memory-delta',domain);
      const base={kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h',operations:[],
        newMemories:[{name:'fact.md',kind:'project',classification:'safe',description:'Observed source.',knowledge:{sourceCitations:[{ref:'e2.b0.l1'},{ref:'e3.b0.l1'}],units:[{text:'Observed source and execution.',citationIndexes:[0,1]}]}}]};
      const check=unit=>Value.Check(schema,{...base,newMemories:[{...base.newMemories[0],knowledge:{...base.newMemories[0].knowledge,units:[unit]}}]});
      let missingRejected=false;try{assertFreshMemoryProjectOutput({...base,newMemories:[{...base.newMemories[0],knowledge:{...base.newMemories[0].knowledge,units:[{sourceCitationIndex:0}]}}]})}catch{missingRejected=true}
      console.log(JSON.stringify({fileRefs:domain.fileRefs,valid:Value.Check(schema,base),terminal:check({sourceCitationIndex:1,fileSourceRef:{ref:'e3.b0.l1'}}),missing:check({sourceCitationIndex:0}),emptyFileDomain:Value.Check(learningOutputSchema('memory-delta',{...domain,fileRefs:[]}),base),legacyDomain:Value.Check(learningOutputSchema('memory-delta',{indices:domain.indices,refs:domain.refs}),base),text:check({text:'Observed output.',citationIndexes:[1]}),atomic:check({kind:'declared-api-relation',factory:{ref:'e2.b0.l1'},owner:{ref:'e2.b0.l1'},member:{ref:'e2.b0.l2'}}),missingRejected}));
    ''')
    assert value['fileRefs'] == ['e2.b0.l1', 'e2.b0.l2']
    assert value['valid'] and value['text'] and value['missingRejected']
    assert not any(value[key] for key in ('terminal', 'missing', 'atomic'))
    assert value['emptyFileDomain'] and value['legacyDomain']


def test_file_reference_domain_cli_is_complete_bounded_and_not_an_optional_source_hint():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import extension from './packages/continual-learning/extensions/planner-json-output.ts';
      import {learningPlannerArgs} from './packages/continual-learning/extensions/planner-prompts.ts';
      fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json'),JSON.stringify({plannerStructuredOutput:true}));
      let domain={indices:[0,1],refs:['e0.b0.l1','e1.b0.l1'],fileRefs:['e1.b0.l1']},encoded=JSON.stringify(domain),handler;
      extension({registerFlag:()=>{},getFlag:name=>name==='learning-output-schema'?'memory-delta':name==='learning-citation-domain'?encoded:undefined,getActiveTools:()=>[],on:(name,fn)=>{if(name==='before_provider_request')handler=fn}});
      const event={payload:{messages:[{role:'user',content:'Return JSON'}]}},ctx={model:{api:'openai-completions',id:'qwen3.8-flash'}};
      const valid=handler(event,ctx);const refusals=[];
      for(const bad of [{...domain,fileRefs:['e1.b0.l1','e1.b0.l1']},{...domain,fileRefs:['e2.b0.l1']},{...domain,fileRefs:'e1.b0.l1'},{...domain,untrustedFileRefs:[]}]){
        encoded=JSON.stringify(bad);try{handler(event,ctx);refusals.push(false)}catch{refusals.push(true)}
      }
      for(const bad of ['complete-catalog-overflow','x'.repeat(64001)]){encoded=bad;try{handler(event,ctx);refusals.push(false)}catch{refusals.push(true)}}
      const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:'/project/source.ts'}}]},{role:'toolResult',toolName:'read',toolCallId:'r',isError:false,content:'observed file'}]};
      const args=learningPlannerArgs('memory-delta',snapshot,undefined,undefined,'/project');const at=args.indexOf('--learning-citation-domain');
      const sent=JSON.parse(args[at+1]);
      console.log(JSON.stringify({valid:!!valid,refusals,sent}));
    ''', temp_dirs=('PI_CODING_AGENT_DIR',))
    assert value['valid'] and all(value['refusals'])
    assert value['sent']['fileRefs'] == ['e1.b0.l1']


def test_provider_independent_file_contract_preserves_frozen_entries_and_complete_domain():
    value = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      import {freshMemoryOutputContract,projectFreshMemoryDossier} from './packages/continual-learning/extensions/planner-prompts.ts';
      import {locatedMemoryEvidence,memoryCitationDomain} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const snapshot={entries:[{role:'user',content:'Keep observed source.'},{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:'/project/source.ts'}}]},
        {role:'toolResult',toolName:'read',toolCallId:'r',isError:false,content:'export const observed = true;'},
        {role:'toolResult',toolName:'bash',toolCallId:'b',isError:false,content:'observed true'}]};
      const dossier={kind:'incremental-learning-dossier',taskSlice:snapshot},before=JSON.stringify(dossier);
      const shown=projectFreshMemoryDossier(dossier,'/project'),repair=freshMemoryOutputContract(snapshot,'/project'),domain=memoryCitationDomain(snapshot,{fileSourcesFromCwd:'/project'});
      const hash=v=>createHash('sha256').update(JSON.stringify(v)).digest('hex');
      const huge=structuredClone(snapshot);huge.entries[2].content=Array.from({length:6000},(_,i)=>'source '+i).join('\n');const completeLarge=freshMemoryOutputContract(huge,'/project');const largeComplete=completeLarge.schema.$defs.memorySourceReference.enum.length===memoryCitationDomain(huge,{fileSourcesFromCwd:'/project'}).refs.length;
      console.log(JSON.stringify({same:JSON.stringify(shown.memoryOutputContract)===JSON.stringify(repair),enum:repair.schema.$defs.memorySourceReference.enum,
        domainMatches:repair.domainDigest===hash(domain),fileMatches:repair.fileDomainDigest===hash(domain.fileRefs),
        frozenUnchanged:before===JSON.stringify(dossier),originalEntriesPreserved:JSON.stringify(shown.taskSlice.entries)===JSON.stringify(locatedMemoryEvidence(snapshot,{declarationViews:true}).entries),largeComplete}));
    ''')
    assert value['same'] and value['domainMatches'] and value['fileMatches']
    assert 'e2.b0.l1' in value['enum'] and 'e0.b0.l1' in value['enum']
    assert value['frozenUnchanged'] and value['originalEntriesPreserved'] and value['largeComplete']


def test_file_contract_task_data_is_independent_of_optional_cli_argument_budget():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {freshMemoryOutputContract,learningPlannerArgs} from './packages/continual-learning/extensions/planner-prompts.ts';
      import {memoryCitationDomain} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json'),JSON.stringify({plannerStructuredOutput:true}));
      const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:'/project/source.ts',limit:3000}}]},
        {role:'toolResult',toolName:'read',toolCallId:'r',isError:false,content:Array.from({length:2600},()=> 'x=1;').join('\n')}]};
      const domain=memoryCitationDomain(snapshot,{fileSourcesFromCwd:'/project'}),contract=freshMemoryOutputContract(snapshot,'/project');
      const args=learningPlannerArgs('memory-delta',snapshot,undefined,undefined,'/project');
      console.log(JSON.stringify({domainBytes:Buffer.byteLength(JSON.stringify(domain)),enumSize:contract.schema.$defs.memorySourceReference.enum.length,contractBytes:Buffer.byteLength(JSON.stringify(contract)),cli:args[args.indexOf('--learning-citation-domain')+1]}));
    ''', temp_dirs=('PI_CODING_AGENT_DIR',))
    assert value['domainBytes'] > 64000 and 0 < value['contractBytes'] < 64000  # Only redundant machine metadata shrank.
    assert value['enumSize'] == 2600 and value['cli'] == 'complete-catalog-overflow'


def test_file_contract_checks_complete_task_json_bytes_and_refuses_without_trimming():
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      import {MAX_SNAPSHOT_BYTES} from './packages/continual-learning/extensions/consolidation-run.ts';
      const schema=await import('./packages/continual-learning/extensions/planner-output-schema.ts');
      mock.module('./packages/continual-learning/extensions/planner-output-schema.ts',()=>({...schema,learningOutputSchema:()=>({type:'object',properties:{payload:{type:'string',enum:['x'.repeat(MAX_SNAPSHOT_BYTES)]}}})}));
      const {freshMemoryOutputContract}=await import('./packages/continual-learning/extensions/planner-prompts.ts');
      const snapshot={entries:[{role:'user',content:'Observed fact.'}]};let error=null;
      try{freshMemoryOutputContract(snapshot,'/project')}catch(e){error=e.message}
      console.log(JSON.stringify({error,maximumTaskDataBytes:MAX_SNAPSHOT_BYTES}));
    ''')
    assert value['error'] and 'task-data' in value['error']
    assert str(value['maximumTaskDataBytes']) in value['error']


def test_description_schema_bounds_cover_fresh_and_atomic_repair_branches():
    value = isolated_run_bun(r'''
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      const fresh=learningOutputSchema('memory-delta',{indices:[0],refs:['e0.b0.l1']});
      const semantic=learningOutputSchema('memory-semantic-amendment',undefined,['newMemories:0:'+ 'a'.repeat(64)],undefined,[],false,true);
      const retained=learningOutputSchema('memory-retained-amendment',undefined,undefined,undefined,undefined,false,true);
      console.log(JSON.stringify([fresh.properties.newMemories.items.anyOf.find(x=>x.properties.knowledge).properties.description,semantic.properties.replacements.items.properties.description,retained.properties.operations.items.anyOf.find(x=>x.properties.knowledge).properties.description]));
    ''')
    assert all(item['minLength'] == 1 and item['maxLength'] == 120 for item in value)
    assert all('UTF-16' in item['description'] for item in value)
