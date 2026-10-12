from support import isolated_run_bun


def test_context_loader_checks_both_frozen_files_and_cancellation() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises'; import os from 'node:os'; import path from 'node:path'; import {createHash} from 'node:crypto';
      const {loadFrozenMemoryRepairContext}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const root=await fs.mkdtemp(path.join(os.tmpdir(),'repair-context-'));const snapshotPath=path.join(root,'snapshot.json'),dossierPath=path.join(root,'dossier.json');
      const frozenEvidence={entries:[{role:'user',content:'Only this task: summarize results.'}]};const existingMemories=[];
      const snapshot=JSON.stringify(frozenEvidence),dossier=JSON.stringify({selectedMemories:existingMemories});const digest=s=>createHash('sha256').update(s).digest('hex');
      await fs.writeFile(snapshotPath,snapshot);await fs.writeFile(dossierPath,dossier);
      const input={snapshotPath,snapshotDigest:digest(snapshot),dossierPath,dossierDigest:digest(dossier)};
      try{const loaded=await loadFrozenMemoryRepairContext(input);await loaded.assertFrozen();
        const checks=[];for(const file of [snapshotPath,dossierPath]){await fs.writeFile(file,'{}');try{await loadFrozenMemoryRepairContext(input);checks.push(false)}catch{checks.push(true)};await fs.writeFile(file,file===snapshotPath?snapshot:dossier)}
        await fs.writeFile(dossierPath,'{}');let after=false;try{await loaded.assertFrozen()}catch{after=true};await fs.writeFile(dossierPath,dossier);
        const controller=new AbortController();controller.abort();let cancelled=false;try{await loadFrozenMemoryRepairContext({...input,signal:controller.signal})}catch{cancelled=true};
        console.log(JSON.stringify({context:loaded.context,checks,after,cancelled}));
      }finally{await fs.rm(root,{recursive:true,force:true})}
    ''')
    assert value['checks'] == [True, True]
    assert value['after'] and value['cancelled']
    assert value['context']['frozenEvidence']['entries'][0]['content'] == 'Only this task: summarize results.'


def test_repair_cannot_reclassify_a_private_proposal() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let calls=0;
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[{name:'preference.md',kind:'project-fact',classification:'private',content:'A private preference.',evidence:[{index:0,quote:'Keep this preference private.'}]}]};
      const changed=structuredClone(original);changed.newMemories[0].kind='preference';changed.newMemories[0].classification='safe';
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{calls++;return{exitCode:0,stderr:'',text:JSON.stringify(changed),cancelled:false}}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,errors:['invalid kind'],selectedNames:[],semanticContext:{frozenEvidence:{entries:[{role:'user',content:'Keep this preference private.'}]},existingMemories:[]}});
      console.log(JSON.stringify({outcome:result.outcome,calls}));
    ''')
    assert value == {'outcome': 'failed', 'calls': 1}


def test_structural_worker_receives_grounding_context_in_same_read_only_call() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');const inputs=[];
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const plan={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[{name:'fact.md',kind:'project',classification:'private',content:'Project uses pnpm.',evidence:[{index:0,quote:'Project uses pnpm.'}]}]};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{inputs.push(input);return{exitCode:0,stderr:'',text:JSON.stringify(plan),cancelled:false}}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const context={frozenEvidence:{entries:[{role:'user',content:'Project uses pnpm. Only this task: summarize failures.'}]},existingMemories:[]};
      const outcome=await repairIncrementalMemoryPlan({identity,rejectedPlan:plan,errors:['invalid kind'],selectedNames:[],structuralCorrection:true,semanticContext:context});
      console.log(JSON.stringify({outcome:outcome.outcome,calls:inputs.length,tools:inputs[0].tools,context:JSON.parse(inputs[0].prompt.split('\n').at(-1)).semanticContext,structural:inputs[0].prompt.includes('existing structural correction slot'),temporary:inputs[0].prompt.includes('Do not promote one-task instructions')}));
    ''')
    assert value['outcome'] == 'repaired' and value['calls'] == 1
    assert value['tools'] == [] and value['structural'] and value['temporary']
    assert value['context']['frozenEvidence']['entries'] == [{'snapshotIndex': 0, 'entry': {'role': 'user', 'content': {'citationLines': {'block': 0, 'lines': [{'line': 1, 'text': 'Project uses pnpm. Only this task: summarize failures.'}]}}}}]


def test_production_structural_repair_holds_tampering_and_accounts_paid_attempt() -> None:
    from pathlib import Path
    from support import run_bun_script
    fixture = Path(__file__).with_name('learning-policy-harness.ts')
    for reason in ('structural-held', 'structural-tamper-snapshot', 'structural-tamper-dossier'):
        value = run_bun_script(fixture, 'remember-shared', env={'CL_JEV_FIXTURE': reason})
        assert value['structuralContextReceived'] and value['totalRepairs'] == (2 if reason == 'structural-held' else 1)
        assert value['semanticRepairs'] == (1 if reason == 'structural-held' else 0) and not value['memoryMirrored']
        attempts = [a for a in value['registryReceipt']['attempts'] if a['phase'] == 'memory']
        assert len(attempts) == (3 if reason == 'structural-held' else 2) and attempts[1]['usage']['input'] == 10, reason
        if reason != 'structural-held':
            assert value['jevValidations'] == []
        assert value['registryReceipt']['operations'] == 0
