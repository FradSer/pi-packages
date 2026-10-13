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
      const plan={kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'x',operations:[],newMemories:[{name:'project_fact.md',kind:'project',content:'Current source',evidence:[]}]};
      const check=e=>{plan.newMemories[0].evidence=[e];return Value.Check(schema,plan)};
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
      let handler,domain;extension({registerFlag:()=>{},getFlag:name=>name==='learning-output-schema'?'memory-delta':domain,getActiveTools:()=>[],on:(name,fn)=>handler=fn});
      const payload={messages:[]};const ctx={model:{id:'qwen3.8-flash',api:'openai-completions'}};
      const errors=[];for(const v of ['damaged','complete-catalog-overflow','{"indices":[0],"refs":[]}','{"indices":[0],"refs":["e2.b0.l1"]}','{"indices":[0,0],"refs":["e0.b0.l1"]}','{"indices":[],"refs":"bad"}']){domain=v;try{handler({payload},ctx);errors.push(false)}catch{errors.push(true)}}
      domain='complete-catalog-overflow';const unsupported=handler({payload},{model:{id:'unknown',api:'openai-completions'}});
      const caller=handler({payload:{...payload,response_format:{type:'caller'}}},ctx);
      domain='{"indices":[],"refs":[]}';const request=handler({payload},ctx);
      const schema=request.response_format.json_schema.schema;
      const empty={kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'x',operations:[],newMemories:[]};
      const proposal={name:'p.md',kind:'project',content:'Unsupported',evidence:[{ref:'e0.b0.l1'}]};
      console.log(JSON.stringify({errors,unsupported,caller,empty:Value.Check(schema,empty),invented:Value.Check(schema,{...empty,newMemories:[proposal]})}));
    ''', temp_dirs=('PI_CODING_AGENT_DIR',))
    assert all(result['errors'])
    assert result.get('unsupported') is None and result.get('caller') is None
    assert result['empty'] and not result['invented']


def test_complete_domain_requires_catalog_references_instead_of_free_coordinates_or_quotes() -> None:
    value = isolated_run_bun(r'''
      import {Value} from 'typebox/value';
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      const domain={indices:[0],refs:['e0.b0.l1','e0.b0.l2']};
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'x'};
      const base={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[{name:'p.md',kind:'project',content:'Unverified candidate',evidence:[]}]};
      const values=[{ref:'e0.b0.l1'},{ref:'e0.b0.l1',endRef:'e0.b0.l2'},
        {index:0,quote:'Verbatim but freely generated'},
        {index:0,lines:{block:0,start:999,end:999}},
        {index:0,lines:{block:0,start:1,end:2}},
        {ref:'e0.b0.l999'},{ref:'e0.b0.l1',quote:'Mixed identity'}];
      const check=(schema,e)=>Value.Check(schema,{...base,newMemories:[{...base.newMemories[0],evidence:[e]}]});
      console.log(JSON.stringify({strict:values.map(e=>check(learningOutputSchema('memory-delta',domain),e)),legacy:check(learningOutputSchema('memory-delta'),values[2]),amendment:values.map(e=>Value.Check(learningOutputSchema('memory-amendment',domain),{kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:'id',content:'Candidate',evidence:[e]}]}))}));
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
      const base={kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'x',operations:[],newMemories:[{name:'fact.md',kind:'project',content:'Claim',evidence:[{ref:'e0.b0.l2'}]}]};
      console.log(JSON.stringify({domain,blankLabels:lines.slice(1,3).some(x=>x.ref!==undefined),blankChunkLabels:chunks.filter(c=>!c.text.trim()).some(c=>c.ref!==undefined),reconstructed:lines.map(l=>l.text).join('\n')===snapshot.entries[0].content&&chunks.map(c=>c.text).join('')===long,unchanged:before===JSON.stringify(snapshot),full:full.operations[0].evidence[0].quote,legacy:legacy.operations[0].evidence[0].quote,emptyRejected,schemaRejectsBlank:!Value.Check(learningOutputSchema('memory-delta',domain),base)}));
    ''')
    assert value['domain']['indices'] == [0, 2]
    assert value['domain']['refs'][:2] == ['e0.b0.l1', 'e0.b0.l4']
    assert not value['blankLabels'] and not value['blankChunkLabels']
    assert value['reconstructed'] and value['unchanged'] and value['emptyRejected']
    assert value['schemaRejectsBlank']
    assert value['full'] == 'First condition.\n\n \t\nLast exception.'
    assert value['legacy'] == '\n \t\nLast exception.'
