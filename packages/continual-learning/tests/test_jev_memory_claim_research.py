import json

from support import isolated_run_bun


def test_memory_claim_research_changes_only_memory_counter_semantics() -> None:
    # Given distinct Memory claims and Harness restrictions, only the Memory
    # counter interpretation changes; source entries and all gates remain.
    value = isolated_run_bun(r'''
      import {memoryClaimRequest} from './packages/continual-learning/tests/jev-memory-claim-shadow.ts';
      const candidate={content:'This project uses pnpm.'};const questions={
        supported_0:{type:'choice',instructions:{candidate},criteria:{grounded:'yes',unsupported:'no',unclear:'unknown'}},
        counter_0_0:{type:'choice',instructions:{question:'old',candidate},criteria:{compatible:'yes',contradicts:'no',unclear:'unknown'}},
        counter_1_0:{type:'choice',instructions:{question:'harness',candidate:{rule:{action:'block'}}},criteria:{compatible:'yes',contradicts:'no',unclear:'unknown'}}};
      const r={model:'jev-1.13.0',state:JSON.stringify({supportEvidence:{entries:[{index:0,entry:{role:'user',content:'This project uses pnpm. Never push.'}}]},reviewEvidence:{entries:[{index:0,entry:{role:'user',content:'This project uses pnpm. Never push.'}}]}}),questions};
      const original=JSON.stringify(r);const patched=memoryClaimRequest(r);console.log(JSON.stringify({r,patched,unchanged:original===JSON.stringify(r)}));
    ''')
    assert value['unchanged']
    assert value['r']['state'] == value['patched']['state']
    assert value['r']['model'] == value['patched']['model']
    for key in ('supported_0', 'counter_1_0'):
        assert value['r']['questions'][key] == value['patched']['questions'][key]
    counter = value['patched']['questions']['counter_0_0']
    assert counter['type'] == 'choice'
    assert counter['instructions']['candidate'] == value['r']['questions']['counter_0_0']['instructions']['candidate']
    assert set(counter['criteria']) == {'compatible', 'contradicts', 'unclear'}
    assert 'actually asserted' in counter['instructions']['question']
    assert 'unrelated behavioral' in counter['criteria']['compatible']
    assert json.loads(value['patched']['state'])['reviewEvidence']['entries'][0]['index'] == 0


def test_memory_claim_research_preserves_uncertainty_relationship_and_service_holds() -> None:
    value = isolated_run_bun(r'''
      import {memoryClaimRequest} from './packages/continual-learning/tests/jev-memory-claim-shadow.ts';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const row=(await Bun.file('./packages/continual-learning/tests/fixtures/jev-noul-heldout-corpus.json').json())[0];const results=[];
      for(const mode of ['supported','unsupported','duplicate','relationship-conflict','counter','unclear','confidence','probability','unavailable']){
        const judge=createJevJudge({enabled:true,apiKey:'fixture',defaultModel:'jev-1.13.0',scopes:['memory'],fetch:async(_url,init)=>{
          if(mode==='unavailable')throw Error('fixture unavailable');const r=memoryClaimRequest(JSON.parse(String(init.body)));const answers={};
          for(const [k,q]of Object.entries(r.questions)){
            const label=k.startsWith('supported')?(mode==='unsupported'?'unsupported':'grounded'):k.startsWith('relation')?(mode==='duplicate'?'duplicate':mode==='relationship-conflict'?'conflict':'unrelated'):mode==='counter'?'contradicts':mode==='unclear'?'unclear':'compatible';
            const probs=Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]));
            if(mode==='probability'&&k.startsWith('counter'))Object.assign(probs,{compatible:.89,contradicts:.06,unclear:.05});
            answers[k]={type:'choice',choice:label,confidence:mode==='confidence'&&k.startsWith('counter')?.79:.99,probabilities:probs};
          }
          return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
        }});
        const existing=[{name:'prior.md',classification:'safe',type:'existing',description:'',content:'The project has a TypeScript API.'}];
        results.push({mode,result:await judge.validate('memory',row.snapshot,row.plan.operations,existing)});
      }
      console.log(JSON.stringify(results));
    ''')
    for row in value:
        assert row['result']['decision'] == ('allow' if row['mode'] == 'supported' else 'propose')
        if row['mode'] in ('confidence', 'probability', 'unclear'):
            assert row['result']['telemetry']['reason'] == 'uncertain'
