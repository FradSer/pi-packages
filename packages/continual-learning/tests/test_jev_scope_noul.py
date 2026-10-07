from support import isolated_run_bun


def test_scope_noul_polarity_and_independent_harness_gates() -> None:
    # Given original authorization and complete evidence, only a strong absence
    # of expansion passes; uncertainty and every independent failed gate hold.
    rows = isolated_run_bun(r'''
      import {loadScopeNoulJudge} from './packages/continual-learning/tests/jev-scope-noul-shadow.ts';
      const research=await loadScopeNoulJudge();const results=[];
      try {
        const row=(await Bun.file('./packages/continual-learning/tests/fixtures/jev-source-development-corpus.json').json())[0];
        for(const [mode,p] of [['none',.1],['edge',.11],['middle',.5],['near',.89],['expansion',.9],['unsupported',.01],['counter',.01],['unavailable',.01]]){
          let scope;let counterType;const judge=research.createJevJudge({enabled:true,apiKey:'fixture',defaultModel:'jev-1.13.0',scopes:['harness'],fetch:async(_url,init)=>{
            if(mode==='unavailable')throw Error('fixture unavailable');const r=JSON.parse(String(init.body));const answers={};
            for(const [k,q] of Object.entries(r.questions)){
              if(k.startsWith('expands'))scope=q;
              if(k.startsWith('counter'))counterType=q.type;
              if(q.type==='noul')answers[k]={type:'noul',noul:k.startsWith('expands')?p:mode==='unsupported'?.01:.99};
              else {const label=k.startsWith('counter')?(mode==='counter'?'contradicts':'compatible'):k.startsWith('supported')?(mode==='unsupported'?'unsupported':'grounded'):['lasting','faithful','authorized'].find(x=>Object.hasOwn(q.criteria,x));
                if(!label)throw Error('unexpected fixture question');answers[k]={type:'choice',choice:label,confidence:.99,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};}
            }
            return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
          }});
          const result=await judge.validate('harness',row.snapshot,row.plan.operations,[],undefined,row.plan.evidence);
          results.push({mode,scope,counterType,result});
        }
      }finally{await research.dispose();}
      console.log(JSON.stringify(results));
    ''')
    for row in rows:
        assert row['result']['decision'] == ('allow' if row['mode'] == 'none' else 'propose'), row['mode']
        if row['mode'] in ('edge', 'middle', 'near'):
            assert row['result']['telemetry']['reason'] == 'uncertain'
        if row['mode'] == 'expansion':
            assert row['result']['telemetry']['reason'] == 'scope-expansion'
        if 'scope' in row:
            assert row['scope']['type'] == 'noul'
            assert set(row['scope']['criteria']) == {'true', 'false'}
            assert row['counterType'] == 'choice'
        else:
            assert row['mode'] in ('unsupported', 'unavailable')
