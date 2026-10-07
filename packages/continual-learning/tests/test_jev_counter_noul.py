from support import isolated_run_bun


def test_counter_noul_polarity_thresholds_and_independent_gates() -> None:
    # Given original frozen evidence, a strong contradiction holds the plan;
    # absence only passes at <=.1, and .11/.5/.89 remain uncertain.
    value = isolated_run_bun(r'''
      import {loadCounterNoulJudge} from './packages/continual-learning/tests/jev-counter-noul-shadow.ts';
      const research=await loadCounterNoulJudge();const outcomes=[];
      try {
        for(const stage of ['harness','memory']){
        const row=stage==='harness'?(await Bun.file('./packages/continual-learning/tests/fixtures/jev-harness-support-corpus.json').json())[1]:(await Bun.file('./packages/continual-learning/tests/fixtures/jev-noul-heldout-corpus.json').json())[0];
        for(const [mode,p]of [['none',.1],['edge',.11],['middle',.5],['near',.89],['conflict',.9],['unsupported',.01],['scope',.01],['unavailable',.01]]){
          if(stage==='memory'&&mode==='scope')continue;
          const requests=[];const judge=research.createJevJudge({enabled:true,apiKey:'fixture',defaultModel:'jev-1.13.0',scopes:['harness','memory'],fetch:async(_url,init)=>{
            if(mode==='unavailable')throw Error('fixture unavailable');const r=JSON.parse(String(init.body));requests.push(r);const answers={};
            for(const [k,q]of Object.entries(r.questions)){
              if(q.type==='noul')answers[k]={type:'noul',noul:k.startsWith('counter')?p:mode==='unsupported'?.01:.99};
              else {const label=stage==='memory'?(mode==='unsupported'?'unsupported':'grounded'):mode==='scope'?'broader':'same';answers[k]={type:'choice',choice:label,confidence:.99,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};}
            }
            return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
          }});
          outcomes.push({stage,mode,result:await judge.validate(stage,row.snapshot,row.plan.operations,[],undefined,stage==='harness'?row.plan.evidence:undefined),requests:requests.map(r=>({questions:Object.fromEntries(Object.entries(r.questions).filter(([k])=>k.startsWith("counter_"))),reviewIndexes:JSON.parse(r.state).reviewEvidence?.entries.map(x=>x.index)}))});
        }
        }
      }finally{await research.dispose();}
      console.log(JSON.stringify(outcomes));
    ''')
    for row in value:
        assert row['result']['decision'] == ('allow' if row['mode'] == 'none' else 'propose')
        if row['mode'] in ('edge', 'middle', 'near'):
            assert row['result']['telemetry']['reason'] == 'uncertain'
        if row['mode'] == 'conflict':
            assert row['result']['telemetry']['reason'] == 'conflict'
        for request in row['requests']:
            for key, question in request['questions'].items():
                if key.startswith('counter_'):
                    assert question['type'] == 'noul'
                    assert 'conflict' in question['instructions']['question']
                    assert 'true' in question['criteria'] and 'false' in question['criteria']
                    assert request['reviewIndexes'][0] == 0
