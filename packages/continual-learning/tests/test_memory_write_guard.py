from support import run_bun


def test_reference_memory_is_read_only_for_ordinary_model_tools():
    result = run_bun('''
      import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
      import {memoryWriteBlock} from './packages/continual-learning/extensions/memory-write-guard.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      const base=await fs.mkdtemp(path.join(os.tmpdir(),'cl-write-boundary-'));
      process.env.PI_CODING_AGENT_DIR=path.join(base,'agent');
      const cwd=path.join(base,'project');await fs.mkdir(cwd);Bun.spawnSync(['git','init','-q',cwd]);
      const roots=resolveMemoryPaths(cwd);await fs.mkdir(roots.harnessDir,{recursive:true});
      await fs.mkdir(roots.publicDir,{recursive:true});await fs.symlink(roots.publicDir,path.join(cwd,'alias'));
      try {
        const check=(name,p)=>Boolean(memoryWriteBlock(cwd,name,{path:p}));
        console.log(JSON.stringify({shared:check('write','.memory/answer.json'),private:check('edit',path.join(roots.harnessDir,'fact.md')),
          alias:check('write','alias/new.md'),traversal:check('write','work/../.memory/fact.md'),
          output:check('write','answer.json'),similar:check('write','.memory-notes.md'),read:check('read','.memory/fact.md')}));
      } finally {await fs.rm(base,{recursive:true,force:true})}
    ''')
    assert result == {'shared':True,'private':True,'alias':True,'traversal':True,
                      'output':False,'similar':False,'read':False}


def test_write_guard_matches_native_pi_path_normalization():
    result = run_bun('''
      import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';import {pathToFileURL} from 'node:url';
      import {createWriteTool} from '@earendil-works/pi-coding-agent';
      import {memoryWriteBlock} from './packages/continual-learning/extensions/memory-write-guard.ts';
      const base=await fs.mkdtemp(path.join(os.tmpdir(),'cl-path-parity-'));
      const cwd=path.join(base,'project space');await fs.mkdir(cwd);Bun.spawnSync(['git','init','-q',cwd]);
      process.env.PI_CODING_AGENT_DIR=path.join(base,'agent');
      const target=path.join(cwd,'.memory/fact.md');
      const paths=['@.memory/fact.md',pathToFileURL(target).href,'~/' + path.relative(os.homedir(),target),target.replaceAll(' ','\\u00a0')];
      try {
        const rows=[];
        for(const p of paths){
          await createWriteTool(cwd).execute('test',{path:p,content:'native'});
          rows.push({native:await fs.readFile(target,'utf8')==='native',blocked:Boolean(memoryWriteBlock(cwd,'write',{path:p}))});
          await fs.unlink(target);
        }
        console.log(JSON.stringify(rows));
      } finally {await fs.rm(base,{recursive:true,force:true})}
    ''')
    assert all(row['native'] and row['blocked'] for row in result)
