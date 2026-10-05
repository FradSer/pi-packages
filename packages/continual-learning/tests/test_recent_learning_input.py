from __future__ import annotations

from support import run_bun


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
