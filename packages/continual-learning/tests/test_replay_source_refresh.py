from support import isolated_run_bun


def test_complete_manual_replay_refreshes_current_sources_without_changing_original_evidence():
    result=isolated_run_bun(r'''
      import {memorySourceAuditRequest} from './packages/continual-learning/extensions/memory-maintenance-audit.ts';
      const replay={mode:'manual',inputSource:{source:'backlog-session',entryCount:50}};
      console.log(JSON.stringify({manual:memorySourceAuditRequest(replay),
        automatic:memorySourceAuditRequest({...replay,mode:'automatic'}),
        ordinary:memorySourceAuditRequest({mode:'manual',inputSource:{source:'current-session'}}),
        incomplete:memorySourceAuditRequest({...replay,inputSource:{...replay.inputSource,omittedEntries:1}}),
        explicit:memorySourceAuditRequest({...replay,memoryRequest:'整理记忆'}),
        otherRequest:memorySourceAuditRequest({...replay,memoryRequest:'remember my editor preference'})}));
    ''')
    assert result['manual']['purpose']=='backlog-replay'
    assert result['explicit']['purpose']=='maintenance'
    assert result['automatic'] is None and result['ordinary'] is None
    assert result['incomplete'] is None and result['otherRequest'] is None


def test_replay_paths_are_discovery_hints_and_fresh_observations_preserve_original_prefix():
    result=isolated_run_bun(r'''
      import {taskSliceMetadata,appendMemorySourceObservations} from './packages/continual-learning/extensions/incremental-learning.ts';
      const slice={kind:'learning-task-slice',version:1,entries:[{message:{role:'assistant',content:[{type:'toolCall',name:'edit',arguments:{path:'/work/project/index.js'}},{type:'toolCall',name:'read',arguments:{path:'/work/other/private.md'}}]}}]};
      const before=JSON.stringify(slice),paths=taskSliceMetadata(slice,'/work/project').touchedPaths;
      const extended=appendMemorySourceObservations(slice,[{message:{role:'toolResult',content:[{type:'text',text:'fresh source'}]}}]);
      console.log(JSON.stringify({paths,unchanged:before===JSON.stringify(slice),prefix:JSON.stringify(extended.entries.slice(0,slice.entries.length))===JSON.stringify(slice.entries),count:extended.entries.length}));
    ''')
    assert result['paths']==['index.js']
    assert result['unchanged'] and result['prefix'] and result['count']==2


def test_local_slice_truncation_disables_refresh_even_if_the_original_backlog_was_complete():
    result=isolated_run_bun(r'''
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {memorySourceAuditRequest} from './packages/continual-learning/extensions/memory-maintenance-audit.ts';
      const source={source:'backlog-session',entryCount:401};
      const entries=[{message:{role:'user',content:'Repair source'}},...Array.from({length:400},(_,i)=>({message:{role:'toolResult',toolName:'read',isError:false,content:[{type:'text',text:'source '+i}]}}))];
      const slice=currentTaskSlice(entries);const effective={...source,omittedEntries:slice.omittedEntries};
      console.log(JSON.stringify({omitted:slice.omittedEntries,result:memorySourceAuditRequest({mode:'manual',inputSource:effective})}));
    ''')
    assert result['omitted']>0 and result['result'] is None


def test_replay_source_collection_refuses_all_stored_memory_claims_before_a_model_call():
    result=isolated_run_bun(r'''
      import fs from 'node:fs/promises';import path from 'node:path';import {mock} from 'bun:test';
      const root=await fs.realpath(process.env.PI_CODING_AGENT_DIR),cwd=path.join(root,'project');await fs.mkdir(cwd);await fs.writeFile(path.join(cwd,'index.js'),'export const actual=1;');
      const memory=path.join(root,'private.md');await fs.writeFile(memory,'Private predecessor must not reach collector');
      const kit=await import('./packages/kit/src/index.ts');let calls=0;mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{calls++;throw Error('Must not be called');}}));
      const {auditMemoryMaintenanceSources}=await import('./packages/continual-learning/extensions/memory-maintenance-audit.ts');
      const audit=await auditMemoryMaintenanceSources({cwd,request:'replay',purpose:'backlog-replay',replayPaths:['index.js'],memoryFiles:[memory],memoryIndex:[{name:'private.md',description:'private',type:'project',classification:'private'}],outputDir:root});
      console.log(JSON.stringify({outcome:audit.outcome,entries:audit.entries,calls,usage:audit.usage}));
    ''')
    assert result['outcome']=='failed' and result['entries']==[] and result['calls']==0
    assert result['usage']['cost']==0
