"""Real corrected contract must retain its mutation context in description review."""
from support import isolated_run_bun


def test_actual_rewrite_description_retains_parent_validated_operation_context():
    value=isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      import fs from 'node:fs';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-description-transition.json','utf8'));
      const candidate=f.plan.operations[0];const rows=[];const before=JSON.stringify(f);
      for(const uncertain of [false,true]){
        const requests=[];
        const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
          const request=JSON.parse(String(init.body));requests.push(request);const answers={};
          for(const [key,q] of Object.entries(request.questions)){
            const keys=Object.keys(q.criteria);const selected=keys.find(k=>['grounded','compatible','unrelated'].includes(k))??keys[0];
            const held=uncertain&&key==='supported_description_0';
            answers[key]={type:'choice',choice:selected,confidence:held ? .89 : 1,probabilities:Object.fromEntries(keys.map((k,i)=>[k,k===selected?(held ? .89 : 1):held&&k===keys.find(x=>x!==selected) ? .11 : 0]))};
          }
          return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:0,output_tokens:0}}));
        }});
        const result=await judge.validate('memory',f.snapshot,[candidate],f.existingMemories);
        rows.push({uncertain,result,questions:Object.assign({},...requests.map(x=>x.questions)),inputUnchanged:JSON.stringify(f)===before});
      }
      console.log(JSON.stringify(rows));
    ''')
    for row in value:
        assert row['inputUnchanged']
        questions=row['questions']
        body=questions['supported_0']['instructions']['candidate']
        description=questions['supported_description_0']['instructions']['candidate']
        assert body['action']=='rewrite' and body['target']=='limit_function_type_contract.md'
        assert description['action']==body['action']
        assert description['target']==body['target']
        assert description['storageScope']==body['storageScope']
        assert description['content']=="p-limit declares limitFunction's returned wrapper type as Pick<LimitFunction, 'clearQueue' | 'onIdle'>"
        assert 'Input:' not in description['content']
        assert row['result']['decision']==('propose' if row['uncertain'] else 'allow')
        for key,q in questions.items():
            if key.startswith('counter_description_'):
                assert q['instructions']['candidate']['action']=='rewrite'
                assert q['instructions']['candidate']['target']==body['target']
        # The raw snapshot remains intact; its own injected reference is routing, not counterevidence.
        assert row['result']['telemetry']['coveredEntries']==42
