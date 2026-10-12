from support import isolated_run_bun


def test_retrieval_support_is_specific_and_keeps_original_body_privacy_gates() -> None:
    # Given a retrieval cue and a complete proposed body, When judging the cue,
    # Then its body is context only and both independent judgments must pass.
    rows = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      import {loadRetrievalDescriptionJudge} from './packages/continual-learning/tests/jev-retrieval-description-shadow.ts';
      const r=await loadRetrievalDescriptionJudge();const outputs=[];
      try {
        const quote='For this project, use pnpm test to verify changes.';
        const candidate={name:'fact.md',kind:'project',classification:'safe',content:'---\nname: fact\ndescription: When verifying changes in this project\ntype: project\n---\n'+quote,evidence:[{index:0,quote,role:'user'}]};
        const snapshot={contextEnabled:true,entries:[{role:'user',content:quote}]};
        for(const mode of ['good','body-unsupported','description-unsupported','later-counter','secret','large']){
          const sent=[];const value=structuredClone(candidate);if(mode==='secret')value.content+='\napi_key=sk-'+'a'.repeat(45);if(mode==='large')value.content+='\n'+'x'.repeat(65000);
          const judge=r.createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
            const request=JSON.parse(String(init.body));sent.push(request);const answers={};
            for(const [key,q]of Object.entries(request.questions)){
              const label=key.startsWith('supported')?((mode==='body-unsupported'&&key==='supported_0')||(mode==='description-unsupported'&&key==='supported_description_0')?'unsupported':'grounded'):mode==='later-counter'&&key==='counter_description_0_0'?'contradicts':'compatible';
              answers[key]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===label?1:0]))};
            }return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
          }});
          const result=await judge.validate('memory',snapshot,[value],[]);
          outputs.push({mode,result,calls:sent.length,questions:Object.assign({},...sent.map(x=>x.questions)),states:sent.map(x=>(typeof x.state === "string" ? JSON.parse(x.state) : x.state))});
        }
      }finally{await r.dispose();}
      console.log(JSON.stringify(outputs));
    ''')
    for row in rows:
        assert row['result']['decision'] == ('allow' if row['mode'] == 'good' else 'propose')
        if row['mode'] in ('secret', 'large'):
            assert row['calls'] == 0
        else:
            q = row['questions']
            assert q['supported_description_0']['instructions']['candidate']['bodyContext'] == 'For this project, use pnpm test to verify changes.'
            assert 'not evidence or authorization' in q['supported_description_0']['instructions']['question']
            assert 'Memory index entry' in q['supported_description_0']['instructions']['question']
            assert 'retrieval cue' in q['supported_description_0']['criteria']['grounded']
            assert 'broader' in q['supported_description_0']['criteria']['unsupported']
            assert q['supported_0']['instructions']['candidate'] == {'content': 'For this project, use pnpm test to verify changes.'}
            assert q['counter_0_0']['instructions']['candidate'] == {'content': 'For this project, use pnpm test to verify changes.'}
            assert row['result']['telemetry']['coveredEntries'] == 1
