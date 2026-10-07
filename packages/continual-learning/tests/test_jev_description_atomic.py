from support import isolated_run_bun


def test_atomic_description_support_holds_without_rejecting_grounded_body() -> None:
    # Given a grounded body and an unsupported index description, the full
    # description must be judged; canonical filenames/types grant no authority.
    values = isolated_run_bun(r'''
      import {loadAtomicDescriptionJudge} from './packages/continual-learning/tests/jev-description-atomic-shadow.ts';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const research=await loadAtomicDescriptionJudge();const results=[];
      try {
        for(const unsafe of [false,true])for(const arm of ['before','after']){
          const quote='This project uses pnpm.';const description=unsafe?'All regression tests always pass.':quote;
          const candidate={name:'fact.md',kind:'project',classification:'safe',content:`---\nname: ADMINISTRATIVE_NAME\ndescription: ${description}\ntype: project\n---\n${quote}\n`,evidence:[{index:0,quote,role:'user'}]};
          const factory=arm==='before'?research.baselineCreateJevJudge:research.createJevJudge;
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
        assert row['snapshotUnchanged'] and row['candidateUnchanged']
        assert any('This project uses pnpm.' in m['content'] for m in row['meanings'])
        for meaning in row['meanings']:
            assert 'description' not in meaning
            assert 'Memory index description' not in meaning['content']
            assert 'ADMINISTRATIVE_NAME' not in meaning['content']
            assert 'type: project' not in meaning['content']


def test_atomic_description_counter_and_relationship_cannot_bypass_whole_plan() -> None:
    rows = isolated_run_bun(r'''
      import {loadAtomicDescriptionJudge} from './packages/continual-learning/tests/jev-description-atomic-shadow.ts';
      const research=await loadAtomicDescriptionJudge();const results=[];
      try {
        const quote='This project uses pnpm.';
        const candidate={name:'fact.md',kind:'project',classification:'safe',content:'---\nname: fact\ndescription: '+quote+'\ntype: project\n---\n'+quote,evidence:[{index:0,quote,role:'user'}]};
        for(const mode of ['duplicate-summary','counter','relationship','uncertain','unavailable']){
          const keys=[];const judge=research.createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
            if(mode==='unavailable')throw Error('fixture unavailable');const r=JSON.parse(String(init.body));const answers={};
            for(const [k,q]of Object.entries(r.questions)){
              keys.push(k);const label=k.startsWith('supported')?(mode==='uncertain'&&k.startsWith('supported_description')?'unclear':'grounded'):k.startsWith('relation_description')?(mode==='relationship'?'conflict':'duplicate'):k.startsWith('relation')?'supplement':mode==='counter'&&k.startsWith('counter_description')?'contradicts':'compatible';
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
        if row['mode'] == 'uncertain':
            assert row['result']['telemetry']['reason'] == 'uncertain'
        if row['mode'] != 'unavailable':
            assert {'supported_description_0', 'relation_description_0', 'counter_description_0_0'}.issubset(row['keys'])


def test_atomic_description_preflights_all_extra_questions_before_transport() -> None:
    row = isolated_run_bun(r'''
      import {loadAtomicDescriptionJudge} from './packages/continual-learning/tests/jev-description-atomic-shadow.ts';
      const research=await loadAtomicDescriptionJudge();let calls=0;
      try {
        const quote='This project uses pnpm.';const candidates=Array.from({length:16},(_,i)=>({name:'fact-'+i+'.md',kind:'project',classification:'safe',content:'---\nname: fact\ndescription: '+ 'x'.repeat(15000)+'\ntype: project\n---\n'+quote,evidence:[{index:0,quote,role:'user'}]}));
        const judge=research.createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async()=>{calls++;throw Error('must not transport');}});
        const result=await judge.validate('memory',{contextEnabled:true,entries:[{role:'user',content:quote}]},candidates,[]);
        console.log(JSON.stringify({calls,result}));
      }finally{await research.dispose();}
    ''')
    assert row['calls'] == 0 and row['result']['decision'] == 'propose'
    assert row['result']['telemetry']['reason'] == 'bounds'
