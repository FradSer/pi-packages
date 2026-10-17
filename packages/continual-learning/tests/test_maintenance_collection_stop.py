import pytest

from support import isolated_run_bun


def test_complete_delivery_stops_collection_but_partial_or_refused_reads_do_not_admit_evidence() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import path from 'node:path';
      import {registerMaintenanceCollector,verifyMaintenanceCollectionProof} from './packages/continual-learning/extensions/maintenance-collection-stop.ts';
      const root=await fs.realpath(process.env.PI_CODING_AGENT_DIR);await fs.writeFile(path.join(root,'source.ts'),'Current source.');
      const scope={cwd:root,files:[],roots:[root]};const results=[];
      for(const mode of ['complete','native-abort','sdk-abort','partial','duplicate','mismatch','overflow','cancel','wrong-nonce','transport','wrong-path','missing-terminal','terminal-error','parent-cancel','corrupt-marker','oversized-required']){
        const dir=path.join(root,mode);await fs.mkdir(dir);let tool;const hooks={};let aborts=0;const observed=[];
        registerMaintenanceCollector({registerTool:t=>tool=t,on:(name,fn)=>hooks[name]=fn,setActiveTools:()=>{}},scope,dir,'parent-nonce',async x=>{observed.push(x);await fs.appendFile(path.join(dir,"observations.jsonl"),JSON.stringify(x)+"\n")},2);
        const signal=new AbortController();const toolResults=[];const calls=[];
        for(let i=0;i<(mode==='overflow'?3:mode==='partial'?1:2);i++){
          const id=mode==='duplicate'?'same':`r${i}`;const args={path:'source.ts'};calls.push({type:'toolCall',id,name:'learning_read',arguments:args});
          try{const r=await tool.execute(id,args,signal.signal,undefined,{abort:()=>{}});toolResults.push({role:'toolResult',toolCallId:id,toolName:'learning_read',isError:false,content:r.content})}catch{}
        }
        if(mode==='wrong-path')calls[0].arguments.path='unread.ts';
        if(mode==='mismatch')toolResults[0].content[0].text='Different result';
        if(mode==='cancel')signal.abort();
        await hooks.turn_end({message:{role:'assistant',content:mode==='oversized-required'?[...calls,{type:'text',text:'x'.repeat(3*1024*1024)}]:calls},toolResults},{signal:signal.signal,abort:()=>{aborts++}});
        if(aborts&&mode!=='missing-terminal'){signal.abort();await hooks.message_end({message:{role:'assistant',stopReason:['terminal-error','native-abort','sdk-abort'].includes(mode)?'error':'aborted',errorMessage:mode==='terminal-error'?'Connection timed out':mode==='native-abort'?'The operation was aborted':mode==='sdk-abort'?'Request was aborted.':undefined,content:[],usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0}}},{signal:signal.signal})}
        const worker={exitCode:1,cancelled:!['native-abort','sdk-abort'].includes(mode),stderr:['transport','native-abort','sdk-abort'].includes(mode)?'Pi worker model failed before successful completion.':'Pi worker model reply was cancelled.'};
        if(mode==='corrupt-marker'&&aborts){const f=path.join(dir,'collection-stop.json');const m=JSON.parse(await fs.readFile(f,'utf8'));m.scopeDigest='wrong';await fs.writeFile(f,JSON.stringify(m))}
        const parentSignal=new AbortController();if(mode==='parent-cancel')parentSignal.abort();
        const accepted=await verifyMaintenanceCollectionProof(dir,mode==='wrong-nonce'?'foreign':'parent-nonce',scope,observed,worker,parentSignal.signal,2);
        results.push({mode,accepted,aborts});
      }
      console.log(JSON.stringify(results));
    ''')
    assert value[0] == {'mode': 'complete', 'accepted': True, 'aborts': 1}
    assert value[1] == {'mode': 'native-abort', 'accepted': True, 'aborts': 1}
    assert value[2] == {'mode': 'sdk-abort', 'accepted': True, 'aborts': 1}
    assert all(not row['accepted'] for row in value[3:])


@pytest.mark.parametrize("missing", [False, True])
@pytest.mark.parametrize("purpose", ["maintenance", "backlog-replay"])
def test_actual_pi_stops_after_complete_reads_and_preserves_cancelled_worker_accounting(missing: bool, purpose: str) -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import path from 'node:path';import {mock} from 'bun:test';
      const root=await fs.realpath(process.env.PI_CODING_AGENT_DIR);const cwd=path.join(root,'project');await fs.mkdir(cwd);
      const source=path.join(cwd,'runtime.ts');await fs.writeFile(source,'export const runtime = "current";\n');
      const events=path.join(root,'calls.jsonl');process.env.PI_COLLECTION_EVENTS=events;process.env.PI_COLLECTION_SOURCE=source;
      const kit=await import('./packages/kit/src/index.ts');const worker=kit.runPiWorker;let workerResult;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async opts=>(workerResult=await worker({...opts,extraArgs:[...opts.extraArgs,'-e',path.resolve('packages/continual-learning/tests/maintenance-collector-live-fixture.ts')],model:'maintenance-collector-fixture/deterministic'}))}));
      const {auditMemoryMaintenanceSources}=await import('./packages/continual-learning/extensions/memory-maintenance-audit.ts');
      const result=await auditMemoryMaintenanceSources({cwd,request:'整理记忆',purpose:process.env.PI_COLLECTION_PURPOSE,replayPaths:['runtime.ts'],memoryFiles:[],outputDir:root});
      const receipt=JSON.parse(await fs.readFile(path.join(result.directory,'receipt.json'),'utf8'));
      const calls=(await fs.readFile(events,'utf8')).trim().split('\n').map(JSON.parse);
      const observations=(await fs.readFile(path.join(result.directory,'observations.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
      await result.assertSourcesUnchanged();await fs.writeFile(source,'changed');let stale=false;try{await result.assertSourcesUnchanged()}catch{stale=true}
      console.log(JSON.stringify({outcome:result.outcome,entries:result.entries.length,receipt,calls,workerResult,reads:observations.length,stale}));
    ''', env={'PI_COLLECTION_MISSING_ONCE': '1' if missing else '0','PI_COLLECTION_PURPOSE':purpose})
    assert [row for row in value['calls'] if 'providerCall' in row] == [{'providerCall': 1}], value
    if purpose == 'backlog-replay' and missing:
        # A denied path outside the explicit original-file scope cannot be admitted.
        assert value['reads'] == 18 and value['entries'] == 0 and value['outcome'] == 'failed', value
        assert value['receipt']['sourceEvidenceStatus'] == 'hold' and not value['receipt']['usageComplete']
        return
    assert value['reads'] == 18 and value['entries'] == (34 if missing else 36) and value['stale'], value
    assert value['outcome'] == 'observed', value
    assert value['receipt']['workerOutcome'] == 'failed', value
    assert value['receipt']['sourceEvidenceStatus'] == 'verified-prefix', value
    assert not value['receipt']['usageComplete'], value


def test_partial_usage_keeps_known_subtotal_and_marks_unknown_usage_and_cost() -> None:
    value = isolated_run_bun(r'''
      import {buildLearningReceipt,isLearningPipelineReceipt} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const attempt={phase:'memory',attempt:0,outcome:'noop',durationMs:1,operations:0,usageComplete:false,usage:{input:10,output:2,cacheRead:0,cacheWrite:0,totalTokens:12,cost:.01}};
      const receipt=buildLearningReceipt('manual',{memory:true,harness:false,agents:false,reasons:[]},[attempt]);
      console.log(JSON.stringify({receipt,valid:isLearningPipelineReceipt(receipt),invalid:isLearningPipelineReceipt({...receipt,attempts:[{...attempt,usageComplete:'true'}]})}));
    ''')
    assert value['valid'] and not value['invalid']
    assert value['receipt']['totals']['cost'] == .01
    assert not value['receipt']['usageAvailable'] and not value['receipt']['costAvailable']


def test_actual_pi_parallel_excess_read_is_retained_and_cannot_admit_source() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import path from 'node:path';import {mock} from 'bun:test';
      const root=await fs.realpath(process.env.PI_CODING_AGENT_DIR);const cwd=path.join(root,'project');await fs.mkdir(cwd);
      const source=path.join(cwd,'runtime.ts');await fs.writeFile(source,'export const runtime = "current";\n');
      const events=path.join(root,'calls.jsonl');process.env.PI_COLLECTION_EVENTS=events;process.env.PI_COLLECTION_SOURCE=source;process.env.PI_COLLECTION_OVERFLOW='1';
      const kit=await import('./packages/kit/src/index.ts');const worker=kit.runPiWorker;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async opts=>worker({...opts,extraArgs:[...opts.extraArgs,'-e',path.resolve('packages/continual-learning/tests/maintenance-collector-live-fixture.ts')],model:'maintenance-collector-fixture/deterministic'})}));
      const {auditMemoryMaintenanceSources}=await import('./packages/continual-learning/extensions/memory-maintenance-audit.ts');
      const result=await auditMemoryMaintenanceSources({cwd,request:'整理记忆',memoryFiles:[],outputDir:root});
      const receipt=JSON.parse(await fs.readFile(path.join(result.directory,'receipt.json'),'utf8'));
      const observations=(await fs.readFile(path.join(result.directory,'observations.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
      const calls=(await fs.readFile(events,'utf8')).trim().split('\n').map(JSON.parse).filter(r=>'providerCall'in r);
      console.log(JSON.stringify({outcome:result.outcome,entries:result.entries.length,receipt,calls,observations,source:await fs.readFile(source,'utf8')}));
    ''')
    assert value['calls'] == [{'providerCall': 1}], value
    assert value['entries'] == 0 and value['receipt']['sourceEvidenceStatus'] == 'hold', value
    assert any(row.get('error') == 'Source audit read budget exceeded' for row in value['observations'])
    assert value['source'] == 'export const runtime = "current";\n'


def test_pending_observation_persistence_cannot_produce_a_stop_proof() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import path from 'node:path';
      import {registerMaintenanceCollector} from './packages/continual-learning/extensions/maintenance-collection-stop.ts';
      const root=await fs.realpath(process.env.PI_CODING_AGENT_DIR);const source=path.join(root,'source.ts');await fs.writeFile(source,'Current source.');
      const dir=path.join(root,'collector');await fs.mkdir(dir);const scope={cwd:root,files:[],roots:[root]};let tool;const hooks={};let aborts=0;
      let release,started;const gate=new Promise(r=>release=r),ready=new Promise(r=>started=r);let pending=0;
      registerMaintenanceCollector({registerTool:t=>tool=t,on:(name,fn)=>hooks[name]=fn,setActiveTools:()=>{}},scope,dir,'nonce',async read=>{if(++pending===2)started();await gate;await fs.appendFile(path.join(dir,'observations.jsonl'),JSON.stringify(read)+'\n')},2);
      const tasks=[0,1].map(i=>tool.execute(`r${i}`,{path:source},new AbortController().signal,undefined,{abort:()=>{}}));
      await ready;
      await hooks.turn_end({message:{role:'assistant',content:[]},toolResults:[]},{abort:()=>aborts++});
      const premature=await fs.stat(path.join(dir,'collection-stop.json')).then(()=>true,()=>false);
      release();await Promise.all(tasks);
      console.log(JSON.stringify({premature,aborts,pending}));
    ''')
    assert value == {'premature': False, 'aborts': 0, 'pending': 2}


def test_actual_openai_transport_stops_without_losing_complete_source_prefix() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import path from 'node:path';import {mock} from 'bun:test';
      const root=await fs.realpath(process.env.PI_CODING_AGENT_DIR);const cwd=path.join(root,'project');await fs.mkdir(cwd);
      const source=path.join(cwd,'runtime.ts');await fs.writeFile(source,'export const runtime = "current";\n');
      const events=path.join(root,'calls.jsonl');process.env.PI_COLLECTION_EVENTS=events;process.env.PI_COLLECTION_SOURCE=source;
      let requests=0;const server=Bun.serve({hostname:'127.0.0.1',port:0,fetch:async request=>{
        requests++;await request.json();
        const tools=Array.from({length:2},(_,index)=>({index,id:`source-${requests}-${index}`,type:'function',function:{name:'learning_read',arguments:JSON.stringify({path:source})}}));
        const chunks=[{id:'fixture',object:'chat.completion.chunk',created:1,model:'deterministic',choices:[{index:0,delta:{role:'assistant',tool_calls:tools},finish_reason:null}]},
          {id:'fixture',object:'chat.completion.chunk',created:1,model:'deterministic',choices:[{index:0,delta:{},finish_reason:'tool_calls'}],usage:{prompt_tokens:1,completion_tokens:1,total_tokens:2}}];
        return new Response(chunks.map(x=>'data: '+JSON.stringify(x)+'\n\n').join('')+'data: [DONE]\n\n',{headers:{'content-type':'text/event-stream'}});
      }});process.env.PI_COLLECTION_OPENAI_URL=`http://127.0.0.1:${server.port}/v1`;
      process.execPath=Bun.which('node');
      const kit=await import('./packages/kit/src/index.ts');const worker=kit.runPiWorker;let workerResult;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async opts=>(workerResult=await worker({...opts,extraArgs:[...opts.extraArgs,'-e',path.resolve('packages/continual-learning/tests/maintenance-collector-live-fixture.ts')],model:'maintenance-collector-fixture/deterministic'}))}));
      const {auditMemoryMaintenanceSources}=await import('./packages/continual-learning/extensions/memory-maintenance-audit.ts');
      const result=await auditMemoryMaintenanceSources({cwd,request:'整理记忆',memoryFiles:[],outputDir:root});
      const calls=(await fs.readFile(events,'utf8')).trim().split('\n').map(JSON.parse);server.stop(true);
      console.log(JSON.stringify({outcome:result.outcome,entries:result.entries.length,requests,calls,workerResult}));
    ''')
    assert value['requests'] == 8, value
    assert value['outcome'] == 'observed' and value['entries'] == 32, value['calls'][-1]


def test_near_budget_proof_requires_complete_count_and_rejects_forged_count() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import path from 'node:path';
      import {registerMaintenanceCollector,verifyMaintenanceCollectionProof} from './packages/continual-learning/extensions/maintenance-collection-stop.ts';
      const root=await fs.realpath(process.env.PI_CODING_AGENT_DIR);await fs.writeFile(path.join(root,'source.ts'),'Current source.');
      const scope={cwd:root,files:[],roots:[root]},results=[];
      for(const count of [15,16]){
        const dir=path.join(root,String(count));await fs.mkdir(dir);let tool,aborts=0;const hooks={},observed=[],calls=[],toolResults=[];
        registerMaintenanceCollector({registerTool:t=>tool=t,on:(n,f)=>hooks[n]=f,setActiveTools:()=>{}},scope,dir,'nonce',async r=>{observed.push(r);await fs.appendFile(path.join(dir,'observations.jsonl'),JSON.stringify(r)+'\n')},18);
        const signal=new AbortController();for(let i=0;i<count;i++){const id=`r${i}`,args={path:'source.ts'};calls.push({type:'toolCall',id,name:'learning_read',arguments:args});const r=await tool.execute(id,args,signal.signal,undefined,{});toolResults.push({role:'toolResult',toolCallId:id,toolName:'learning_read',isError:false,content:r.content})}
        await hooks.turn_end({message:{role:'assistant',content:calls},toolResults},{signal:signal.signal,abort:()=>{aborts++;signal.abort()}});
        if(aborts)await hooks.message_end({message:{role:'assistant',stopReason:'error',errorMessage:'The operation was aborted',content:[],usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0}}},{signal:signal.signal});
        const worker={exitCode:1,stderr:'Pi worker model failed before successful completion.'};
        const accepted=await verifyMaintenanceCollectionProof(dir,'nonce',scope,observed,worker,undefined,18);let forged=false;
        if(aborts){const file=path.join(dir,'collection-stop.json'),m=JSON.parse(await fs.readFile(file,'utf8'));m.readCount=15;await fs.writeFile(file,JSON.stringify(m));forged=await verifyMaintenanceCollectionProof(dir,'nonce',scope,observed,worker,undefined,18)}
        results.push({count,aborts,accepted,forged});
      }console.log(JSON.stringify(results));
    ''')
    assert value == [
        {'count': 15, 'aborts': 0, 'accepted': False, 'forged': False},
        {'count': 16, 'aborts': 1, 'accepted': True, 'forged': False},
    ]


def test_collection_proof_does_not_duplicate_cumulative_turn_context() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import path from 'node:path';
      import {registerMaintenanceCollector,verifyMaintenanceCollectionProof} from './packages/continual-learning/extensions/maintenance-collection-stop.ts';
      const root=await fs.realpath(process.env.PI_CODING_AGENT_DIR);await fs.writeFile(path.join(root,'runtime.ts'),'Actual source observation.');const scope={cwd:root,files:[],roots:[root]};
      const dir=path.join(root,'proof');await fs.mkdir(dir);const hooks={};let tool,aborts=0;const observations=[];
      registerMaintenanceCollector({registerTool:t=>tool=t,on:(name,fn)=>hooks[name]=fn,setActiveTools:()=>{}},scope,dir,'nonce',async r=>{observations.push(r);await fs.appendFile(path.join(dir,'observations.jsonl'),JSON.stringify(r)+'\n')},2);
      const calls=[],results=[],controller=new AbortController();
      for(let i=0;i<2;i++){const id=`r${i}`,arguments_={path:'runtime.ts'};const r=await tool.execute(id,arguments_,controller.signal,undefined,{abort:()=>{}});calls.push({type:'toolCall',id,name:'learning_read',arguments:arguments_});results.push({role:'toolResult',toolCallId:id,toolName:'learning_read',isError:false,content:r.content});}
      const message={role:'assistant',content:calls};await hooks.turn_end({type:'turn_end',message,toolResults:results,context:{repeatedHistory:'x'.repeat(3*1024*1024)}},{signal:controller.signal,abort:()=>aborts++});controller.abort();
      await hooks.message_end({message:{role:'assistant',stopReason:'error',errorMessage:'The operation was aborted',content:[],usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0}}},{signal:controller.signal});
      const worker={exitCode:1,cancelled:false,stderr:'Pi worker model failed before successful completion.'};const accepted=await verifyMaintenanceCollectionProof(dir,'nonce',scope,observations,worker,undefined,2);
      const bytes=await fs.readFile(path.join(dir,'collection-prefix.json'),'utf8'),proof=JSON.parse(bytes);const exact=JSON.stringify(proof[0].message)===JSON.stringify(message)&&JSON.stringify(proof[0].toolResults)===JSON.stringify(results);
      observations[0].result='changed';const changedRejected=!await verifyMaintenanceCollectionProof(dir,'nonce',scope,observations,worker,undefined,2);
      console.log(JSON.stringify({accepted,exact,changedRejected,aborts,bytes:Buffer.byteLength(bytes),keys:Object.keys(proof[0]).sort()}));
    ''')
    assert value['accepted'] and value['exact'] and value['changedRejected']
    assert value['aborts'] == 1 and value['bytes'] < 2 * 1024 * 1024
    assert value['keys'] == ['message', 'toolResults']
