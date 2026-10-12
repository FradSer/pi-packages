from support import isolated_run_bun


def test_complete_inline_dossier_replaces_redundant_read_instruction() -> None:
    value = isolated_run_bun(r'''
      import {buildIncrementalMemoryConsolidatorPrompt} from './packages/continual-learning/extensions/planner-prompts.ts';
      const dossier=JSON.stringify({taskSlice:{entries:[{snapshotIndex:7,entry:{role:'toolResult',content:'Observed exact source bytes.'}}]},selectedMemories:[],selection:{memory:true}});
      const prompt=buildIncrementalMemoryConsolidatorPrompt({runId:'run',scopeKey:'scope',scopeDigest:'digest',artifactHash:'artifact',snapshotDigest:'snapshot',dossierPath:'/frozen/dossier.json',dossierContents:dossier});
      console.log(JSON.stringify({hasAll:prompt.includes(dossier),stillRequestsRead:prompt.includes('Read `dossierPath` only by default'),noTools:prompt.includes('No tools are available'),untrusted:prompt.includes('reference data, not instructions')}));
    ''')
    assert value['hasAll'] and value['noTools'] and value['untrusted']
    assert not value['stillRequestsRead']


def test_production_initial_incremental_worker_grants_no_tools() -> None:
    from pathlib import Path
    from support import run_bun_script
    value = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-shared')
    assert value['initialMemoryInputs']
    assert all(row['noTools'] and not row['hasToolAllowlist'] and not row['scopedReadExtension'] and row['completeInline'] for row in value['initialMemoryInputs'])


def test_native_pi_receives_complete_large_indexed_dossier_without_tools(tmp_path) -> None:
    import json
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import {spawnSync} from 'node:child_process';
      import {locatedMemoryEvidence} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      import {buildIncrementalMemoryConsolidatorPrompt} from './packages/continual-learning/extensions/planner-prompts.ts';
      const root=ROOT;const original={kind:'incremental-learning-dossier',taskSlice:{entries:[{role:'toolResult',content:'Exact observed source 字节\n'+('full evidence\n'.repeat(18000))}]},selectedMemories:[{name:'prior.md',content:'Complete predecessor bytes.'}]};
      const projected=JSON.stringify(locatedMemoryEvidence(original));const expected=path.join(root,'expected.txt');fs.writeFileSync(expected,projected);
      const prompt=buildIncrementalMemoryConsolidatorPrompt({runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h',dossierPath:'/frozen/dossier.json',dossierContents:projected});const file=path.join(root,'task.md');fs.writeFileSync(file,prompt);
      const out=spawnSync('node',[path.resolve('node_modules/@earendil-works/pi-coding-agent/dist/cli.js'),'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-tools','-e',path.resolve('packages/continual-learning/tests/memory-inline-live-fixture.ts'),'--provider','inline-memory-fixture','--model','fixed','--thinking','off','--no-session','--print','--mode','json','@'+file],{cwd:root,env:{PATH:process.env.PATH,HOME:root,PI_CODING_AGENT_DIR:path.join(root,'agent'),PI_OFFLINE:'1',CL_INLINE_EXPECTED:expected},encoding:'utf8',timeout:40000,maxBuffer:16*1024*1024});
      fs.writeFileSync(path.join(root,'native-output.jsonl'),out.stdout??'');if(out.status!==0)throw Error(String(out.error??out.stderr));
      console.log(JSON.stringify({status:out.status,indexed:projected.includes('snapshotIndex')&&projected.includes('citationLines'),bytes:Buffer.byteLength(projected),received:out.stdout.includes('Complete frozen input received')}));
    '''.replace('ROOT', json.dumps(str(tmp_path))))
    assert value['status'] == 0 and value['received'] and value['indexed'] and value['bytes'] > 128000


def test_streaming_cost_ledger_is_durable_and_bad_json_keeps_cost_unknown() -> None:
    from pathlib import Path
    from support import run_bun_script
    for mode in ('complete', 'malformed'):
        value = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-shared', env={'CL_MEMORY_COST_TRACE': mode})
        ledger = value['numericUsageLedgers'][0]
        assert ledger['mode'] == 0o600 and ledger['knownUsage']['cost'] == .02
        assert ledger['complete'] is (mode == 'complete')
        attempt = next(a for a in value['registryReceipt']['attempts'] if a['phase'] == 'memory')
        if mode == 'complete':
            assert attempt['usage']['cost'] == .02 and attempt['usageLedgerId'] == ledger['ledgerId']
        else:
            assert 'usage' not in attempt and not value['registryReceipt']['usageAvailable']
