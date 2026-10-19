import pytest

from support import isolated_run_bun


def test_unresponsive_repair_is_terminated_and_partial_usage_is_retained() -> None:
    # Given a repair child that reports known usage then never finishes,
    # When the recorded Memory correction budget expires, Then terminate it,
    # preserve partial cost, and retain the rejected plan without admitting it.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
      import {repairIncrementalMemoryPlan} from './packages/continual-learning/extensions/inject-memory.ts';
      import {MEMORY_CORRECTION_WORKER_DEADLINE_MS} from './packages/continual-learning/extensions/memory-body-review.ts';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'repair-deadline-')),pkg=path.join(root,'fake-package');fs.mkdirSync(pkg);
      fs.writeFileSync(path.join(pkg,'package.json'),JSON.stringify({name:'@earendil-works/pi-coding-agent'}));
      const cli=path.join(pkg,'cli.mjs'),marker=path.join(root,'pid');process.argv[1]=cli;
      fs.writeFileSync(cli,`import fs from 'node:fs';fs.writeFileSync(${JSON.stringify(marker)},String(process.pid));console.log(JSON.stringify({type:'message_end',message:{role:'assistant',stopReason:'toolUse',content:[],usage:{input:2,output:3,cacheRead:0,cacheWrite:0,totalTokens:5,cost:{total:0.25}}}}));setInterval(()=>{},1000);`);
      const timer=globalThis.setTimeout;let bound;
      // Accelerate only the production deadline after observing child readiness.
      globalThis.setTimeout=(fn,ms,...args)=>ms===MEMORY_CORRECTION_WORKER_DEADLINE_MS?(bound=ms,timer(function check(){if(fs.existsSync(marker))timer(fn,50,...args);else timer(check,10)},10)):timer(fn,ms,...args);
      const controller=new AbortController();let removed=0;
      const remove=controller.signal.removeEventListener.bind(controller.signal);controller.signal.removeEventListener=(...args)=>{removed++;return remove(...args)};
      const out=await repairIncrementalMemoryPlan({rejectedPlan:{operations:[],newMemories:[]},errors:['held'],selectedNames:[],identity:{runId:'r',scopeKey:'s',scopeDigest:'s',artifactHash:'a',snapshotDigest:'a'},signal:controller.signal,outputDir:root});
      let alive=true;try{process.kill(Number(fs.readFileSync(marker,'utf8')),0)}catch{alive=false}
      const ledgers=fs.readdirSync(root).filter(x=>x.startsWith('memory-repair-usage-')).map(x=>JSON.parse(fs.readFileSync(path.join(root,x),'utf8')));
      console.log(JSON.stringify({out,bound,recorded:MEMORY_CORRECTION_WORKER_DEADLINE_MS,alive,removed,parentAborted:controller.signal.aborted,ledgers}));
    ''', timeout=15)
    assert result['recorded'] == 600000
    assert result['bound'] == result['recorded']
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
      import {MEMORY_CORRECTION_WORKER_DEADLINE_MS} from './packages/continual-learning/extensions/memory-body-review.ts';
      const agent=process.env.PI_CODING_AGENT_DIR;let calls=0,expire;
      const server=Bun.serve({hostname:'127.0.0.1',port:0,idleTimeout:0,fetch:async request=>{
        calls++;await request.text();expire();return new Promise(()=>{});
      }});
      fs.writeFileSync(path.join(agent,'models.json'),JSON.stringify({providers:{fixture:{baseUrl:`http://127.0.0.1:${server.port}/v1`,api:'openai-completions',apiKey:'public-test-placeholder',models:[{id:'hang',name:'hang',reasoning:false,input:['text'],contextWindow:1000000,maxTokens:64,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}]}}}));
      fs.writeFileSync(path.join(agent,'settings.json'),JSON.stringify({packages:[],extensions:[],skills:[],retry:{enabled:false}}));
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'native-repair-cancel-'));process.env.HOME=root;process.env.PI_OFFLINE='1';
      const cli=fs.realpathSync('./node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js');process.argv[1]=cli;process.execPath=Bun.which('node');
      const expectedVersion=JSON.parse(fs.readFileSync('./node_modules/@earendil-works/pi-coding-agent/package.json','utf8')).version;
      const version=Bun.spawnSync([process.execPath,cli,'--version'],{env:process.env}).stdout.toString().trim();
      const timer=globalThis.setTimeout;let bound;
      globalThis.setTimeout=(fn,ms,...args)=>ms===MEMORY_CORRECTION_WORKER_DEADLINE_MS?(bound=ms,expire=()=>timer(fn,0,...args),timer(()=>{throw Error('No local provider request')},10000)):timer(fn,ms,...args);
      try{
        const out=await repairIncrementalMemoryPlan({rejectedPlan:{operations:[],newMemories:[]},errors:['held'],selectedNames:[],identity:{runId:'r',scopeKey:'s',scopeDigest:'s',artifactHash:'a',snapshotDigest:'a'},model:'fixture/hang',outputDir:root});
        const event=JSON.parse(fs.readFileSync(path.join(root,fs.readdirSync(root).find(x=>x.endsWith('-closed.json'))),'utf8'));
        console.log(JSON.stringify({out,event,bound,recorded:MEMORY_CORRECTION_WORKER_DEADLINE_MS,calls,version,expectedVersion,externalRequests:0}));
      }finally{server.stop(true)}
    ''', timeout=20)
    assert result['expectedVersion'] and result['version'] == result['expectedVersion']
    assert result['calls'] == 1 and result['externalRequests'] == 0
    assert result['bound'] == result['recorded'] == 600000
    assert result['out']['outcome'] == 'failed' and result['out']['failureKind'] == 'timeout'
    assert result['event']['stage'] == 'closed' and result['event']['timedOut'] is True


def test_active_parent_cancel_wins_a_deadline_during_child_cleanup() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
      import {repairIncrementalMemoryPlan} from './packages/continual-learning/extensions/inject-memory.ts';
      import {MEMORY_CORRECTION_WORKER_DEADLINE_MS} from './packages/continual-learning/extensions/memory-body-review.ts';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'repair-parent-cancel-')),pkg=path.join(root,'fake-package');fs.mkdirSync(pkg);
      fs.writeFileSync(path.join(pkg,'package.json'),JSON.stringify({name:'@earendil-works/pi-coding-agent'}));
      const cli=path.join(pkg,'cli.mjs'),marker=path.join(root,'pid');process.argv[1]=cli;
      fs.writeFileSync(cli,`import fs from 'node:fs';fs.writeFileSync(${JSON.stringify(marker)},String(process.pid));setInterval(()=>{},1000);`);
      const controller=new AbortController(),timer=globalThis.setTimeout;
      globalThis.setTimeout=(fn,ms,...args)=>ms===MEMORY_CORRECTION_WORKER_DEADLINE_MS?timer(function check(){
        if(fs.existsSync(marker)){controller.abort();fn(...args)}else timer(check,10)
      },10):timer(fn,ms,...args);
      const out=await repairIncrementalMemoryPlan({rejectedPlan:{operations:[],newMemories:[]},errors:['held'],selectedNames:[],identity:{runId:'r',scopeKey:'s',scopeDigest:'s',artifactHash:'a',snapshotDigest:'a'},signal:controller.signal});
      console.log(JSON.stringify(out));
    ''')
    assert result['outcome'] == 'cancelled'
    assert 'failureKind' not in result and 'plan' not in result


def test_recorded_correction_budget_admits_a_repair_that_outlives_the_historical_bound() -> None:
    # Given a held Memory repair that needs longer than the historical 230-second
    # bound, When it completes inside the recorded correction budget, Then the
    # complete response is accepted and the parent records the recorded deadline.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
      import {repairIncrementalMemoryPlan} from './packages/continual-learning/extensions/inject-memory.ts';
      import {MEMORY_CORRECTION_WORKER_DEADLINE_MS} from './packages/continual-learning/extensions/memory-body-review.ts';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'repair-budget-')),pkg=path.join(root,'fake-package');fs.mkdirSync(pkg);
      fs.writeFileSync(path.join(pkg,'package.json'),JSON.stringify({name:'@earendil-works/pi-coding-agent'}));
      const cli=path.join(pkg,'cli.mjs'),sentinel=path.join(root,'go');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'s',artifactHash:'a',snapshotDigest:'a'};
      const plan={kind:'incremental-memory-plan',version:1,...identity,operations:[],newMemories:[]};
      fs.writeFileSync(cli,`import fs from 'node:fs';const plan=${JSON.stringify(plan)};
        const wait=()=>{if(fs.existsSync(${JSON.stringify(sentinel)})){
          console.log(JSON.stringify({type:'message_end',message:{role:'assistant',stopReason:'stop',content:[{type:'text',text:JSON.stringify(plan)}],usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:{total:0.01}}}}));process.exit(0)}
          setTimeout(wait,5)};wait();`);
      process.argv[1]=cli;
      const timer=globalThis.setTimeout,SCALE=200;
      let bound=null;
      globalThis.setTimeout=(fn,ms,...args)=>{if(ms===MEMORY_CORRECTION_WORKER_DEADLINE_MS){bound=ms;return timer(fn,ms/SCALE,...args)}return timer(fn,ms,...args)};
      // A repair needing 300 of the recorded seconds still arrives before the deadline.
      timer(()=>fs.writeFileSync(sentinel,'1'),300_000/SCALE);
      const out=await repairIncrementalMemoryPlan({rejectedPlan:{operations:[],newMemories:[]},errors:['held'],selectedNames:[],identity,outputDir:root});
      const lifecycles=fs.readdirSync(root).filter(x=>x.startsWith('memory-repair-lifecycle-')).map(x=>JSON.parse(fs.readFileSync(path.join(root,x),'utf8')));
      const lifecycle=lifecycles.find(x=>x.stage==='started'),closed=lifecycles.find(x=>x.stage==='closed');
      console.log(JSON.stringify({outcome:out.outcome,failureKind:out.failureKind??null,hasPlan:!!out.plan,bound,recorded:MEMORY_CORRECTION_WORKER_DEADLINE_MS,lifecycle,closed}));
    ''', timeout=20)
    assert result['recorded'] == 600000
    assert result['recorded'] > 230000
    assert result['bound'] == result['recorded']
    assert result['outcome'] == 'repaired' and result['hasPlan']
    assert result['lifecycle']['deadlineMs'] == result['recorded']
    assert result['closed']['stage'] == 'closed' and result['closed']['timedOut'] is False and result['closed']['exitCode'] == 0


@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize("failed_artifact", ["closed", "usage", "both"])
def test_closed_marker_failure_retains_completed_worker_usage_without_admitting_plan(failed_artifact: str, partial: bool) -> None:
    # Given a paid worker result and a failing close marker, When retaining it,
    # Then keep known usage and fail closed instead of throwing away the costs.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import os from 'node:os';import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');
      const run=await import('./packages/continual-learning/extensions/consolidation-run.ts');const write=run.writeFileAtomic;
      const usage={input:2,output:3,cacheRead:0,cacheWrite:0,totalTokens:5,cost:0.25};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{input.onUpdate?.({text:'body',liveThinking:'fixture reasoning',turns:0});return {exitCode:__PARTIAL__?143:0,cancelled:__PARTIAL__,stderr:'',text:'{}',...(__PARTIAL__?{}:{usage}),usageLedger:{knownUsage:usage,assistantMessages:1,complete:!__PARTIAL__}}}}));
      mock.module('./packages/continual-learning/extensions/consolidation-run.ts',()=>({...run,writeFileAtomic:async(file,body)=>{
        if(('__FAILED_ARTIFACT__'!=='usage'&&file.endsWith('-closed.json'))||('__FAILED_ARTIFACT__'!=='closed'&&file.includes('memory-repair-usage-')))throw Error('fixture artifact write failed');
        return write(file,body);
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'repair-marker-failure-'));let out,error;
      try{out=await repairIncrementalMemoryPlan({rejectedPlan:{operations:[],newMemories:[]},errors:['held'],selectedNames:[],identity:{runId:'r',scopeKey:'s',scopeDigest:'s',artifactHash:'a',snapshotDigest:'a'},outputDir:root})}catch(e){error=e.message}
      const ledgers=fs.readdirSync(root).filter(x=>x.startsWith('memory-repair-usage-')).map(x=>JSON.parse(fs.readFileSync(path.join(root,x),'utf8')));
      const close=fs.readdirSync(root).find(x=>x.endsWith('-closed.json'));
      console.log(JSON.stringify({out,error:error??null,ledgers,closed:!!close,closedRecord:close?JSON.parse(fs.readFileSync(path.join(root,close),'utf8')):null}));
    '''.replace('__FAILED_ARTIFACT__', failed_artifact).replace('__PARTIAL__', str(partial).lower()))
    assert result['error'] is None
    assert result['out']['outcome'] == 'failed' and 'plan' not in result['out']
    assert result['out']['usage']['cost'] == 0.25
    assert result['out']['usageComplete'] is (not partial)
    assert result['out']['failureKind'] == 'artifact'
    assert len(result['ledgers']) == (1 if failed_artifact == 'closed' else 0)
    if result['ledgers']:
        assert result['ledgers'][0]['knownUsage']['cost'] == 0.25
    assert result['closed'] is (failed_artifact == 'usage')
    if result['closedRecord']:
        progress = result['closedRecord']['progress']
        assert progress['updates'] == 1 and progress['thinkingCharacters'] == 17
        assert progress['textCharacters'] == 4 and progress['completedTurns'] == 0
        assert progress['firstUpdateMs'] <= progress['lastUpdateMs']
        assert 'fixture reasoning' not in str(result['closedRecord'])
