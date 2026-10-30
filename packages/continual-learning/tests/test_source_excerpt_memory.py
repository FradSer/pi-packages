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


def test_fresh_relation_schema_replaces_source_units_and_keeps_private_legacy_excerpt():
    value = isolated_run_bun(r'''
      import {learningOutputSchema,assertFreshMemoryProjectOutput} from './packages/continual-learning/extensions/planner-output-schema.ts';
      import {Value} from 'typebox/value';
      const schema=learningOutputSchema('memory-delta',{indices:[1],refs:['e1.b0.l1'],fileRefs:['e1.b0.l1']});
      const item={name:'contract.md',kind:'project',classification:'private',sourceExcerpt:{ref:'e1.b0.l1'},evidence:[{ref:'e1.b0.l1'}]};
      const plan={kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'x',operations:[],newMemories:[item]};
      const relation={kind:'declared-api-relation',factory:{ref:'e1.b0.l1'},owner:{ref:'e1.b0.l1'},member:{ref:'e1.b0.l1'}};
      const mixed={name:'contract.md',kind:'project',classification:'private',description:'Observed declaration.',knowledge:{sourceCitations:[{ref:'e1.b0.l1'}],units:[relation,{text:'Why: declared contract.',citationIndexes:[0]}]}};
      const check=x=>Value.Check(schema,{...plan,newMemories:[x]});
      let freshExcerptRejected=false;try{assertFreshMemoryProjectOutput(plan)}catch{freshExcerptRejected=true}
      console.log(JSON.stringify({freshExcerpt:check(item),freshExcerptRejected,mixed:check(mixed),safe:check({...mixed,classification:'safe'}),
        missing:check({...mixed,knowledge:{...mixed.knowledge,units:[{...relation,owner:undefined}]}}),
        old:check({...mixed,knowledge:{...mixed.knowledge,units:[{sourceCitationIndex:0,fileSourceRef:{ref:'e1.b0.l1'}}]}}),
        legacy:Value.Check(learningOutputSchema('memory-retained-amendment'),plan)}));
    ''')
    assert not value['mixed'] and not value['safe']
    assert value['legacy'] and value['freshExcerptRejected']
    assert not value['freshExcerpt'] and not value['missing'] and not value['old']


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


def test_selected_complete_declaration_is_retained_after_original_units_only_for_used_catalog_refs():
    # Given selected complete declarations used as evidence for prose,
    # When a new project proposal is materialized,
    # Then retain neutral source data without choosing more references or rewriting prose.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {materializeSourceExcerptPlan} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'retain-declaration-')));
      try {
        const text='export function makeBatch(size: number): Batch;\nexport function openBatch(): Batch;\nexport function unrelated(): Other;';
        const file=path.join(root,'api.d.ts');fs.writeFileSync(file,text);
        const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:file}}]},
          {role:'toolResult',toolName:'read',toolCallId:'r',isError:false,content:text}]};
        const prose='The observed factories return Batch; runtime behavior is unverified.';
        const knowledge={sourceCitations:[{ref:'e1.b0.l2'},{ref:'e1.b0.l1'},{ref:'e1.b0.l3'}],units:[{text:prose,citationIndexes:[1,0]}]};
        const raw={operations:[],newMemories:[{name:'batch.md',kind:'project',classification:'safe',description:'Observed declared Batch return.',knowledge}]};
        const baseline=await materializeSourceExcerptPlan({manifest:{cwd:root}},raw,snapshot);
        const before=JSON.stringify(raw),out=await materializeSourceExcerptPlan({manifest:{cwd:root}},raw,snapshot,undefined,{retainSelectedDeclarations:true});
        const explicit=structuredClone(raw);explicit.newMemories[0].knowledge.units.unshift({sourceCitationIndex:0,fileSourceRef:{ref:'e1.b0.l2'}});
        let oldRejected=false;try{await materializeSourceExcerptPlan({manifest:{cwd:root}},explicit,snapshot,undefined,{retainSelectedDeclarations:true})}catch{oldRejected=true}
        const overflow=structuredClone(raw);overflow.newMemories[0].knowledge.units=Array.from({length:32},()=>({text:prose,citationIndexes:[1]}));
        let bounded=false;try{await materializeSourceExcerptPlan({manifest:{cwd:root}},overflow,snapshot,undefined,{retainSelectedDeclarations:true})}catch{bounded=true}
        console.log(JSON.stringify({body:out.newMemories[0].content,evidence:out.newMemories[0].evidence,oldRejected,rawUnchanged:before===JSON.stringify(raw),defaultBody:baseline.newMemories[0].content,bounded,prose}));
      }finally{fs.rmSync(root,{recursive:true,force:true})}
    ''')
    body = value['body']
    assert body.index(value['prose']) < body.index('export function openBatch') < body.index('export function makeBatch')
    assert 'Observed source excerpt from "api.d.ts":' in body
    assert 'export function unrelated' not in body
    assert value['defaultBody'].endswith(value['prose']) and 'Observed source excerpt' not in value['defaultBody']
    assert len(value['evidence']) == 3 and value['rawUnchanged'] and value['bounded']
    assert value['oldRejected']


def test_selected_declaration_retention_keeps_provenance_syntax_and_size_boundaries():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {MAX_MEMORY_BYTES} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {materializeSourceExcerptPlan,assertSourceExcerptBindings} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'retain-declaration-boundaries-')));
      try {
        const declaration='export function createRecord(): RecordValue;';
        const evaluate=async({suffix='.d.ts',observed=declaration,current=observed,selection={ref:'e1.b0.l1'},failed=false,duplicate=false,explicit=false,stale=false,link=false}={})=>{
          const file=path.join(root,'api'+suffix);fs.writeFileSync(file,current);
          const target=link?path.join(root,'linked'+suffix):file;if(link){try{fs.unlinkSync(target)}catch{}fs.symlinkSync(file,target)}
          const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:target}}]},
            {role:'toolResult',toolName:'read',toolCallId:'r',isError:failed,content:observed}]};
          const catalog=duplicate?[selection,{...selection,endRef:selection.ref}]:[selection];
          const units=explicit?[{sourceCitationIndex:0,fileSourceRef:selection},{text:'Observed return contract; not a runtime test.',citationIndexes:[1]}]:[{text:'Observed return contract; not a runtime test.',citationIndexes:duplicate?[0,1]:[0]}];
          const raw={operations:[],newMemories:[{name:'record.md',kind:'project',classification:'private',description:'Observed contract.',knowledge:{sourceCitations:catalog,units}}]};
          try{const run={manifest:{cwd:root}},out=await materializeSourceExcerptPlan(run,raw,snapshot,undefined,{retainSelectedDeclarations:true});
            if(stale){fs.writeFileSync(file,current+'\n// changed');await assertSourceExcerptBindings(run)}
            return {body:out.newMemories[0].content,rejected:false};
          }catch{return {rejected:true}}
        };
        const aliases=await evaluate({duplicate:true}),explicit=await evaluate({duplicate:true,explicit:true});
        const variants={mts:await evaluate({suffix:'.d.mts'}),cts:await evaluate({suffix:'.d.cts'}),
          ordinary:await evaluate({suffix:'.ts'}),failed:await evaluate({failed:true}),
          extraStatement:await evaluate({observed:declaration+' export const extra: number;'}),
          callback:await evaluate({observed:'export interface Host { createRecord(): RecordValue; }'}),
          stringLiteral:await evaluate({observed:'export type Text = "export function createRecord(): RecordValue;";'}),
          partial:await evaluate({observed:'export function createRecord(\n  value: string\n): RecordValue;',selection:{ref:'e1.b0.l3'}}),
          nestedRegion:await evaluate({current:'declare namespace Nested {\n'+declaration+'\n}'}),
          changed:await evaluate({current:'export function different(): RecordValue;'}),
          duplicateSource:await evaluate({observed:declaration+'\n'+declaration}),
          symlink:await evaluate({link:true}),race:await evaluate({stale:true})};
        const file=path.join(root,'large.d.ts');fs.writeFileSync(file,declaration);
        const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'b',name:'read',arguments:{path:file}}]},
          {role:'toolResult',toolName:'read',toolCallId:'b',isError:false,content:declaration}]};
        const raw={operations:[],newMemories:[{name:'large.md',kind:'project',classification:'private',description:'Observed contract.',knowledge:{sourceCitations:[{ref:'e1.b0.l1'}],units:[{text:'Observed.',citationIndexes:[0]}]}}]};
        const base=await materializeSourceExcerptPlan({manifest:{cwd:root}},raw,snapshot);raw.newMemories[0].knowledge.units[0].text+='x'.repeat(MAX_MEMORY_BYTES-Buffer.byteLength(base.newMemories[0].content)-1);
        let bodyBound=false;try{await materializeSourceExcerptPlan({manifest:{cwd:root}},raw,snapshot,undefined,{retainSelectedDeclarations:true})}catch{bodyBound=true}
        console.log(JSON.stringify({aliases,explicit,variants,bodyBound,declaration}));
      }finally{fs.rmSync(root,{recursive:true,force:true})}
    ''')
    assert value['aliases']['body'].count(value['declaration']) == 1
    assert value['explicit']['rejected']
    for key in ('mts', 'cts'):
        assert value['declaration'] in value['variants'][key]['body']
    for key in ('ordinary', 'failed', 'extraStatement', 'callback', 'stringLiteral', 'partial'):
        assert 'Observed source excerpt' not in value['variants'][key].get('body', '')
    assert value['variants']['duplicateSource']['body'].count(value['declaration']) == 1
    for key in ('nestedRegion', 'changed', 'symlink', 'race'):
        assert value['variants'][key]['rejected'], (key, value['variants'][key])
    assert value['bodyBound']


def test_retained_declaration_qualifies_the_selected_occurrence_not_an_equal_outer_elsewhere():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {materializeSourceExcerptPlan} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'selected-occurrence-')));
      try {
        const declaration='export function makeUnit(): Unit;',file=path.join(root,'api.d.ts');
        const cases={comment:{text:'/*\n'+declaration+'\n*/\n'+declaration,offset:2},namespace:{text:'declare namespace Nested {\n'+declaration+'\n}\n'+declaration,offset:2},outer:{text:'/*\n'+declaration+'\n*/\n'+declaration,offset:4}};
        const result={};for(const [name,c] of Object.entries(cases)){
          fs.writeFileSync(file,c.text);const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:file,offset:c.offset,limit:1}}]},
            {role:'toolResult',toolName:'read',toolCallId:'r',isError:false,content:declaration}]};
          const raw={operations:[],newMemories:[{name:'unit.md',kind:'project',classification:'private',description:'Observed signature.',knowledge:{sourceCitations:[{ref:'e1.b0.l1'}],units:[{text:'Observed return type.',citationIndexes:[0]}]}}]};
          try{const out=await materializeSourceExcerptPlan({manifest:{cwd:root}},raw,snapshot,undefined,{retainSelectedDeclarations:true});result[name]={retained:out.newMemories[0].content.includes('```text\n'+declaration)}}catch{result[name]={rejected:true}}
        }console.log(JSON.stringify(result));
      }finally{fs.rmSync(root,{recursive:true,force:true})}
    ''')
    assert not value['comment'].get('retained') and not value['namespace'].get('retained')
    assert value['outer'].get('retained')


def test_initial_selected_api_relationship_requires_model_selected_dependency_roles():
    # Given the original user names a wrapper/member topic and the proposal uses
    # its explicitly mapped local call source, a partial relation must not silently pass.
    # A single repair that explicitly selects and uses every role may keep ordinary
    # text units; the parent must not reveal a new exclusive-format error afterward.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {materializeSourceExcerptPlan} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'relation-closure-')));
      try {
        const js='export default function allocatePool(size) { return {flush() {}}; }\nexport function batchWorker(options) {\n  const pool = allocatePool(options);\n  return () => pool.flush();\n}\n';
        const dts='export type Pool = {\n  flush(): void;\n};\nexport default function allocatePool(size: number): Pool;\nexport function batchWorker(options: number): () => void;\nexport interface Unrelated { extra(): void; }\n';
        const pkg=JSON.stringify({type:'module',exports:{types:'./api.d.ts',default:'./api.js'}});
        for(const [name,text] of [['api.js',js],['api.d.ts',dts],['package.json',pkg]])fs.writeFileSync(path.join(root,name),text);
        const call=(id,name)=>({type:'toolCall',id,name:'read',arguments:{path:path.join(root,name),offset:1,limit:1000}});
        const result=(id,text)=>({role:'toolResult',toolName:'read',toolCallId:id,isError:false,content:text});
        const snapshot={entries:[{role:'user',content:'Inspect batchWorker and its flush relationship to the internal pool; preserve observation limits.'},
          {role:'assistant',content:[call('p','package.json'),call('j','api.js'),call('d','api.d.ts')]},result('p',pkg),result('j',js),result('d',dts)]};
        const knowledge={sourceCitations:[{ref:'e4.b0.l5'},{ref:'e3.b0.l3'},{ref:'e0.b0.l1'}],units:[{text:'Observed wrapper declaration.',citationIndexes:[0]},
          {text:'batchWorker creates an internal allocatePool result. The wrapper does not expose flush; this is not a runtime guarantee.',citationIndexes:[0,1,2]}]};
        const raw={operations:[],newMemories:[{name:'batch.md',kind:'project',classification:'private',description:'Observed wrapper interface.',knowledge}]};
        const before=JSON.stringify(raw);let reason=null,projectionDigest=null;const retainedRun={manifest:{cwd:root}};
        try{await materializeSourceExcerptPlan(retainedRun,raw,snapshot,undefined,{retainSelectedDeclarations:true})}catch(e){reason=e.message;projectionDigest=e.snapshotProjectionDigest}
        const dropped=[];for(const index of [0,1]){const repair=structuredClone(raw);repair.newMemories[0].knowledge.sourceCitations[index]={ref:'e0.b0.l1'};let rejected=false;try{await materializeSourceExcerptPlan(retainedRun,repair,snapshot,undefined,{retainSelectedDeclarations:true})}catch{rejected=true}dropped.push(rejected)}
        const abstained=await materializeSourceExcerptPlan(retainedRun,{operations:[],newMemories:[]},snapshot,undefined,{retainSelectedDeclarations:true});
        const legacyRaw=structuredClone(raw);legacyRaw.newMemories[0].knowledge.units[0]={sourceCitationIndex:0};const legacy=await materializeSourceExcerptPlan({manifest:{cwd:root}},legacyRaw,snapshot);
        const corrected=structuredClone(raw);corrected.newMemories[0].knowledge.sourceCitations.push({ref:'e4.b0.l4'},{ref:'e4.b0.l1',endRef:'e4.b0.l3'},{ref:'e4.b0.l2'});
        corrected.newMemories[0].knowledge.units[1].citationIndexes.push(3,4,5);
        const downgraded=structuredClone(raw);downgraded.newMemories[0]={name:'batch.md',kind:'preference',classification:'private',description:'Observed wrapper interface.',content:'batchWorker does not expose flush.'};let downgradeRejected=false;try{await materializeSourceExcerptPlan(retainedRun,downgraded,snapshot,undefined,{retainSelectedDeclarations:true})}catch{downgradeRejected=true}
        const changedSnapshot=structuredClone(snapshot);changedSnapshot.entries[0].content+=' changed';let changedRejected=false;try{await materializeSourceExcerptPlan(retainedRun,corrected,changedSnapshot,undefined,{retainSelectedDeclarations:true})}catch{changedRejected=true}
        const out=await materializeSourceExcerptPlan(retainedRun,corrected,snapshot,undefined,{retainSelectedDeclarations:true});
        // Keep every selected quote and function line, but move the member to a
        // different current owner; substring presence cannot authenticate a role.
        fs.writeFileSync(path.join(root,'api.d.ts'),dts.replace('export type Pool = {','/* export type Pool = { */ export type Pool = {}; export type Other = {'));
        let raceRejected=false;try{await materializeSourceExcerptPlan({manifest:{cwd:root}},corrected,snapshot,undefined,{retainSelectedDeclarations:true})}catch{raceRejected=true}
        console.log(JSON.stringify({reason,projectionDigest,dropped,abstained,downgradeRejected,changedRejected,raceRejected,rawUnchanged:JSON.stringify(raw)===before,legacyBody:legacy.newMemories[0].content,body:out.newMemories[0].content,evidence:out.newMemories[0].evidence,originalText:knowledge.units[1].text}));
      }finally{fs.rmSync(root,{recursive:true,force:true})}
    ''')
    assert value['reason'] and 'relation' in value['reason'].lower()
    assert value['dropped'] == [True, True]
    assert len(value['projectionDigest']) == 64 and 'Snapshot projection digest:' in value['reason']
    assert value['abstained']['newMemories'] == []
    assert value['downgradeRejected'] and value['changedRejected']
    assert all(role in value['reason'] for role in ('factory', 'owner', 'member'))
    assert all(ref in value['reason'] for ref in ('e4.b0.l4', 'e4.b0.l1', 'e4.b0.l2'))
    assert value['rawUnchanged'] and value['raceRejected'] and value['legacyBody'].endswith(value['originalText'])
    assert value['originalText'] in value['body']
    assert 'export default function allocatePool(size: number): Pool;' in value['body']
    assert '`Pool` declares `flush`' in value['body']
    assert 'Unrelated' not in value['body'] and len(value['evidence']) == 6


def test_relation_closure_requires_provable_local_bindings_module_pair_and_visible_topic():
    value = isolated_run_bun(r'''
      import {selectedMemoryRelationClosures} from './packages/continual-learning/extensions/memory-relation-closure.ts';
      const js='export default function allocatePool(size) { return {flush() {}}; }\nexport function batchWorker(options) {\n  const pool = allocatePool(options);\n  return () => pool.flush();\n}\n';
      const dts='export type Pool = {\n  flush(): void;\n};\nexport default function allocatePool(size: number): Pool;\nexport function batchWorker(options: number): () => void;\n';
      const pkg={type:'module',exports:{types:'./api.d.ts',default:'./api.js'}};
      const base=()=>({snapshot:{entries:[{role:'user',content:'Inspect batchWorker and its flush relationship to the internal pool.'},
        {role:'assistant',content:[['p','package.json'],['j','api.js'],['d','api.d.ts']].map(([id,name])=>({type:'toolCall',id,name:'read',arguments:{path:'/project/'+name,offset:1,limit:1000}}))},
        {role:'toolResult',toolName:'read',toolCallId:'p',isError:false,content:JSON.stringify(pkg)},
        {role:'toolResult',toolName:'read',toolCallId:'j',isError:false,content:js},
        {role:'toolResult',toolName:'read',toolCallId:'d',isError:false,content:dts}]},
        knowledge:{sourceCitations:[{ref:'e4.b0.l5'},{ref:'e3.b0.l3'},{ref:'e0.b0.l1'}],units:[{text:'Observed wrapper declaration.',citationIndexes:[0]},
          {text:'batchWorker creates an internal allocatePool result; the wrapper does not expose flush.',citationIndexes:[0,1,2]}]}});
      const run=(v)=>{try{return {relations:selectedMemoryRelationClosures(v.snapshot,v.knowledge,'/project'),error:null}}catch(e){return {error:e.message}}};
      const original=base(),partial=run(original),negative={};
      const arrayUser=base();arrayUser.snapshot.entries[0].content=[{type:'text',text:arrayUser.snapshot.entries[0].content},{type:'image',data:'ignored'}];
      const arrayPartial=run(arrayUser);
      const crossSentence=base();crossSentence.knowledge.units[1].text='batchWorker creates an internal allocatePool result. The returned wrapper does not expose flush.';const crossSentencePartial=run(crossSentence);
      const propertyTopic=base();propertyTopic.snapshot.entries[0].content='Inspect batchWorker.flush behavior.';propertyTopic.knowledge.units[1].text='batchWorker.flush is absent from the wrapper.';const propertyPartial=run(propertyTopic);
      const possessive=base();possessive.knowledge.units[1].text="The pool's interface belongs to batchWorker and allocatePool; the wrapper's interface does not expose flush.";const possessivePartial=run(possessive);
      const contractions=base();contractions.knowledge.units[1].text="It isn't a batchWorker flush interface; don't confuse allocatePool with its wrapper.";const contractionPartial=run(contractions);
      const mutations={
        unrelated:(v)=>v.snapshot.entries[0].content='Inspect caching behavior only.',
        splitUnits:(v)=>{v.knowledge.units[1].text='batchWorker creates an allocatePool result.';v.knowledge.units.push({text:'The wrapper does not expose flush.',citationIndexes:[0,1,2]})},
        quotedMemberSplitUnits:(v)=>{v.knowledge.units[1].text='batchWorker creates an allocatePool result. The glossary says "flush".';v.knowledge.units.push({text:'The wrapper does not expose flush.',citationIndexes:[0,1,2]})},
        separateTopic:(v)=>{v.snapshot.entries[0].content='Inspect batchWorker startup only. Separately, flush appears in an unrelated glossary.';v.knowledge.units[1].text='batchWorker invokes allocatePool for startup. The glossary uses the unrelated word flush.'},
        nonTextUser:(v)=>v.snapshot.entries[0].content=[{type:'thinking',text:'batchWorker flush'}],
        quotedArrayUser:(v)=>v.snapshot.entries[0].content=[{type:'text',text:'\"batchWorker flush\"'}],
        quotedUser:(v)=>v.snapshot.entries[0].content='"batchWorker flush"',
        fencedUser:(v)=>v.snapshot.entries[0].content='```text\nbatchWorker flush\n```',
        unclosedFencedUser:(v)=>v.snapshot.entries[0].content='```text\nbatchWorker flush',
        quotedBody:(v)=>v.knowledge.units[1].text='"batchWorker flush allocatePool"',
        singleQuotedBody:(v)=>v.knowledge.units[1].text="'batchWorker flush allocatePool'",
        curlyQuotedBody:(v)=>v.knowledge.units[1].text='‘batchWorker flush allocatePool’',
        blockquotedBody:(v)=>v.knowledge.units[1].text='> batchWorker flush allocatePool',
        fencedBody:(v)=>v.knowledge.units[1].text='```text\nbatchWorker flush allocatePool\n```',
        unclosedFencedBody:(v)=>v.knowledge.units[1].text='```text\nbatchWorker flush allocatePool',
        joinedDifferentMember:(v)=>v.knowledge.units[1].text='batchWorker creates allocatePool with flush\u200dExtra.',
        inlineCodeOnly:(v)=>v.knowledge.units[1].text='`batchWorker` `allocatePool` `flush`',
        attachedUserData:(v)=>v.snapshot.entries[0].content='<file name=\"quoted.txt\">batchWorker flush</file>',
        descriptionOnly:(v)=>{v.knowledge.description='batchWorker flush';v.knowledge.units[1].text='Observed interface.'},
        noWrapperSelection:(v)=>v.knowledge.sourceCitations[0]={ref:'e0.b0.l1'},
        differentMember:(v)=>v.knowledge.units[1].text='batchWorker wraps allocatePool and an unrelated extra member.',
        wrongCallSpan:(v)=>v.knowledge.sourceCitations[1]={ref:'e3.b0.l1'},
        importedFactory:(v)=>v.snapshot.entries[3].content=js.replace(js.split('\n')[0],"import allocatePool from './pool.js';"),
        parameter:(v)=>v.snapshot.entries[3].content=js.replace('batchWorker(options)','batchWorker(allocatePool)'),
        destructuredParameter:(v)=>v.snapshot.entries[3].content=js.replace('batchWorker(options)','batchWorker({allocatePool})'),
        localConst:(v)=>v.snapshot.entries[3].content=js.replace('  return () => pool.flush();','  const allocatePool = other;\n  return () => pool.flush();'),
        hoistedVar:(v)=>v.snapshot.entries[3].content=js.replace('  return () => pool.flush();','  if (false) {var allocatePool;}\n  return () => pool.flush();'),
        localFunction:(v)=>v.snapshot.entries[3].content=js.replace('  return () => pool.flush();','  function allocatePool() {}\n  return () => pool.flush();'),
        localClass:(v)=>v.snapshot.entries[3].content=js.replace('  return () => pool.flush();','  class allocatePool {}\n  return () => pool.flush();'),
        catchBinding:(v)=>v.snapshot.entries[3].content=js.replace('  return () => pool.flush();','  try {} catch (allocatePool) {}\n  return () => pool.flush();'),
        reassigned:(v)=>v.snapshot.entries[3].content=js+'allocatePool = other;\n',
        updated:(v)=>v.snapshot.entries[3].content=js+'allocatePool++;\n',
        forOfWrite:(v)=>v.snapshot.entries[3].content=js+'for (allocatePool of things) {}\n',
        forInWrite:(v)=>v.snapshot.entries[3].content=js+'for (allocatePool in things) {}\n',
        globalEval:(v)=>v.snapshot.entries[3].content=js+"eval('allocatePool = other');\n",
        dynamic:(v)=>v.snapshot.entries[3].content=js.replace('allocatePool(options)','globalThis.allocatePool(options)'),
        optional:(v)=>v.snapshot.entries[3].content=js.replace('allocatePool(options)','allocatePool?.(options)'),
        alias:(v)=>v.snapshot.entries[3].content=js.replace('const pool = allocatePool(options)','const create = allocatePool; const pool = create(options)'),
        nestedCallback:(v)=>v.snapshot.entries[3].content=js.replace('const pool = allocatePool(options)','const pool = () => allocatePool(options)'),
        eval:(v)=>v.snapshot.entries[3].content=js.replace('const pool = allocatePool(options)','const pool = allocatePool(eval(options))'),
        ambiguousExports:(v)=>v.snapshot.entries[2].content=JSON.stringify({...pkg,exports:{...pkg.exports,import:'./other.js'}}),
        wrongModule:(v)=>v.snapshot.entries[2].content=JSON.stringify({...pkg,exports:{...pkg.exports,default:'./other.js'}}),
        missingModuleMap:(v)=>v.snapshot.entries[2].content=JSON.stringify({type:'module'}),
        genericShadow:(v)=>v.snapshot.entries[4].content=dts.replace('allocatePool(size: number)','allocatePool<Pool>(size: number)'),
        qualifiedOwner:(v)=>v.snapshot.entries[4].content=dts.replace('number): Pool;','number): Names.Pool;'),
        callbackOwner:(v)=>v.snapshot.entries[4].content=dts.replace('number): Pool;','number): (() => Pool);'),
        incompleteRead:(v)=>v.snapshot.entries[1].content[1].arguments.offset=2,
        failedRead:(v)=>v.snapshot.entries[3].isError=true,
      };
      for(const [name,mutate] of Object.entries(mutations)){const v=base();mutate(v);negative[name]=run(v)}
      const complete=base();complete.knowledge.sourceCitations.push({ref:'e4.b0.l4'},{ref:'e4.b0.l1',endRef:'e4.b0.l3'},{ref:'e4.b0.l2'});complete.knowledge.units[1].citationIndexes.push(3,4,5);
      const selected=run(complete),unused=structuredClone(complete);unused.knowledge.units[1].citationIndexes=[0,1,2];
      console.log(JSON.stringify({partial,arrayPartial,crossSentencePartial,propertyPartial,possessivePartial,contractionPartial,negative,selected,unused:run(unused)}));
    ''')
    assert value['partial']['error'] and value['arrayPartial']['error'] and value['crossSentencePartial']['error'] and value['propertyPartial']['error'] and len(value['selected']['relations']) == 1
    assert value['unused']['error'] and 'factory' in value['unused']['error']
    assert value['possessivePartial']['error'] and value['contractionPartial']['error']
    for name, result in value['negative'].items():
        assert result.get('relations') == [] and result['error'] is None, (name, result)


def test_relation_closure_binds_partial_owner_roles_with_existing_budgets_and_read_aliases():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {MAX_MEMORY_BYTES} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {materializeSourceExcerptPlan} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'relation-role-bounds-')));
      try {
        const js='export default function allocatePool(size) { return {flush() {}}; }\nexport function batchWorker(options) {\n const pool=allocatePool(options); const second=allocatePool(options);\n return () => pool.flush();\n}\n';
        const dts='export type Pool = {\n /* '+('observed '.repeat(3))+'*/\n flush(): void;\n};\nexport default function allocatePool(size: number): Pool;\nexport function batchWorker(options: number): () => void;\n';
        const pkg=JSON.stringify({type:'module',exports:{types:'./api.d.ts',default:'./api.js'}});
        for(const [name,text] of [['api.js',js],['api.d.ts',dts],['package.json',pkg]])fs.writeFileSync(path.join(root,name),text);
        const call=(id,file)=>({type:'toolCall',id,name:'read',arguments:{path:path.join(root,file),offset:1,limit:1000}}),result=(id,text)=>({role:'toolResult',toolName:'read',toolCallId:id,isError:false,content:text});
        const snapshot={entries:[{role:'user',content:[{type:'text',text:'Inspect batchWorker and its flush relationship to the internal pool.'}]},
          {role:'assistant',content:[call('p','package.json'),call('j','api.js'),call('d','api.d.ts')]},result('p',pkg),result('j',js),result('d',dts),
          {role:'assistant',content:[call('d2','api.d.ts')]},result('d2',dts)]};
        const knowledge={sourceCitations:[{ref:'e4.b0.l6'},{ref:'e3.b0.l3'},{ref:'e0.b0.l1'},{ref:'e6.b0.l5'},{ref:'e6.b0.l1'},{ref:'e6.b0.l3'}],units:[{kind:'declared-api-relation',factory:{ref:'e6.b0.l5'},owner:{ref:'e6.b0.l1',endRef:'e6.b0.l4'},member:{ref:'e6.b0.l3'}},
          {text:'batchWorker creates an internal allocatePool result; the wrapper does not expose flush.',citationIndexes:[0,1,2,3,4,5]}]};
        const raw={operations:[],newMemories:[{name:'pool.md',kind:'project',classification:'private',description:'Observed wrapper contract.',knowledge}]};
        const before=JSON.stringify(raw),out=await materializeSourceExcerptPlan({manifest:{cwd:root}},raw,snapshot,undefined,{retainSelectedDeclarations:true});
        const plain=structuredClone(raw);plain.newMemories[0].knowledge.units[0]={text:'Observed wrapper declaration.',citationIndexes:[0]};
        plain.newMemories[0].knowledge.sourceCitations.push({ref:'e0.b0.l1'},{ref:'e0.b0.l1'});
        const plainBefore=JSON.stringify(plain),plainOut=await materializeSourceExcerptPlan({manifest:{cwd:root}},plain,snapshot,undefined,{retainSelectedDeclarations:true});
        const limits={};const reject=async(v)=>{try{await materializeSourceExcerptPlan({manifest:{cwd:root}},v,snapshot,undefined,{retainSelectedDeclarations:true});return false}catch{return true}};
        const aliasRepair=async(reverse=false,mode='same')=>{
          const local=structuredClone(snapshot),run={manifest:{cwd:root}},from=reverse?6:4,to=reverse?4:6;
          if(mode==='changed')local.entries[to].content=dts.replace('flush(): void','flush(): Promise<void>');
          if(mode==='foreign')local.entries[5].content[0].arguments.path=path.join(root,'foreign.d.ts');
          if(mode==='partial')local.entries[to].content=dts+'\n[Showing lines 1-6]';
          if(mode==='error')local.entries[to].isError=true;
          if(mode==='ambiguous')local.entries[5].content.push(structuredClone(local.entries[5].content[0]));
          const draft=structuredClone(raw);draft.newMemories[0].knowledge={sourceCitations:[{ref:`e${from}.b0.l6`},{ref:'e3.b0.l3'},{ref:'e0.b0.l1'}],units:[{text:'batchWorker creates an internal allocatePool result; its wrapper does not expose flush.',citationIndexes:[0,1,2]}]};
          let initialError;try{await materializeSourceExcerptPlan(run,draft,local,undefined,{retainSelectedDeclarations:true})}catch(e){initialError=e.message}
          const fixed=structuredClone(draft);fixed.newMemories[0].knowledge={sourceCitations:[{ref:`e${to}.b0.l6`},{ref:'e3.b0.l3'},{ref:'e0.b0.l1'},{ref:`e${to}.b0.l5`},{ref:`e${to}.b0.l1`},{ref:`e${to}.b0.l3`}],units:[{text:'batchWorker creates an internal allocatePool result; its wrapper does not expose flush.',citationIndexes:[0,1,2,3,4,5]}]};
          if(mode==='unused')fixed.newMemories[0].knowledge.units[0].citationIndexes.pop();
          if(mode==='dropWrapper')fixed.newMemories[0].knowledge.units[0].citationIndexes.shift();
          if(mode==='race')fs.writeFileSync(path.join(root,'api.d.ts'),dts+'\n// changed');
          const bytes=JSON.stringify(fixed);try{const result=await materializeSourceExcerptPlan(run,fixed,local,undefined,{retainSelectedDeclarations:true});return {initialError,error:null,body:result.newMemories[0].content,evidence:result.newMemories[0].evidence,unchanged:bytes===JSON.stringify(fixed)}}catch(e){return {initialError,error:e.message,unchanged:bytes===JSON.stringify(fixed)}}finally{fs.writeFileSync(path.join(root,'api.d.ts'),dts)}
        };
        const switchedAliases={later:await aliasRepair(),earlier:await aliasRepair(true)};
        const rejectedAliases={};for(const mode of ['changed','foreign','partial','error','ambiguous','unused','dropWrapper','race'])rejectedAliases[mode]=await aliasRepair(false,mode);

        const tooManyRefs=structuredClone(plain);tooManyRefs.newMemories[0].knowledge.sourceCitations.push({ref:'e0.b0.l1'});limits.catalog=await reject(tooManyRefs);
        const many=structuredClone(raw);many.newMemories[0].knowledge.units=[knowledge.units[0],...Array.from({length:30},()=>knowledge.units[1])];limits.units=await reject(many);
        const longSnapshot=structuredClone(snapshot),longDts=dts.replace('observed '.repeat(3),'observed '.repeat(350));longSnapshot.entries[4].content=longDts;longSnapshot.entries[6].content=longDts;fs.writeFileSync(path.join(root,'api.d.ts'),longDts);try{await materializeSourceExcerptPlan({manifest:{cwd:root}},raw,longSnapshot,undefined,{retainSelectedDeclarations:true});limits.quote=false}catch{limits.quote=true}fs.writeFileSync(path.join(root,'api.d.ts'),dts);
        const large=structuredClone(raw),legacyLarge=structuredClone(raw);legacyLarge.newMemories[0].knowledge.units[0]={sourceCitationIndex:0};const baseline=await materializeSourceExcerptPlan({manifest:{cwd:root}},legacyLarge,snapshot);
        large.newMemories[0].knowledge.units[1].text+='x'.repeat(MAX_MEMORY_BYTES-Buffer.byteLength(baseline.newMemories[0].content)-1);limits.body=await reject(large);
        console.log(JSON.stringify({switchedAliases,rejectedAliases,body:out.newMemories[0].content,rawUnchanged:before===JSON.stringify(raw),evidence:out.newMemories[0].evidence.length,plainBody:plainOut.newMemories[0].content,plainEvidence:plainOut.newMemories[0].evidence.length,plainUnchanged:plainBefore===JSON.stringify(plain),limits}));
      }finally{fs.rmSync(root,{recursive:true,force:true})}
    ''')
    for alias in value['switchedAliases'].values():
        assert alias['initialError'] and not alias['error'], alias
        assert alias['unchanged'] and len(alias['evidence']) == 6
        assert '`Pool` declares `flush`' in alias['body']
    assert all(row['error'] and row['unchanged'] for row in value['rejectedAliases'].values()), value['rejectedAliases']
    assert value['rawUnchanged'] and value['evidence'] == 7
    assert value['plainUnchanged'] and value['plainEvidence'] == 8
    assert value['plainBody'].count('`Pool` declares `flush`') == 1
    assert 'Observed wrapper declaration.' in value['plainBody']
    assert 'batchWorker creates an internal allocatePool result' in value['plainBody']
    assert value['body'].count('`Pool` declares `flush`') == 1
    assert value['body'].count('export default function allocatePool') == 1
    assert ('observed ' * 10) not in value['body']
    assert all(value['limits'].values()), value['limits']


def test_fresh_file_source_reference_is_not_terminal_evidence_or_a_catalog_repair():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {materializeSourceExcerptPlan} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'file-unit-capability-')));
      try {
        const source='export const enabled = true;\nexport const mode = 1;';fs.writeFileSync(path.join(root,'api.ts'),source);
        const snapshot={entries:[{role:'user',content:'Keep this observation.'},{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:path.join(root,'api.ts')}},{type:'toolCall',id:'b',name:'bash',arguments:{command:'node example.js'}}]},
          {role:'toolResult',toolName:'read',toolCallId:'r',isError:false,content:source},{role:'toolResult',toolName:'bash',toolCallId:'b',isError:false,content:'observed true'}]};
        const base={operations:[],newMemories:[{name:'facts.md',kind:'project',classification:'private',description:'Observed source and execution.',knowledge:{sourceCitations:[{ref:'e2.b0.l1'},{ref:'e3.b0.l1'},{ref:'e2.b0.l2'}],units:[{sourceCitationIndex:0,fileSourceRef:{ref:'e2.b0.l1'}},{text:'The execution observed true.',citationIndexes:[1]}]}}]};
        const run=async(raw,fresh=true)=>{try{const plan=await materializeSourceExcerptPlan({manifest:{cwd:root}},raw,snapshot,undefined,fresh?{retainSelectedDeclarations:true}:{});return {plan,error:null}}catch(e){return {error:e.message}}};
        const original=JSON.stringify(base),valid=await run(base),bad={};
        const sameLine=structuredClone(base);sameLine.newMemories[0].knowledge.units[0].fileSourceRef.endRef='e2.b0.l1';const sameLineResult=await run(sameLine);
        for(const [label,unit] of Object.entries({missing:{sourceCitationIndex:0},terminal:{sourceCitationIndex:1,fileSourceRef:{ref:'e3.b0.l1'}},wrongSlot:{sourceCitationIndex:1,fileSourceRef:{ref:'e2.b0.l1'}},unselected:{sourceCitationIndex:0,fileSourceRef:{ref:'e2.b0.l2'}},crossBlock:{sourceCitationIndex:0,fileSourceRef:{ref:'e2.b0.l1',endRef:'e3.b0.l1'}}})){
          const raw=structuredClone(base);raw.newMemories[0].knowledge.units[0]=unit;bad[label]=await run(raw);
        }
        const subset=structuredClone(base);subset.newMemories[0].knowledge.sourceCitations[0].endRef='e2.b0.l2';bad.subset=await run(subset);
        const legacy=structuredClone(base);delete legacy.newMemories[0].knowledge.units[0].fileSourceRef;
        const legacyResult=await run(legacy,false);fs.unlinkSync(path.join(root,'api.ts'));const absent=await run(base);
        console.log(JSON.stringify({valid,sameLineResult,bad,legacyResult,absent,rawUnchanged:original===JSON.stringify(base)}));
      }finally{fs.rmSync(root,{recursive:true,force:true})}
    ''')
    assert value['valid']['error'] and value['legacyResult']['error'] is None and value['sameLineResult']['error']
    assert 'observed true' in value['legacyResult']['plan']['newMemories'][0]['content']
    assert value['rawUnchanged'] and value['absent']['error']
    assert all(result['error'] and 'units[0]' in result['error'] for result in value['bad'].values())


def test_fresh_atomic_declared_relation_normalizes_explicit_roles_and_rejects_foreign_sources():
    # Given complete observed declarations, one fresh relation selects every role.
    # When materialized, citations and copied syntax stay synchronized under all gates.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {materializeSourceExcerptPlan} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'atomic-relation-')));
      try{
        const dts='export interface Pool {\n  flush(): void;\n}\nexport function allocatePool(): Pool;\nexport interface Other { close(): void; }\n';
        fs.writeFileSync(path.join(root,'api.d.ts'),dts);
        const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'d',name:'read',arguments:{path:path.join(root,'api.d.ts'),limit:1000}},{type:'toolCall',id:'b',name:'bash',arguments:{command:'node x.js'}}]},
          {role:'toolResult',toolName:'read',toolCallId:'d',isError:false,content:dts},
          {role:'toolResult',toolName:'bash',toolCallId:'b',isError:false,content:'observed true'}]};
        const relation={kind:'declared-api-relation',factory:{ref:'e1.b0.l4'},owner:{ref:'e1.b0.l1',endRef:'e1.b0.l3'},member:{ref:'e1.b0.l2'}};
        const raw={newMemories:[{name:'api.md',kind:'project',classification:'private',description:'Observed Pool contract.',knowledge:{sourceCitations:[{ref:'e2.b0.l1'}],units:[relation,{text:'Why: inspected contract. How to apply: revisit declarations; execution observed true.',citationIndexes:[0]}]}}],operations:[]};
        const run=async(p=raw,s=snapshot,fresh=true)=>{try{return {plan:await materializeSourceExcerptPlan({manifest:{cwd:root}},p,s,undefined,fresh?{retainSelectedDeclarations:true}:{}),error:null}}catch(e){return {error:e.message}}};
        const before=JSON.stringify(raw),valid=await run(),bad={};
        for(const [label,change] of Object.entries({missing:u=>delete u.owner,terminal:u=>u.owner={ref:'e2.b0.l1'},wrongOwner:u=>u.owner={ref:'e1.b0.l5'},wrongMember:u=>u.member={ref:'e1.b0.l5'},partialOwner:u=>u.owner={ref:'e1.b0.l3'},crossSource:u=>u.member={ref:'e1.b0.l2',endRef:'e2.b0.l2'},oldUnit:u=>{delete u.kind;delete u.factory;delete u.owner;delete u.member;u.sourceCitationIndex=0;u.fileSourceRef={ref:'e2.b0.l1'}}})){
          const p=structuredClone(raw);change(p.newMemories[0].knowledge.units[0]);bad[label]=await run(p);
        }
        const overflow=structuredClone(raw);overflow.newMemories[0].knowledge.units=Array(32).fill(relation);bad.units=await run(overflow);
        const duplicateCatalog=structuredClone(raw);duplicateCatalog.newMemories[0].knowledge.sourceCitations=Array(8).fill({ref:'e2.b0.l1'});bad.catalog=await run(duplicateCatalog);
        const excerpt={operations:[],newMemories:[{name:'legacy.md',kind:'project',classification:'private',sourceExcerpt:relation.owner,evidence:[relation.owner]}]};bad.freshExcerpt=await run(excerpt);const legacyExcerpt=await run(excerpt,snapshot,false);
        const changed=structuredClone(snapshot);changed.entries[1].content=dts.replace('allocatePool(): Pool','allocatePool(): Other');bad.source=await run(raw,changed);
        const ambiguous=structuredClone(snapshot);ambiguous.entries.push(structuredClone(ambiguous.entries[1]));bad.ambiguous=await run(raw,ambiguous);
        const literal=structuredClone(snapshot);literal.entries[1].content=dts.replace('flush()',String.raw`'flush\`instruction'()`);fs.writeFileSync(path.join(root,'api.d.ts'),literal.entries[1].content);bad.literalMember=await run(raw,literal);fs.writeFileSync(path.join(root,'api.d.ts'),dts);
        const legacy=structuredClone(raw);legacy.newMemories[0].knowledge.sourceCitations.push(relation.owner);legacy.newMemories[0].knowledge.units[0]={sourceCitationIndex:1};const legacyResult=await run(legacy,snapshot,false);
        console.log(JSON.stringify({valid,bad,legacyResult,legacyExcerpt,unchanged:JSON.stringify(raw)===before}));
      }finally{fs.rmSync(root,{recursive:true,force:true})}
    ''')
    assert value['valid']['error'] is None, value['valid']
    body=value['valid']['plan']['newMemories'][0]['content']
    assert 'allocatePool(): Pool' in body and 'flush(): void' in body and '`Pool` declares `flush`' in body
    assert len(value['valid']['plan']['newMemories'][0]['evidence']) == 4
    assert all(row['error'] for row in value['bad'].values()), value['bad']
    assert value['legacyResult']['error'] is None and value['legacyExcerpt']['error'] is None and value['unchanged']


def test_real_complete_declaration_relation_uses_owner_identity_without_unrelated_members():
    # Given the complete retained public declaration, owner identity is not its inventory.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import {parse} from '@babel/parser';
      import {materializeSourceExcerptPlan} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const fixture=JSON.parse(fs.readFileSync('packages/continual-learning/tests/fixtures/real-description-body-conflict.json','utf8')).declarationOwnerBridgeCase;
      const text=fixture.sourceText,ast=parse(text,{sourceType:'module',plugins:['typescript']}),rows=ast.program.body;
      const factory=rows.find(n=>n.type==='ExportDefaultDeclaration'),owner=rows.find(n=>n.declaration?.id?.name==='LimitFunction'),member=owner.declaration.typeAnnotation.members.find(n=>n.key?.name==='clearQueue');
      const ref=n=>({ref:`e1.b0.l${n.loc.start.line}`,endRef:`e1.b0.l${n.loc.end.line}`});
      const heading={...owner,loc:{...owner.loc,end:owner.declaration.typeAnnotation.loc.start}};
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'real-owner-identity-')));
      try{
        fs.writeFileSync(path.join(root,'api.d.ts'),text);
        const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:path.join(root,'api.d.ts'),limit:2000}}]}, {role:'toolResult',toolName:'read',toolCallId:'r',isError:false,content:text}]};
        const relation={kind:'declared-api-relation',factory:ref(factory),owner:ref(heading),member:ref(member)};
        const raw={operations:[],newMemories:[{name:'api.md',kind:'project',classification:'private',description:'Observed declared owner.',knowledge:{sourceCitations:[ref(factory)],units:[relation,{text:'Why: observed declaration. How to apply: revisit the declared contract.',citationIndexes:[0]}]}}]};
        const out=await materializeSourceExcerptPlan({manifest:{cwd:root}},raw,snapshot,undefined,{retainSelectedDeclarations:true});
        console.log(JSON.stringify({body:out.newMemories[0].content,evidence:out.newMemories[0].evidence.length,ownerChars:text.slice(owner.start,owner.end).length,headingChars:text.split('\n').slice(heading.loc.start.line-1,heading.loc.end.line).join('\n').length}));
      }finally{fs.rmSync(root,{recursive:true,force:true})}
    ''')
    assert value['ownerChars'] > 2000 and value['headingChars'] < 2000
    assert value['evidence'] == 3
    assert '`pLimit` has the named return type `LimitFunction`' in value['body']
    assert '`LimitFunction` declares `clearQueue`' in value['body']
    assert 'activeCount' not in value['body'] and 'pendingCount' not in value['body']


def test_static_fresh_diagnostics_collect_metadata_quote_and_missing_roles_before_file_reads():
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';
      import {materializeSourceExcerptPlan} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const root='/uncreated-static-diagnostic-project';
      const js='export default function allocatePool(size) { return {flush() {}}; }\nexport function batchWorker(options) {\n const pool=allocatePool(options);\n return () => pool.flush();\n}\n';
      const dts='export type Pool = {\n /* '+ 'observed '.repeat(350)+'*/\n flush(): void;\n};\nexport default function allocatePool(size:number): Pool;\nexport function batchWorker(options:number): () => void;\n';
      const pkg=JSON.stringify({type:'module',exports:{types:'./api.d.ts',default:'./api.js'}});
      const call=(id,name)=>({type:'toolCall',id,name:'read',arguments:{path:root+'/'+name,offset:1,limit:1000}}),result=(id,content)=>({role:'toolResult',toolName:'read',toolCallId:id,isError:false,content});
      const snapshot={entries:[{role:'user',content:'Inspect batchWorker and its flush relationship.'},{role:'assistant',content:[call('p','package.json'),call('j','api.js'),call('d','api.d.ts')]},result('p',pkg),result('j',js),result('d',dts)]};
      const raw={operations:[],newMemories:[{name:'fact.md',kind:'project',classification:'private',description:'x'.repeat(138),knowledge:{sourceCitations:[{ref:'e4.b0.l6'},{ref:'e3.b0.l3'},{ref:'e4.b0.l1',endRef:'e4.b0.l4'}],units:[{text:'batchWorker uses allocatePool; its internal result has the declared flush member.',citationIndexes:[0,1,2]}]}}]};
      const original=JSON.stringify(raw),run={manifest:{cwd:root}};let reads=0;
      const prior={lstat:fs.lstat,open:fs.open,realpath:fs.realpath};for(const key of Object.keys(prior))fs[key]=async()=>{reads++;throw Error('Unexpected current-file read')};
      const check=async p=>{try{await materializeSourceExcerptPlan(run,p,snapshot,undefined,{retainSelectedDeclarations:true});return null}catch(e){return e.message}};
      let all,bounds,utf16,dropped;
      try{all=await check(raw);const many=structuredClone(raw);many.newMemories[0].knowledge.sourceCitations=Array(9).fill({ref:'e0.b0.l1'});many.newMemories[0].knowledge.units=Array(33).fill({text:'Observed.',citationIndexes:[0]});bounds=await check(many);
        const unicode=structuredClone(raw);unicode.newMemories[0].description='😀'.repeat(61);utf16=await check(unicode);
        const removed=structuredClone(raw);removed.newMemories[0].description='Observed role.';removed.newMemories[0].knowledge.sourceCitations=[{ref:'e0.b0.l1'}];removed.newMemories[0].knowledge.units=[{text:'Observed role.',citationIndexes:[0]}];dropped=await check(removed);
      }finally{Object.assign(fs,prior)}
      console.log(JSON.stringify({all,bounds,utf16,dropped,reads,unchanged:JSON.stringify(raw)===original}));
    ''')
    assert 'description' in value['all'] and '138' in value['all'] and 'UTF-16' in value['all']
    assert 'quote-length-out-of-bounds' in value['all'] and '2000' in value['all']
    assert 'factory' in value['all'] and 'e4.b0.l5' in value['all']
    assert 'sourceCitations' in value['bounds'] and '1..8' in value['bounds']
    assert 'units' in value['bounds'] and '1..32' in value['bounds']
    assert '122' in value['utf16'] and 'UTF-16' in value['utf16']
    assert 'factory' in value['dropped']  # Parent closure obligation survives diagnostic failure.
    assert 'initiating-wrapper' in value['dropped']  # Already selected wrapper witness survives an invalid draft.
    assert 'sourceSpan' not in value['dropped']  # Internal character boundaries never become producer diagnostics.
    assert value['reads'] == 0 and value['unchanged']


def test_semantic_project_source_continuity_preserves_prior_header_and_retained_roles():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {materializeSourceExcerptPlan,materializeSemanticProjectKnowledge,selectedProjectSourceObligations} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'semantic-source-')));
      try {
        const js='export default function allocatePool(size) { return {flush() {}}; }\nexport function batchWorker(options) {\n const pool=allocatePool(options);\n return () => pool.flush();\n}\n';
        const dts='export type Pool = {\n flush(): void;\n};\nexport default function allocatePool(size:number): Pool;\nexport function batchWorker(options:number): () => void;\n';
        const pkg=JSON.stringify({type:'module',exports:{types:'./api.d.ts',default:'./api.js'}});
        for(const [file,text] of Object.entries({'api.js':js,'api.d.ts':dts,'package.json':pkg}))fs.writeFileSync(path.join(root,file),text);
        const call=(id,name)=>({type:'toolCall',id,name:'read',arguments:{path:root+'/'+name,offset:1,limit:1000}}),result=(id,content)=>({role:'toolResult',toolName:'read',toolCallId:id,isError:false,content});
        const snapshot={entries:[{role:'user',content:'Inspect batchWorker and its flush relationship.'},{role:'assistant',content:[call('p','package.json'),call('j','api.js'),call('d','api.d.ts')]},result('p',pkg),result('j',js),result('d',dts)]};
        const knowledge={sourceCitations:[{ref:'e4.b0.l4'},{ref:'e4.b0.l2'},{ref:'e3.b0.l3'},{ref:'e4.b0.l5'}],units:[{text:'batchWorker uses allocatePool; its internal result has the declared flush member. Why: inspected contract. How to apply: revisit source.',citationIndexes:[0,1,2,3]}]};
        const run={manifest:{cwd:root}},raw={operations:[],newMemories:[{name:'fact.md',kind:'project',classification:'private',description:'Observed relationship.',knowledge}]};
        const before=JSON.stringify(knowledge),fresh=await materializeSourceExcerptPlan(run,raw,snapshot,undefined,{retainSelectedDeclarations:true});
        const threeKnowledge=structuredClone(knowledge);threeKnowledge.sourceCitations.push({ref:'e4.b0.l1'});threeKnowledge.units[0].citationIndexes.push(4);
        const threeRaw=structuredClone(raw);threeRaw.newMemories[0].knowledge=threeKnowledge;
        const three=await materializeSourceExcerptPlan(run,threeRaw,snapshot,undefined,{retainSelectedDeclarations:true});
        const prior='---\nname: fact.md\ndescription: Prior source fact.\ntype: project\ncustom: keep exactly\n---\nOld body';
        const semantic=await materializeSemanticProjectKnowledge(run,'fact.md',prior,knowledge,snapshot);
        const noWrapper=structuredClone(knowledge);noWrapper.sourceCitations.pop();noWrapper.units[0].citationIndexes.pop();let wrapperError=null;
        try{await materializeSemanticProjectKnowledge(run,'fact.md',prior,noWrapper,snapshot)}catch(e){wrapperError=e.message}
        const quiet=structuredClone(knowledge);quiet.units[0].text='Why: inspected contract. How to apply: revisit source.';
        const same=await materializeSemanticProjectKnowledge(run,'fact.md',prior,quiet,snapshot);
        const missing=structuredClone(quiet);missing.sourceCitations=[{ref:'e4.b0.l2'}];missing.units[0].citationIndexes=[0];let error=null;
        try{await materializeSemanticProjectKnowledge(run,'fact.md',prior,missing,snapshot)}catch(e){error=e.message}
        console.log(JSON.stringify({three:three.newMemories[0],fresh:fresh.newMemories[0],semantic,same,error,wrapperError,obligations:selectedProjectSourceObligations(run),unchanged:JSON.stringify(knowledge)===before}));
      }finally{fs.rmSync(root,{recursive:true,force:true})}
    ''')
    assert 'export type Pool = {' in value['three']['content']
    assert len(value['three']['evidence']) == 5
    assert value['unchanged']
    for record in (value['fresh'], value['semantic'], value['same']):
        assert '`allocatePool` has the named return type `Pool`' in record['content']
        assert '`Pool` declares `flush`' in record['content']
        assert 'export default function allocatePool(size:number): Pool;' in record['content']
        assert 'flush(): void;' in record['content']
        assert len(record['evidence']) == 4
    assert value['semantic']['content'].startswith('---\nname: fact.md\ndescription: Prior source fact.\ntype: project\ncustom: keep exactly\n---\n')
    assert 'batchWorker uses allocatePool' in value['semantic']['content']
    assert 'factory' in value['error'] and 'owner' in value['error']
    assert value['wrapperError'] and 'initiating-wrapper' in value['wrapperError']
    assert value['obligations']['fact.md']['requirements'][0]['owner'] == 'Pool'


def test_factory_return_owner_witness_keeps_three_roles_and_rejects_ambiguous_ast():
    value = isolated_run_bun(r'''
      import {declaredMemoryRelation} from './packages/continual-learning/extensions/memory-relation-closure.ts';
      const root='/factory-owner-witness';
      const base='export interface Pool {\n flush(): void;\n}\nexport function allocatePool(): Pool;\nexport interface Other {\n flush(): void;\n}\n';
      const unit={kind:'declared-api-relation',factory:{ref:'e1.b0.l4'},owner:{ref:'e1.b0.l4'},member:{ref:'e1.b0.l2'}};
      const snapshot=text=>({entries:[{role:'assistant',content:[{type:'toolCall',id:'d',name:'read',arguments:{path:root+'/api.d.ts',limit:1000}}]},{role:'toolResult',toolName:'read',toolCallId:'d',isError:false,content:text}]});
      const check=(text=base,u=unit,s=snapshot(text))=>{try{return {value:declaredMemoryRelation(s,u,root)}}catch(e){return {error:e.message}}};
      const bad={};
      for(const [name,text] of Object.entries({generic:base.replace('allocatePool()', 'allocatePool<Pool>()'),genericOwner:base.replace('interface Pool {','interface Pool<T> {'),genericMember:base.replace('flush()', 'flush<T>()'),genericReturn:base.replace('(): Pool;', '(): Pool<string>;'),alias:base.replace('interface Pool {\n flush(): void;\n}', 'type Pool = Other;\n\n'),intersection:base.replace('interface Pool {\n flush(): void;\n}', 'type Pool = Other & {flush():void};\n\n'),inherited:base.replace('interface Pool {','interface Pool extends Other {'),merged:base+'export interface Pool { close():void; }',overload:base+'export function allocatePool(size:number): Pool;',imported:base+"import {Pool} from './other.js';",qualified:base.replace('(): Pool;', '(): ns.Pool;'),union:base.replace('(): Pool;', '(): Pool | Other;'),duplicateMember:base.replace(' flush(): void;', ' flush(): void; flush():void;')}))bad[name]=check(text);
      bad.otherOwner=check(base,{...unit,member:{ref:'e1.b0.l6'}});
      const multiple=snapshot(base);multiple.entries.push({role:'assistant',content:[{type:'toolCall',id:'x',name:'read',arguments:{path:root+'/api.d.ts',limit:1000}}]},{role:'toolResult',toolName:'read',toolCallId:'x',isError:false,content:base.replace('(): Pool;', '(): Other;')});
      bad.crossRevision=check(base,{...unit,member:{ref:'e3.b0.l2'}},multiple);
      bad.partial=check(base,{...unit,factory:{ref:'e1.b0.l3'}});
      bad.terminal=check(base,unit,{entries:[{role:'assistant',content:[{type:'toolCall',id:'d',name:'bash',arguments:{command:'cat api.d.ts'}}]},{role:'toolResult',toolName:'bash',toolCallId:'d',isError:false,content:base}]});
      console.log(JSON.stringify({two:check(),three:check(base,{...unit,owner:{ref:'e1.b0.l1',endRef:'e1.b0.l3'}}),bad}));
    ''')
    assert value['two']['value']['relation']['owner'] == 'Pool'
    assert value['two']['value']['refs'][0] == value['two']['value']['refs'][1]
    assert value['three']['value']['relation']['owner'] == 'Pool'
    assert all('error' in outcome for outcome in value['bad'].values()), value['bad']


def test_legacy_atomic_success_keeps_source_obligations_without_wrapper_topic():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {materializeSourceExcerptPlan,materializeSemanticProjectKnowledge,selectedProjectSourceObligations} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'legacy-source-continuity-')));
      try{
        const dts='export interface Reservoir {\n drain(): void;\n}\nexport function makeReservoir(): Reservoir;\n';fs.writeFileSync(path.join(root,'api.d.ts'),dts);
        const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'d',name:'read',arguments:{path:root+'/api.d.ts',limit:1000}}]},{role:'toolResult',toolName:'read',toolCallId:'d',isError:false,content:dts}]};
        const run={manifest:{cwd:root}},refs=[{ref:'e1.b0.l4'},{ref:'e1.b0.l1',endRef:'e1.b0.l3'},{ref:'e1.b0.l2'}];
        const relation={kind:'declared-api-relation',factory:refs[0],owner:refs[1],member:refs[2]};
        const first=await materializeSourceExcerptPlan(run,{operations:[],newMemories:[{kind:'project',name:'reservoir.md',description:'Observed declaration.',classification:'private',knowledge:{sourceCitations:[refs[2]],units:[relation]}}]},snapshot,undefined,{retainSelectedDeclarations:true});
        const prior=first.newMemories[0].content,knowledge={sourceCitations:refs,units:[{text:'Why: inspected declaration. How to apply: recheck source.',citationIndexes:[0,1,2]}]};
        const complete=await materializeSemanticProjectKnowledge(run,'reservoir.md',prior,knowledge,snapshot);let missing=null;
        try{await materializeSemanticProjectKnowledge(run,'reservoir.md',prior,{sourceCitations:[refs[2]],units:[{text:'Why: inspected declaration. How to apply: recheck source.',citationIndexes:[0]}]},snapshot)}catch(e){missing=e.message}
        console.log(JSON.stringify({first:first.newMemories[0],complete,missing,cache:selectedProjectSourceObligations(run)}));
      }finally{fs.rmSync(root,{recursive:true,force:true})}
    ''')
    assert '`Reservoir` declares `drain`' in value['first']['content']
    assert '`Reservoir` declares `drain`' in value['complete']['content']
    assert value['missing'] and 'factory' in value['missing'] and 'owner' in value['missing']
    requirement = value['cache']['reservoir.md']['requirements'][0]
    assert 'wrapper' not in requirement
    assert [role['role'] for role in requirement['roles']] == ['factory', 'owner', 'member']


def test_automatic_role_blocks_project_wide_catalog_without_trimming_evidence_or_legacy():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {materializeSourceExcerptPlan,materializeSemanticProjectKnowledge,selectedProjectSourceObligations} from './packages/continual-learning/extensions/source-excerpt-memory.ts';
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'role-local-source-')));
      try{
        const js='export default function allocatePool(size) { return {flush() {}}; }\nexport function batchWorker(options) {\n const pool=allocatePool(options);\n return () => pool.flush();\n}\n';
        const dts='export type Pool = {\n /** unrelated documentation */\n unrelatedInventory: number;\n flush(): void;\n};\nexport default function allocatePool(size:number): Pool;\nexport function batchWorker(options:number): () => void;\n';
        const pkg=JSON.stringify({type:'module',exports:{types:'./api.d.ts',default:'./api.js'}});
        const write=text=>{for(const [file,value] of Object.entries({'api.js':js,'api.d.ts':text,'package.json':pkg}))fs.writeFileSync(path.join(root,file),value)};write(dts);
        const call=(id,name)=>({type:'toolCall',id,name:'read',arguments:{path:root+'/'+name,offset:1,limit:1000}}),result=(id,content)=>({role:'toolResult',toolName:'read',toolCallId:id,isError:false,content});
        const snapshot=text=>({entries:[{role:'user',content:'Inspect only batchWorker and its flush relationship; do not inventory other properties.'},{role:'assistant',content:[call('p','package.json'),call('j','api.js'),call('d','api.d.ts')]},result('p',pkg),result('j',js),result('d',text)]});
        const refs=[{ref:'e4.b0.l1',endRef:'e4.b0.l4'},{ref:'e4.b0.l6'},{ref:'e4.b0.l7'},{ref:'e3.b0.l3'}];
        const knowledge={sourceCitations:refs,units:[{text:'batchWorker delegates to allocatePool; its result has the declared flush member. Why: inspected contract. How to apply: recheck this relationship.',citationIndexes:[0,1,2,3]}]};
        const raw={operations:[],newMemories:[{name:'fact.md',kind:'project',classification:'private',description:'Observed relationship.',knowledge}]},run={manifest:{cwd:root}},before=JSON.stringify(raw);
        const first=await materializeSourceExcerptPlan(run,raw,snapshot(dts),undefined,{retainSelectedDeclarations:true});
        const semantic=await materializeSemanticProjectKnowledge(run,'fact.md',first.newMemories[0].content,knowledge,snapshot(dts));
        const legacy=structuredClone(raw);legacy.newMemories[0].knowledge.units.unshift({kind:'declared-api-relation',factory:refs[1],owner:{ref:'e4.b0.l1',endRef:'e4.b0.l5'},member:{ref:'e4.b0.l4'}});
        const exact=await materializeSourceExcerptPlan({manifest:{cwd:root}},legacy,snapshot(dts),undefined,{retainSelectedDeclarations:true});
        const excerpt=await materializeSourceExcerptPlan({manifest:{cwd:root}},{operations:[],newMemories:[{name:'literal.md',kind:'project',classification:'private',sourceExcerpt:refs[0],evidence:[refs[0]]}]},snapshot(dts));
        const reject=async text=>{write(text);try{await materializeSourceExcerptPlan({manifest:{cwd:root}},raw,snapshot(text),undefined,{retainSelectedDeclarations:true});return null}catch(e){return e.message}};
        const inlineText='export type Pool = { unrelatedInventory: number; flush(): void; }; export default function allocatePool(size:number): Pool; export function batchWorker(options:number): () => void;\n';
        write(inlineText);const inlineRaw=structuredClone(raw),inlineRun={manifest:{cwd:root}};inlineRaw.newMemories[0].knowledge={sourceCitations:[{ref:'e4.b0.l1'},{ref:'e3.b0.l3'}],units:[{text:knowledge.units[0].text,citationIndexes:[0,1]}]};
        const inline=await materializeSourceExcerptPlan(inlineRun,inlineRaw,snapshot(inlineText),undefined,{retainSelectedDeclarations:true});const publicProof=JSON.stringify(selectedProjectSourceObligations(inlineRun));
        const secret=await reject(dts.replace('unrelated documentation','api_key: abcdefghijklmnop'));
        const quoteBound=await reject(dts.replace('unrelated documentation','unrelated '.repeat(300)));
        write(dts);const tooMany=structuredClone(raw);tooMany.newMemories[0].knowledge.units=Array(32).fill(knowledge.units[0]);let unitsBound=null;
        try{await materializeSourceExcerptPlan({manifest:{cwd:root}},tooMany,snapshot(dts),undefined,{retainSelectedDeclarations:true})}catch(e){unitsBound=e.message}
        console.log(JSON.stringify({inline:inline.newMemories[0],publicProof,first:first.newMemories[0],semantic,exact:exact.newMemories[0],excerpt:excerpt.newMemories[0],secret,quoteBound,unitsBound,unchanged:JSON.stringify(raw)===before,modelText:knowledge.units[0].text,wholeQuote:dts.split('\n').slice(0,4).join('\n')}));
      }finally{fs.rmSync(root,{recursive:true,force:true})}
    ''')
    for item in (value['first'], value['semantic']):
        assert 'unrelatedInventory' not in item['content']
        assert 'unrelated documentation' not in item['content']
        assert 'export type Pool = {' in item['content'] and 'flush(): void;' in item['content']
        assert 'export default function allocatePool(size:number): Pool;' in item['content']
        assert 'export function batchWorker(options:number): () => void;' in item['content']
        assert item['evidence'][0]['quote'] == value['wholeQuote']
        assert len(item['evidence']) == 4 and value['modelText'] in item['content']
    assert value['first']['evidence'] == value['semantic']['evidence']
    assert 'unrelatedInventory' not in value['inline']['content']
    assert 'export type Pool = {' in value['inline']['content']
    assert 'flush(): void;' in value['inline']['content']
    assert 'export default function allocatePool(size:number): Pool;' in value['inline']['content']
    assert 'export function batchWorker(options:number): () => void;' in value['inline']['content']
    assert len(value['inline']['evidence']) == 2
    assert 'unrelatedInventory' in value['inline']['evidence'][0]['quote']
    assert 'sourceSpan' not in value['publicProof']
    assert value['unchanged']
    assert 'unrelatedInventory' in value['exact']['content'] and 'unrelatedInventory' in value['excerpt']['content']
    assert value['secret'] and '2000' in value['quoteBound'] and value['unitsBound']
