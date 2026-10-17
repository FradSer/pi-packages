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
