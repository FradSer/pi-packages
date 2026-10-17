from support import isolated_run_bun


def test_complete_selection_windows_preserve_entries_and_hold_late_uncertainty() -> None:
    # Given a long task with a final revocation, When routing runs, Then review
    # every original whole record; a partial positive never bypasses a late hold.
    rows = isolated_run_bun(r'''
      import crypto from 'node:crypto';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const rows=[];
      for(const mode of ['complete','uncertain','failure','cancelled','sensitive','too-many']){
        const entries=Array.from({length:mode==='too-many'?40:6},(_,index)=>({role:index===5?'user':'toolResult',snapshotIndex:index,content:index===5?'Revoke the earlier restriction.':'Public source observation. '.repeat(450)}));
        if(mode==='sensitive')entries.at(-1).content='api_key=sk-'+'x'.repeat(40);
        const controller=new AbortController(),wires=[];
        const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['selection'],requestConcurrency:1,fetch:async(_url,init)=>{
          const wire=JSON.parse(String(init.body));wires.push(wire);const last=wire.state.entries.some(e=>(e.entry??e).snapshotIndex===5);
          if(last&&mode==='failure')throw Error('private diagnostic must stay hidden');
          if(last&&mode==='cancelled')controller.abort();
          const answers={};for(const [key,q]of Object.entries(wire.questions))answers[key]=q.type==='noul'?{type:'noul',noul:last&&mode==='uncertain'?.5:key==='memory'?.99:.01}:{type:'score',score:2,confidence:1,legend:{'0':'Unrelated','1':'Generic','2':'Useful','3':'Direct'},probabilities:{'0':0,'1':0,'2':1,'3':0}};
          return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
        }});
        const result=await judge.select({contextEnabled:true,entries},[{name:'existing.md',description:'Public contract',classification:'safe'}],false,controller.signal);
        const digest=value=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
        rows.push({mode,result,wires:wires.map(w=>({entryDigests:w.state.entries.map(e=>digest(e.entry??e))})),entryDigests:entries.map(digest)});
      }console.log(JSON.stringify(rows));
    ''')
    complete = rows[0]
    assert len(complete['wires']) > 1
    observed = [digest for wire in complete['wires'] for digest in wire['entryDigests']]
    assert observed == complete['entryDigests']
    assert complete['result']['selection'] == {'memory': True, 'harness': False, 'selected': ['existing.md']}
    assert complete['result']['telemetry']['evidenceWindows'] == len(complete['wires'])
    assert complete['result']['telemetry']['completedWindows'] == len(complete['wires'])
    assert complete['result']['telemetry']['inputTokens'] == len(complete['wires'])
    for row in rows[1:4]:
        assert row['result']['selection'] is None
    for row in rows[4:]:
        assert row['wires'] == []
        assert row['result']['selection'] is None
    assert rows[4]['result']['telemetry']['reason'] == 'sensitive'
    assert rows[5]['result']['telemetry']['reason'] == 'bounds'


def test_selection_windows_keep_partial_usage_and_unknown_prices_unknown() -> None:
    # Given a failed usage record or an unpriced model, When window costs merge,
    # Then no single window shadows cumulative usage and missing prices stay unknown.
    rows = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const rows=[];
      for(const mode of ['partial','unpriced','mixed-priced','fixed-mismatch']){
        let calls=0;const model=mode==='unpriced'?'jev-1.15.0':mode==='mixed-priced'?'jev-latest':'jev-1.13.0';
        const judge=createJevJudge({enabled:true,apiKey:'fixture',defaultModel:model,scopes:['selection'],fetch:async()=>{
          calls++;const usage=mode==='partial'&&calls===2?{input_tokens:20}:{input_tokens:calls*10,output_tokens:0};
          return new Response(JSON.stringify({model:mode==='mixed-priced'?(calls===2?'jev-1.15.0':'jev-1.13.0'):mode==='fixed-mismatch'&&calls===2?'jev-1.14.0':model,answers:{memory:{type:'noul',noul:.99},harness:{type:'noul',noul:.01}},usage}));
        }});
        const result=await judge.select({entries:Array.from({length:3},(_,snapshotIndex)=>({snapshotIndex,role:'toolResult',content:'Public source. '.repeat(750)}))},[],false);
        rows.push({mode,calls,result});
      }console.log(JSON.stringify(rows));
    ''')
    partial, unpriced, mixed, fixed = rows
    assert partial['calls'] == 2
    assert unpriced['calls'] == 3
    telemetry = partial['result']['telemetry']
    assert partial['result']['selection'] is None
    assert 'inputTokens' not in telemetry
    assert 'outputTokens' not in telemetry
    assert 'estimatedCostUsd' not in telemetry
    assert telemetry['knownInputTokens'] == 30
    assert abs(telemetry['knownEstimatedCostUsd'] - 30 * .000000042) < 1e-12
    telemetry = unpriced['result']['telemetry']
    assert telemetry['inputTokens'] == 60
    assert 'estimatedCostUsd' not in telemetry
    assert unpriced['result']['selection'] == {'memory': True, 'harness': False, 'selected': []}

    telemetry = mixed['result']['telemetry']
    assert mixed['result']['selection'] is None
    assert telemetry['inputTokens'] == 60
    assert 'estimatedCostUsd' not in telemetry
    assert abs(telemetry['knownEstimatedCostUsd'] - 40 * .000000042) < 1e-12

    # A fixed-version mismatch stops further windows, while preserving every
    # returned usage record and the now-known price of both actual versions.
    assert fixed['calls'] == 2
    assert fixed['result']['selection'] is None
    telemetry = fixed['result']['telemetry']
    assert telemetry['reason'] == 'invalid-response'
    assert telemetry['completedWindows'] == 1
    assert telemetry['evidenceWindows'] == 3
    assert telemetry['knownInputTokens'] == 30
    assert 'inputTokens' not in telemetry and 'estimatedCostUsd' not in telemetry
    assert abs(telemetry['knownEstimatedCostUsd'] - 30 * .000000042) < 1e-12
