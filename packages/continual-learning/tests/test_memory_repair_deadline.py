from support import isolated_run_bun


def test_unresponsive_repair_is_terminated_and_partial_usage_is_retained() -> None:
    # Given a repair child that reports known usage then never finishes,
    # When the existing 230-second review budget expires, Then terminate it,
    # preserve partial cost, and retain the rejected plan without admitting it.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
      import {repairIncrementalMemoryPlan} from './packages/continual-learning/extensions/inject-memory.ts';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'repair-deadline-')),pkg=path.join(root,'fake-package');fs.mkdirSync(pkg);
      fs.writeFileSync(path.join(pkg,'package.json'),JSON.stringify({name:'@earendil-works/pi-coding-agent'}));
      const cli=path.join(pkg,'cli.mjs'),marker=path.join(root,'pid');process.argv[1]=cli;
      fs.writeFileSync(cli,`import fs from 'node:fs';fs.writeFileSync(${JSON.stringify(marker)},String(process.pid));console.log(JSON.stringify({type:'message_end',message:{role:'assistant',stopReason:'toolUse',content:[],usage:{input:2,output:3,cacheRead:0,cacheWrite:0,totalTokens:5,cost:{total:0.25}}}}));setInterval(()=>{},1000);`);
      const timer=globalThis.setTimeout;let bound;
      // Accelerate only the production deadline after observing child readiness.
      globalThis.setTimeout=(fn,ms,...args)=>ms===230_000?(bound=ms,timer(function check(){if(fs.existsSync(marker))timer(fn,50,...args);else timer(check,10)},10)):timer(fn,ms,...args);
      const controller=new AbortController();let removed=0;
      const remove=controller.signal.removeEventListener.bind(controller.signal);controller.signal.removeEventListener=(...args)=>{removed++;return remove(...args)};
      const out=await repairIncrementalMemoryPlan({rejectedPlan:{operations:[],newMemories:[]},errors:['held'],selectedNames:[],identity:{runId:'r',scopeKey:'s',scopeDigest:'s',artifactHash:'a',snapshotDigest:'a'},signal:controller.signal,outputDir:root});
      let alive=true;try{process.kill(Number(fs.readFileSync(marker,'utf8')),0)}catch{alive=false}
      const ledgers=fs.readdirSync(root).filter(x=>x.startsWith('memory-repair-usage-')).map(x=>JSON.parse(fs.readFileSync(path.join(root,x),'utf8')));
      console.log(JSON.stringify({out,bound,alive,removed,parentAborted:controller.signal.aborted,ledgers}));
    ''', timeout=15)
    assert result['bound'] == 230000
    assert result['out']['outcome'] == 'failed'
    assert result['out']['failureKind'] == 'timeout'
    assert 'plan' not in result['out']
    assert not result['alive'] and not result['parentAborted']
    assert result['removed'] == 1
    assert len(result['ledgers']) == 1
    assert result['ledgers'][0]['knownUsage']['cost'] == 0.25


def test_parent_cancellation_is_not_relabelled_as_timeout() -> None:
    result = isolated_run_bun(r'''
      import {repairIncrementalMemoryPlan} from './packages/continual-learning/extensions/inject-memory.ts';
      const controller=new AbortController();controller.abort();
      const out=await repairIncrementalMemoryPlan({rejectedPlan:{operations:[],newMemories:[]},errors:['held'],selectedNames:[],identity:{runId:'r',scopeKey:'s',scopeDigest:'s',artifactHash:'a',snapshotDigest:'a'},signal:controller.signal});
      console.log(JSON.stringify(out));
    ''')
    assert result['outcome'] == 'cancelled'
    assert 'failureKind' not in result and 'plan' not in result


def test_actual_workspace_pi_repair_cancels_an_unresponsive_local_provider() -> None:
    # Actual selected workspace Pi and loopback transport; accelerate only the
    # parent deadline. Historical study copies keep their original Pi 1.0 pin.
    # This proves worker cancellation, not remote learning or semantic benefit.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
      import {repairIncrementalMemoryPlan} from './packages/continual-learning/extensions/inject-memory.ts';
      const agent=process.env.PI_CODING_AGENT_DIR;let calls=0,expire;
      const server=Bun.serve({hostname:'127.0.0.1',port:0,idleTimeout:0,fetch:async request=>{
        calls++;await request.text();expire();return new Promise(()=>{});
      }});
      fs.writeFileSync(path.join(agent,'models.json'),JSON.stringify({providers:{fixture:{baseUrl:`http://127.0.0.1:${server.port}/v1`,api:'openai-completions',apiKey:'public-test-placeholder',models:[{id:'hang',name:'hang',reasoning:false,input:['text'],contextWindow:1000000,maxTokens:64,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}]}}}));
      fs.writeFileSync(path.join(agent,'settings.json'),JSON.stringify({packages:[],extensions:[],skills:[],retry:{enabled:false}}));
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'native-repair-cancel-'));process.env.HOME=root;process.env.PI_OFFLINE='1';
      const cli=fs.realpathSync('./node_modules/@earendil-works/pi-coding-agent/dist/cli.js');process.argv[1]=cli;process.execPath=Bun.which('node');
      const expectedVersion=JSON.parse(fs.readFileSync('./node_modules/@earendil-works/pi-coding-agent/package.json','utf8')).version;
      const version=Bun.spawnSync([process.execPath,cli,'--version'],{env:process.env}).stdout.toString().trim();
      const timer=globalThis.setTimeout;let bound;
      globalThis.setTimeout=(fn,ms,...args)=>ms===230_000?(bound=ms,expire=()=>timer(fn,0,...args),timer(()=>{throw Error('No local provider request')},10000)):timer(fn,ms,...args);
      try{
        const out=await repairIncrementalMemoryPlan({rejectedPlan:{operations:[],newMemories:[]},errors:['held'],selectedNames:[],identity:{runId:'r',scopeKey:'s',scopeDigest:'s',artifactHash:'a',snapshotDigest:'a'},model:'fixture/hang',outputDir:root});
        const event=JSON.parse(fs.readFileSync(path.join(root,fs.readdirSync(root).find(x=>x.startsWith('memory-repair-lifecycle-'))),'utf8'));
        console.log(JSON.stringify({out,event,bound,calls,version,expectedVersion,externalRequests:0}));
      }finally{server.stop(true)}
    ''', timeout=20)
    assert result['expectedVersion'] and result['version'] == result['expectedVersion']
    assert result['calls'] == 1 and result['externalRequests'] == 0
    assert result['bound'] == 230000
    assert result['out']['outcome'] == 'failed' and result['out']['failureKind'] == 'timeout'
    assert result['event']['stage'] == 'closed' and result['event']['timedOut'] is True


def test_active_parent_cancel_wins_a_deadline_during_child_cleanup() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
      import {repairIncrementalMemoryPlan} from './packages/continual-learning/extensions/inject-memory.ts';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'repair-parent-cancel-')),pkg=path.join(root,'fake-package');fs.mkdirSync(pkg);
      fs.writeFileSync(path.join(pkg,'package.json'),JSON.stringify({name:'@earendil-works/pi-coding-agent'}));
      const cli=path.join(pkg,'cli.mjs'),marker=path.join(root,'pid');process.argv[1]=cli;
      fs.writeFileSync(cli,`import fs from 'node:fs';fs.writeFileSync(${JSON.stringify(marker)},String(process.pid));setInterval(()=>{},1000);`);
      const controller=new AbortController(),timer=globalThis.setTimeout;
      globalThis.setTimeout=(fn,ms,...args)=>ms===230_000?timer(function check(){
        if(fs.existsSync(marker)){controller.abort();fn(...args)}else timer(check,10)
      },10):timer(fn,ms,...args);
      const out=await repairIncrementalMemoryPlan({rejectedPlan:{operations:[],newMemories:[]},errors:['held'],selectedNames:[],identity:{runId:'r',scopeKey:'s',scopeDigest:'s',artifactHash:'a',snapshotDigest:'a'},signal:controller.signal});
      console.log(JSON.stringify(out));
    ''')
    assert result['outcome'] == 'cancelled'
    assert 'failureKind' not in result and 'plan' not in result
