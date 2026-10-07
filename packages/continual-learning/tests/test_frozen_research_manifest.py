from support import isolated_run_bun


def test_frozen_manifest_rejects_source_and_sample_drift() -> None:
    # Given initially captured manifest bytes, When samples or registered code
    # change, Then the run rejects drift and never binds a new hash to old inputs.
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';import {createHash} from 'node:crypto';
      import {readFrozenResearchManifest} from './packages/continual-learning/tests/frozen-research-manifest.ts';
      const dir=await fs.mkdtemp(path.join(os.tmpdir(),'cl-frozen-study-'));const outputs=[];
      try{const code=path.join(dir,'code.ts'),file=path.join(dir,'manifest.json');const original='source';await fs.writeFile(code,original);
       const manifest={codeHashes:{'code.ts':createHash('sha256').update(original).digest('hex')},samples:[{id:'original'}]};const bytes=JSON.stringify(manifest);await fs.writeFile(file,bytes);
       const frozen=await readFrozenResearchManifest(new URL('file://'+file));await frozen.verify();outputs.push(frozen.sha256===createHash('sha256').update(bytes).digest('hex'));
       await fs.writeFile(file,JSON.stringify({...manifest,samples:[{id:'changed'}]}));try{await frozen.verify();outputs.push(false);}catch{outputs.push(true);}
       await fs.writeFile(file,bytes);await fs.writeFile(code,'changed');try{await frozen.verify();outputs.push(false);}catch{outputs.push(true);}
       await fs.writeFile(code,original);await frozen.verify();outputs.push(frozen.value.samples[0].id==='original');
      }finally{await fs.rm(dir,{recursive:true,force:true});}console.log(JSON.stringify(outputs));
    ''')
    assert value == [True, True, True, True]
