from support import isolated_run_bun


def test_memory_schema_constrains_delta_and_amendment_without_selecting_facts() -> None:
    value = isolated_run_bun(r'''
      import {Value} from 'typebox/value';
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      const delta=learningOutputSchema('memory-delta'),amendment=learningOutputSchema('memory-amendment');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'h',snapshotDigest:'h'};
      const rewrite={name:'existing.md',kind:'rewrite',classification:'private',content:'Candidate, not truth.',evidence:[{ref:'e2.b0.l1',endRef:'e2.b0.l2'}]};
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
      const sparse={kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:'parent-id',content:'Candidate',evidence:[{ref:'e2.b0.l1'}]}]};
      console.log(JSON.stringify({valid:valid.map(v=>Value.Check(delta,v)),invalid:invalid.map(v=>Value.Check(delta,v)),sparse:Value.Check(amendment,sparse),missingEvidence:Value.Check(amendment,{...sparse,replacements:[{candidateId:'parent-id',content:'Candidate'}]}),unknown:learningOutputSchema('unknown')}));
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
      const amendment={kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:id,content:'Candidate',evidence:[{ref:'e0.b0.l1'}]}],operations:[]};
      const schema=learningOutputSchema('memory-combined-amendment',{indices:[0],refs:['e0.b0.l1']},[id]);const emptySchema=learningOutputSchema('memory-combined-amendment',undefined,[]);
      fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json'),JSON.stringify({plannerStructuredOutput:true}));let encoded=JSON.stringify([id]),handler;
      extension({registerFlag:()=>{},getFlag:name=>name==='learning-output-schema'?'memory-combined-amendment':name==='learning-candidate-ids'?encoded:undefined,getActiveTools:()=>[],on:(name,fn)=>{if(name==='before_provider_request')handler=fn}});
      const payload={messages:[{role:'user',content:'Return JSON'}]};const ctx={model:{api:'openai-completions',id:'qwen3.8-flash'}};const wire=handler({payload},ctx);
      const refused=[];for(const input of [JSON.stringify([id,id]),JSON.stringify(['foreign']),JSON.stringify({id}),'{', 'complete-candidates-overflow','x'.repeat(64001)]){encoded=input;try{handler({payload},ctx);refused.push(false)}catch{refused.push(true)}}
      const unsupported=handler({payload},{model:{api:'openai-completions',id:'unknown'}});
      console.log(JSON.stringify({valid:Value.Check(schema,amendment),foreign:Value.Check(schema,{...amendment,replacements:[{...amendment.replacements[0],candidateId:'foreign'}]}),newNames:Value.Check(schema,{...amendment,newMemories:[]}),emptyValid:Value.Check(emptySchema,{...amendment,replacements:[]}),emptyRejectsPatch:!Value.Check(emptySchema,amendment),emptyItem:emptySchema.properties.replacements.items.properties.candidateId,wire,refused,unsupported,args:learningPlannerArgs('memory-combined-amendment',{entries:[{role:'user',content:'Source'}]},[id]),id}));
    ''', temp_dirs=('PI_CODING_AGENT_DIR',))
    assert value['valid'] and not value['foreign'] and not value['newNames']
    assert value['emptyValid'] and value['emptyRejectsPatch']
    assert value['emptyItem'] == {'type': 'string'}
    assert all(value['refused']) and value.get('unsupported') is None
    assert value['wire']['response_format']['json_schema']['schema']['properties']['replacements']['items']['properties']['candidateId']['enum'] == [value['id']]
    assert '--learning-candidate-ids' in value['args']
