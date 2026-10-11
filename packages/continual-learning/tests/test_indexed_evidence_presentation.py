"""Parent-generated citation labels do not alter authoritative evidence."""
from support import run_bun


def test_real_long_evidence_gets_exact_indexes_without_changing_originals():
    value=run_bun(r'''
      import {indexedMemoryEvidence} from './packages/continual-learning/extensions/evidence-presentation.ts';
      const {evidence}=await Bun.file('./packages/continual-learning/tests/fixtures/real-project-wire.json').json();
      const original=JSON.stringify(evidence);
      const shown=indexedMemoryEvidence(evidence);
      const dossier={kind:'incremental-learning-dossier',taskSlice:evidence,selectedMemories:[]};
      const display=indexedMemoryEvidence(dossier);
      console.log(JSON.stringify({count:shown.entries.length,unchanged:JSON.stringify(evidence)===original,
        indexes:shown.entries.map(e=>e.snapshotIndex),exact:shown.entries.every((e,i)=>JSON.stringify(e.entry)===JSON.stringify(evidence.entries[i])),
        same:JSON.stringify(display.taskSlice)===JSON.stringify(shown),selected:display.selectedMemories}));
    ''')
    assert value['count']==205
    assert value['indexes']==list(range(205))
    assert value['unchanged'] and value['exact'] and value['same']
    assert value['selected']==[]


def test_scoped_read_projection_is_opt_in_and_keeps_file_unchanged():
    value=run_bun(r'''
      import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
      import {readPlannerFile} from './packages/continual-learning/extensions/planner-read-scope.ts';
      const dir=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'indexed-evidence-')));
      try {
        const file=path.join(dir,'dossier.json');
        const raw=JSON.stringify({kind:'incremental-learning-dossier',taskSlice:{entries:[{id:'nonsequential-b',message:{role:'assistant',content:'same quote'}},{id:'nonsequential-a',message:{role:'toolResult',content:'same quote'}}]}});
        await fs.writeFile(file,raw);const scope={cwd:dir,files:[file],roots:[]};
        const plain=await readPlannerFile(file,scope,1,2000);
        const projected=await readPlannerFile(file,{...scope,indexedEvidence:true},1,2000);
        const parsed=JSON.parse(projected.slice(0,projected.lastIndexOf('\n[lines')));
        const page=await readPlannerFile(file,{...scope,indexedEvidence:true},2,3);
        console.log(JSON.stringify({unchanged:await fs.readFile(file,'utf8')===raw,plain:plain.startsWith(raw),
          entries:parsed.taskSlice.entries,pageStable:page.startsWith(projected.split('\n').slice(1,4).join('\n'))}));
      } finally {await fs.rm(dir,{recursive:true,force:true});}
    ''')
    assert value['unchanged'] and value['plain'] and value['pageStable']
    assert [e['snapshotIndex'] for e in value['entries']]==[0,1]
    assert [e['entry']['message']['role'] for e in value['entries']]==['assistant','toolResult']
