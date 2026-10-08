from support import isolated_run_bun


def test_standalone_readiness_keeps_strict_thresholds_and_never_write_authority() -> None:
    value = isolated_run_bun(r'''
      import {interpretStandaloneMemory} from './packages/continual-learning/tests/jev-standalone-memory-research.ts';
      const answer=(choice='selfContained',confidence=1,p=.99)=>({type:'choice',choice,confidence,
        probabilities:{selfContained:choice==='selfContained'?p:(1-p)/2,needsOther:choice==='needsOther'?p:(1-p)/2,unresolved:choice==='unresolved'?p:(1-p)/2}});
      const inputs=[answer(),answer('selfContained',.79),answer('selfContained',1,.89),answer('needsOther'),answer('unresolved'),{},
        {...answer(),probabilities:{...answer().probabilities,extra:0}},answer('selfContained',NaN),{...answer(),type:'noul'}];
      console.log(JSON.stringify(inputs.map(interpretStandaloneMemory)));
    ''')
    assert value[0]['standaloneObserved']
    assert all(not row['standaloneObserved'] for row in value[1:])
    assert all(row['writeAuthorized'] is False for row in value)
    assert [row['status'] for row in value[:5]] == ['decided', 'uncertain', 'uncertain', 'decided', 'uncertain']
    assert all(row['status'] == 'invalid-response' for row in value[5:])


def test_standalone_question_retains_complete_originals_and_both_semantic_fields() -> None:
    value = isolated_run_bun(r'''
      import {standaloneMemoryState,standaloneMemoryQuestion} from './packages/continual-learning/tests/jev-standalone-memory-research.ts';
      const evidence={entries:[{role:'user',content:'Use pnpm. A transient cache timeout recovered.'}]};
      const candidates=['Use pnpm.','Cache always fails.'].map((body,i)=>({name:`${i}.md`,content:`---
name: fact-${i}
description: ${body}
type: project
---
${body}`,evidence:[{index:0,quote:evidence.entries[0].content}]}));
      const state=standaloneMemoryState(evidence,candidates,0);
      let denied=false;try{standaloneMemoryState(evidence,candidates,2)}catch{denied=true}
      console.log(JSON.stringify({state,evidence,candidates,denied,question:standaloneMemoryQuestion()}));
    ''')
    assert value['state']['originalEvidence'] == value['evidence']
    assert value['state']['originalCandidates'] == value['candidates']
    assert value['state']['target']['body'] == 'Use pnpm.'
    assert value['state']['target']['description'] == 'Use pnpm.'
    assert value['denied']
    assert value['question']['type'] == 'choice'


def test_research_rejects_unfrozen_sdk_or_policy_before_reserving_or_calling() -> None:
    # Given forged SDK/threshold metadata, When the evaluator starts, Then it
    # rejects before reservations or transport. No real files are modified.
    for change in [{'sdkVersion': '0.7.0'}, {'retry': 1}, {'thresholds': {'confidence': .7, 'probability': .9}}]:
        import json

        value = isolated_run_bun(r'''
          import fs from 'node:fs/promises';
          import {historicalResearchPath} from './packages/continual-learning/tests/historical-research-source.ts';
          const original=fs.readFile.bind(fs); const change=CHANGE;
          fs.readFile=async function(file,...args){
            file=historicalResearchPath(file);
            // Preserve this historical study's source bytes while isolating
            // forged policy metadata. No manifest, snapshot or real file edits.
            const source=String(file).endsWith('/extensions/independent-memory-partition.ts')
              ? new URL('./packages/continual-learning/tests/fixtures/composed-partition-preintegration/independent-memory-partition.ts',`file://${process.cwd()}/`)
              : file;
            const legacyName=['jev-learning.ts','inject-memory.ts','learning-efficiency.ts','jev-memory-relations.ts'].find(name=>String(file).endsWith('/extensions/'+name));
            const frozenSource=legacyName ? new URL('./packages/continual-learning/tests/fixtures/composed-parent-preintegration/'+legacyName,`file://${process.cwd()}/`) : source;
            const bytes=await original(frozenSource,...args);
            if(String(file).endsWith('jev-standalone-memory-study-manifest.json'))
              return Buffer.from(JSON.stringify({...JSON.parse(String(bytes)),...change}));
            return bytes;
          };
          let reservations=0,requests=0;
          fs.open=async()=>{reservations++;throw new Error('Unexpected reservation')};
          globalThis.fetch=async()=>{requests++;throw new Error('Unexpected network')};
          process.argv.push('--preflight-only');let error='';
          try{await import('./packages/continual-learning/tests/evaluate_jev_standalone_memory.ts')}catch(e){error=e.message}
          console.log(JSON.stringify({error,reservations,requests}));
        '''.replace('CHANGE', json.dumps(change)))
        assert value['error'] == 'Invalid fixed research bounds or SDK version'
        assert value['reservations'] == value['requests'] == 0
