from support import isolated_run_bun


def test_memory_start_ignores_hash_key_order_but_rejects_actual_source_changes():
    # Given the real Memory startup path and a bound selection, When the same
    # hashes arrive in another traversal order, Then reach spawn; changed bytes
    # still stop before any worker. No model or network request is admitted.
    result = isolated_run_bun(r'''
      import {plugin} from 'bun';import {mock} from 'bun:test';
      import fs from 'node:fs';import path from 'node:path';
      plugin({name:'private-startup-test',setup(build){build.onLoad({filter:/[/]inject-memory\.ts$/},args=>({contents:fs.readFileSync(args.path,'utf8')+'\nexport {spawnAsyncConsolidation};',loader:'ts'}));}});
      const original=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const kit=await import('./packages/kit/index.ts');const root=process.env.PI_CODING_AGENT_DIR;
      const dossierPath=path.join(root,'dossier.json');fs.writeFileSync(dossierPath,JSON.stringify({taskSlice:{entries:[]},selectedMemories:[]}));
      const selected={harness:{'a.md':'a'.repeat(64),'b.md':'b'.repeat(64)},public:{}};
      let current={harness:{'b.md':'b'.repeat(64),'a.md':'a'.repeat(64)},public:{}},spawns=0;
      mock.module('./packages/continual-learning/extensions/consolidation-run.ts',()=>({...original,
        createConsolidationRun:async()=>({manifest:{runId:'test',scopeKey:'s',scopeDigest:'d',snapshotDigest:'d',runDir:root,harnessDir:'private',publicDir:'public',sourceHashes:current},normalization:{repaired:[],removed:[]}}),
        hashMemoryRoot:async root=>root==='private'?current.harness:current.public,releaseConsolidationRun:async()=>{}}));
      mock.module('./packages/kit/index.ts',()=>({...kit,resolvePiCli:()=>({command:'forbidden',args:[]}),spawnPiChild:()=>{spawns++;throw Error('OFFLINE_SPAWN_BOUNDARY');}}));
      const module=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const source=fs.readFileSync('./packages/continual-learning/extensions/inject-memory.ts','utf8');
      // Compute the selected identity with the exact production selection expression.
      const expression=source.match(/selectedSourceDigest = ([^;]+selectorRun\.manifest\.sourceHashes[^;]+);/)[1];
      const selectedDigest=new Function('selectorRun','sha256Digest','digest',`return ${expression}`)({manifest:{sourceHashes:selected}},original.sha256Digest,original.digest);
      const outcomes=[];for(const change of ['order','changed','added','removed']){current={harness:{'b.md':'b'.repeat(64),'a.md':'a'.repeat(64)},public:{}};if(change==='changed')current.harness['a.md']='c'.repeat(64);if(change==='added')current.harness['c.md']='c'.repeat(64);if(change==='removed')delete current.harness['a.md'];let error;const notices=[];
        try{await module.spawnAsyncConsolidation({ui:{notify:m=>notices.push(m)}},{active:false,cancelled:false,generation:0},{cwd:root,pkgDir:root,reason:'test',mode:'automatic',dossierPath,dossierDigest:original.sha256Digest(fs.readFileSync(dossierPath)),selectedSourceDigest:selectedDigest,selectedScope:['a.md'],applyChanges:false});}catch(e){error=e.message}
        outcomes.push({spawns,error,notices});}
      console.log(JSON.stringify({outcomes,externalRequests:0}));
    ''')
    assert result['outcomes'][0]['spawns'] == 1, result
    assert 'OFFLINE_SPAWN_BOUNDARY' in str(result['outcomes'][0]['notices'])
    for outcome in result['outcomes'][1:]:
        assert outcome['spawns'] == 1, result
        assert outcome['error'] == 'selected Memory changed after incremental selection'
