from support import isolated_run_bun


def test_projection_labels_evidence_roles_without_removing_context() -> None:
    value = isolated_run_bun(r'''
      import {locatedMemoryEvidence} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const snapshot={entries:[{role:'assistant',content:'unsupported inference'},{role:'user',content:'explicit correction'},
        {message:{role:'toolResult',content:'observed source'}}]};
      const before=JSON.stringify(snapshot);console.log(JSON.stringify({shown:locatedMemoryEvidence(snapshot),unchanged:before===JSON.stringify(snapshot)}));
    ''')
    assert value['unchanged']
    assert [entry.get('citationEligible') for entry in value['shown']['entries']] == [False, True, True]
    assert value['shown']['entries'][0]['entry']['content'] == 'unsupported inference'


def test_structural_repair_only_announces_empty_scope_for_actual_damaged_output() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');const prompts=[];
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{prompts.push(input.prompt);return {exitCode:0,stderr:'',text:'{}'};}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const input={structuralCorrection:true,identity:{runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'},errors:['citation source unavailable'],selectedNames:['existing.md']};
      await repairIncrementalMemoryPlan({...input,rejectedPlan:{operations:[],newMemories:[]}});
      await repairIncrementalMemoryPlan({...input,selectedNames:[],rejectedPlan:{malformedPlanText:'damaged output'}});
      console.log(JSON.stringify({emptyScope:prompts.map(prompt=>prompt.includes('The selected existing scope is empty.'))}));
    ''')
    assert value['emptyScope'] == [False, True]


def test_one_repair_receives_count_and_coordinate_failures_together() -> None:
    value = isolated_run_bun(r'''
      import {resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const snapshot={entries:[{role:'toolResult',content:'actual source'}]};
      const plan={operations:[{evidence:[{index:0,lines:{block:0,start:2,end:2}}]},
        {evidence:Array.from({length:9},()=>({index:0,lines:{block:0,start:1,end:1}}))}],newMemories:[]};
      const before=JSON.stringify(plan);let error='';try{resolveMemoryPlanCitations(plan,snapshot)}catch(e){error=e.message}
      console.log(JSON.stringify({error,unchanged:JSON.stringify(plan)===before}));
    ''')
    assert value['unchanged']
    assert 'operations[0].evidence[0]: line-range-out-of-bounds' in value['error']
    assert 'operations[1].evidence: item-count-out-of-bounds (required=1..8, actual=9)' in value['error']


def test_parent_extracts_line_locations_without_transcription_or_evidence_changes() -> None:
    value = isolated_run_bun(r'''
      import {resolveMemoryPlanCitations,locatedMemoryEvidence} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      import {candidateCitationProblems} from './packages/continual-learning/extensions/inject-memory.ts';
      const text='49:\t// Node.js 20 has a bug\r\n50:\tconst check = enabled ? run : skip;\r\n51:\treturn check;';
      const snapshot={contextEnabled:true,entries:[{role:'assistant',content:'not evidence'},{id:'original',message:{role:'toolResult',content:[{type:'text',text},{type:'image',data:'not text'},{type:'text',text:'Later correction: disabled.'}]}}]};
      const original=JSON.stringify(snapshot);
      const raw={operations:[],newMemories:[{name:'a.md',content:'unchanged',evidence:[{index:1,lines:{block:0,start:1,end:2},role:'toolResult'}]}]};
      const resolved=resolveMemoryPlanCitations(raw,snapshot);
      const shown=locatedMemoryEvidence(snapshot);
      console.log(JSON.stringify({resolved,shown,unchanged:JSON.stringify(snapshot)===original,rawUnchanged:!raw.newMemories[0].evidence[0].quote,problems:candidateCitationProblems(snapshot,resolved.newMemories)}));
    ''')
    citation = value['resolved']['newMemories'][0]['evidence'][0]
    assert citation == {'index': 1, 'quote': '49:\t// Node.js 20 has a bug\r\n50:\tconst check = enabled ? run : skip;\r', 'role': 'toolResult'}
    assert value['unchanged'] and value['rawUnchanged'] and not value['problems']
    entries = value['shown']['entries']
    assert entries[0]['entry']['content'] == 'not evidence'
    blocks = entries[1]['entry']['message']['content']
    assert blocks[0]['citationLines']['block'] == 0
    assert blocks[0]['citationLines']['lines'][0] == {'line': 1, 'text': '49:\t// Node.js 20 has a bug\r', 'ref': 'e1.b0.l1'}
    assert blocks[1] == {'type': 'image', 'data': 'not text'}
    assert blocks[2]['citationLines']['block'] == 2
    assert blocks[2]['citationLines']['lines'][0]['text'] == 'Later correction: disabled.'


def test_locations_cannot_add_authority_change_roles_or_evade_quote_bounds() -> None:
    value = isolated_run_bun(r'''
      import {resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const snapshot={entries:[{role:'assistant',content:'invented'},{role:'toolResult',content:[{text:'one\ntwo'},{text:'three'}]},{role:'user',content:'x'.repeat(2001)}]};
      const bad=[{index:0,lines:{block:0,start:1,end:1}},
        {index:1,lines:{block:0,start:0,end:1}},{index:1,lines:{block:0,start:2,end:1}},
        {index:1,lines:{block:0,start:1,end:3}},{index:1,lines:{block:9,start:1,end:1}},
        {index:1,lines:{block:0,start:1.5,end:2}},{index:1,lines:{block:0,start:1,end:1,omit:[1]}},
        {index:1,lines:{block:0,start:1,end:1},role:'user'},
        {index:1,lines:{block:0,start:1,end:1},quote:'not one'},
        {index:2,lines:{block:0,start:1,end:1}},{index:99,lines:{block:0,start:1,end:1}}];
      const rejected=bad.map(c=>{try{resolveMemoryPlanCitations({operations:[{evidence:[c]}]},snapshot);return false;}catch{return true;}});
      const legacy={operations:[{evidence:[{index:1,quote:'one'}]}]};
      const good=resolveMemoryPlanCitations({newMemories:[{evidence:[{index:1,lines:{block:0,start:1,end:1},quote:'one'}]}]},snapshot);
      console.log(JSON.stringify({rejected,legacyUnchanged:resolveMemoryPlanCitations(legacy,snapshot)===legacy,good}));
    ''')
    assert all(value['rejected'])
    assert value['legacyUnchanged']
    assert value['good']['newMemories'][0]['evidence'][0]['quote'] == 'one'


def test_semantic_repair_resolves_locations_before_retaining_protected_candidates() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let prompt='';let payload;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{prompt=input.prompt;return {exitCode:0,stderr:'',text:JSON.stringify(payload),usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:.01}};}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {resolveMemoryPlanCitations}=await import('./packages/continual-learning/extensions/memory-citation-locations.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const item={name:'fact.md',kind:'project',classification:'safe',content:'Project uses Vitest.',evidence:[{index:0,lines:{block:0,start:1,end:1}}]};
      const rejectedPlan={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[item]};
      payload={...rejectedPlan,newMemories:[{...item,evidence:[{index:0,quote:'Project uses Vitest.'}]}]};
      const semanticContext={frozenEvidence:{entries:[{role:'toolResult',content:'Project uses Vitest.'}]},existingMemories:[]};
      const resolved=resolveMemoryPlanCitations(payload,semanticContext.frozenEvidence);
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan,selectedNames:[],errors:['uncertain'],repairableNames:[],semanticContext});
      payload={...payload,newMemories:[{...item,evidence:[{index:0,lines:{block:0,start:1,end:9}}]}]};
      const invalid=await repairIncrementalMemoryPlan({identity,rejectedPlan,selectedNames:[],errors:['uncertain'],semanticContext});
      console.log(JSON.stringify({result,resolved,invalid,locatedProjection:prompt.includes('citationLines')}));
    ''')
    assert value['result']['outcome'] == 'failed' and value['result']['failureKind'] == 'no-correction'
    assert 'plan' not in value['result']
    assert value['resolved']['newMemories'][0]['evidence'] == [{'index': 0, 'quote': 'Project uses Vitest.'}]
    assert value['invalid']['outcome'] == 'failed' and value['invalid']['failureKind'] == 'citation'
    assert value['invalid']['usage']['cost'] == .01
    assert value['locatedProjection']


def test_parent_pipeline_applies_initial_and_repaired_locations_with_existing_gates() -> None:
    from pathlib import Path
    from support import run_bun_script
    fixture = Path(__file__).with_name('learning-policy-harness.ts')
    for reason in ['located-supported', 'located-repair', 'referenced-supported', 'referenced-repair']:
        value = run_bun_script(fixture, 'remember-shared', env={'CL_JEV_FIXTURE': reason})
        assert value['registryReceipt']['operations'] == 1
        assert 'concise.md' in value['privateFiles'] and 'concise.md' in value['publicFiles']
        assert value['semanticRepairs'] == (1 if reason.endswith('-repair') else 0)
        assert not value['lock']


def test_locations_cannot_resolve_against_a_changed_frozen_snapshot() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
      import {expandIncrementalMemoryPlan} from './packages/continual-learning/extensions/incremental-memory-plan.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const root=await fs.mkdtemp(path.join(os.tmpdir(),'located-plan-'));
      try {
        const snapshotFile=path.join(root,'snapshot.json');const snapshot=JSON.stringify({schemaVersion:1,runId:'run_located',scopeKey:'s'.repeat(64),contextEnabled:true,entries:[{role:'toolResult',content:'Project uses Vitest.'}]});
        await fs.writeFile(snapshotFile,snapshot);
        const identity={runId:'run_located',scopeKey:'s'.repeat(64),scopeDigest:'d'.repeat(64),artifactHash:sha256Digest(snapshot),snapshotDigest:sha256Digest(snapshot)};
        const run={manifest:{schemaVersion:1,...identity,snapshotDigest:identity.snapshotDigest,cwd:root,harnessDir:root,publicDir:root,sourceHashes:{harness:{},public:{}}},paths:{snapshotFile}};
        const delta={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[{name:'fact.md',kind:'project',classification:'safe',content:'Project uses Vitest.',evidence:[{ref:'e0.b0.l1'}]}]};
        const valid=await expandIncrementalMemoryPlan(run,[],delta);
        await fs.writeFile(snapshotFile,snapshot+' ');
        let refused=false;try{await expandIncrementalMemoryPlan(run,[],delta);}catch{refused=true;}
        console.log(JSON.stringify({valid,refused}));
      } finally {await fs.rm(root,{recursive:true,force:true});}
    ''')
    assert value['valid']['newMemories'][0]['evidence'][0]['quote'] == 'Project uses Vitest.'
    assert value['refused']


def test_location_repair_receives_all_controlled_failures_without_source_text() -> None:
    value = isolated_run_bun(r'''
      import {resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const snapshot={entries:[{role:'toolResult',content:'one\ntwo'},{role:'toolResult',content:'private-marker-'.repeat(200)}]};
      const raw={operations:[{evidence:[{index:0,lines:{block:0,start:1,end:1}},{index:0,lines:{block:0,start:3,end:3}}]}],
        newMemories:[{evidence:[{index:1,lines:{block:0,start:1,end:1}},{index:0,lines:{block:99,start:1,end:1}},{index:0,lines:{block:0,start:1,end:1},quote:'different'}]}]};
      const before=JSON.stringify(raw);let error='';
      try {resolveMemoryPlanCitations(raw,snapshot);}catch(e){error=e.message;}
      console.log(JSON.stringify({error,unchanged:JSON.stringify(raw)===before}));
    ''')
    assert value['unchanged']
    assert 'operations[0].evidence[1]: line-range-out-of-bounds (availableLines=2)' in value['error']
    assert 'newMemories[0].evidence[0]: quote-length-out-of-bounds (maximumCharacters=2000)' in value['error']
    assert 'newMemories[0].evidence[1]: source-unavailable' in value['error']
    assert 'newMemories[0].evidence[2]: quote-mismatch' in value['error']
    assert 'private-marker' not in value['error'] and 'different' not in value['error']


def test_location_diagnostics_are_bounded_for_untrusted_plan_sizes() -> None:
    value = isolated_run_bun(r'''
      import {resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      let error='';try {resolveMemoryPlanCitations({operations:[{evidence:Array.from({length:1000},()=>({index:0,lines:{block:0,start:9,end:9}}))}]},{entries:[{role:'user',content:'one'}]});}catch(e){error=e.message;}
      console.log(JSON.stringify({error}));
    ''')
    assert value['error'].count('item-count-out-of-bounds') == 1
    assert value['error'].count('line-range-out-of-bounds') == 7
    assert len(value['error']) < 800


def test_parent_extracted_long_line_spans_are_lossless_and_keep_quote_limits() -> None:
    value = isolated_run_bun(r'''
      import {locatedMemoryEvidence,resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const text='prefix-'.repeat(300)+'\\n  test-on-idle.js:33:50 Prefer await to then()/catch()/finally(). promise/prefer-await-to-then'+'-suffix'.repeat(100);
      const snapshot={entries:[{role:'toolResult',content:[{type:'text',text}]}]};
      const before=JSON.stringify(snapshot);const shown=locatedMemoryEvidence(snapshot).entries[0].entry.content[0].citationLines.lines[0];
      const start=text.indexOf('test-on-idle.js'),end=start+'test-on-idle.js:33:50 Prefer await to then()/catch()/finally(). promise/prefer-await-to-then'.length;
      const ref={index:0,lines:{block:0,start:1,end:1,characters:{start,end}}};
      const resolved=resolveMemoryPlanCitations({newMemories:[{evidence:[ref]}]},snapshot);
      const invalid=[{start:-1,end:1},{start:0,end:text.length+1},{start:2,end:2},{start:0.5,end:2},{start:0,end:2001},{start:0,end:1,decode:true}];
      const rejects=invalid.map(characters=>{try{resolveMemoryPlanCitations({operations:[{evidence:[{index:0,lines:{block:0,start:1,end:1,characters}}]}]},snapshot);return false;}catch{return true;}});
      let crossLineRejected=false;try{resolveMemoryPlanCitations({operations:[{evidence:[{index:0,lines:{block:0,start:1,end:2,characters:{start:0,end:1}}}]}]},{entries:[{role:'user',content:'one\ntwo'}]});}catch{crossLineRejected=true;}
      console.log(JSON.stringify({shown,resolved,rejects,crossLineRejected,unchanged:before===JSON.stringify(snapshot),text}));
    ''')
    chunks = value['shown']['chunks']
    assert ''.join(c['text'] for c in chunks) == value['text']
    assert chunks[0]['start'] == 0 and chunks[-1]['end'] == len(value['text'])
    assert all(c['end'] == chunks[i+1]['start'] for i,c in enumerate(chunks[:-1]))
    assert value['resolved']['newMemories'][0]['evidence'][0]['quote'] == 'test-on-idle.js:33:50 Prefer await to then()/catch()/finally(). promise/prefer-await-to-then'
    assert all(value['rejects']) and value['crossLineRejected'] and value['unchanged']


def test_character_locations_never_decode_json_or_accept_a_partial_quote_hint() -> None:
    value = isolated_run_bun(r'''
      import {resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const text='prefix literal\\nthen suffix';const snapshot={entries:[{role:'user',content:text}]};
      const ref={index:0,lines:{block:0,start:1,end:1,characters:{start:7,end:20}}};
      const result=resolveMemoryPlanCitations({operations:[{evidence:[ref]}]},snapshot);
      const bad=[{...ref,quote:'literal\nthen'},{index:0,lines:{block:0,start:1,end:1},quote:'literal\\nthen'}];
      const rejected=bad.map(c=>{try{resolveMemoryPlanCitations({operations:[{evidence:[c]}]},snapshot);return false;}catch{return true;}});
      console.log(JSON.stringify({result,rejected,expected:text.slice(7,20)}));
    ''')
    assert value['result']['operations'][0]['evidence'][0]['quote'] == value['expected']
    assert all(value['rejected'])


def test_actual_encoded_verifier_line_has_exact_bounded_parent_citations() -> None:
    value = isolated_run_bun(r'''
      import {locatedMemoryEvidence,resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const fixture=await Bun.file('./packages/continual-learning/tests/fixtures/real-long-verifier-line.json').json();
      const snapshot={entries:[fixture.entry]},before=JSON.stringify(snapshot);
      const message=fixture.entry.message??fixture.entry;const source=message.content[0].text.split('\n')[22];
      const shown=locatedMemoryEvidence(snapshot).entries[0].entry;
      const line=(shown.message??shown).content[0].citationLines.lines[22];
      const citations=line.chunks.map(chunk=>resolveMemoryPlanCitations({operations:[{evidence:[{index:0,lines:{block:0,start:23,end:23,characters:{start:chunk.start,end:chunk.end}}}]}]},snapshot).operations[0].evidence[0].quote);
      console.log(JSON.stringify({sourceLength:source.length,lossless:citations.join('')===source,bounded:citations.every(q=>q.length<=512),unchanged:JSON.stringify(snapshot)===before}));
    ''')
    assert value['sourceLength'] > 2000
    assert value['lossless'] and value['bounded'] and value['unchanged']


def test_unicode_spans_and_chunk_edges_preserve_original_characters() -> None:
    value = isolated_run_bun(r'''
      import {locatedMemoryEvidence,resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const source='a'.repeat(511)+String.fromCodePoint(0x20000)+'b'.repeat(2000),snapshot={entries:[{role:'user',content:source}]};
      const chunks=locatedMemoryEvidence(snapshot).entries[0].entry.content.citationLines.lines[0].chunks;
      const ref=characters=>({index:0,lines:{block:0,start:1,end:1,characters}});
      const accepted=resolveMemoryPlanCitations({operations:[{evidence:[ref({start:511,end:513})]}]},snapshot).operations[0].evidence[0].quote;
      const bad=[{start:511,end:512},{start:512,end:513}].map(c=>{try{resolveMemoryPlanCitations({operations:[{evidence:[ref(c)]}]},snapshot);return false;}catch{return true;}});
      console.log(JSON.stringify({chunkEnd:chunks[0].end,restored:chunks.map(c=>c.text).join('')===source,accepted:accepted===String.fromCodePoint(0x20000),bad}));
    ''')
    assert value['chunkEnd'] == 511
    assert value['restored'] and value['accepted'] and all(value['bad'])


def test_parent_generated_references_select_exact_frozen_source_without_coordinates() -> None:
    value = isolated_run_bun(r'''
      import {locatedMemoryEvidence,resolveMemoryPlanCitations,hasMemoryCitationLocations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const snapshot={entries:[{role:'assistant',content:'not evidence'},{role:'toolResult',content:[{type:'text',text:'first\r\n  preserve condition\r\nlast'},{type:'image',data:'context'},{type:'text',text:'other block'}]}]};
      const before=JSON.stringify(snapshot),shown=locatedMemoryEvidence(snapshot);
      const lines=shown.entries[1].entry.content[0].citationLines.lines;
      const evidence=[{ref:lines[0].ref,endRef:lines[1].ref}];
      const plan={operations:[{evidence}]};
      const resolved=resolveMemoryPlanCitations(plan,snapshot);
      console.log(JSON.stringify({refs:lines.map(x=>x.ref),resolved,located:hasMemoryCitationLocations(plan),unchanged:JSON.stringify(snapshot)===before,rawUnchanged:!plan.operations[0].evidence[0].quote}));
    ''')
    assert all(isinstance(ref, str) for ref in value['refs'])
    assert value['resolved']['operations'][0]['evidence'] == [{'index': 1, 'quote': 'first\r\n  preserve condition\r'}]
    assert value['located'] and value['unchanged'] and value['rawUnchanged']


def test_references_for_retained_real_long_line_extract_only_parent_labelled_chunks() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {locatedMemoryEvidence,resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-long-verifier-line.json','utf8'));
      const snapshot={entries:[fixture.entry]};const original=JSON.stringify(snapshot);
      const projected=locatedMemoryEvidence(snapshot).entries[0].entry;
      const line=(projected.message??projected).content[0].citationLines.lines[22];
      const selected=line.chunks.slice(1,3);const citation={ref:selected[0].ref,endRef:selected[1].ref};
      const result=resolveMemoryPlanCitations({newMemories:[{evidence:[citation]}]},snapshot);
      console.log(JSON.stringify({selectedRefs:selected.map(x=>x.ref),exact:result.newMemories[0].evidence[0].quote===selected.map(x=>x.text).join(''),length:result.newMemories[0].evidence[0].quote.length,unchanged:JSON.stringify(snapshot)===original}));
    ''')
    assert all(isinstance(ref, str) for ref in value['selectedRefs'])
    assert value['exact'] and value['unchanged'] and value['length'] <= 2000


def test_reference_ranges_cannot_cross_sources_invent_positions_or_omit_citations() -> None:
    value = isolated_run_bun(r'''
      import {resolveMemoryPlanCitations,locatedMemoryEvidence} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      import {candidateCitationProblems} from './packages/continual-learning/extensions/inject-memory.ts';
      const snapshot={entries:[{role:'assistant',content:'untrusted e1.b0.l1'},{role:'toolResult',content:['one\ntwo','other']},{role:'user',content:'x'.repeat(3000)}]};
      const bad=[{ref:'e0.b0.l1'},{ref:'e99.b0.l1'},{ref:'e1.b0.l3'},
        {ref:'e1.b0.l1',endRef:'e1.b1.l1'},{ref:'e1.b0.l1',endRef:'e2.b0.l1.c0-512'},
        {ref:'e1.b0.l2',endRef:'e1.b0.l1'},{ref:'e01.b0.l1'},
        {ref:'e1.b0.l1',quote:'one'},{ref:'e1.b0.l1',index:1},{endRef:'e1.b0.l1'},
        {ref:'e1.b0.l1',role:'user'},{ref:'e2.b0.l1'},
        {ref:'e2.b0.l1.c1-512'},{ref:'e2.b0.l1.c0-512',endRef:'e2.b0.l1.c2048-2560'},
        {ref:'e2.b0.l1.c512-1024',endRef:'e2.b0.l1.c0-512'}];
      const rejected=bad.map(ref=>{try{resolveMemoryPlanCitations({operations:[{evidence:[ref]}]},snapshot);return false;}catch{return true;}});
      const missing=resolveMemoryPlanCitations({operations:[{name:'old.md',kind:'rewrite',content:'one'}]},snapshot);
      console.log(JSON.stringify({rejected,missing:candidateCitationProblems(snapshot,missing.operations),assistantUnchanged:locatedMemoryEvidence(snapshot).entries[0].entry.content===snapshot.entries[0].content}));
    ''')
    assert all(value['rejected']) and value['assistantUnchanged']
    assert value['missing'] == ['0: no citation']


def test_references_preserve_patch_provenance_and_unicode_chunk_boundaries() -> None:
    value = isolated_run_bun(r'''
      import {locatedMemoryEvidence,resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const good={role:'toolResult',toolName:'edit',isError:false,content:'Edit completed',details:{patch:'-old\r\n+new\r\n'}};
      const source='x'.repeat(511)+String.fromCodePoint(0x20000)+'z'.repeat(2000);
      const snapshot={entries:[good,{...good,isError:true},{...good,role:'assistant'},{role:'user',content:source}]};
      const shown=locatedMemoryEvidence(snapshot);
      const patchRef=shown.entries[0].entry.details.patch.citationLines.lines[1].ref;
      const chunks=shown.entries[3].entry.content.citationLines.lines[0].chunks;
      const resolve=ref=>resolveMemoryPlanCitations({operations:[{evidence:[ref]}]},snapshot).operations[0].evidence[0].quote;
      const patch=resolve({ref:patchRef});const unicode=resolve({ref:chunks[1].ref});
      const bad=[{ref:'e1.b0.p2'},{ref:'e2.b0.p2'},{ref:'e0.b0.l1',endRef:patchRef},{ref:'e3.b0.l1.c511-512'}].map(ref=>{try{resolve(ref);return false;}catch{return true;}});
      console.log(JSON.stringify({patch,unicodeExact:unicode===chunks[1].text,startsWithWholeCharacter:unicode.startsWith(String.fromCodePoint(0x20000)),chunkBoundary:chunks[0].end,bad}));
    ''')
    assert value['patch'] == '+new\r'
    assert value['unicodeExact'] and value['startsWithWholeCharacter'] and value['chunkBoundary'] == 511
    assert all(value['bad'])


def test_declaration_view_exposes_outer_return_and_owner_without_changing_evidence() -> None:
    value = isolated_run_bun(r'''
      import {locatedMemoryEvidence,memoryCitationDomain,resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const source='export type Pool = {\n\tflush: () => void;\n};\nexport default function makePool(): Pool;\nexport function wrap<T>(callback: () => PromiseLike<T>): (...args: unknown[]) => Promise<T> & Pick<Pool, "flush">;';
      const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:'api.d.ts',offset:1,limit:200}}]},
        {role:'toolResult',toolName:'read',toolCallId:'r',isError:false,content:source}]};
      const original=JSON.stringify(snapshot),shown=locatedMemoryEvidence(snapshot,{declarationViews:true}),view=shown.entries[1].declarationViews[0];
      const refs=new Set(memoryCitationDomain(snapshot).refs);
      const positions=view.declarations.flatMap(n=>[n.source,...(n.members??[]).map(m=>m.source)]);
      const allRefs=positions.every(p=>refs.has(p.ref)&&refs.has(p.endRef));
      const exact=positions.every(p=>resolveMemoryPlanCitations({newMemories:[{evidence:[{ref:p.ref,endRef:p.endRef}]}]},snapshot).newMemories[0].evidence[0].quote===p.quote);
      console.log(JSON.stringify({view,allRefs,exact,unchanged:JSON.stringify(snapshot)===original,
        sourcePreserved:shown.entries[1].entry.content.citationLines.lines.map(l=>l.text).join('\n')===source}));
    ''')
    assert value['unchanged'] and value['sourcePreserved'] and value['allRefs'] and value['exact']
    view = value['view']
    assert view['status'] == 'available' and view['scope'] == 'observed-region'
    nodes = {n['name']: n for n in view['declarations']}
    assert nodes['makePool']['outerReturnKind'] == 'TSTypeReference'
    assert nodes['makePool']['namedReturn'] == 'Pool'
    assert nodes['makePool']['syntax'] == 'export default function makePool(): Pool;'
    assert nodes['makePool']['outerReturnSyntax'] == 'Pool'
    assert nodes['makePool']['observedTypeCandidate'] == nodes['Pool']['id']
    assert nodes['Pool']['members'][0]['name'] == 'flush'
    assert nodes['wrap']['outerReturnKind'] == 'TSFunctionType'
    assert 'namedReturn' not in nodes['wrap'] and 'observedTypeCandidate' not in nodes['wrap']
    assert 'PromiseLike<T>' in nodes['wrap']['syntax']


def test_declaration_view_refuses_guessed_edges_and_unbound_source() -> None:
    value = isolated_run_bun(r'''
      import {locatedMemoryEvidence} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const show=(source,mutate=()=>{})=>{const s={entries:[{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:'api.d.ts'}}]},
        {role:'toolResult',toolName:'read',toolCallId:'r',isError:false,content:source}]};mutate(s);return locatedMemoryEvidence(s,{declarationViews:true}).entries.at(-1).declarationViews;};
      const duplicates=show('export interface Pool { flush(): void; }\nexport interface Pool { other(): void; }\nexport function make(): Pool;')[0];
      const imports=show('import {Pool} from "./other";\nexport function make(): Pool;\nexport function qualified(): Namespace.Pool;')[0];
      const overloads=show('export interface Pool { flush(): void; }\nexport function make(a: string): Pool;\nexport function make(a: number): Pool;')[0];
      console.log(JSON.stringify({duplicates,imports,overloads,unbound:show('export type Pool = {};',s=>s.entries.shift()),
        failed:show('export type Pool = {};',s=>s.entries[1].isError=true),config:show('export type Pool = {};',s=>s.entries[0].content[0].arguments.path='config.json'),
        malformed:show('export interface Pool {')[0]}));
    ''')
    assert all('observedTypeCandidate' not in n for n in value['duplicates']['declarations'])
    assert all('observedTypeCandidate' not in n for n in value['imports']['declarations'])
    assert value['imports']['declarations'][1]['outerReturnKind'] == 'TSTypeReference'
    assert 'namedReturn' not in value['imports']['declarations'][1]
    overloads = [n for n in value['overloads']['declarations'] if n['name'] == 'make']
    assert len(overloads) == 2 and overloads[0]['id'] != overloads[1]['id']
    assert not value.get('unbound') and not value.get('failed') and not value.get('config')
    assert value['malformed']['status'] == 'omitted' and value['malformed']['reason'] == 'parse-error'


def test_declaration_view_does_not_resolve_a_shadowing_function_type_parameter() -> None:
    value = isolated_run_bun(r'''
      import {locatedMemoryEvidence} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const source='export interface Owner { clear(): void; }\nexport declare function make<Owner>(): Owner;';
      const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:'api.d.ts'}}]},
        {role:'toolResult',toolName:'read',toolCallId:'r',isError:false,content:source}]};
      console.log(JSON.stringify(locatedMemoryEvidence(snapshot,{declarationViews:true}).entries[1].declarationViews[0]));
    ''')
    factory = next(n for n in value['declarations'] if n['name'] == 'make')
    assert factory['namedReturn'] == 'Owner'
    assert 'observedTypeCandidate' not in factory


def test_declaration_view_projects_retained_complete_source_bridge_without_rejudging_knowledge() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import {createHash} from 'node:crypto';
      import {locatedMemoryEvidence} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const f=JSON.parse(fs.readFileSync('packages/continual-learning/tests/fixtures/real-description-body-conflict.json','utf8')).declarationOwnerBridgeCase;
      const source=f.sourceText,snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:'index.d.ts'}}]},
        {role:'toolResult',toolName:'read',toolCallId:'r',isError:false,content:source}]};
      const view=locatedMemoryEvidence(snapshot,{declarationViews:true}).entries[1].declarationViews[0];
      const factory=view.declarations.find(n=>n.name==='pLimit'),owner=view.declarations.find(n=>n.name==='LimitFunction');
      console.log(JSON.stringify({sourceBound:createHash('sha256').update(source).digest('hex')===f.provenance.sourceSha256,
        factory,owner,member:owner.members.find(n=>n.name==='clearQueue'),oldCandidateUnchanged:f.originalContent,
        sourceCopy:locatedMemoryEvidence(snapshot,{declarationViews:true}).entries[1].entry.content.citationLines.lines.map(l=>l.text).join('\n')===source}));
    ''')
    assert value['sourceBound'] and value['sourceCopy']
    assert value['factory']['observedTypeCandidate'] == value['owner']['id']
    assert value['factory']['syntax'].startswith('export default function pLimit')
    assert value['factory']['source']['characters'] == 77
    assert value['factory']['source']['withinCitationLimit']
    assert value['member']['name'] == 'clearQueue'
    assert value['owner']['source']['characters'] > 2000 and not value['owner']['source']['withinCitationLimit']
    assert 'clearQueue: () => void;' in value['oldCandidateUnchanged']


def test_declaration_view_keeps_crlf_refs_region_offsets_and_bounds_explicit() -> None:
    value = isolated_run_bun(r'''
      import {locatedMemoryEvidence,resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const source='// emoji 🪶\r\nexport interface Owner { clear(): void; }\r\nexport function make(): Owner;';
      const show=(text,tool='read',offset=1)=>{const s={entries:[{role:'assistant',content:[{type:'toolCall',id:'r',name:tool,arguments:{path:'api.d.ts',offset}}]},
        {role:'toolResult',toolName:tool,toolCallId:'r',isError:false,content:text}]};return {s,entry:locatedMemoryEvidence(s,{declarationViews:true}).entries[1]};};
      const normal=show(source),nodes=normal.entry.declarationViews[0].declarations;
      const exact=nodes.every(n=>source.slice(n.source.syntaxStart,n.source.syntaxEnd)===n.syntax);
      const refs=nodes.every(n=>resolveMemoryPlanCitations({operations:[{evidence:[{ref:n.source.ref,endRef:n.source.endRef}]}]},normal.s).operations[0].evidence[0].quote===n.source.quote);
      const region=show(source+'\n[lines 101-103 of 200]','learning_read',101),truncated=show(source+'\n[lines 1-3 of 200; byte limit reached]','learning_read');
      const huge=show('export interface Owner {\n'+Array.from({length:110},(_,i)=>'field'+i+'x'.repeat(100)+'(): void;').join('\n')+'\n}');
      const tooMany=show(Array.from({length:129},(_,i)=>'export type T'+i+' = {};').join('\n'));
      const longLine=show('export type Owner = { /*'+'x'.repeat(2200)+'*/ clear(): void; };');
      console.log(JSON.stringify({exact,refs,region:region.entry.declarationViews[0],regionSourceUnchanged:region.entry.entry.content.citationLines.lines.map(l=>l.text).join('\n')===source+'\n[lines 101-103 of 200]',
        truncated:truncated.entry.declarationViews[0],huge:huge.entry.declarationViews[0],tooMany:tooMany.entry.declarationViews[0],longLine:longLine.entry.declarationViews[0]}));
    ''')
    assert value['exact'] and value['refs'] and value['regionSourceUnchanged']
    assert value['region']['status'] == 'available' and value['region']['scope'] == 'observed-region'
    assert value['truncated']['reason'] == 'truncated-region'
    assert value['huge']['status'] == 'omitted' and value['huge']['reason'] == 'view-size-limit'
    assert value['tooMany']['status'] == 'omitted' and value['tooMany']['omittedNodeCount'] == 129
    assert value['longLine']['declarations'] == [] and value['longLine']['omittedNodeCount'] == 1


def test_declaration_views_are_generation_opt_in_with_one_total_metadata_budget() -> None:
    value = isolated_run_bun(r'''
      import {locatedMemoryEvidence} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const source='export interface Owner { clear(): void; }\nexport function make(): Owner;';
      const entries=Array.from({length:50},(_,i)=>[{role:'assistant',content:[{type:'toolCall',id:'r'+i,name:'read',arguments:{path:'api.d.ts'}}]},
        {role:'toolResult',toolName:'read',toolCallId:'r'+i,isError:false,content:source}]).flat();
      const snapshot={entries},plain=locatedMemoryEvidence(snapshot),shown=locatedMemoryEvidence(snapshot,{declarationViews:true});
      console.log(JSON.stringify({defaultHasView:plain.entries.some(e=>e.declarationViews),defaultSummary:plain.declarationViewSummary,
        shownHasView:shown.entries.some(e=>e.declarationViews),summary:shown.declarationViewSummary,
        originalSourceEqual:JSON.stringify(plain.entries.map(e=>e.entry))===JSON.stringify(shown.entries.map(e=>e.entry))}));
    ''')
    assert not value['defaultHasView'] and not value.get('defaultSummary')
    assert not value['shownHasView'] and value['originalSourceEqual']
    assert value['summary']['reason'] == 'projection-size-limit'
    assert value['summary']['totalEntries'] == 100 and value['summary']['maximumMetadataBytes'] == 32000


def test_declaration_view_bounds_members_and_refuses_ambiguous_read_provenance() -> None:
    value = isolated_run_bun(r'''
      import {locatedMemoryEvidence} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const source='export interface Owner {\n'+Array.from({length:129},(_,i)=>'f'+i+'(): void;').join('\n')+'\n}';
      const build=()=>({entries:[{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:'api.d.ts'}}]},
        {role:'toolResult',toolName:'read',toolCallId:'r',isError:false,content:source}]});
      const view=s=>locatedMemoryEvidence(s,{declarationViews:true}).entries.at(-1).declarationViews;
      const big=build(),duplicate=build(),offset=build(),privatePath=build();duplicate.entries.unshift(duplicate.entries[0]);
      offset.entries[0].content[0].arguments.offset=-1;privatePath.entries[0].content[0].arguments.path='/project/.MEMORY/api.d.ts';
      const dossier={kind:'incremental-learning-dossier',taskSlice:big,selectedMemories:[]};
      console.log(JSON.stringify({big:view(big)[0],duplicate:view(duplicate),offset:view(offset),privatePath:view(privatePath),
        dossier:locatedMemoryEvidence(dossier,{declarationViews:true}).taskSlice.entries.at(-1).declarationViews[0],
        defaultDossier:locatedMemoryEvidence(dossier).taskSlice.entries.at(-1).declarationViews}));
    ''')
    assert value['big']['status'] == 'omitted' and value['big']['reason'] == 'node-count-limit'
    assert value['big']['omittedNodeCount'] == 130
    assert value['dossier'] == value['big']
    assert not value.get('duplicate') and not value.get('offset') and not value.get('privatePath') and not value.get('defaultDossier')


def test_file_reference_capabilities_require_unique_successful_project_file_observations():
    value = isolated_run_bun(r'''
      import {memoryCitationDomain} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const base=()=>({entries:[{role:'user',content:'A fact.'},{role:'assistant',content:[{type:'toolCall',id:'r',name:'read',arguments:{path:'/project/source.ts',offset:1,limit:10}}]},{role:'toolResult',toolName:'read',toolCallId:'r',isError:false,content:'first\nsecond'}]});
      const files=v=>memoryCitationDomain(v,{fileSourcesFromCwd:'/project'}).fileRefs;
      const bad={};for(const [name,mutate]of Object.entries({failed:v=>v.entries[2].isError=true,bash:v=>{v.entries[1].content[0].name='bash';v.entries[2].toolName='bash'},outside:v=>v.entries[1].content[0].arguments.path='/other/source.ts',private:v=>v.entries[1].content[0].arguments.path='/project/.MeMoRy/fact.md',settings:v=>v.entries[1].content[0].arguments.path='/project/.pi/settings.json',git:v=>v.entries[1].content[0].arguments.path='/project/.git/config',duplicateCall:v=>v.entries[1].content.push(v.entries[1].content[0]),duplicateResult:v=>v.entries.push(v.entries[2]),wrongName:v=>v.entries[1].content[0].name='edit',missingCall:v=>v.entries[1].content=[],badOffset:v=>v.entries[1].content[0].arguments.offset=0,badLimit:v=>v.entries[1].content[0].arguments.limit=-1})){
        const v=base();mutate(v);bad[name]=files(v);
      }
      const edit=base();edit.entries[1].content[0]={type:'toolCall',id:'r',name:'edit',arguments:{path:'/project/source.ts',oldText:'old',newText:'new'}};edit.entries[2]={role:'toolResult',toolCallId:'r',toolName:'edit',isError:false,content:'Edited',details:{patch:'-old\n+new'}};
      console.log(JSON.stringify({good:files(base()),bad,legacy:memoryCitationDomain(base()),edit:files(edit)}));
    ''')
    assert value['good'] == ['e2.b0.l1', 'e2.b0.l2']
    assert all(refs == [] for refs in value['bad'].values())
    assert 'fileRefs' not in value['legacy']
    assert value['edit'] == ['e2.b0.p2']


def test_linear_file_reference_projection_preserves_prior_position_selection_and_order():
    value = isolated_run_bun(r'''
      import {locatedMemoryEvidence,memoryCitationDomain} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const wide=String.fromCodePoint(0x20000),long='z'.repeat(511)+wide+'x'.repeat(2500),results=[];
      for(const [tool,content,patch] of [['read','first\r\n'+long+'\nlast',null],['read',[{type:'text',text:'first\nsecond'},{type:'image',data:'ignored'},{type:'text',text:long}],null],['edit','Edit completed','-old\r\n+new\r\n+'+long+'\n context\n+++ metadata']]){
        const result={role:'toolResult',toolName:tool,toolCallId:'r',isError:false,content,...(patch===null?{}:{details:{patch}})};
        const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'r',name:tool,arguments:{path:'/project/api.ts',oldText:'old',newText:'new'}}]},result]};
        const shown=locatedMemoryEvidence(snapshot).entries[1].entry;
        const positions=(lines,isPatch)=>lines.flatMap(row=>row.ref?[{ref:row.ref,patch:isPatch,line:row.line}]:((row.chunks??[]).filter(c=>c.ref).map(c=>({ref:c.ref,patch:isPatch,line:row.line,start:c.start}))));
        const parts=Array.isArray(shown.content)?shown.content:[shown.content];
        const observed=parts.flatMap(part=>part?.citationLines?positions(part.citationLines.lines,false):[]);
        if(shown.details?.patch?.citationLines)observed.push(...positions(shown.details.patch.citationLines.lines,true));
        const prior=observed.filter(position=>tool==='read'?!position.patch:position.patch&&(position.start===undefined||position.start===0)&&patch.split('\n')[position.line-1].startsWith('+')&&!patch.split('\n')[position.line-1].startsWith('+++')).map(position=>position.ref);
        const actual=memoryCitationDomain(snapshot,{fileSourcesFromCwd:'/project'}).fileRefs;
        results.push({same:JSON.stringify(prior)===JSON.stringify(actual),count:actual.length});
      }
      console.log(JSON.stringify({results}));
    ''')
    assert all(result['same'] and result['count'] > 0 for result in value['results'])
