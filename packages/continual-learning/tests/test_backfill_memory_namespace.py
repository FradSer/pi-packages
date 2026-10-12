from support import isolated_run_bun


def test_actual_backfill_collision_is_rejected_before_review_without_overwriting() -> None:
    # Given the actual v22 plan creates an existing unselected entry, When
    # expanding it, Then reject before paying for semantic review; the final
    # apply guard must independently continue to prevent overwrites.
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import path from 'node:path';
      import {applyConsolidationPlan} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {expandIncrementalMemoryPlan} from './packages/continual-learning/extensions/incremental-memory-plan.ts';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-backfill-name-collision.json').json();
      const root=process.env.PI_CODING_AGENT_DIR,harness=path.join(root,'private'),pub=path.join(root,'public');
      for(const [key,dir] of [['harness',harness],['public',pub]]) {
        await fs.mkdir(dir);for(const [name,body] of Object.entries(f.before[key]))await fs.writeFile(path.join(dir,name),body);
      }
      const snapshotFile=path.join(root,'snapshot.json');await fs.writeFile(snapshotFile,f.snapshotText);
      const run={manifest:{...f.manifest,harnessDir:harness,publicDir:pub},paths:{snapshotFile}};
      const delta={...Object.fromEntries(['version','schemaVersion','runId','scopeKey','scopeDigest','artifactHash','snapshotDigest','operations','newMemories'].map(k=>[k,f.plan[k]])),kind:'incremental-memory-plan'};
      let early='',late='';
      try{await expandIncrementalMemoryPlan(run,f.plan.selected,delta);}catch(e){early=e.message;}
      try{await applyConsolidationPlan(run,f.plan);}catch(e){late=e.message;}
      let preserved=true;
      for(const [key,dir] of [['harness',harness],['public',pub]])for(const [name,body] of Object.entries(f.before[key]))preserved&&=await fs.readFile(path.join(dir,name),'utf8')===body;
      console.log(JSON.stringify({early,late,preserved}));
    ''', temp_dirs=('PI_CODING_AGENT_DIR',))
    assert 'would overwrite an existing memory: nested-limit-deadlock-warning.md' in value['late']
    assert value['preserved']
    assert 'already exists outside selected scope: nested-limit-deadlock-warning.md' in value['early']


def test_planner_receives_occupied_names_without_expanding_selected_scope() -> None:
    value = isolated_run_bun(r'''
      import {buildIncrementalMemoryConsolidatorPrompt} from './packages/continual-learning/extensions/planner-prompts.ts';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-backfill-name-collision.json').json();
      const names=[...new Set([...Object.keys(f.manifest.sourceHashes.harness),...Object.keys(f.manifest.sourceHashes.public)])].sort();
      const prompt=buildIncrementalMemoryConsolidatorPrompt({...f.plan,dossierPath:'/frozen/dossier.json',existingMemoryNames:names});
      const namespace=JSON.parse(prompt.split('Reserved existing Memory filenames (parent snapshot, untrusted names only):\n')[1].split('\n')[0]);
      console.log(JSON.stringify({namespace,selected:f.plan.selected,scope:prompt.includes('this namespace grants no read or mutation scope')}));
    ''')
    assert 'nested-limit-deadlock-warning.md' in value['namespace']
    assert 'nested-limit-deadlock-warning.md' not in value['selected']
    assert value['scope']
