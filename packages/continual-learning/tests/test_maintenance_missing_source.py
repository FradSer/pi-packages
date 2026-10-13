from support import isolated_run_bun


def test_exhausted_source_reader_disables_wire_tools_and_stops_excess() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
      import {registerPlannerRead} from './packages/continual-learning/extensions/planner-read-scope.ts';
      const cwd=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'scoped-wire-')));await fs.writeFile(path.join(cwd,'source.ts'),'observed source');
      const handlers={};let tool,active=['learning_read'],aborts=0;const observations=[];
      registerPlannerRead({on:(name,fn)=>handlers[name]=fn,registerTool:t=>tool=t,setActiveTools:t=>active=t,getActiveTools:()=>active},{cwd,roots:[cwd],files:[]},async r=>{observations.push(r)},1);
      const request={messages:[{role:'tool',content:'retained observation'}],tools:[]};const ctx={model:{api:'openai-completions'},abort:()=>aborts++};
      const before=handlers.before_provider_request({payload:request},ctx);
      await tool.execute('one',{path:'source.ts'},new AbortController().signal,undefined,ctx);
      const after=handlers.before_provider_request({payload:request},ctx);
      const other=handlers.before_provider_request({payload:request},{model:{api:'anthropic-messages'}});
      const conflicting=handlers.before_provider_request({payload:{...request,tools:[{name:'unexpected'}]}},ctx);
      let excess=false;try{await tool.execute('two',{path:'source.ts'},new AbortController().signal,undefined,ctx)}catch{excess=true}
      console.log(JSON.stringify({before,after,other,conflicting,request,active,aborts,excess,observations}));await fs.rm(cwd,{recursive:true,force:true});
    ''')
    assert value.get('before') is None and value.get('other') is None and value.get('conflicting') is None
    assert value['after'] == {**value['request'], 'tool_choice': 'none'}
    assert 'tool_choice' not in value['request']
    assert value['active'] == [] and value['aborts'] == 1 and value['excess']
    assert value['observations'][1]['error'] == 'Source audit read budget exceeded'


def test_missing_paths_do_not_discard_verified_source_or_become_evidence() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import path from 'node:path';import os from 'node:os';import {mock} from 'bun:test';
      const root=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'maintenance-missing-')));const cwd=path.join(root,'project');await fs.mkdir(cwd);
      await fs.writeFile(path.join(cwd,'actual.ts'),'export const actual = true;');let mode='missing';
      const kit=await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async options=>{
        const input=JSON.parse(options.prompt.split('\n').at(-1));
        const {recordMaintenanceRead}=await import('./packages/continual-learning/extensions/memory-maintenance-audit.ts');
        const {readPlannerFileSnapshot}=await import('./packages/continual-learning/extensions/planner-read-scope.ts');
        const missing=mode==='existing'?path.join(cwd,'actual.ts'):mode==='outside'?path.join(root,'missing.ts'):mode==='sensitive'?path.join(cwd,'absent','.env'):path.join(cwd,'missing.ts');
        await recordMaintenanceRead(input.observationsPath,{path:missing,offset:1,limit:200,error:'Scoped source path missing'});
        const read=await readPlannerFileSnapshot('actual.ts',input.readScope);
        await recordMaintenanceRead(input.observationsPath,{path:path.join(cwd,'actual.ts'),offset:1,limit:200,result:read.text,sha256:read.sha256});
        return {exitCode:0,text:'',stderr:'',usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:0.01}};
      }}));
      const {auditMemoryMaintenanceSources}=await import('./packages/continual-learning/extensions/memory-maintenance-audit.ts');
      const rows=[];for(mode of ['missing','existing','outside','sensitive']){
        const result=await auditMemoryMaintenanceSources({cwd,request:'整理记忆',memoryFiles:[],outputDir:root});
        await result.assertSourcesUnchanged();rows.push({mode,outcome:result.outcome,entries:result.entries,usage:result.usage});
      }
      console.log(JSON.stringify(rows));await fs.rm(root,{recursive:true,force:true});
    ''')
    assert value[0]['outcome'] == 'observed'
    assert len(value[0]['entries']) == 2
    assert 'missing.ts' not in str(value[0]['entries'])
    assert all(row['outcome'] == 'failed' and not row['entries'] for row in value[1:])
    assert all(row['usage']['cost'] == 0.01 for row in value)
