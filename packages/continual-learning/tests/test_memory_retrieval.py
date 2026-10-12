from __future__ import annotations
from support import run_bun


def test_related_complete_memory_is_delivered_with_revision_not_authority() -> None:
    value = run_bun(r'''
      import {retrieveMemory} from './packages/continual-learning/extensions/memory-retrieval.ts';
      const entry=(filename,description,content)=>({filename,description,content,readPath:'/private/'+filename,source:'harness'});
      const entries=[entry('scheduler.md','paused scheduler concurrency','Verified scheduler reserves slots before starting callbacks.'),
        entry('release.md','release package publishing','Release uses a different command.'),
        entry('large.md','paused scheduler concurrency','x'.repeat(20000))];
      const result=retrieveMemory('Fix paused scheduler concurrency',entries);
      console.log(JSON.stringify({result,again:retrieveMemory('Fix paused scheduler concurrency',[{...entries[0],content:'Corrected scheduler behavior.'}]),
        unrelated:retrieveMemory('Change unrelated typography',entries)}));
    ''')
    assert [e['filename'] for e in value['result']['entries']] == ['scheduler.md']
    assert 'untrusted reference' in value['result']['content']
    assert 'Verified scheduler reserves' in value['result']['content']
    assert len(value['result']['entries'][0]['revision']) == 64
    assert value['again']['entries'][0]['revision'] != value['result']['entries'][0]['revision']
    assert value['unrelated']['entries'] == []


def test_latest_delivery_targets_win_without_exceeding_complete_content_budget() -> None:
    value = run_bun(r'''
      import {deliveredMemoryNames,retrieveMemory} from './packages/continual-learning/extensions/memory-retrieval.ts';
      const ref=names=>({customType:'continual-learning-memory-reference',details:{retrieved:names.map(filename=>({filename,revision:'a'.repeat(64),readPath:'/private/'+filename}))}});
      console.log(JSON.stringify({names:deliveredMemoryNames([ref(['a.md','b.md','c.md']),ref(['corrected.md'])]),length:retrieveMemory('scheduler concurrency',[1,2,3].map(n=>({filename:`scheduler-${n}.md`,description:'scheduler concurrency',content:'x'.repeat(3800),readPath:'/private/a'}))).content.length}));
    ''')
    assert value['names'][0] == 'corrected.md'
    assert value['length'] <= 8000


def test_explicit_memory_selection_does_not_inherit_unrelated_previous_delivery() -> None:
    import tempfile
    from support import isolated_run_bun
    with tempfile.TemporaryDirectory(prefix='cl-selection-scope-') as root:
        value = isolated_run_bun(r'''
          import {mock} from 'bun:test';import fs from 'node:fs';import path from 'node:path';import {execFileSync} from 'node:child_process';
          const cwd=path.join(process.env.TEST_ROOT,'project');fs.mkdirSync(cwd);execFileSync('git',['init','-q',cwd]);fs.mkdirSync(path.join(cwd,'.memory'));
          for(const name of ['requested','unrelated'])fs.writeFileSync(path.join(cwd,'.memory',name+'.md'),`---\nname: ${name}\ndescription: ${name} project fact\ntype: project\n---\n${name} body\n`);
          const kit=await import('./packages/kit/src/index.ts');mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>({text:JSON.stringify({kind:'incremental-memory-selection',version:1,contextDigest:'scope-digest',selected:['requested.md'],memory:true,harness:false,agents:false,reason:'Only the explicitly requested entry.'}),exitCode:0,stderr:'',cancelled:false})}));
          const {selectIncrementalLearning}=await import('./packages/continual-learning/extensions/incremental-learning.ts');
          const result=await selectIncrementalLearning({cwd,contextDigest:'scope-digest',outputDir:path.join(process.env.TEST_ROOT,'output'),memoryOnly:true,taskSlice:{kind:'learning-task-slice',version:1,entries:[{customType:'continual-learning-memory-reference',details:{retrieved:[{filename:'unrelated.md',revision:'a'.repeat(64),readPath:'/private/unrelated.md'}]}},{message:{role:'user',content:'Update requested.md only.'}}]}});
          console.log(JSON.stringify({outcome:result.outcome,selected:result.selection?.selected}));
        ''', {'TEST_ROOT':root})
    assert value == {'outcome':'selected','selected':['requested.md']}


def test_actual_wrapper_task_keeps_contract_body_despite_generic_prompt_words() -> None:
    # Given actual learned Memory and the full v24 maintenance prompt,
    # When ranking complete bodies, Then generic instruction words must not
    # displace the relevant wrapper contract, or alter its conditions/revision.
    value = run_bun(r'''
      import fs from 'node:fs';import {createHash} from 'node:crypto';
      import {retrieveMemory} from './packages/continual-learning/extensions/memory-retrieval.ts';
      const f=JSON.parse(fs.readFileSync('packages/continual-learning/tests/fixtures/real-memory-retrieval-ranking.json','utf8'));
      const result=retrieveMemory(f.query,f.entries);
      const contract=f.entries.find(e=>e.filename==='limit_function_type_contract.md');
      console.log(JSON.stringify({result,contract,revision:createHash('sha256').update(contract.content).digest('hex'),
        generic:retrieveMemory('Only when this is not a task you must implement',f.entries)}));
    ''')
    assert 'limit_function_type_contract.md' in [e['filename'] for e in value['result']['entries']]
    assert value['contract']['content'] in '\n'.join(__import__('json').loads(line)['body'] for line in value['result']['content'].splitlines() if line.startswith('{'))
    assert next(e['revision'] for e in value['result']['entries'] if e['filename'] == value['contract']['filename']) == value['revision']
    assert len(value['result']['entries']) <= 3
    assert len(value['result']['content']) <= 8000
    assert value['generic']['entries'] == []


def test_domain_terms_compound_types_chinese_and_explicit_names_keep_recall() -> None:
    value = run_bun(r'''
      import {retrieveMemory} from './packages/continual-learning/extensions/memory-retrieval.ts';
      const queries=['CAN bus','before after','Promise contract','队列并发','only.md'];
      const descriptions=['CAN bus','before after','PromiseLike-returning contract','队列并发','Unrelated entry'];
      console.log(JSON.stringify(queries.map((query,i)=>retrieveMemory(query,[{
        filename:i===4?'only.md':'domain.md',description:descriptions[i],content:'Complete reference body.',readPath:'/isolated/domain.md'
      }]).entries.length)));
    ''')
    assert value == [1, 1, 1, 1, 1]
