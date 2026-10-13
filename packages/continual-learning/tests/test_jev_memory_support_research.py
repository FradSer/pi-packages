from support import isolated_run_bun


def test_narrow_memory_support_preserves_other_checks_and_held_plan() -> None:
    # Given fully cited new knowledge, When support changes to one Noul per field,
    # Then complete counter Choice and strong-probability whole-plan holds remain.
    value = isolated_run_bun(r'''
      import {loadMemorySupportNoulJudge} from './packages/continual-learning/tests/jev-memory-support-research.ts';
      const fixture=await loadMemorySupportNoulJudge();const quote='This project uses pnpm.';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:quote}]};
      const candidate={name:'fact.md',kind:'project',classification:'safe',content:`---\nname: fact\ndescription: ${quote}\ntype: project\n---\n${quote}`,evidence:[{index:0,quote,role:'user'}]};const rows=[];
      try{for(const mode of ['yes','no','unknown','counter-held','private','legacy']){
       const requests=[];const judge=fixture.createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
        const r=JSON.parse(String(init.body));requests.push(r);const answers={};
        for(const[k,q]of Object.entries(r.questions)){
         if(q.type==='noul')answers[k]={type:'noul',noul:mode==='no'?.05:mode==='unknown'?.5:.99};
         else{const label=k.startsWith('supported')?'grounded':mode==='counter-held'?'unclear':'compatible';answers[k]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};}
        }return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
       }});
       const c=mode==='private'?{...candidate,classification:'private'}:candidate;
       rows.push({mode,result:await judge.validate('memory',mode==='legacy'?'Legacy evidence':snapshot,[c],[]),questionTypes:Object.assign({},...requests.map(r=>Object.fromEntries(Object.entries(r.questions).map(([k,q])=>[k,q.type])))),requests:requests.length});
      }}finally{await fixture.dispose()}console.log(JSON.stringify(rows));
    ''')
    assert value[0]['result']['decision'] == 'allow'
    assert value[0]['questionTypes'] == {
        'supported_0': 'noul', 'supported_description_0': 'noul',
        'counter_0_0': 'choice', 'counter_description_0_0': 'choice',
    }
    for row in value[1:5]:
        assert row['result']['decision'] == 'propose'
    assert value[4]['requests'] == 0
    assert value[5]['questionTypes']['supported_0'] == 'choice'


def test_research_observer_rejects_uncontrolled_or_incomplete_answers() -> None:
    value = isolated_run_bun(r'''
      import {observeMemoryJudgments} from './packages/continual-learning/tests/jev-memory-support-research.ts';
      const request={questions:{supported_0:{type:'noul'},counter_description_0_1:{type:'choice',criteria:{compatible:'ok',contradicts:'bad',unclear:'unknown'}}}};
      const good={model:'jev-1.13.0',answers:{supported_0:{type:'noul',noul:.93},counter_description_0_1:{type:'choice',choice:'unclear',confidence:.8,probabilities:{compatible:.05,contradicts:.05,unclear:.9}}}};
      const rows=[good,{...good,model:'PRIVATE_MODEL'}, {...good,answers:{...good.answers,PRIVATE_TEXT:{type:'noul',noul:.9}}},{...good,answers:{supported_0:{type:'noul',noul:NaN}}},{...good,answers:{...good.answers,counter_description_0_1:{...good.answers.counter_description_0_1,choice:'PRIVATE_TEXT'}}}].map(r=>observeMemoryJudgments(request,r,'jev-1.13.0'));
      console.log(JSON.stringify(rows));
    ''')
    assert value[0]['valid'] is True
    assert value[0]['judgments'][0]['probability'] == .93
    assert value[0]['judgments'][1]['windowIndex'] == 1
    assert value[0]['judgments'][1]['field'] == 'description'
    assert all(not row['valid'] and row['judgments'] == [] for row in value[1:])
    assert 'PRIVATE_' not in str(value)


def test_preflight_completes_later_batches_and_denies_late_bounds_or_privacy() -> None:
    value = isolated_run_bun(r'''
      import {loadMemorySupportNoulJudge,completeMemoryResearchPreflight} from './packages/continual-learning/tests/jev-memory-support-research.ts';
      const fixture=await loadMemorySupportNoulJudge(),quote='This project uses pnpm.';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:quote},...Array.from({length:5},()=>({role:'toolResult',content:'Public observation. '.repeat(1150)}))]};
      const candidate={name:'fact.md',kind:'project',classification:'safe',content:`---\nname: fact\ndescription: ${quote}\ntype: project\n---\n${quote}`,evidence:[{index:0,quote,role:'user'}]};
      let denied=false,privateDenied=false;try{
       const complete=await completeMemoryResearchPreflight(fixture.createJevJudge,snapshot,[candidate]);
       try{await completeMemoryResearchPreflight(fixture.createJevJudge,snapshot,[candidate],body=>{const r=JSON.parse(body);if(Object.keys(r.questions).some(k=>/^counter_0_4$/.test(k)))r.state='x'.repeat(64000);return JSON.stringify(r)})}catch{denied=true}
       const sensitive=structuredClone(snapshot);sensitive.entries.at(-1).content='Bearer sk-live-'+'x'.repeat(40);
       try{await completeMemoryResearchPreflight(fixture.createJevJudge,sensitive,[candidate])}catch{privateDenied=true}
       console.log(JSON.stringify({complete,denied,privateDenied}));
      }finally{await fixture.dispose()}
    ''')
    assert value['complete']['requests'] > 4
    assert value['complete']['windows'] >= 5
    assert value['denied'] and value['privateDenied']
