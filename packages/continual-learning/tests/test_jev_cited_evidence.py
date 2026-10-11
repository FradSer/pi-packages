from support import isolated_run_bun


def test_cited_rewrites_and_deletions_keep_full_review_and_mutation_intent() -> None:
    """Given long real-task evidence, rewriting known Memory must still review its tail."""
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const entries=[{role:'user',content:'Replace the old database note with PostgreSQL. Archive the duplicate note.'},
        ...Array.from({length:35},(_,i)=>({role:'toolResult',content:`Observation ${i}: `+'x'.repeat(2800)})),
        {role:'user',content:'Correction: the replacement is not authorized after all.'}];
      const snapshot={contextEnabled:true,entries};
      const evidence=[{index:0,role:'user',quote:entries[0].content}];
      const candidates=[{kind:'rewrite',name:'database.md',classification:'safe',content:'PostgreSQL.',observations:[{path:'schema.sql',status:'updated'}],evidence},
        {kind:'delete',name:'duplicate.md',classification:'safe',preservedIn:['database.md'],evidence}];
      const existing=[{name:'database.md',classification:'safe',content:'Old database note.',type:'project',description:'old'},
        {name:'duplicate.md',classification:'safe',content:'Duplicate note.',type:'project',description:'duplicate'}];
      let mode='good',calls=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const req=JSON.parse(init.body);calls.push(req);const state=JSON.parse(req.state);
        const answers=Object.fromEntries(Object.entries(req.questions).map(([key,q])=>{
          const selected=key.startsWith('counter_')?(mode==='conflict'&&state.reviewEvidence.entries.some(e=>e.index===36)?'contradicts':'compatible'):key.startsWith('relation_')?'supplement':'grounded';
          return [key,{type:'choice',choice:selected,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===selected?1:0]))}];
        }));
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:10,output_tokens:2},answers}));
      }});
      const good=await judge.validate('memory',snapshot,candidates,existing);const requests=calls;
      calls=[];mode='conflict';const conflict=await judge.validate('memory',snapshot,candidates,existing);
      calls=[];const forged=await judge.validate('memory',snapshot,[{...candidates[0],evidence:[{index:0,role:'user',quote:'invented quote'}]}],existing);
      const support=requests.find(r=>r.questions.supported_0);
      console.log(JSON.stringify({good,conflict,forged,forgedCalls:calls.length,
        coverage:requests.flatMap(r=>JSON.parse(r.state).reviewEvidence?.entries.map(e=>e.index)??[]),
        maxBytes:requests.length?Math.max(...requests.map(r=>Buffer.byteLength(JSON.stringify(r)))):null,
        rewrite:support?.questions.supported_0.instructions.candidate,
        deletion:support?.questions.supported_1.instructions.candidate,
        counterStates:requests.filter(r=>JSON.parse(r.state).reviewEvidence).map(r=>{
          const s=JSON.parse(r.state);return {existingMemories:s.existingMemories,proposedMemoryOperations:s.proposedMemoryOperations};
        }),
        deletionCounter:requests.find(r=>r.questions.counter_1_0)?.questions.counter_1_0.instructions,
        existing:support?JSON.parse(support.state).existingMemories:null}));
    ''')
    assert result['good']['decision'] == 'allow'
    assert result['coverage'] == list(range(37))
    assert result['maxBytes'] <= 64_000
    assert result['rewrite']['action'] == 'rewrite'
    assert result['rewrite']['target'] == 'database.md'
    assert result['rewrite']['observations'] == [{'path': 'schema.sql', 'status': 'updated'}]
    assert result['deletion']['kind'] == 'delete'
    assert result['deletion']['preservedIn'] == ['database.md']
    assert len(result['existing']) == 2
    assert all(state['existingMemories'] == result['existing'] for state in result['counterStates'])
    assert all(state['proposedMemoryOperations'][0]['content'] == 'PostgreSQL.' for state in result['counterStates'])
    assert 'preservation' in result['deletionCounter']['question']
    assert result['deletionCounter']['candidate']['preservedIn'] == ['database.md']
    assert result['conflict']['decision'] == 'propose'
    assert result['conflict']['telemetry']['dimension'] == 'counterevidence'
    assert result['forged']['decision'] == 'propose'
    assert result['forgedCalls'] == 0


def test_cited_memory_requires_complete_bounded_review() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const entries=[{role:'user',content:'This project uses SQLite.'},
        ...Array.from({length:35},(_,i)=>({role:'toolResult',content:`Public observation ${i}: `+'x'.repeat(2800)})),
        {role:'user',content:'Correction: this project uses PostgreSQL, not SQLite.'}];
      const snapshot={contextEnabled:true,entries};
      const candidates=[{name:'database.md',kind:'project',classification:'safe',content:'This project uses SQLite.',evidence:[{index:0,role:'user',quote:'This project uses SQLite.'}]}];
      let mode='good',calls=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const req=JSON.parse(init.body);calls.push(req);const state=JSON.parse(req.state);
        const review=state.reviewEvidence;
        if(mode==='offline'&&review?.entries.some(e=>e.index===36))throw new Error('provider private detail');
        const answers={};
        for(const [key,q] of Object.entries(req.questions)) {
          const selected=key.startsWith('counter_')?(mode==='conflict'&&review.entries.some(e=>e.index===36)?'contradicts':mode==='uncertain'?'unclear':'compatible'):key.startsWith('relation_')?'unrelated':'grounded';
          answers[key]={type:'choice',choice:selected,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===selected?1:0]))};
        }
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:100,output_tokens:20},answers}));
      }});
      const good=await judge.validate('memory',snapshot,candidates,[]);
      const requests=calls;calls=[];mode='conflict';const conflict=await judge.validate('memory',snapshot,candidates,[]);
      calls=[];mode='offline';const offline=await judge.validate('memory',snapshot,candidates,[]);
      calls=[];mode='uncertain';const uncertain=await judge.validate('memory',snapshot,candidates,[]);
      const coverage=requests.flatMap(r=>JSON.parse(r.state).reviewEvidence?.entries.map(e=>e.index)??[]);
      console.log(JSON.stringify({good,conflict,offline,uncertain,coverage,maxBytes:Math.max(...requests.map(r=>Buffer.byteLength(JSON.stringify(r))))}));
    ''')
    assert result["good"]["decision"] == "allow"
    assert result["coverage"] == list(range(37))
    assert result["maxBytes"] <= 64_000
    assert result["good"]["telemetry"]["coveredEntries"] == 37
    assert result["conflict"]["decision"] == "propose"
    assert result["conflict"]["telemetry"]["dimension"] == "counterevidence"
    assert result["offline"]["decision"] == "propose"
    assert result["offline"]["telemetry"]["reason"] == "unavailable"
    assert "inputTokens" not in result["offline"]["telemetry"]
    assert result["offline"]["telemetry"]["knownInputTokens"] > 0
    assert result["uncertain"]["decision"] == "propose"


def test_cited_memory_preflights_uncited_privacy_citations_and_bounds() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let calls=0;
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async()=>{calls++;throw new Error('must not call');}});
      const candidate={name:'database.md',kind:'project',classification:'safe',content:'This project uses SQLite.',evidence:[{index:0,role:'user',quote:'This project uses SQLite.'}]};
      const base={contextEnabled:true,entries:[{role:'user',content:'This project uses SQLite.'}]};
      const sensitive=await judge.validate('memory',{...base,entries:[...base.entries,{role:'toolResult',content:'api_key: super-secret-fixture-value'}]},[candidate],[]);
      const forged=await judge.validate('memory',base,[{...candidate,evidence:[{index:0,role:'user',quote:'Missing original quote.'}]}],[]);
      const huge=await judge.validate('memory',{...base,entries:[...base.entries,{role:'toolResult',content:'x'.repeat(70_000)}]},[candidate],[]);
      const tooMany=await judge.validate('memory',{...base,entries:[...base.entries,...Array.from({length:30},()=>({role:'toolResult',content:'x'.repeat(20_000)}))]},[candidate],[]);
      console.log(JSON.stringify({calls,sensitive,forged,huge,tooMany}));
    ''')
    assert result["calls"] == 0
    assert result["sensitive"]["telemetry"]["reason"] == "sensitive"
    for name in ["forged", "huge", "tooMany"]:
        assert result[name]["decision"] == "propose"


def test_cited_review_freezes_every_request_before_first_transport() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:'This project uses SQLite.'},...Array.from({length:8},()=>({role:'toolResult',content:'x'.repeat(2800)})),{role:'toolResult',content:'Verified source schema: PostgreSQL, not SQLite.'}]};
      const candidate={name:'database.md',kind:'project',classification:'safe',content:'This project uses SQLite.',evidence:[{index:0,role:'user',quote:'This project uses SQLite.'}]};
      let first=true,retained=false;
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const req=JSON.parse(init.body), state=JSON.parse(req.state);
        if(first){first=false;snapshot.entries.at(-1).content='Altered after planning';}
        const contradiction=state.reviewEvidence?.entries.some(e=>JSON.stringify(e.entry).includes('Verified source schema: PostgreSQL'));
        if(contradiction)retained=true;
        const answers=Object.fromEntries(Object.entries(req.questions).map(([key,q])=>{
          const selected=key.startsWith('counter_')?(contradiction?'contradicts':'compatible'):'grounded';
          return [key,{type:'choice',choice:selected,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===selected?1:0]))}];
        }));
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:100,output_tokens:20},answers}));
      }});
      console.log(JSON.stringify({result:await judge.validate('memory',snapshot,[candidate],[]),retained}));
    ''')
    assert result['retained'] is True
    assert result['result']['decision'] == 'propose'


def test_harness_citations_use_complete_review_without_losing_authority_checks() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:'Never run git push in this project in future tasks.'},...Array.from({length:30},()=>({role:'toolResult',content:'unrelated '.repeat(280)})),{role:'user',content:'Correction: git push is allowed after my explicit approval.'}]};
      const candidates=[{op:'addRule',rule:{bash:'^git[ \\t]+push(?:[ \\t]|$(?![\\s\\S]))',action:'block',message:'Never run git push.'}}];
      const citations=[{index:0,eventIndex:0,source:'user',quote:'Never run git push in this project in future tasks.',count:1}];
      let mode='good', calls=[],keys=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const req=JSON.parse(init.body),state=JSON.parse(req.state);calls.push(req);keys.push(...Object.keys(req.questions));
        const answers=Object.fromEntries(Object.entries(req.questions).map(([key,q])=>{
          const selected=key.startsWith('counter_')?(mode==='exception'&&state.reviewEvidence.entries.some(e=>e.index===31)?'contradicts':'compatible'):key.startsWith('authority_')?'lasting':key.startsWith('family_')?'authorized':'faithful';
          return [key,{type:'choice',choice:selected,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===selected?1:0]))}];
        }));
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:100,output_tokens:20},answers}));
      }});
      const good=await judge.validate('harness',snapshot,candidates,[],undefined,citations);
      const coverage=calls.flatMap(r=>JSON.parse(r.state).reviewEvidence?.entries.map(e=>e.index)??[]);
      mode='exception';const exception=await judge.validate('harness',snapshot,candidates,[],undefined,citations);
      const before=calls.length;const forged=await judge.validate('harness',snapshot,candidates,[],undefined,[{...citations[0],eventIndex:1}]);
      console.log(JSON.stringify({good,exception,forged,coverage,keys,forgedCalls:calls.length-before}));
    ''')
    assert result['good']['decision'] == 'allow'
    assert result['coverage'] == list(range(32))
    assert all(key in result['keys'] for key in ['authority_0', 'family_0', 'explanation_0'])
    assert result['exception']['decision'] == 'propose'
    assert result['exception']['telemetry']['dimension'] == 'counterevidence'
    assert result['forgedCalls'] == 0


def test_early_window_contradiction_is_not_overwritten_by_later_compatibility() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:'This project uses SQLite.'},{role:'toolResult',content:'Verified: PostgreSQL, not SQLite.'},...Array.from({length:18},()=>({role:'toolResult',content:'unrelated '.repeat(280)}))]};
      const candidate={name:'database.md',kind:'project',classification:'safe',content:'This project uses SQLite.',evidence:[{index:0,role:'user',quote:'This project uses SQLite.'}]};
      const responses=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const req=JSON.parse(init.body), state=JSON.parse(req.state);
        const conflict=state.reviewEvidence?.entries.some(e=>e.index===1);
        const answers=Object.fromEntries(Object.entries(req.questions).map(([key,q])=>{
          const selected=key.startsWith('counter_')?(conflict?'contradicts':'compatible'):'grounded';
          if(key.startsWith('counter_'))responses.push({key,selected});
          return [key,{type:'choice',choice:selected,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===selected?1:0]))}];
        }));
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:100,output_tokens:20},answers}));
      }});
      console.log(JSON.stringify({result:await judge.validate('memory',snapshot,[candidate],[]),responses}));
    ''')
    assert result['responses'][0]['selected'] == 'contradicts'
    assert result['responses'][-1]['selected'] == 'compatible'
    assert result['result']['decision'] == 'propose'
    assert result['result']['telemetry']['dimension'] == 'counterevidence'


def test_cancelled_jobs_do_not_count_as_outbound_requests() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const controller=new AbortController();let calls=0;
      const snapshot={contextEnabled:true,entries:[{role:'user',content:'This project uses SQLite.'},...Array.from({length:25},()=>({role:'toolResult',content:'x'.repeat(2800)}))]};
      const candidate={name:'database.md',kind:'project',classification:'safe',content:'This project uses SQLite.',evidence:[{index:0,role:'user',quote:'This project uses SQLite.'}]};
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async()=>{calls++;controller.abort();throw new Error('abort');}});
      const result=await judge.validate('memory',snapshot,[candidate],[],controller.signal);
      console.log(JSON.stringify({calls,result}));
    ''')
    assert result['calls'] == 1
    assert result['result']['telemetry']['requestCount'] == 1
    assert result['result']['decision'] == 'propose'


def test_twelve_cited_harness_operations_split_support_with_atomic_results() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const entries=Array.from({length:12},(_,i)=>({role:'user',content:`Never run git operation${i} in this project in future tasks.`}));
      const candidates=entries.map((_,i)=>({op:'addRule',rule:{bash:`^git[ \\t]+operation${i}(?:[ \\t]|$(?![\\s\\S]))`,action:'block',message:`Never run git operation${i}.`}}));
      const citations=entries.map((e,i)=>({index:i,eventIndex:i,source:'user',quote:e.content,count:1}));
      let requests=[],active=0,peak=0,fail=false;
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const req=JSON.parse(init.body);requests.push(req);active++;peak=Math.max(peak,active);
        await Promise.resolve();active--;
        if(fail&&Object.hasOwn(req.questions,'family_11'))throw new Error('offline');
        const answers=Object.fromEntries(Object.entries(req.questions).map(([key,q])=>{
          const selected=key.startsWith('counter_')?'compatible':key.startsWith('authority_')?'lasting':key.startsWith('family_')?'authorized':'faithful';
          return [key,{type:'choice',choice:selected,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===selected?1:0]))}];
        }));
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:100,output_tokens:20},answers}));
      }});
      const good=await judge.validate('harness',{contextEnabled:true,entries},candidates,[],undefined,citations);
      const goodRequests=requests;requests=[];fail=true;
      const partial=await judge.validate('harness',{contextEnabled:true,entries},candidates,[],undefined,citations);
      console.log(JSON.stringify({good,partial,peak,count:goodRequests.length,maxQuestions:Math.max(...goodRequests.map(r=>Object.keys(r.questions).length)),maxBytes:Math.max(...goodRequests.map(r=>Buffer.byteLength(JSON.stringify(r))))}));
    ''')
    assert result['good']['decision'] == 'allow'
    assert result['count'] == 3
    assert result['maxQuestions'] <= 32
    assert result['maxBytes'] <= 64_000
    assert result['peak'] <= 4
    assert result['good']['telemetry']['completedWindows'] == 1
    assert result['good']['telemetry']['coveredEntries'] == 12
    assert result['partial']['decision'] == 'propose'
    assert result['partial']['telemetry']['knownInputTokens'] == 200


def test_harness_explanation_judgment_includes_parent_validated_scope() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let meaning;
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const req=JSON.parse(init.body);if(req.questions.explanation_0)meaning=req.questions.explanation_0;
        throw new Error('fixture stops before any decision');
      }});
      await judge.validate('harness',{contextEnabled:true,entries:[{role:'user',content:'Never run git push in this project in future tasks.'}]},[{op:'addRule',rule:{bash:'^git[ \\t]+push(?:[ \\t]|$(?![\\s\\S]))',action:'block',message:'Never run git push.'}}],[],undefined,[{index:0,eventIndex:0,source:'user',quote:'Never run git push in this project in future tasks.',count:1}]);
      console.log(JSON.stringify({meaning}));
    ''')
    assert 'current project, lasting' in str(result)


def test_full_review_keeps_support_context_and_oversized_whole_entries() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const source='For future work the verified regression command is pnpm test.';
      const longEntry={role:'toolResult',content:'Public test output: '+'x'.repeat(29_000)+'\nVerified command: pnpm test passed.'};
      const snapshot={contextEnabled:true,entries:[{role:'user',content:source},longEntry,{role:'toolResult',content:'Unrelated successful read.'}]};
      const candidate={name:'test-command.md',kind:'project',classification:'safe',content:'The regression command is pnpm test.',evidence:[{index:0,role:'user',quote:source}]};
      let requests=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const req=JSON.parse(init.body);requests.push(req);const state=JSON.parse(req.state);
        const supported=state.supportEvidence?.entries.some(e=>e.index===0&&e.entry.content===source);
        const answers=Object.fromEntries(Object.entries(req.questions).map(([key,q])=>{
          const selected=key.startsWith('counter_')?(supported?'compatible':'unclear'):'grounded';
          return [key,{type:'choice',choice:selected,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===selected?1:0]))}];
        }));
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:100,output_tokens:20},answers}));
      }});
      const judgment=await judge.validate('memory',snapshot,[candidate],[]);
      const retained=requests.flatMap(r=>JSON.parse(r.state).reviewEvidence?.entries??[]);
      console.log(JSON.stringify({judgment,retained,maxBytes:Math.max(...requests.map(r=>Buffer.byteLength(JSON.stringify(r)))),longEntry}));
    ''')
    assert result['judgment']['decision'] == 'allow'
    assert result['judgment']['telemetry']['coveredEntries'] == 3
    assert [e['index'] for e in result['retained']] == [0, 1, 2]
    assert result['retained'][1]['entry'] == result['longEntry']
    assert result['maxBytes'] <= 64_000


def test_verbatim_harness_explanation_keeps_authority_and_scope_checks() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const source='Never run git push in this project, including --dry-run, in future tasks.';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:source}]};
      const candidate={op:'addRule',rule:{bash:'^git[ \\t]+push(?:[ \\t]|$(?![\\s\\S]))',action:'block',message:source}};
      const citation={index:0,eventIndex:0,source:'user',quote:source,count:1};
      let keys=[],authority='lasting',family='authorized';
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const req=JSON.parse(init.body);keys.push(...Object.keys(req.questions));
        const answers=Object.fromEntries(Object.entries(req.questions).map(([key,q])=>{
          const selected=key.startsWith('counter_')?'compatible':key.startsWith('authority_')?authority:key.startsWith('family_')?family:'faithful';
          return [key,{type:'choice',choice:selected,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===selected?1:0]))}];
        }));return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:100,output_tokens:20},answers}));
      }});
      const good=await judge.validate('harness',snapshot,[candidate],[],undefined,[citation]);const goodKeys=keys;keys=[];
      authority='conditional';const approval=await judge.validate('harness',snapshot,[candidate],[],undefined,[citation]);
      authority='lasting';family='extra';const expansion=await judge.validate('harness',snapshot,[candidate],[],undefined,[citation]);
      family='authorized';keys=[];await judge.validate('harness',snapshot,[{...candidate,rule:{...candidate.rule,message:'Never run git push or git fetch.'}}],[],undefined,[citation]);
      const paraphraseKeys=keys;keys=[];await judge.validate('harness',snapshot,[candidate],[],undefined,[{...citation,eventIndex:9}]);
      console.log(JSON.stringify({good,goodKeys,approval,expansion,paraphraseKeys,forgedCalls:keys.length}));
    ''')
    assert result['good']['decision'] == 'allow'
    assert 'explanation_0' not in result['goodKeys']
    assert 'authority_0' in result['goodKeys'] and 'family_0' in result['goodKeys']
    assert result['approval']['decision'] == 'propose'
    assert result['expansion']['decision'] == 'propose'
    assert 'explanation_0' in result['paraphraseKeys']
    assert result['forgedCalls'] == 0


def test_memory_counterevidence_judges_content_without_write_metadata() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let counterMeanings=[];
      const source='For future personal reports, always end with PUBLIC_SYNTHETIC_SIGNOFF.';
      const candidate={name:'report.md',kind:'preference',classification:'private',content:source,evidence:[{index:0,role:'user',quote:source}]};
      const judge=createJevJudge({enabled:true,apiKey:'fixture',allowPrivateMemory:true,fetch:async(_url,init)=>{
        const req=JSON.parse(init.body);
        const answers=Object.fromEntries(Object.entries(req.questions).map(([key,q])=>{
          const counter=key.startsWith('counter_');if(counter)counterMeanings.push(q.instructions.candidate);
          const selected=counter?(Object.keys(q.instructions.candidate).join(',')==='content'?'compatible':'unclear'):'grounded';
          return [key,{type:'choice',choice:selected,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===selected?1:0]))}];
        }));return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:100,output_tokens:20},answers}));
      }});
      const result=await judge.validate('memory',{contextEnabled:true,entries:[{role:'user',content:source},{role:'user',content:'Do not write learning files directly; the extension handles learning.'}]},[candidate],[]);
      console.log(JSON.stringify({result,counterMeanings}));
    ''')
    assert result['result']['decision'] == 'allow'
    assert list(result['counterMeanings'][0]) == ['content']


def test_literal_tab_classes_keep_proved_family_without_widening_grammar() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const source='Never run git push in this project in future tasks, including any arguments.';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:source}]};
      const citation={index:0,eventIndex:0,source:'user',quote:source,count:1};
      let keys=[],mode='good',calls=0;
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        calls++;const req=JSON.parse(init.body);keys.push(...Object.keys(req.questions));
        const answers=Object.fromEntries(Object.entries(req.questions).map(([key,q])=>{
          const choice=key.startsWith('authority_')?(mode==='approval'?'conditional':'lasting'):key.startsWith('family_')?(mode==='exact'?'extra':'authorized'):key.startsWith('counter_')?(mode==='revoked'?'contradicts':'compatible'):'unclear';
          return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(label=>[label,label===choice?1:0]))}];
        }));
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:10,output_tokens:10},answers}));
      }});
      const make=(bash)=>({op:'addRule',rule:{bash,action:'block',message:source}});
      const end='$(?![\\s\\S])';
      const variants=[];
      for(const separator of ['[ \\t]+','[ \t]+'])for(const boundary of ['[ \\t]','[ \t]']){
        keys=[];const bash=`^git${separator}push(?:${boundary}|${end})`;
        const answer=await judge.validate('harness',snapshot,[make(bash)],[],undefined,[citation]);
        const probes=['git push','git\tpush','git push --dry-run','git\npush','git\u00a0push','git push\r','git pushy'];
        variants.push({answer,keys:[...keys],matches:probes.map(probe=>new RegExp(bash).test(probe))});
      }
      const rejected=[];
      for(const bash of [`^git[\\s]+push(?:[ \\t]|${end})`,`^git[ \t\r]+push(?:[ \t]|${end})`,`^git[ \t]+push(?:[ \t]|$)`,`^git[ \t\u00a0]+push(?:[ \t]|${end})`]){
        keys=[];const answer=await judge.validate('harness',snapshot,[make(bash)],[],undefined,[citation]);rejected.push({answer,keys:[...keys]});
      }
      const candidate=make(`^git[ \t]+push(?:[ \t]|${end})`);
      mode='approval';const approval=await judge.validate('harness',snapshot,[candidate],[],undefined,[citation]);
      mode='exact';const exact=await judge.validate('harness',snapshot,[candidate],[],undefined,[citation]);
      mode='revoked';const revoked=await judge.validate('harness',snapshot,[candidate],[],undefined,[citation]);
      const before=calls;await judge.validate('harness',snapshot,[candidate],[],undefined,[{...citation,quote:'forged'}]);
      console.log(JSON.stringify({variants,rejected,approval,exact,revoked,forgedCalls:calls-before}));
    ''')
    assert all(row['answer']['decision'] == 'allow' for row in result['variants'])
    assert all('authority_0' in row['keys'] and 'family_0' in row['keys'] for row in result['variants'])
    assert all(row['matches'] == [True, True, True, False, False, False, False] for row in result['variants'])
    assert all(row['answer']['decision'] == 'propose' and 'family_0' not in row['keys'] for row in result['rejected'])
    assert all(result[key]['decision'] == 'propose' for key in ['approval', 'exact', 'revoked'])
    assert result['forgedCalls'] == 0


def test_proved_family_counterevidence_uses_matching_meaning_and_preserves_exceptions() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const source='Never run git push in this project in future tasks, including any arguments.';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:source},{role:'toolResult',content:'Do not directly write learning files; the parent extension handles them.'}]};
      const candidate={op:'addRule',rule:{id:'administrative-id',bash:'^git[ \\t]+push(?:[ \\t]|$(?![\\s\\S]))',action:'block',message:source},cases:{positive:[{bash:'git push --dry-run'}],negative:[{bash:'git status'}]}};
      const citation={index:0,eventIndex:0,source:'user',quote:source,count:1};
      let mode='good',counters=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const req=JSON.parse(init.body);const answers={};
        for(const [key,q] of Object.entries(req.questions)){
          let choice=key.startsWith('authority_')?'lasting':key.startsWith('family_')?'authorized':key.startsWith('supported_')?'grounded':key.startsWith('expands_')?'same':'faithful';
          if(key.startsWith('counter_')){
            const c=q.instructions.candidate;counters.push(c);
            choice=mode==='exception'?'contradicts':c.rule.commandWords&&c.rule.matching&&!c.action&&!c.behaviorExamples&&!c.rule.bash&&!c.rule.id?'compatible':'unclear';
          }
          answers[key]={type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(label=>[label,label===choice?1:0]))};
        }
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:10,output_tokens:10},answers}));
      }});
      const good=await judge.validate('harness',snapshot,[candidate],[],undefined,[citation]);const proved=counters;counters=[];
      const unproved=await judge.validate('harness',snapshot,[{...candidate,rule:{...candidate.rule,bash:'git.*push'}}],[],undefined,[citation]);const raw=counters;
      mode='exception';const exception=await judge.validate('harness',{...snapshot,entries:[...snapshot.entries,{role:'user',content:'Correction: git push is allowed after my explicit approval for this invocation.'}]},[candidate],[],undefined,[citation]);
      console.log(JSON.stringify({good,proved,unproved,raw,exception,source}));
    ''')
    assert result['good']['decision'] == 'allow'
    assert result['proved'][0]['rule']['commandWords'] == 'git push'
    assert result['proved'][0]['rule']['message'] == result['source']
    assert result['proved'][0]['rule']['action'] == 'block'
    assert result['proved'][0]['rule']['scope'] == 'current project'
    assert result['unproved']['decision'] == 'propose'
    assert result['raw'][0]['rule']['bash'] == 'git.*push'
    assert 'behaviorExamples' in result['raw'][0]
    assert result['exception']['decision'] == 'propose'
    assert result['exception']['telemetry']['reason'] == 'conflict'


def test_cited_new_memory_support_judges_only_body_and_keeps_privacy_preflight() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const source='For future personal reports, always end with PUBLIC_SYNTHETIC_SIGNOFF.';
      const candidate={name:'report.md',kind:'preference',classification:'private',content:source,evidence:[{index:0,role:'user',quote:source}]};
      const snapshot={contextEnabled:true,entries:[{role:'user',content:source}]};
      let calls=0,meanings=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',allowPrivateMemory:true,fetch:async(_url,init)=>{
        calls++;const req=JSON.parse(init.body);
        const answers=Object.fromEntries(Object.entries(req.questions).map(([key,q])=>{
          const support=key.startsWith('supported_');if(support)meanings.push(q.instructions.candidate);
          const selected=support?(Object.keys(q.instructions.candidate).join(',')==='content'?'grounded':'unclear'):'compatible';
          return [key,{type:'choice',choice:selected,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(label=>[label,label===selected?1:0]))}];
        }));return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:100,output_tokens:20},answers}));
      }});
      const good=await judge.validate('memory',snapshot,[candidate],[]);const before=calls;
      const sensitive=await judge.validate('memory',snapshot,[{...candidate,name:'api_key=sk-'+ 'x'.repeat(24)}],[]);
      const privateDenied=await createJevJudge({enabled:true,apiKey:'fixture',fetch:async()=>{throw new Error('must not transport');}}).validate('memory',snapshot,[candidate],[]);
      console.log(JSON.stringify({good,meanings,sensitive,privateDenied,sensitiveCalls:calls-before}));
    ''')
    assert result['good']['decision'] == 'allow'
    assert result['meanings'] == [{'content': 'For future personal reports, always end with PUBLIC_SYNTHETIC_SIGNOFF.'}]
    assert result['sensitive']['telemetry']['reason'] == 'sensitive'
    assert result['sensitiveCalls'] == 0
    assert result['privateDenied']['telemetry']['reason'] == 'private-memory-denied'


def test_single_executable_family_proves_only_matching_and_retains_semantic_holds() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const quote='In this project never run a command beginning with npm in future tasks.';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:quote}]};
      const citation={index:0,eventIndex:0,source:'user',quote,count:1};
      let mode='good',keys=[],meanings=[],familyMatching='';
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const req=JSON.parse(init.body),answers={};keys.push(...Object.keys(req.questions));
        for(const [key,q] of Object.entries(req.questions)){
          if(key.startsWith('counter_'))meanings.push(q.instructions.candidate);
          if(key.startsWith('family_'))familyMatching=q.instructions.candidate.matching;
          const choice=key.startsWith('authority_')?(mode==='temporary'?'temporary':'lasting'):key.startsWith('family_')?(mode==='narrow'?'extra':'authorized'):key.startsWith('counter_')?(mode==='revoked'?'contradicts':'compatible'):key.startsWith('explanation_')?'faithful':'unclear';
          answers[key]={type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(label=>[label,label===choice?1:0]))};
        }
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:10,output_tokens:10},answers}));
      }});
      const candidate={op:'addRule',rule:{bash:'^npm(?:[ \\t]|$(?![\\s\\S]))',action:'block',message:'Do not run npm in this project.'}};
      const good=await judge.validate('harness',snapshot,[candidate],[],undefined,[citation]);const goodKeys=[...keys],goodMeaning=meanings[0];
      const held=[];for(mode of ['temporary','narrow','revoked'])held.push(await judge.validate('harness',snapshot,[candidate],[],undefined,[citation]));
      mode='good';keys=[];meanings=[];
      const correction=await judge.validate('harness',snapshot,[{...candidate,op:'updateRule',correction:{eventIndex:0,quote,priorRevision:'a'.repeat(64)},priorRule:candidate.rule}],[],undefined,[citation]);
      const correctionKeys=[...keys];
      const probes=['npm','npm test','npm\t--version','npm \nnext','npm \u00a0next','npms','npm\r','npm\n','npm\u00a0test',' npm test','env npm test',"'npm' test",'/usr/bin/npm test'];
      console.log(JSON.stringify({good,goodKeys,goodMeaning,familyMatching,held,correction,correctionKeys,matches:probes.map(s=>new RegExp(candidate.rule.bash).test(s))}));
    ''')
    assert result['good']['decision'] == 'allow'
    assert {'authority_0', 'explanation_0', 'family_0', 'counter_0_0'} <= set(result['goodKeys'])
    assert result['goodMeaning']['rule']['commandWords'] == 'npm'
    assert 'word boundary' not in result['familyMatching']
    assert 'absolute end' in result['familyMatching']
    assert 'unrestricted' in result['familyMatching']
    assert all(row['decision'] == 'propose' for row in result['held'])
    assert result['correction']['decision'] == 'propose'
    assert 'family_0' not in result['correctionKeys']
    assert result['matches'] == [True] * 5 + [False] * 8


def test_encoded_mutation_context_splits_whole_review_windows_before_transport() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const entries=Array.from({length:16},(_,i)=>({role:'user',content:`Source ${i}: SQLite. `+'"quoted" \\ '.repeat(260)}));
      entries.push({role:'user',content:'Correction: PostgreSQL replaces SQLite.'});
      const evidence=entries.slice(0,8).map((e,index)=>({index,quote:`Source ${index}: SQLite.`}));
      const candidates=[{kind:'rewrite',name:'db.md',classification:'safe',content:'SQLite. '+'replacement '.repeat(250),evidence}];
      const existing=[{name:'db.md',content:'SQLite. '+'predecessor '.repeat(250),description:'database',type:'project',classification:'safe'}];
      let conflict=false,calls=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_u,init)=>{
        const req=JSON.parse(init.body);calls.push(req);const s=JSON.parse(req.state);
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(req.questions).map(([key,q])=>{
          const choice=key.startsWith('counter_')?(conflict&&s.reviewEvidence.entries.some(e=>e.index===16)?'contradicts':'compatible'):key.startsWith('relation_')?'supplement':'grounded';
          return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}];
        }))}));
      }});
      const good=await judge.validate('memory',{contextEnabled:true,entries},candidates,existing);
      const coverage=[...new Set(calls.flatMap(r=>JSON.parse(r.state).reviewEvidence?.entries.map(e=>e.index)??[]))].sort((a,b)=>a-b);
      const bytes=calls.map(r=>Buffer.byteLength(JSON.stringify(r)));
      const retained=calls.every(r=>{const s=JSON.parse(r.state);return JSON.stringify(s.existingMemories)===JSON.stringify(existing)&&JSON.stringify(s.proposedMemoryOperations)===JSON.stringify(candidates)});
      conflict=true;calls=[];const bad=await judge.validate('memory',{contextEnabled:true,entries},candidates,existing);
      console.log(JSON.stringify({good,bad,coverage,bytes,retained}));
    ''')
    assert result['good']['decision'] == 'allow'
    assert result['coverage'] == list(range(17))
    assert max(result['bytes']) <= 64_000
    assert result['retained']
    assert result['bad']['decision'] == 'propose'
    assert result['bad']['telemetry']['dimension'] == 'counterevidence'
