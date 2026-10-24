from support import isolated_run_bun


def test_mixed_initial_knowledge_copies_source_bytes_with_its_context_and_exact_catalog():
    # Given a parent-audited declaration and separate user applicability evidence,
    # When an initial safe or private record selects source plus explanatory units,
    # Then the parent preserves actual newlines/tabs, both type owners and context.
    # Selecting this generic fixture is not evidence of real-model selection.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {materializeSourceExcerptPlan,assertSourceExcerptBindings} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'mixed-source-')));
      try {
        const text='export interface Pool {\n\tflush(): void;\n}\nexport function makePool(): Pool;\n';
        const file=path.join(root,'index.d.ts');fs.writeFileSync(file,text);
        const snapshot={entries:[{message:{role:'assistant',content:[{type:'toolCall',id:'a',name:'learning_read',arguments:{path:file}}]}},
          {message:{role:'toolResult',toolName:'learning_read',toolCallId:'a',isError:false,details:{readOnlyMaintenanceAudit:true,sourcePath:file,sourceSha256:sha256Digest(text)},content:[{type:'text',text}]}},
          {message:{role:'user',content:'Use the inspected Pool contract when maintaining batch exports. Runtime behavior has not been verified.'}}]};
        const grant=s=>({evidenceDigest:sha256Digest(JSON.stringify(s)),entryDigests:s.entries.slice(0,2).map(e=>sha256Digest(JSON.stringify(e)))});
        const knowledge={sourceCitations:[{ref:'e1.b0.l1',endRef:'e1.b0.l4'},{ref:'e2.b0.l1'}],units:[
          {sourceCitationIndex:0},{text:'Why: This is the inspected declared contract for batch exports.',citationIndexes:[0,1]},
          {text:'How to apply: Revisit it when maintaining batch exports. Runtime behavior is unverified.',citationIndexes:[1]}]};
        const raw={operations:[],newMemories:[{name:'pool.md',kind:'project',classification:'private',description:'The inspected Pool type declares flush.',knowledge}]};
        const run={manifest:{cwd:root}},out=await materializeSourceExcerptPlan(run,raw,snapshot,grant(snapshot));
        await assertSourceExcerptBindings(run);
        const safe=await materializeSourceExcerptPlan({manifest:{cwd:root}},{...raw,newMemories:[{...raw.newMemories[0],classification:'safe'}]},snapshot,grant(snapshot));
        const stated=await materializeSourceExcerptPlan({manifest:{cwd:root}},{...raw,newMemories:[{...raw.newMemories[0],classification:'safe',knowledge:{sourceCitations:[{ref:'e2.b0.l1'}],units:[{text:'Use the inspected Pool contract for batch exports; runtime behavior is unverified.',citationIndexes:[0]}]}}]},snapshot);
        const rejected={};
        const mutations={missingGrant:(s,p,g)=>undefined,forgedGrant:(s,p,g)=>({...g,evidenceDigest:'0'.repeat(64)}),
          userAsSource:(s,p,g)=>{p.newMemories[0].knowledge.units[0].sourceCitationIndex=1;return g},
          ambiguous:(s,p,g)=>{s.entries.splice(2,0,structuredClone(s.entries[1]));return grant(s)},
          stale:(s,p,g)=>{fs.writeFileSync(file,'changed');return g},
          escaped:(s,p,g)=>{s.entries[1].message.content[0].text=text.replaceAll('\n','\\n');return grant(s)},
          classification:(s,p,g)=>{p.newMemories[0].classification='public';return g},preference:(s,p,g)=>{p.newMemories[0].kind='preference';return g},
          content:(s,p,g)=>{p.newMemories[0].content='detached content';return g},evidence:(s,p,g)=>{p.newMemories[0].evidence=[{ref:'e2.b0.l1'}];return g},
          otherMetadata:(s,p,g)=>{p.newMemories[0].type='feedback';return g},
          sensitiveText:(s,p,g)=>{p.newMemories[0].classification='safe';p.newMemories[0].knowledge.units[1].text='api_key: abcdefghijklmnop';return g},
          classificationArray:(s,p,g)=>{p.newMemories[0].classification=['safe'];return g},
          mixedUnit:(s,p,g)=>{p.newMemories[0].knowledge.units[0].text='invented';return g},
          booleanIndex:(s,p,g)=>{p.newMemories[0].knowledge.units[0].sourceCitationIndex=true;return g},
          outOfRange:(s,p,g)=>{p.newMemories[0].knowledge.units[0].sourceCitationIndex=2;return g},
          noUnits:(s,p,g)=>{p.newMemories[0].knowledge.units=[];return g},
          tooMany:(s,p,g)=>{p.newMemories[0].knowledge.sourceCitations=Array(9).fill({ref:'e1.b0.l1'});return g},
          tooManyUnits:(s,p,g)=>{p.newMemories[0].knowledge.units=Array(33).fill({sourceCitationIndex:0});return g},
          oversize:(s,p,g)=>{p.newMemories[0].knowledge.units[1].text='x'.repeat(64001);return g},
          descriptionLines:(s,p,g)=>{p.newMemories[0].description='claim\ntype: feedback';return g}};
        for(const [name,mutate] of Object.entries(mutations)){
          fs.writeFileSync(file,text);const s=structuredClone(snapshot),p=structuredClone(raw),g=mutate(s,p,grant(s));
          try{await materializeSourceExcerptPlan({manifest:{cwd:root}},p,s,g);rejected[name]=false}catch{rejected[name]=true}
        }
        fs.writeFileSync(file,text+'// drift');
        let drift=false;try{await assertSourceExcerptBindings(run)}catch{drift=true}
        console.log(JSON.stringify({out,safe,stated,text,rejected,drift,rawUnchanged:raw.newMemories[0].content===undefined}));
      }finally{fs.rmSync(root,{recursive:true,force:true})}
    ''')
    record = value['out']['newMemories'][0]
    assert value['text'].rstrip('\n') in record['content']
    assert '\\n\\t' not in record['content']
    assert 'Why: This is the inspected declared contract' in record['content']
    assert 'Runtime behavior is unverified.' in record['content']
    assert 'knowledge' not in record and len(record['evidence']) == 2
    assert record['classification'] == 'private' and value['rawUnchanged'] and value['drift']
    assert value['safe']['newMemories'][0]['content'] == record['content']
    assert value['safe']['newMemories'][0]['classification'] == 'safe'
    assert value['stated']['newMemories'][0]['content'].endswith('runtime behavior is unverified.')
    assert len(value['stated']['newMemories'][0]['evidence']) == 1
    assert all(value['rejected'].values()), value['rejected']


def test_parent_audit_excerpt_requires_complete_grant_and_current_source_hash():
    # Given an original parent audit, When selecting its exact source span,
    # Then extract bytes only with the complete binding; this grants no approval.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {materializeSourceExcerptPlan,assertSourceExcerptBindings} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'audit-excerpt-')));
      try {
        const file=path.join(root,'index.d.ts'),text='export type Limiter = Pick<Limit, "clearQueue" | "onIdle">;\n';fs.writeFileSync(file,text);
        const snapshot={entries:[{message:{role:'assistant',content:[{type:'toolCall',id:'audit',name:'learning_read',arguments:{path:file}}]}},
          {message:{role:'toolResult',toolName:'learning_read',toolCallId:'audit',isError:false,details:{readOnlyMaintenanceAudit:true,sourcePath:file,sourceSha256:sha256Digest(text)},content:[{type:'text',text}]}}]};
        const grant=s=>({evidenceDigest:sha256Digest(JSON.stringify(s)),entryDigests:s.entries.map(e=>sha256Digest(JSON.stringify(e)))});
        const raw={operations:[],newMemories:[{name:'contract.md',kind:'project',classification:'private',sourceExcerpt:{ref:'e1.b0.l1'},evidence:[{ref:'e1.b0.l1'}]}]};
        const run={manifest:{cwd:root}},out=await materializeSourceExcerptPlan(run,raw,snapshot,grant(snapshot));
        const mutations={noGrant:(s,g)=>undefined,wrongDigest:(s,g)=>({...g,evidenceDigest:'0'.repeat(64)}),
          missingCall:(s,g)=>({...g,entryDigests:g.entryDigests.slice(1)}),missingResult:(s,g)=>({...g,entryDigests:g.entryDigests.slice(0,1)}),
          duplicate:(s,g)=>({...g,entryDigests:[...g.entryDigests,g.entryDigests[0]]}),
          foreignEntry:(s,g)=>({...g,entryDigests:[...g.entryDigests,'0'.repeat(64)]}),
          wrongHash:(s,g)=>{s.entries[1].message.details.sourceSha256='0'.repeat(64);return grant(s)},
          wrongPath:(s,g)=>{s.entries[1].message.details.sourcePath=file+'.other';return grant(s)},
          failed:(s,g)=>{s.entries[1].message.isError=true;return grant(s)},
          unmarked:(s,g)=>{s.entries[1].message.details.readOnlyMaintenanceAudit=false;return grant(s)},
          memory:(s,g)=>{s.entries[0].message.content[0].arguments.path=path.join(root,'.memory','entry.md');s.entries[1].message.details.sourcePath=path.join(root,'.memory','entry.md');return grant(s)},
          duplicateResult:(s,g)=>{s.entries.push(structuredClone(s.entries[1]));return grant(s)}};
        const rejected={};for(const [name,mutate] of Object.entries(mutations)){const s=structuredClone(snapshot),g=mutate(s,grant(s));
          try{await materializeSourceExcerptPlan({manifest:{cwd:root}},raw,s,g);rejected[name]=false}catch{rejected[name]=true}}
        await assertSourceExcerptBindings(run);fs.writeFileSync(file,text+'// drift');let drift=false;try{await assertSourceExcerptBindings(run)}catch{drift=true}
        console.log(JSON.stringify({out,rejected,drift,text}));
      }finally{fs.rmSync(root,{recursive:true,force:true})}
    ''')
    assert value['text'].strip() in value['out']['newMemories'][0]['content']
    assert all(value['rejected'].values()), value
    assert value['drift']


def test_parent_source_excerpt_copies_original_bytes_and_keeps_all_existing_gates():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {materializeSourceExcerptPlan,assertSourceExcerptBindings} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const dir=fs.mkdtempSync(path.join(os.tmpdir(),'source-excerpt-'));try{
        const quote='export function sample(): (() => Promise<string>) & {clearQueue(): void};';
        const source=path.join(dir,'index.d.ts');fs.writeFileSync(source,quote+'\n');
        const run={manifest:{cwd:dir,runDir:dir}};
        const snapshot={contextEnabled:true,entries:[{role:'assistant',content:[{type:'toolCall',id:'read-source',name:'read',arguments:{path:source}}]},
          {role:'toolResult',toolName:'read',toolCallId:'read-source',isError:false,content:[{type:'text',text:quote}]}]};
        const item={name:'sample-contract.md',kind:'project',classification:'private',sourceExcerpt:{ref:'e1.b0.l1'},evidence:[{ref:'e1.b0.l1'}]};
        const raw={operations:[],newMemories:[item]};
        const plan=await materializeSourceExcerptPlan(run,raw,snapshot);await assertSourceExcerptBindings(run);
        fs.writeFileSync(source,quote+'\n// changed');let changed=false;try{await assertSourceExcerptBindings(run)}catch{changed=true}
        console.log(JSON.stringify({rawUnchanged:raw.newMemories[0].content===undefined,plan,quote,changed}));
      }finally{fs.rmSync(dir,{recursive:true,force:true})}
    ''')
    item=value['plan']['newMemories'][0]
    assert value['rawUnchanged'] and value['changed']
    assert item['classification']=='private' and item['name']=='sample-contract.md'
    assert item['content'].startswith('---\nname: ')
    assert '\ntype: project\n---\n' in item['content']
    assert value['quote'] in item['content']
    assert 'Observed source excerpt from index.d.ts' in item['content']
    assert '; text cues: sample' in item['content'].split('\n---\n', 1)[0]
    assert 'sourceExcerpt' not in item
    assert item['evidence']==[{'ref':'e1.b0.l1'}]


def test_source_excerpt_rejects_unobserved_stale_unsafe_or_uncovered_claims():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {materializeSourceExcerptPlan,assertSourceExcerptBindings} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const dir=fs.mkdtempSync(path.join(os.tmpdir(),'source-excerpt-negative-'));try{
        const quote='export type Result = (() => Promise<string>) & {clear(): void};';
        const source=path.join(dir,'index.d.ts');fs.writeFileSync(source,quote+'\n');
        const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:source}}]},
          {role:'toolResult',toolName:'read',toolCallId:'r',isError:false,content:[{type:'text',text:quote+'\nother'}]}]};
        const raw={operations:[],newMemories:[{name:'contract.md',kind:'project',classification:'private',sourceExcerpt:{ref:'e1.b0.l1'},evidence:[{ref:'e1.b0.l1'}]}]};
        const mutations={
          user:(s,p)=>s.entries[1].role='user',
          assistant:(s,p)=>s.entries[1].role='assistant',
          failed:(s,p)=>s.entries[1].isError=true,
          missingCall:(s,p)=>s.entries[0].content=[],
          duplicateCall:(s,p)=>s.entries[0].content.push(structuredClone(s.entries[0].content[0])),
          wrongTool:(s,p)=>s.entries[0].content[0].name='bash',
          futureCall:(s,p)=>{s.entries.push(s.entries[0]);s.entries[0]={role:'user',content:[]}},
          outside:(s,p)=>s.entries[0].content[0].arguments.path=path.join(dir,'../index.d.ts'),
          memory:(s,p)=>s.entries[0].content[0].arguments.path=path.join(dir,'.memory','entry.md'),
          uppercaseAgent:(s,p)=>{fs.mkdirSync(path.join(dir,'.PI'));fs.writeFileSync(path.join(dir,'.PI','entry.md'),quote);s.entries[0].content[0].arguments.path=path.join(dir,'.PI','entry.md')},
          hiddenAgent:(s,p)=>s.entries[0].content[0].arguments.path=path.join(dir,'.pi','entry.md'),
          uncovered:(s,p)=>p.newMemories[0].evidence=[{ref:'e1.b0.l2'}],
          mixedContent:(s,p)=>p.newMemories[0].content='model paraphrase',
          safe:(s,p)=>p.newMemories[0].classification='safe',
          preference:(s,p)=>p.newMemories[0].kind='preference',
          extraRefField:(s,p)=>p.newMemories[0].sourceExcerpt.quote=quote,
          symlink:(s,p)=>{fs.symlinkSync(source,path.join(dir,'linked'));s.entries[0].content[0].arguments.path=path.join(dir,'linked')},
          stale:(s,p)=>fs.writeFileSync(source,'different bytes'),
        };
        const rejected={};for(const [name,mutate] of Object.entries(mutations)){
          fs.writeFileSync(source,quote+'\n');const s=structuredClone(snapshot),p=structuredClone(raw);mutate(s,p);
          try{await materializeSourceExcerptPlan({manifest:{cwd:dir}},p,s);rejected[name]=false}catch{rejected[name]=true}
        }
        fs.writeFileSync(source,quote+'\n');const run={manifest:{cwd:dir}};await materializeSourceExcerptPlan(run,raw,snapshot);
        fs.chmodSync(source,0o600);let modeRejected=false;try{await assertSourceExcerptBindings(run)}catch{modeRejected=true}
        const prose={operations:[],newMemories:[{name:'normal.md',content:'unchanged'}]};
        const unchanged=await materializeSourceExcerptPlan({manifest:{cwd:dir}},prose,{})===prose;
        console.log(JSON.stringify({rejected,modeRejected,unchanged}));
      }finally{fs.rmSync(dir,{recursive:true,force:true})}
    ''')
    assert all(value['rejected'].values()), value
    assert value['modeRejected'] and value['unchanged']


def test_source_excerpt_schema_is_opt_in_and_keeps_legacy_prose_contract():
    value = isolated_run_bun(r'''
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      const schema=learningOutputSchema('memory-delta',{indices:[1],refs:['e1.b0.l1']});
      import {Value} from 'typebox/value';
      const item={name:'contract.md',kind:'project',classification:'private',sourceExcerpt:{ref:'e1.b0.l1'},evidence:[{ref:'e1.b0.l1'}]};
      const plan={kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'x',operations:[],newMemories:[item]};
      const mixed={name:'contract.md',kind:'project',classification:'private',description:'An inspected contract.',
        knowledge:{sourceCitations:[{ref:'e1.b0.l1'}],units:[{sourceCitationIndex:0},{text:'Why: declared contract.',citationIndexes:[0]}]}};
      const check=x=>Value.Check(schema,{...plan,newMemories:[x]});
      console.log(JSON.stringify({items:schema.properties.newMemories.items,defs:schema.$defs,
        valid:Value.Check(schema,plan),outside:Value.Check(schema,{...plan,newMemories:[{...item,sourceExcerpt:{ref:'e1.b0.l2'}}]}),
        mixed:check(mixed),safeMixed:check({...mixed,classification:'safe'}),detached:check({...mixed,content:'body'}),
        boolIndex:check({...mixed,knowledge:{...mixed.knowledge,units:[{sourceCitationIndex:true}]}}),
        mixedUnit:check({...mixed,knowledge:{...mixed.knowledge,units:[{sourceCitationIndex:0,text:'other'}]}}),
        retainedBranchCount:learningOutputSchema('memory-retained-amendment').properties.newMemories.items.anyOf.length}));
    ''')
    prose, excerpt, mixed = value['items']['anyOf']
    assert 'content' in prose['required'] and 'sourceExcerpt' not in prose['properties']
    assert prose['properties']['kind']['enum'] == ['preference']
    assert excerpt['properties']['kind']['const']=='project'
    assert excerpt['properties']['classification']['const']=='private'
    assert excerpt['properties']['sourceExcerpt']['properties']['ref']=={'$ref': '#/$defs/memorySourceReference'}
    assert excerpt['properties']['sourceExcerpt']['properties']['endRef']==excerpt['properties']['sourceExcerpt']['properties']['ref']
    assert value['defs']['memorySourceReference']=={'type': 'string', 'enum': ['e1.b0.l1']}
    assert value['valid'] and not value['outside']
    assert 'sourceExcerpt' in excerpt['required'] and 'content' not in excerpt['properties']
    assert excerpt['additionalProperties'] is False
    assert value['mixed'] and value['safeMixed']
    assert not any(value[key] for key in ('detached', 'boolIndex', 'mixedUnit'))
    assert value['retainedBranchCount'] == 2
    assert mixed['properties']['classification']['enum'] == ['safe', 'private']
    assert mixed['properties']['kind']['const'] == 'project'
    assert mixed['required'] == ['name', 'kind', 'classification', 'description', 'knowledge']
    assert mixed['additionalProperties'] is False
    assert mixed['properties']['knowledge']['properties']['units']['items']['anyOf'][1] == {
        'type': 'object', 'properties': {'sourceCitationIndex': {'type': 'integer', 'minimum': 0, 'maximum': 7}},
        'required': ['sourceCitationIndex'], 'additionalProperties': False,
    }


def test_source_excerpt_expands_normally_and_rolls_back_on_post_review_source_drift():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {execFileSync} from 'node:child_process';
      import {createConsolidationRun,releaseConsolidationRun,applyConsolidationPlan} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {expandCitedIncrementalMemoryPlan} from './packages/continual-learning/extensions/inject-memory.ts';
      import {materializeSourceExcerptPlan,assertSourceExcerptBindings} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'excerpt-transaction-')));
      process.env.PI_CODING_AGENT_DIR=path.join(root,'agent');const repo=path.join(root,'project');fs.mkdirSync(repo);execFileSync('git',['init','-q',repo]);
      const source=path.join(repo,'contract.ts'),quote='export type Result = (() => Promise<string>) & {clear(): void};';fs.writeFileSync(source,quote+'\n');
      const entries=[{message:{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:'contract.ts'}}]}},
        {message:{role:'toolResult',toolName:'read',toolCallId:'r',isError:false,content:[{type:'text',text:quote}]}}];
      const run=await createConsolidationRun({cwd:repo,sessionManager:{getBranch:()=>entries,buildContextEntries:()=>entries}},repo,false);
      try{
        const snapshot=JSON.parse(fs.readFileSync(run.paths.snapshotFile,'utf8'));
        const m=run.manifest,raw={kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:m.runId,scopeKey:m.scopeKey,scopeDigest:m.scopeDigest,artifactHash:m.snapshotDigest,snapshotDigest:m.snapshotDigest,operations:[],newMemories:[{name:'contract.md',kind:'project',classification:'private',sourceExcerpt:{ref:'e1.b0.l1'},evidence:[{ref:'e1.b0.l1'}]}]};
        const materialized=await materializeSourceExcerptPlan(run,raw,snapshot);
        const expanded=await expandCitedIncrementalMemoryPlan(run,[],materialized);await assertSourceExcerptBindings(run);
        if(!m.publicDir)throw Error("Public project root not configured");
        let observedWrite=false,noPublicDuringWrite=false,rejected=false;
        try{await applyConsolidationPlan(run,expanded,()=>true,async()=>{
          observedWrite=fs.existsSync(path.join(m.harnessDir,'contract.md'));
          noPublicDuringWrite=!fs.existsSync(path.join(m.publicDir,'contract.md'));
          fs.writeFileSync(source,quote+'\n// changed after review');await assertSourceExcerptBindings(run);
        })}catch{rejected=true}
        console.log(JSON.stringify({expanded:expanded.newMemories[0],observedWrite,noPublicDuringWrite,rejected,rolledBack:!fs.existsSync(path.join(m.harnessDir,'contract.md')),noPublicCopy:!m.publicDir||!fs.existsSync(path.join(m.publicDir,'contract.md'))}));
      }finally{await releaseConsolidationRun(run);fs.rmSync(root,{recursive:true,force:true})}
    ''')
    assert value['expanded']['classification']=='private'
    assert value['expanded']['content'].startswith('---\nname: ')
    assert value['noPublicDuringWrite']
    assert value['observedWrite'] and value['rejected'] and value['rolledBack'] and value['noPublicCopy']


def test_exact_successful_edit_additions_can_supply_source_without_paraphrasing_or_inventing_completion():
    # The actual retained patch is replayed in a disposable file. This proves
    # extraction/provenance only; every semantic and mutation gate still follows.
    value=isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {materializeSourceExcerptPlan,assertSourceExcerptBindings} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-quoted-description-distillation.json').json();
      const snapshot=structuredClone(f.evidence),entries=snapshot.entries;
      const msg=x=>x.message??x,result=msg(entries[22]);
      const call=entries.flatMap(x=>Array.isArray(msg(x).content)?msg(x).content:[]).find(c=>c.id===result.toolCallId);
      const lines=result.details.patch.split('\n'),start=lines.findIndex(x=>x.startsWith('+\tWait for')),end=lines.findIndex(x=>x.startsWith('+\tonIdle:'));
      const quote=lines.slice(start,end+1).map(x=>x.slice(1)).join('\n');
      const dir=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'edit-excerpt-')));try{
        const file=path.join(dir,'index.d.ts');call.arguments.path=file;fs.writeFileSync(file,quote+'\n');
        const raw={operations:[],newMemories:[{name:'observed-contract.md',kind:'project',classification:'private',sourceExcerpt:{ref:`e22.b0.p${start+1}`,endRef:`e22.b0.p${end+1}`},evidence:[{ref:`e22.b0.p${start+1}`,endRef:`e22.b0.p${end+1}`}]}]};
        const run={manifest:{cwd:dir}},plan=await materializeSourceExcerptPlan(run,raw,snapshot);await assertSourceExcerptBindings(run);
        const mutations={failed:s=>msg(s.entries[22]).isError=true,wrongTool:s=>msg(s.entries[22]).toolName='bash',
          missingPatch:s=>delete msg(s.entries[22]).details.patch,
          noAppliedText:s=>s.entries.flatMap(x=>Array.isArray(msg(x).content)?msg(x).content:[]).find(c=>c.id===result.toolCallId).arguments.edits=[{oldText:'old',newText:'other'}],
          removal:s=>msg(s.entries[22]).details.patch=msg(s.entries[22]).details.patch.replace('+\tonIdle:','-\tonIdle:')};
        const rejected={};for(const [name,mutate] of Object.entries(mutations)){
          const s=structuredClone(snapshot);mutate(s);try{await materializeSourceExcerptPlan({manifest:{cwd:dir}},raw,s);rejected[name]=false}catch{rejected[name]=true}
        }
        fs.writeFileSync(file,'reverted source');let reverted=false;try{await assertSourceExcerptBindings(run)}catch{reverted=true}
        console.log(JSON.stringify({plan,quote,rejected,reverted}));
      }finally{fs.rmSync(dir,{recursive:true,force:true})}
    ''')
    assert value['quote'] in value['plan']['newMemories'][0]['content']
    assert '+\tonIdle:' not in value['plan']['newMemories'][0]['content']
    assert value['plan']['newMemories'][0]['classification']=='private'
    assert all(value['rejected'].values()) and value['reverted']


def test_source_excerpt_retrieval_cues_are_literal_bounded_and_preserve_full_body():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {materializeSourceExcerptPlan} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'excerpt-cues-')),out=[];
      const cases={duplicates:'export function sample(): void;\nexport function sample(): void;',
        bounded:'export type First = string;\nexport interface Second {}\nexport function third(): void;\nexport const fourth = 1;',
        comments:'// export function ignored(): void;\nexport function actual(): void;',
        blockComment:'/*\nexport function ghost(): void;\n*/\nexport function real(): void;',
        template:'const text = `\nexport function ghost(): void;\n`;',
        unsupported:'def inspect():\n  return 1',unicode:'export function café(): void;',
        long:'export function '+ 'x'.repeat(61) +'(): void;'};
      for(const [name,quote] of Object.entries(cases)){
        const relative=name==='long'?'nested/'.repeat(22)+'index.d.ts':name+'.ts',source=path.join(root,relative);
        fs.mkdirSync(path.dirname(source),{recursive:true});fs.writeFileSync(source,quote);
        const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'source',name:'read',arguments:{path:source}}]},
          {role:'toolResult',toolName:'read',toolCallId:'source',isError:false,content:[{type:'text',text:quote}]}]};
        const citation={ref:'e1.b0.l1',endRef:'e1.b0.l'+quote.split('\n').length};
        const plan=await materializeSourceExcerptPlan({manifest:{cwd:root}}, {operations:[],newMemories:[{name:name+'.md',kind:'project',classification:'private',sourceExcerpt:citation,evidence:[citation]}]},snapshot);
        const content=plan.newMemories[0].content,description=JSON.parse(content.split('\n').find(line=>line.startsWith('description: ')).slice(13));
        out.push({name,description,bodyPreserved:content.includes(quote),evidence:plan.newMemories[0].evidence});
      }
      console.log(JSON.stringify(out));fs.rmSync(root,{recursive:true,force:true});
    ''')
    rows = {row['name']: row for row in value}
    assert all(row['bodyPreserved'] and len(row['description']) <= 120 and row['evidence'] for row in value)
    assert rows['duplicates']['description'].endswith('text cues: sample')
    assert rows['bounded']['description'].endswith('text cues: First, Second, third')
    assert rows['comments']['description'].endswith('text cues: actual')
    for name in ('unsupported', 'unicode', 'long', 'blockComment', 'template'):
        assert 'text cues:' not in rows[name]['description']
    assert rows['long']['description'].endswith('index.d.ts')


def test_partial_comment_or_template_excerpt_cues_claim_only_the_exact_quoted_text():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {materializeSourceExcerptPlan} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'partial-cues-')),quote='export function ghost(): void;',out=[];
      for(const [name,text] of Object.entries({comment:'/*\n'+quote+'\n*/',template:'const text = `\n'+quote+'\n`;'})){
        const file=path.join(root,name+'.ts');fs.writeFileSync(file,text);
        const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:file}}]},
          {role:'toolResult',toolName:'read',toolCallId:'r',isError:false,content:[{type:'text',text}]}]};
        const ref={ref:'e1.b0.l2'};
        const plan=await materializeSourceExcerptPlan({manifest:{cwd:root}},{operations:[],newMemories:[{name:name+'.md',kind:'project',classification:'private',sourceExcerpt:ref,evidence:[ref]}]},snapshot);
        out.push(plan.newMemories[0]);
      }
      console.log(JSON.stringify({out,quote}));fs.rmSync(root,{recursive:true,force:true});
    ''')
    for entry in value['out']:
        frontmatter = entry['content'].split('\n---\n', 1)[0]
        assert '; text cues: ghost' in frontmatter
        assert 'identifiers:' not in frontmatter and 'declarations:' not in frontmatter
        assert value['quote'] in entry['content']
        assert entry['evidence'] == [{'ref': 'e1.b0.l2'}]
        assert entry['classification'] == 'private'
