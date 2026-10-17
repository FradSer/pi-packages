from support import isolated_run_bun


def test_complete_candidate_review_is_bound_and_never_partial_write_permission() -> None:
    # Given two original new Memories, When all requests finish but one field
    # is uncertain, Then report each check without changing the whole-plan hold.
    rows = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      import {createHash} from 'node:crypto';
      const quote='This project uses pnpm.';const rows=[];
      for(const mode of ['held','all-pass','unavailable','missing','mutation']){
       const snapshot={contextEnabled:true,runId:'fixture-run',scopeKey:'fixture-scope',entries:[{role:'user',content:quote}]};
       const candidates=[0,1].map(i=>({name:`fact-${i}.md`,kind:'project',classification:'safe',content:`---\nname: fact-${i}\ndescription: ${quote}\ntype: project\n---\n${quote}`,evidence:[{index:0,quote,role:'user'}]}));
       const original=JSON.stringify(candidates);let changed=false;
       const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
        if(mode==='unavailable')throw Error('fixture unavailable');const r=JSON.parse(String(init.body));const answers={};
        for(const [k,q]of Object.entries(r.questions)){
         if(mode==='missing'&&k==='supported_description_1')continue;
         const label=k.startsWith('coherence_')?'compatible':k==='supported_description_1'&&mode==='held'?'unclear':k.startsWith('supported')?'grounded':'compatible';answers[k]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};
        }
        if(mode==='mutation'&&!changed){candidates[0].content+=' altered';changed=true;}
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
       }});
       rows.push({mode,result:await judge.validate('memory',snapshot,candidates,[]),originalDigest:createHash('sha256').update(original).digest('hex')});
      }console.log(JSON.stringify(rows));
    ''')
    held, passed, unavailable, missing, mutation = rows
    assert held['result']['decision'] == 'propose'
    review = held['result']['candidateReview']
    assert review['complete'] is True
    assert review['purpose'] == 'diagnostic-only'
    assert review['sameBatchIndependenceReviewed'] is False
    assert review['candidatesDigest'] == held['originalDigest']
    assert [x['outcome'] for x in review['candidates']] == ['passed', 'held']
    assert review['candidates'][1]['heldChecks'] == ['supported_description_1']
    assert 'counter_description_0_0' in review['candidates'][0]['passedChecks']
    assert passed['result']['decision'] == 'allow'
    assert all(x['outcome'] == 'passed' for x in passed['result']['candidateReview']['candidates'])
    for row in [unavailable, missing, mutation]:
        assert 'candidateReview' not in row['result']
    assert unavailable['result']['decision'] == missing['result']['decision'] == mutation['result']['decision'] == 'propose'


def test_candidate_review_absent_for_incomplete_or_ineligible_inputs() -> None:
    # Given denied/legacy/mutated inputs, When review cannot prove the complete
    # original checklist, Then no observational proof is returned.
    rows = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const rows=[],quote='This project uses pnpm.';
      for(const mode of ['disabled','private','cancelled','legacy','rewrite','evidence-mutation','existing-mutation','model-mismatch']){
       const snapshot={contextEnabled:mode!=='legacy',entries:[{role:'user',content:quote}]};const existing=[];
       const candidate={name:'fact.md',kind:'project',classification:mode==='private'?'private':'safe',content:`---\nname: fact\ndescription: ${quote}\ntype: project\n---\n${quote}`,evidence:[{index:0,quote,role:'user'}],...(mode==='rewrite'?{op:'rewrite'}:{})};
       const controller=new AbortController();if(mode==='cancelled')controller.abort();let calls=0;
       const judge=createJevJudge({maxRequestBytes:64_000,enabled:mode!=='disabled',apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
        calls++;const r=JSON.parse(String(init.body));const answers={};
        for(const [k,q]of Object.entries(r.questions)){if(q.type==='noul')answers[k]={type:'noul',noul:.99};else {const label=k.startsWith('coherence_')?'compatible':k.startsWith('supported')?'grounded':'compatible';answers[k]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};}}
        if(mode==='evidence-mutation')snapshot.entries[0].content+=' altered';if(mode==='existing-mutation')existing.push({name:'altered',content:'altered'});
        return new Response(JSON.stringify({model:mode==='model-mismatch'&&calls>1?'jev-1.12.0':'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
       }});rows.push({mode,result:await judge.validate('memory',snapshot,[candidate],existing,controller.signal)});
      }console.log(JSON.stringify(rows));
    ''')
    assert all('candidateReview' not in row['result'] for row in rows)
    assert all(x['result']['decision']=='propose' for x in rows if x['mode'] in ['model-mismatch','evidence-mutation','existing-mutation'])


def test_candidate_review_includes_existing_relationship_and_all_windows() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const quote='This project uses pnpm.';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:quote},{role:'toolResult',content:'Verified public fixture observation. '.repeat(900)}]};
      const existing=[{name:'prior.md',classification:'safe',type:'project',description:'Prior toolchain fact.',content:'The project has a TypeScript API.'}];
      const candidate={name:'fact.md',kind:'project',classification:'safe',content:`---\nname: fact\ndescription: ${quote}\ntype: project\n---\n${quote}`,evidence:[{index:0,quote,role:'user'}]};
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
       const r=JSON.parse(String(init.body)),answers={};for(const [k,q]of Object.entries(r.questions)){
        const label=k.startsWith('coherence_')?'compatible':k.startsWith('supported')?'grounded':k.startsWith('relation')?'supplement':'compatible';answers[k]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};
       }return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
      }});console.log(JSON.stringify(await judge.validate('memory',snapshot,[candidate],existing)));
    ''')
    assert value['decision'] == 'allow'
    assert value['telemetry']['evidenceWindows'] == 2
    assert value['telemetry']['completedWindows'] == 2
    assert set(value['candidateReview']['candidates'][0]['passedChecks']) == {
        'coherence_0', 'supported_0', 'supported_description_0', 'relation_0',
        'relation_description_0', 'counter_0_0', 'counter_description_0_0',
        'counter_0_1', 'counter_description_0_1',
    }
