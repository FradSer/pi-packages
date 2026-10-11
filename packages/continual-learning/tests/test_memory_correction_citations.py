from support import run_bun


def test_cited_rewrite_survives_expansion_and_parent_citation_validation():
    value = run_bun('''
      import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
      import {expandIncrementalMemoryPlan} from './packages/continual-learning/extensions/incremental-memory-plan.ts';
      import {candidateCitationProblems,expandCitedIncrementalMemoryPlan} from './packages/continual-learning/extensions/inject-memory.ts';
      const root=await fs.mkdtemp(path.join(os.tmpdir(),'cl-cited-update-'));
      await fs.writeFile(path.join(root,'MEMORY.md'),'# Memory\\n- [fact.md](fact.md)\\n');
      await fs.writeFile(path.join(root,'fact.md'),'The old value.');
      const snapshot={schemaVersion:1,runId:'run_update',scopeKey:'k',entries:[{message:{role:'user',content:'Correction: the current value is new.'}}]};
      const text=JSON.stringify(snapshot);const digest=new Bun.CryptoHasher('sha256').update(text).digest('hex');
      const snapshotFile=path.join(root,'snapshot.json');await fs.writeFile(snapshotFile,text);
      const manifest={runId:'run_update',scopeKey:'k',scopeDigest:'d',snapshotDigest:digest,harnessDir:root,cwd:root};
      const evidence=[{index:0,quote:'Correction: the current value is new.',role:'user'}];
      const delta={kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:'run_update',scopeKey:'k',scopeDigest:'d',artifactHash:manifest.snapshotDigest,snapshotDigest:manifest.snapshotDigest,
        operations:[{name:'fact.md',kind:'rewrite',classification:'safe',content:'The current value is new.',evidence}],newMemories:[]};
      try {
        const run={manifest,paths:{snapshotFile}};
        const plan=await expandCitedIncrementalMemoryPlan(run,['fact.md'],delta);
        const uncited=structuredClone(delta);delete uncited.operations[0].evidence;
        let rejected=false;try{await expandCitedIncrementalMemoryPlan(run,['fact.md'],uncited)}catch(e){rejected=e.message.includes('no citation')}
        if(!rejected)throw Error('Uncited corrected plan accepted');
        console.log(JSON.stringify({evidence:plan.operations[0].evidence,problems:candidateCitationProblems(snapshot,plan.operations)}));
      } finally {await fs.rm(root,{recursive:true,force:true})}
    ''')
    assert value['evidence'] == [{'index':0,'quote':'Correction: the current value is new.','role':'user'}]
    assert value['problems'] == []


def test_assistant_claim_cannot_authorize_memory_correction():
    value = run_bun('''
      import {candidateCitationProblems} from './packages/continual-learning/extensions/inject-memory.ts';
      console.log(JSON.stringify(candidateCitationProblems({entries:[{message:{role:'assistant',content:'A made-up fact.'}}]},
        [{evidence:[{index:0,quote:'A made-up fact.'}]}])));
    ''')
    assert value and 'user or tool' in value[0]
