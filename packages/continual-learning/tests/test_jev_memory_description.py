from support import isolated_run_bun


def test_production_memory_description_support_holds_without_rejecting_grounded_body() -> None:
    # Given a grounded body and an unsupported index description, the full
    # description must be judged; canonical filenames/types grant no authority.
    values = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const research={createJevJudge,dispose:async()=>{}};const results=[];
      try {
        for(const unsafe of [false,true])for(const arm of ['after']){
          const quote='This project uses pnpm.';const description=unsafe?'All regression tests always pass.':quote;
          const candidate={name:'fact.md',kind:'project',classification:'safe',content:`---\nname: ADMINISTRATIVE_NAME\ndescription: ${description}\ntype: project\n---\n${quote}\n`,evidence:[{index:0,quote,role:'user'}]};
          const factory=arm==='before'?createJevJudge:research.createJevJudge;
          const sent=[];const judge=factory({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
            const r=JSON.parse(String(init.body));sent.push(r);const answers={};
            for(const [k,q]of Object.entries(r.questions)){
              const text=q.instructions.candidate.content;const label=k.startsWith('supported')?(text.includes('always pass')?'unsupported':'grounded'):'compatible';
              answers[k]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};
            }
            return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
          }});
          const snapshot={contextEnabled:true,entries:[{role:'user',content:quote}]};
          const result=await judge.validate('memory',snapshot,[candidate],[]);
          results.push({unsafe,arm,result,meanings:sent.flatMap(r=>Object.values(r.questions).map(q=>q.instructions.candidate)),snapshotUnchanged:snapshot.entries[0].content===quote,candidateUnchanged:candidate.content.includes('ADMINISTRATIVE_NAME')});
        }
      }finally{await research.dispose();}
      console.log(JSON.stringify(results));
    ''')
    for row in values:
        assert row['result']['decision'] == ('propose' if row['unsafe'] and row['arm'] == 'after' else 'allow')
        if row['unsafe'] and row['arm'] == 'after':
            assert row['result']['telemetry']['reason'] == 'unsupported'
            assert row['result']['telemetry']['field'] == 'description'
        assert row['snapshotUnchanged'] and row['candidateUnchanged']
        assert any('This project uses pnpm.' in m['content'] for m in row['meanings'])
        for meaning in row['meanings']:
            assert 'description' not in meaning
            assert 'Memory index description' not in meaning['content']
            assert 'ADMINISTRATIVE_NAME' not in meaning['content']
            assert 'type: project' not in meaning['content']


def test_production_memory_description_counter_and_relationship_cannot_bypass_whole_plan() -> None:
    rows = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const research={createJevJudge,dispose:async()=>{}};const results=[];
      try {
        const quote='This project uses pnpm.';
        const candidate={name:'fact.md',kind:'project',classification:'safe',content:'---\nname: fact\ndescription: '+quote+'\ntype: project\n---\n'+quote,evidence:[{index:0,quote,role:'user'}]};
        for(const mode of ['duplicate-summary','duplicate-body','counter','relationship','uncertain','unavailable']){
          const keys=[];const judge=research.createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
            if(mode==='unavailable')throw Error('fixture unavailable');const r=JSON.parse(String(init.body));const answers={};
            for(const [k,q]of Object.entries(r.questions)){
              keys.push(k);const label=k.startsWith('supported')?(mode==='uncertain'&&k.startsWith('supported_description')?'unclear':'grounded'):k.startsWith('relation_description')?(mode==='relationship'?'conflict':'duplicate'):k.startsWith('relation')?(mode==='duplicate-body'?'duplicate':'supplement'):mode==='counter'&&k.startsWith('counter_description')?'contradicts':'compatible';
              answers[k]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};
            }
            return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
          }});
          const result=await judge.validate('memory',{contextEnabled:true,entries:[{role:'user',content:quote}]},[candidate],[{name:'prior.md',classification:'safe',type:'existing',description:'',content:'The project has a TypeScript API.'}]);
          results.push({mode,result,keys});
        }
      }finally{await research.dispose();}
      console.log(JSON.stringify(results));
    ''')
    for row in rows:
        assert row['result']['decision'] == ('allow' if row['mode'] == 'duplicate-summary' else 'propose')
        if row['mode'] in ('counter', 'relationship'):
            assert row['result']['telemetry']['reason'] == 'conflict'
            assert row['result']['telemetry']['candidateIndex'] == 0
            assert row['result']['telemetry']['field'] == 'description'
        if row['mode'] == 'uncertain':
            assert row['result']['telemetry']['reason'] == 'uncertain'
        if row['mode'] != 'unavailable':
            assert {'supported_description_0', 'relation_description_0', 'counter_description_0_0'}.issubset(row['keys'])


def test_production_memory_description_preflights_all_extra_questions_before_transport() -> None:
    row = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const research={createJevJudge,dispose:async()=>{}};let calls=0;
      try {
        const quote='This project uses pnpm.';const candidates=Array.from({length:16},(_,i)=>({name:'fact-'+i+'.md',kind:'project',classification:'safe',content:'---\nname: fact\ndescription: '+ 'x'.repeat(15000)+'\ntype: project\n---\n'+quote,evidence:[{index:0,quote,role:'user'}]}));
        const judge=research.createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async()=>{calls++;throw Error('must not transport');}});
        const result=await judge.validate('memory',{contextEnabled:true,entries:[{role:'user',content:quote}]},candidates,[]);
        console.log(JSON.stringify({calls,result}));
      }finally{await research.dispose();}
    ''')
    assert row['calls'] == 0 and row['result']['decision'] == 'propose'
    assert row['result']['telemetry']['reason'] == 'bounds'


def test_description_failure_repair_hints_are_controlled() -> None:
    row = isolated_run_bun(r'''
      import {jevRepairFailureHints} from './packages/continual-learning/extensions/jev-learning.ts';
      const telemetry={stage:'memory',status:'propose',reason:'unsupported',durationMs:1,candidateFailures:[{candidateIndex:0,dimension:'support',field:'description',reason:'unsupported'},{candidateIndex:1,dimension:'relationship',reason:'duplicate'}]};
      console.log(JSON.stringify(jevRepairFailureHints(telemetry)));
    ''')
    assert row == ['Candidate failures: 0:support.description:unsupported, 1:relationship:duplicate']


def test_production_description_keeps_complete_claim_and_original_secret_guard() -> None:
    rows = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const results=[];
      for(const secret of [false,true]) {
        let calls=0;const descriptions=[];const body='This project uses pnpm.\n';
        const description='"'+ 'x'.repeat(4000)+' COMPLETE_TAIL"';
        const candidate={name:'fact.md',kind:'project',classification:'safe',content:'---\r\nname: administrative\r\ndescription: '+description+'\r\ndescription: IGNORE_SECOND\r\n'+(secret?'api_key: SYNTHETIC_SECRET_VALUE\r\n':'')+'type: project\r\n---\r\n'+body,evidence:[{index:0,quote:body,role:'user'}]};
        const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
          calls++;const r=JSON.parse(String(init.body));const answers={};
          for(const [key,q]of Object.entries(r.questions)){
            if(key.includes('_description_'))descriptions.push(q.instructions.candidate.content);
            else if(q.instructions.candidate.content!==body)throw Error('Body changed');
            const label=key.startsWith('supported')?'grounded':'compatible';
            answers[key]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===label?1:0]))};
          }
          return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
        }});
        const result=await judge.validate('memory',{contextEnabled:true,entries:[{role:'user',content:body}]},[candidate],[]);
        results.push({secret,calls,result,descriptions,description});
      }
      console.log(JSON.stringify(results));
    ''')
    for row in rows:
        if row['secret']:
            assert row['calls'] == 0 and row['result']['telemetry']['reason'] == 'sensitive'
        else:
            assert row['result']['decision'] == 'allow'
            assert row['descriptions'] == [row['description'], row['description']]
