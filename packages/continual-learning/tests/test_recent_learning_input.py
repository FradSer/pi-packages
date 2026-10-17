from __future__ import annotations

from support import run_bun


def test_actual_pi12_empty_timeout_removal_keeps_exact_failed_task_replay(tmp_path) -> None:
    import json
    # Given the actual V53 retry log, When Pi removes only an empty failed
    # assistant reply, Then exact replay remains digest-bound and retains the
    # failure without reviving deleted message content.
    result = run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {recentProjectLearningInput} from './packages/continual-learning/extensions/learning-input.ts';
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {sha256Digest,containsSensitiveMemoryMaterial} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {successfulFailureObservationReady} from './packages/continual-learning/tests/failure-observation-proof.ts';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-pi12-timeout-context-edit.json','utf8'));
      const root=ROOT,cwd=path.join(root,'project'),agent=path.join(root,'agent'),dir=path.join(agent,'sessions','scope');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(dir,{recursive:true});
      const original=f.files['orientation/without-learning/verifier-feedback/session.jsonl'].text;
      const rows=original.trimEnd().split('\n').map(JSON.parse);rows[0].cwd=cwd;
      const file=path.join(dir,'stage-0.jsonl'),text=rows.map(JSON.stringify).join('\n')+'\n';fs.writeFileSync(file,text);
      const source=await recentProjectLearningInput({cwd,agentDir:agent,sessionDir:dir,requestedSessionFile:file});
      const task=source?.contextEntries?currentTaskSlice(source.contextEntries.slice(f.queued.from,f.queued.to+1)):undefined;
      const read=rows.filter(row=>row.message?.role==='toolResult'&&row.message.toolName==='read').at(-1);
      const proof=successfulFailureObservationReady({
        originalSession:f.files['orientation/without-learning/session.jsonl'].text,currentSession:original,
        verifierText:read.message.content[0].text,verifierPath:'/home/node/project-verification.json',
        sourceBefore:f.observation.sourceHashes,sourceAfter:f.observation.sourceHashes,queued:f.queued,explicitBackfills:0});
      console.log(JSON.stringify({proof,accepted:!!source,rawUnchanged:fs.readFileSync(file,'utf8')===text,
        sourceBound:source?.sourceDigest===sha256Digest(text),taskDigest:task?sha256Digest(JSON.stringify(task)):null,expectedDigest:f.queued.digest,
        removedReplyProjected:source?!source.entries.some(x=>x.id==='00be88a8'):false,
        sensitive:containsSensitiveMemoryMaterial(JSON.stringify(f)),historicalFailure:f.provenance.status}));
    '''.replace('ROOT', json.dumps(str(tmp_path))))
    assert result['rawUnchanged'] and not result['sensitive'] and result['historicalFailure'] == 'failed'
    assert result['accepted'] and result['sourceBound'] and result['removedReplyProjected']
    assert result['taskDigest'] == result['expectedDigest']
    assert result['proof']['ready'], result['proof']


def test_exact_replay_sanitizes_removed_error_metadata_and_refuses_meaningful_edits(tmp_path) -> None:
    import json
    result = run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {recentProjectLearningInput} from './packages/continual-learning/extensions/learning-input.ts';
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-pi12-timeout-context-edit.json','utf8'));
      const root=ROOT,cwd=path.join(root,'project'),agent=path.join(root,'agent'),dir=path.join(agent,'sessions','scope');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(dir,{recursive:true});
      const original=f.files['orientation/without-learning/verifier-feedback/session.jsonl'].text.trimEnd().split('\n').map(JSON.parse);
      const file=path.join(dir,'source.jsonl'),results={};let sanitized,digest;
      const changes={metadata:(target,edit)=>{target.message.errorMessage='REMOVED_PRIVATE_ERROR';target.message.provider='REMOVED_PRIVATE_PROVIDER';target.message.model='REMOVED_PRIVATE_MODEL'},
        text:target=>target.message.content=[{type:'text',text:'REMOVED_PRIVATE_TEXT'}],
        thinking:target=>target.message.content=[{type:'thinking',thinking:'REMOVED_PRIVATE_THOUGHT'}],
        user:target=>target.message={role:'user',content:'REMOVED_PRIVATE_USER'},
        tool:target=>target.message={role:'toolResult',toolName:'read',toolCallId:'removed',content:[{type:'text',text:'REMOVED_PRIVATE_TOOL'}]},
        summary:target=>{delete target.message;target.type='compaction';target.summary='REMOVED_PRIVATE_SUMMARY'},
        replacement:(_target,edit)=>edit.replacement={role:'assistant',content:[{type:'text',text:'Replacement'}]},
        aborted:target=>target.message.stopReason='aborted',successful:target=>target.message.stopReason='stop',
        unknownTarget:(_target,edit)=>edit.targetId='missing',extraWrapper:target=>target.privateNote='REMOVED_PRIVATE_OUTER',
        extraEdit:(_target,edit)=>edit.privateNote='REMOVED_PRIVATE_EDIT',timestamp:target=>target.message.timestamp='REMOVED_PRIVATE_TIMESTAMP',
        outerTimestamp:target=>target.timestamp={privateNote:'REMOVED_PRIVATE_OUTER_TIMESTAMP'},
        outerTimestampText:target=>target.timestamp='REMOVED_PRIVATE_OUTER_TIMESTAMP',
        editTimestamp:(_target,edit)=>edit.timestamp={privateNote:'REMOVED_PRIVATE_EDIT_TIMESTAMP'}};
      for(const [name,change] of Object.entries(changes)){
        const rows=structuredClone(original);rows[0].cwd=cwd;
        const edit=rows.find(x=>x.type==='context_edit'),target=rows.find(x=>x.id===edit.targetId);change(target,edit);
        fs.writeFileSync(file,rows.map(JSON.stringify).join('\n')+'\n');
        const source=await recentProjectLearningInput({cwd,agentDir:agent,sessionDir:dir,requestedSessionFile:file});results[name]=!!source;
        if(name==='metadata'&&source){
          sanitized=!JSON.stringify({entries:source.entries,context:source.contextEntries}).includes('REMOVED_PRIVATE_');
          digest=sha256Digest(JSON.stringify(currentTaskSlice(source.contextEntries.slice(f.queued.from,f.queued.to+1))));
        }
      }
      console.log(JSON.stringify({results,sanitized,digest,expected:f.queued.digest}));
    '''.replace('ROOT', json.dumps(str(tmp_path))))
    assert result['results'].pop('metadata') and result['sanitized']
    assert not any(result['results'].values()), result['results']
    assert result['digest'] == result['expected']


def test_recent_project_input_uses_active_context_without_mutating_source() -> None:
    result = run_bun(r'''
      import fs from 'node:fs'; import path from 'node:path';
      import {recentProjectLearningInput} from './packages/continual-learning/extensions/learning-input.ts';
      const root=process.env.TEST_ROOT, cwd=path.join(root,'project'), agent=path.join(root,'agent'), dir=path.join(agent,'sessions','scope');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(dir,{recursive:true});
      const rows=[{type:'session',version:3,id:'previous',cwd,timestamp:new Date().toISOString()},
        {type:'message',id:'u',parentId:null,timestamp:new Date().toISOString(),message:{role:'user',content:'This project uses pnpm.'}},
        {type:'message',id:'a',parentId:'u',timestamp:new Date().toISOString(),message:{role:'assistant',content:[]}}];
      const file=path.join(dir,'previous.jsonl'), original=rows.map(JSON.stringify).join('\n')+'\n';fs.writeFileSync(file,original);
      const result=await recentProjectLearningInput({cwd,agentDir:agent,sessionDir:dir,currentSessionFile:path.join(dir,'current.jsonl')});
      console.log(JSON.stringify({result,unchanged:fs.readFileSync(file,'utf8')===original}));
    ''', temp_dirs=("TEST_ROOT",))
    assert result["unchanged"] is True
    assert result["result"]["sessionId"] == "previous"
    assert len(result["result"]["sourceDigest"]) == 64
    assert result["result"]["entries"][0]["message"]["content"] == "This project uses pnpm."


def test_recent_project_input_rejects_wrong_scope_aliases_and_removed_context() -> None:
    result = run_bun(r'''
      import fs from 'node:fs'; import path from 'node:path';
      import {recentProjectLearningInput} from './packages/continual-learning/extensions/learning-input.ts';
      const root=process.env.TEST_ROOT,cwd=path.join(root,'project'),agent=path.join(root,'agent'),dir=path.join(agent,'sessions','scope');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(dir,{recursive:true});
      const header=project=>({type:'session',version:3,id:'fixture',cwd:project,timestamp:new Date().toISOString()});
      const user={type:'message',id:'u',parentId:null,timestamp:new Date().toISOString(),message:{role:'user',content:'Private project fact'}};
      const write=(file,rows)=>fs.writeFileSync(file,rows.map(JSON.stringify).join('\n')+'\n');
      write(path.join(dir,'wrong.jsonl'),[header(path.join(root,'other')),user]);
      const outside=path.join(root,'outside.jsonl');write(outside,[header(cwd),user]);fs.symlinkSync(outside,path.join(dir,'linked.jsonl'));
      write(path.join(dir,'removed.jsonl'),[header(cwd),user,{type:'context_edit',id:'edit',parentId:'u',targetId:'u',replacement:null,timestamp:new Date().toISOString()}]);
      const value=await recentProjectLearningInput({cwd,agentDir:agent,sessionDir:dir});
      console.log(JSON.stringify(value??null));
    ''', temp_dirs=("TEST_ROOT",))
    assert result is None


def test_recent_input_rejects_cycles_duplicate_ids_and_missing_parents() -> None:
    result = run_bun(r'''
      import fs from 'node:fs'; import path from 'node:path';
      import {recentProjectLearningInput} from './packages/continual-learning/extensions/learning-input.ts';
      const root=process.env.TEST_ROOT,cwd=path.join(root,'project'),agent=path.join(root,'agent'),dir=path.join(agent,'sessions','scope');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(dir,{recursive:true});
      const header={type:'session',version:3,id:'fixture',cwd,timestamp:new Date().toISOString()};
      const user={type:'message',id:'u',parentId:null,timestamp:new Date().toISOString(),message:{role:'user',content:'This project uses pnpm.'}};
      const cases=[[{...user,parentId:'u'}],[user,{...user}], [{...user,parentId:'missing'}],
        [{...user,parentId:'b'},{...user,id:'b',parentId:'u'}]];
      const results=[];
      for(const rows of cases){fs.writeFileSync(path.join(dir,'source.jsonl'),[header,...rows].map(JSON.stringify).join('\n')+'\n');
        results.push((await recentProjectLearningInput({cwd,agentDir:agent,sessionDir:dir}))??null);}
      console.log(JSON.stringify(results));
    ''', temp_dirs=("TEST_ROOT",), timeout=2)
    assert result == [None] * 4



def test_v1_projection_never_revives_removed_summaries_or_user_messages() -> None:
    result = run_bun(r''' 
      import {mock} from 'bun:test';
      const sdk=await import('./node_modules/@earendil-works/pi-coding-agent/dist/index.js');
      const exports={...sdk};mock.module('./packages/continual-learning/node_modules/@earendil-works/pi-coding-agent/dist/index.js',()=>exports);
      const {recentProjectLearningInput}=await import('./packages/continual-learning/extensions/learning-input.ts');
      const fs=await import('node:fs'),path=await import('node:path');
      const root=process.env.TEST_ROOT,cwd=path.join(root,'project'),agent=path.join(root,'agent'),dir=path.join(agent,'sessions','scope');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(dir,{recursive:true});
      const timestamp=new Date().toISOString();
      const rows=[{type:'session',version:3,id:'fixture',cwd,timestamp},
        {type:'message',id:'old',parentId:null,timestamp,message:{role:'user',content:'REMOVED_PRIVATE_USER'}},
        {type:'compaction',id:'summary',parentId:'old',timestamp,summary:'REMOVED_PRIVATE_SUMMARY',firstKeptEntryId:'old',tokensBefore:1},
        {type:'context_edit',id:'edit1',parentId:'summary',timestamp,targetId:'summary',replacement:null},
        {type:'context_edit',id:'edit2',parentId:'edit1',timestamp,targetId:'old',replacement:null},
        {type:'message',id:'new',parentId:'edit2',timestamp,message:{role:'user',content:'Retain this project fact.'}}];
      const file=path.join(dir,'source.jsonl'),original=rows.map(JSON.stringify).join('\n')+'\n';fs.writeFileSync(file,original);
      const value=await recentProjectLearningInput({cwd,agentDir:agent,sessionDir:dir});
      console.log(JSON.stringify({value,unchanged:fs.readFileSync(file,'utf8')===original}));
    ''', temp_dirs=("TEST_ROOT",))
    assert result["unchanged"] is True
    assert len(result["value"]["entries"]) == 1
    assert result["value"]["entries"][0]["message"]["content"] == "Retain this project fact."


def test_recent_input_bounds_cancellation_and_current_source_exclusion() -> None:
    result = run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {recentProjectLearningInput} from './packages/continual-learning/extensions/learning-input.ts';
      const root=process.env.TEST_ROOT,cwd=path.join(root,'project'),agent=path.join(root,'agent'),dir=path.join(agent,'sessions','scope');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(dir,{recursive:true});
      const rows=[{type:'session',version:3,id:'fixture',cwd,timestamp:new Date().toISOString()},
        {type:'message',id:'u',parentId:null,message:{role:'user',content:'Use pnpm.'}}];
      const file=path.join(dir,'source.jsonl'),data=rows.map(JSON.stringify).join('\n')+'\n',args={cwd,agentDir:agent,sessionDir:dir};
      const results=[];fs.writeFileSync(file,data);
      results.push(await recentProjectLearningInput({...args,currentSessionFile:file})??null);
      results.push(await recentProjectLearningInput({...args,signal:AbortSignal.abort()})??null);
      fs.writeFileSync(file,data+'broken json\n');results.push(await recentProjectLearningInput(args)??null);
      fs.writeFileSync(file,data);fs.utimesSync(file,new Date(0),new Date(0));results.push(await recentProjectLearningInput(args)??null);
      fs.writeFileSync(file,' '.repeat(8*1024*1024+1));results.push(await recentProjectLearningInput(args)??null);
      const alias=path.join(agent,'sessions','alias');fs.symlinkSync(dir,alias);results.push(await recentProjectLearningInput({...args,sessionDir:alias})??null);
      console.log(JSON.stringify(results));
    ''', temp_dirs=("TEST_ROOT",))
    assert result == [None] * 6
