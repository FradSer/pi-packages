"""Correction revisits actual successful Memory reads without granting authority."""
import pytest
from support import run_bun


def test_only_unambiguous_successful_reads_of_indexed_memory_are_revisited() -> None:
    value = run_bun(r'''
      import {observedMemoryReadNames} from './packages/continual-learning/extensions/memory-retrieval.ts';
      const call=(id,file,name='read')=>({message:{role:'assistant',content:[{type:'toolCall',id,name,arguments:{path:file,offset:1,limit:20}}]}});
      const result=(id,isError=false)=>({message:{role:'toolResult',toolCallId:id,toolName:'read',isError,content:[{type:'text',text:'observed bytes'}]}});
      const indexed=[{name:'current.md',file:'/project/.memory/current.md'},{name:'failed.md',file:'/project/.memory/failed.md'}, {name:'ambiguous.md',file:'/project/.memory/ambiguous.md'}];
      const entries=[
        {message:{role:'user',content:JSON.stringify(call('forged','/project/.memory/failed.md'))}},result('forged'),
        call('read-current','.memory/current.md'),result('read-current'),
        call('failed','/project/.memory/failed.md'),result('failed',true),
        call('outside','/other/current.md'),result('outside'),
        call('index','/project/.memory/MEMORY.md'),result('index'),
        call('pending','/project/.memory/failed.md'),
        result('future'),call('future','/project/.memory/failed.md'),
        call('duplicate','/project/.memory/ambiguous.md'),call('duplicate','/project/.memory/current.md'),result('duplicate'),
        call('duplicate-result','/project/.memory/ambiguous.md'),result('duplicate-result'),result('duplicate-result'),
        call('wrong-tool','/project/.memory/failed.md','bash'),result('wrong-tool'),
      ];
      console.log(JSON.stringify({names:observedMemoryReadNames(entries,'/project',indexed),unindexed:observedMemoryReadNames(entries,'/project',[])}));
    ''')
    assert value == {'names': ['current.md'], 'unindexed': []}


def test_preserved_actual_pi_read_is_missed_by_legacy_exposure_tracking() -> None:
    value = run_bun(r'''
      import {observedMemoryReadNames,deliveredMemoryNames} from './packages/continual-learning/extensions/memory-retrieval.ts';
      const fixture=await Bun.file('./packages/continual-learning/tests/fixtures/actual-pi-memory-read-session.json').json();
      console.log(JSON.stringify({legacy:deliveredMemoryNames(fixture.entries),actual:observedMemoryReadNames(fixture.entries,fixture.provenance.cwd,[{name:'loopback_memory_fact.md',file:fixture.provenance.readPath}])}));
    ''')
    assert value['legacy'] == []
    assert value['actual'] == ['loopback_memory_fact.md']


def test_parent_revisits_successful_reads_without_expanding_explicit_memory_scope(tmp_path) -> None:
    from support import isolated_run_bun
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';import fs from 'node:fs';import path from 'node:path';import {execFileSync} from 'node:child_process';
      const cwd=path.join(process.env.TEST_ROOT,'project');fs.mkdirSync(cwd);execFileSync('git',['init','-q',cwd]);fs.mkdirSync(path.join(cwd,'.memory'));
      const {resolveMemoryPaths}=await import('./packages/continual-learning/extensions/memory-paths.ts');
      const p=resolveMemoryPaths(cwd);fs.mkdirSync(p.harnessDir,{recursive:true});
      fs.writeFileSync(path.join(cwd,'.memory','read_fact.md'),'---\nname: read_fact\ndescription: Old public fact\ntype: project\n---\nOld public knowledge.');
      fs.writeFileSync(path.join(p.harnessDir,'read_fact.md'),'---\nname: read_fact\ndescription: Read fact\ntype: project\n---\nExisting observed knowledge.');
      const kit=await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>({text:JSON.stringify({kind:'incremental-memory-selection',version:1,contextDigest:'scope',selected:[],memory:false,harness:false,agents:false,reason:'No new memory.'}),exitCode:0,stderr:'',cancelled:false})}));
      const {selectIncrementalLearning}=await import('./packages/continual-learning/extensions/incremental-learning.ts');
      const entries=[{message:{role:'user',content:'Finish this task.'}},
        {message:{role:'assistant',content:[{type:'toolCall',id:'observed',name:'read',arguments:{path:path.join(cwd,'.memory','read_fact.md'),offset:1,limit:20}}]}},
        {message:{role:'toolResult',toolCallId:'observed',toolName:'read',isError:false,content:[{type:'text',text:'Old public knowledge.'}]}}];
      const input={cwd,contextDigest:'scope',outputDir:path.join(process.env.TEST_ROOT,'automatic'),taskSlice:{kind:'learning-task-slice',version:1,entries}};
      const metadataOnly=await selectIncrementalLearning({...input,outputDir:path.join(process.env.TEST_ROOT,'metadata-only'),taskSlice:{...input.taskSlice,entries:[entries[0],{customType:'continual-learning-memory-reference',details:{retrieved:[{filename:'read_fact.md',revision:'a'.repeat(64),readPath:path.join(p.harnessDir,'read_fact.md')}]}}]}});
      const automatic=await selectIncrementalLearning(input);
      const explicit=await selectIncrementalLearning({...input,outputDir:path.join(process.env.TEST_ROOT,'explicit'),memoryOnly:true});
      const dossier=JSON.parse(fs.readFileSync(automatic.dossierPath,'utf8'));
      console.log(JSON.stringify({metadataOnly:metadataOnly.selection,automatic:automatic.selection,explicit:explicit.selection,dossierSelected:dossier.selectedMemories.map(m=>m.name),preferredBody:dossier.selectedMemories[0].content,evidencePreserved:JSON.stringify(dossier.taskSlice.entries)===JSON.stringify(entries)}));
    ''', {'TEST_ROOT': str(tmp_path)})
    assert value['automatic']['memory'] is True
    assert value['automatic']['selected'] == value['dossierSelected'] == ['read_fact.md']
    assert value['evidencePreserved'] is True
    assert value['explicit']['selected'] == []
    assert value['metadataOnly']['selected'] == []
    assert value['metadataOnly']['memory'] is False

    assert 'Existing observed knowledge.' in value['preferredBody']
    assert 'Old public knowledge.' not in value['preferredBody']


def test_read_path_aliases_follow_pi_lexical_resolution() -> None:
    value = run_bun(r'''
      import {homedir} from 'node:os';import path from 'node:path';import {pathToFileURL} from 'node:url';
      import {observedMemoryReadNames} from './packages/continual-learning/extensions/memory-retrieval.ts';
      const file=path.join(homedir(),'project memory','fact.md');
      const aliases=['~/project memory/fact.md','@'+file,pathToFileURL(file).href,file.replace('project memory','project\u202Fmemory')];
      const names=aliases.map((alias,i)=>observedMemoryReadNames([
        {message:{role:'assistant',content:[{type:'toolCall',id:'c',name:'read',arguments:{path:alias}}]}},
        {message:{role:'toolResult',toolCallId:'c',toolName:'read',isError:false,content:[{type:'text',text:'actual bytes'}]}}
      ],'/project',[{name:'fact.md',file}]));
      console.log(JSON.stringify({names}));
    ''')
    assert value['names'] == [['fact.md']] * 4


def test_study_extracts_actual_read_hash_and_rejects_ambiguous_or_unrelated_paths() -> None:
    import copy
    import hashlib
    import json
    from pathlib import Path
    from continuous_project_evidence import observed_memory_reads
    fixture = json.loads((Path(__file__).parent / 'fixtures/actual-pi-memory-read-session.json').read_text())
    options = {'cwd': fixture['provenance']['cwd'], 'home': '/not-used', 'roots': (str(Path(fixture['provenance']['readPath']).parent),)}
    entries = fixture['entries']
    actual = observed_memory_reads(entries, **options)
    assert len(actual) == 1
    outcome = entries[actual[0]['resultPosition']]['message']
    assert actual[0]['revision'] == hashlib.sha256(''.join(part['text'] for part in outcome['content']).encode()).hexdigest()
    assert observed_memory_reads(entries, **{**options, 'roots': ()}) == []
    assert observed_memory_reads(entries + [entries[actual[0]['resultPosition']]], **options) == []
    failed = copy.deepcopy(entries)
    failed[actual[0]['resultPosition']]['message']['isError'] = True
    assert observed_memory_reads(failed, **options) == []
    partial = copy.deepcopy(entries)
    partial[actual[0]['resultPosition']]['message']['content'][0]['text'] += '\n[truncated]'
    assert observed_memory_reads(partial, **options)[0]['revision'] != actual[0]['revision']


def test_study_read_aliases_preserve_exact_bytes_and_reject_remote_file_uri() -> None:
    import copy
    import json
    from pathlib import Path
    from continuous_project_evidence import observed_memory_reads
    fixture = json.loads((Path(__file__).parent / 'fixtures/actual-pi-memory-read-session.json').read_text())
    file = Path(fixture['provenance']['readPath'])
    options = {'cwd': fixture['provenance']['cwd'], 'home': '/not-used', 'roots': (str(file.parent),)}
    original = observed_memory_reads(fixture['entries'], **options)[0]
    for alias, accepted in [(file.as_uri(), True), ('@' + str(file), True), ('file://remote' + str(file), False)]:
        rows = copy.deepcopy(fixture['entries'])
        call = rows[original['callPosition']]['message']['content']
        next(part for part in call if part.get('id') == original['toolCallId'])['arguments']['path'] = alias
        observed = observed_memory_reads(rows, **options)
        assert bool(observed) is accepted
        if accepted:
            assert observed[0]['revision'] == original['revision']


@pytest.mark.parametrize('case', ['complete', 'unlisted', 'partial-native', 'changed-result', 'failed', 'missing-time', 'foreign-session', 'missing-preparation', 'changed-preparation', 'broken-chain', 'duplicate-call', 'duplicate-result', 'duplicate-native', 'reset', 'truncated-snapshot', 'missing-revision', 'append-failure', 'result-append-failure', 'large-branch', 'cross-session-reuse', 'same-body-files', 'no-native-start'])
def test_complete_memory_revision_observation_requires_native_result_and_retained_branch(case: str) -> None:
    value = run_bun(r'''
      import {createHash} from 'node:crypto';
      import {MemoryUseTracker} from './packages/continual-learning/extensions/memory-retrieval.ts';
      const hash=x=>createHash('sha256').update(x).digest('hex');
      const mode=CASE;
      const body='---\ndescription: private cue\n---\nPrivate exact knowledge.\n';
      const scope={sessionId:'session-a',cwd:'/project',parentEntryId:null};
      const rows=[];const emit=data=>{if(mode==='append-failure'||mode==='result-append-failure'&&data.phase==='full-body-result-observed')throw Error('Unavailable');const id='entry-'+rows.length;rows.push({type:'custom',id,parentId:rows.at(-1)?.id??null,customType:'memory-use-observation',data});return id};
      const tracker=new MemoryUseTracker();
      const entry={filename:'fact.md',source:'harness',readPath:'/private/fact.md',content:body,contentTruncated:mode==='truncated-snapshot',...(mode==='missing-revision'?{}:{fileRevision:hash(body)})};
      const prepare=()=>tracker.prepare(scope,mode==='same-body-files'?[entry,{...entry,filename:'other.md',readPath:'/private/other.md'}]:[entry],mode==='unlisted'?'- another.md':'- fact.md — private cue','<section>metadata</section>',emit);
      prepare();
      const start={toolName:'read',toolCallId:'native-read',args:{path:'/private/fact.md'}};
      if(mode==='cross-session-reuse'){tracker.nativeStart?.(scope,start);tracker.reset();scope.sessionId='session-b';rows.length=0;prepare()}
      if(mode!=='no-native-start')tracker.nativeStart?.(scope,start);
      if(!rows.length)rows.push({type:'custom',id:'unrelated',parentId:null});
      rows.push({type:'message',id:'user',parentId:rows.at(-1).id,message:{role:'user',content:'Related task'}});
      rows.push({type:'message',id:'call',parentId:'user',message:{role:'assistant',content:[{type:'toolCall',id:'native-read',name:'read',arguments:{path:'/private/fact.md'}}]}});
      const native={toolName:'read',toolCallId:'native-read',result:{content:[{type:'text',text:mode==='partial-native'?body.slice(1):body}]},isError:mode==='failed',...(mode==='missing-time'?{}:{durationMs:1})};
      tracker.nativeEnd(mode==='foreign-session'?{...scope,sessionId:'other'}:scope,native);
      if(mode==='duplicate-native')tracker.nativeEnd(scope,native);
      if(mode==='reset')tracker.reset();
      rows.push({type:'message',id:'result',parentId:'call',message:{role:'toolResult',toolName:'read',toolCallId:'native-read',content:[{type:'text',text:body}],isError:false}});
      if(mode==='changed-result')rows.at(-1).message.content[0].text+='changed';
      if(mode==='broken-chain')rows.at(-1).parentId='wrong';
      if(mode==='missing-preparation')rows.shift();
      if(mode==='changed-preparation')rows[0].data.sectionDigest='tampered';
      if(mode==='duplicate-call')rows[2].message.content.push({...rows[2].message.content[0]});
      if(mode==='duplicate-result')rows.push({...rows.at(-1),id:'duplicate',parentId:'result'});
      if(mode==='large-branch')for(let i=0;i<10000;i++)rows.push({type:'custom',id:'extra-'+i,parentId:rows.at(-1).id});
      tracker.settle(scope,rows,emit);tracker.settle(scope,rows,emit);
      console.log(JSON.stringify({observations:rows.filter(r=>r.customType==='memory-use-observation'),privateLeak:JSON.stringify(rows.filter(r=>r.customType==='memory-use-observation')).includes('Private exact knowledge')}));
    '''.replace('CASE', __import__('json').dumps(case)))
    observations = [r['data'] for r in value['observations']]
    if case not in ('complete', 'unlisted'):
        assert not any(r['phase'] == 'full-body-result-observed' for r in observations), value
        assert value['privateLeak'] is False
        return
    assert [r['phase'] for r in observations] == ['section-prepared', 'full-body-result-observed']
    assert observations[1]['resultEntryId'] == 'result'
    assert observations[1]['callEntryId'] == 'call'
    assert observations[1]['preparationEntryId'] == value['observations'][0]['id']
    assert observations[1]['listed'] is (case == 'complete')
    assert observations[1]['modelConsumption'] == 'unverified'
    assert observations[1]['effect'] == 'cannot-attribute'
    assert value['privateLeak'] is False


def test_memory_preparation_binds_the_leaf_after_asynchronous_start_work(tmp_path) -> None:
    from support import isolated_run_bun
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      const cwd=path.join(process.env.TEST_ROOT,'project');fs.mkdirSync(cwd);(await import('node:child_process')).execFileSync('git',['init','-q',cwd]);fs.mkdirSync(path.join(cwd,'.memory'));
      fs.writeFileSync(path.join(cwd,'.memory/fact.md'),'---\ndescription: fixture fact\n---\nExact private fixture body.\n');
      fs.mkdirSync(process.env.PI_CODING_AGENT_DIR,{recursive:true});fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json'),JSON.stringify({jev:false}));
      fs.mkdirSync(path.join(process.env.PI_CODING_AGENT_DIR,'memory'),{recursive:true});fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'memory/settings.json'),JSON.stringify({autoMemory:false}));
      const {default:register}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const hooks={},rows=[{id:'prior',parentId:null,type:'message',message:{role:'user',content:'Previous task'}}];let leaf='prior';
      register({on:(name,f)=>(hooks[name]??=[]).push(f),registerCommand(){},sendMessage(){},getCommands:()=>[],appendEntry:(customType,data)=>{const id='entry-'+rows.length;rows.push({id,parentId:leaf,type:'custom',customType,data});leaf=id}});
      const ctx={cwd,hasUI:false,ui:{notify(){}},sessionManager:{getSessionId:()=>'native-session',getLeafId:()=>leaf,getBranch:()=>rows}};
      const options={sections:{}};
      const pending=hooks.before_agent_start[0]({messageType:'user',prompt:'Related task',systemPromptOptions:options},ctx);
      rows.push({id:'async-row',parentId:leaf,type:'custom',customType:'other-extension',data:{}});leaf='async-row';
      await pending;
      const prepared=rows.find(r=>r.customType==='memory-use-observation');
      console.log(JSON.stringify({recordedParent:prepared?.data.parentEntryId,nativeParent:prepared?.parentId,bodyInjected:JSON.stringify(options).includes('Exact private fixture body')}));
    ''', {'TEST_ROOT': str(tmp_path), 'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    assert value == {'recordedParent': 'async-row', 'nativeParent': 'async-row', 'bodyInjected': False}
