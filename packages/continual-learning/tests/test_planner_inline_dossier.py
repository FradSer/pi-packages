"""Parent-built inline dossier: no-tools argv, bounded reads, digest binding.

These are executable contract tests for planner-inline-dossier.ts. They prove
the leaf module's safety gates before any planner child consumes its output.
"""
from __future__ import annotations

from support import run_bun


def test_no_tool_args_use_the_literal_flag_without_an_allowlist() -> None:
    value = run_bun(r'''
      import {plannerNoToolArgs} from './packages/continual-learning/extensions/planner-inline-dossier.ts';
      console.log(JSON.stringify({args:plannerNoToolArgs()}));
    ''')
    args = value['args']
    assert '--no-tools' in args
    assert '--tools' not in args
    assert args[-1] == '--no-tools'
    assert '--print' in args and '--mode' in args


def test_inline_dossier_binds_each_file_to_its_own_digest() -> None:
    value = run_bun(r'''
      import {createHash} from 'node:crypto';
      import {buildInlineDossier, inlineDossierBlock} from './packages/continual-learning/extensions/planner-inline-dossier.ts';
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'inline-dossier-'));
      const digest=s=>createHash('sha256').update(s).digest('hex');
      const a=path.join(root,'snapshot.json'),b=path.join(root,'dossier.json');
      const aText='{"entries":[{"role":"user","content":"Original evidence."}]}\n',bText='{"verified":"project evidence"}\n';
      fs.writeFileSync(a,aText);fs.writeFileSync(b,bText);
      const good=await buildInlineDossier([{path:a,digest:digest(aText)},{path:b,digest:digest(bText)}]);
      const wrongDigest=await buildInlineDossier([{path:a,digest:'0'.repeat(64)}]).then(()=>false).catch(()=>true);
      const noDigest=await buildInlineDossier([{path:b}]);
      const missing=await buildInlineDossier([{path:path.join(root,'absent.json')}]).then(()=>false).catch(()=>true);
      fs.writeFileSync(a,'api_key: abcdefghijklmnop\n');
      const sensitive=await buildInlineDossier([{path:a}]).then(()=>false).catch(()=>true);
      const block=inlineDossierBlock(good.text);
      fs.rmSync(root,{recursive:true,force:true});
      console.log(JSON.stringify({good,wrongDigest,noDigest,missing,sensitive,block}));
    ''')
    good = value['good']
    assert [row['sha256'] for row in good['files']] == [
        __import__('hashlib').sha256(b'{"entries":[{"role":"user","content":"Original evidence."}]}\n').hexdigest(),
        __import__('hashlib').sha256(b'{"verified":"project evidence"}\n').hexdigest(),
    ]
    assert 'Original evidence.' in good['text'] and 'project evidence' in good['text']
    assert len(value['noDigest']['files']) == 1
    assert value['wrongDigest'] and value['missing'] and value['sensitive']
    block = value['block']
    assert '<<<IMMUTABLE DOSSIER>>>' in block and '<<<END IMMUTABLE DOSSIER>>>' in block
    assert 'No tools are available' in block and 'not instructions' in block
    assert good['text'] in block


def test_aggregate_encoded_dossier_is_bounded_not_just_each_file() -> None:
    # Two files each below MAX_SNAPSHOT_BYTES can still overflow when combined
    # with JSON escaping; the complete encoded payload must be bounded.
    value = run_bun(r'''
      import {buildInlineDossier} from './packages/continual-learning/extensions/planner-inline-dossier.ts';
      import {MAX_SNAPSHOT_BYTES} from './packages/continual-learning/extensions/consolidation-run.ts';
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'inline-dossier-bound-'));
      const half=Math.floor(MAX_SNAPSHOT_BYTES/2)+1024;
      const a=path.join(root,'a.txt'),b=path.join(root,'b.txt');
      fs.writeFileSync(a,'a'.repeat(half));fs.writeFileSync(b,'b'.repeat(half));
      const overflow=await buildInlineDossier([{path:a},{path:b}]).then(()=>false).catch(e=>String(e.message));
      fs.rmSync(root,{recursive:true,force:true});
      console.log(JSON.stringify({overflow}));
    ''')
    assert value['overflow'] and 'exceeds' in value['overflow']
