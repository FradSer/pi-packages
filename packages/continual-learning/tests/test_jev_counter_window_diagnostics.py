from support import isolated_run_bun


def test_counter_failure_locates_original_window_for_body_and_description() -> None:
    # Given whole-entry windows, When a complete counter judgment is held,
    # Then retain its original window/range and propose the whole plan.
    rows = isolated_run_bun(r'''
      import {createJevJudge,jevRepairFailureHints} from './packages/continual-learning/extensions/jev-learning.ts';
      import {buildLearningReceipt,learningSummaryDetails} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const quote='This project uses pnpm.',rows=[];
      for(const mode of ['body','description','support','missing','unavailable','cancelled']){
       const snapshot={contextEnabled:true,entries:[{role:'user',content:quote},{role:'toolResult',content:'Public observation. '.repeat(1300)},{role:'user',content:'Unrelated public note.'}]};
       const candidate={name:'PRIVATE_FILENAME.md',kind:'project',classification:'safe',content:`---\nname: fact\ndescription: ${quote}\ntype: project\n---\n${quote}`,evidence:[{index:0,quote,role:'user'}]};
       const controller=new AbortController();let requests=0;
       const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
        requests++;const r=JSON.parse(String(init.body)),answers={};
        if(mode==='unavailable'&&Object.hasOwn(r.questions,'counter_0_1'))throw Error('PRIVATE_ERROR');
        for(const [k,q]of Object.entries(r.questions)){
         if(mode==='missing'&&k==='counter_0_1')continue;
         const held=k===(mode==='description'?'counter_description_0_1':mode==='support'?'supported_0':'counter_0_1');
         const label=held?'unclear':k.startsWith('supported')?'grounded':'compatible';answers[k]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};
        }
        if(mode==='cancelled')controller.abort();
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
       }});
       const result=await judge.validate('memory',snapshot,[candidate],[],controller.signal);
       const receipt=buildLearningReceipt('manual',{memory:true,harness:false,agents:false,reasons:[]},[{phase:'memory',attempt:0,outcome:'proposed',durationMs:1,operations:0,jev:result.telemetry}]);
       rows.push({mode,result,requests,hints:jevRepairFailureHints(result.telemetry),lines:learningSummaryDetails(receipt)});
      }console.log(JSON.stringify(rows));
    ''')
    for row in rows[:2]:
        telemetry = row['result']['telemetry']
        assert row['result']['decision'] == 'propose'
        assert telemetry['evidenceWindows'] == telemetry['completedWindows'] == 3
        assert telemetry['evidenceWindowIndex'] == 1
        assert telemetry['evidenceEntryStart'] == telemetry['evidenceEntryEnd'] == 1
        failure = telemetry['candidateFailures'][0]
        assert failure['evidenceWindowIndex'] == 1
        assert failure['evidenceEntryStart'] == failure['evidenceEntryEnd'] == 1
        assert 'window 1 entries 1-1' in '\n'.join(row['hints'])
        assert 'window 1 entries 1-1' in '\n'.join(row['lines'])
        assert 'PRIVATE_' not in str(telemetry) + str(row['hints']) + str(row['lines'])
    assert rows[1]['result']['telemetry']['field'] == 'description'
    # A support failure precedes a held counter window, so first failure has no range.
    assert 'evidenceWindowIndex' not in rows[2]['result']['telemetry']
    assert 'evidenceWindowIndex' not in rows[2]['result']['telemetry']['candidateFailures'][0]
    for row in rows[3:]:
        assert row['result']['decision'] == 'propose'
        assert 'evidenceWindowIndex' not in row['result']['telemetry']
        assert 'candidateFailures' not in row['result']['telemetry']


def test_counter_locations_are_numeric_only_and_repair_hints_remain_bounded() -> None:
    # Given untrusted persisted location fields, When rendering/hinting,
    # Then discard invalid ranges and never interpolate arbitrary values.
    value = isolated_run_bun(r'''
      import {jevRepairFailureHints} from './packages/continual-learning/extensions/jev-learning.ts';
      import {buildLearningReceipt,learningSummaryDetails} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const rows=[];
      for(const patch of [
       {evidenceWindowIndex:0,evidenceEntryStart:0,evidenceEntryEnd:2},
       {evidenceWindowIndex:'PRIVATE_LOCATION',evidenceEntryStart:0,evidenceEntryEnd:2},
       {evidenceWindowIndex:-1,evidenceEntryStart:0,evidenceEntryEnd:2},
       {evidenceWindowIndex:0,evidenceEntryStart:2,evidenceEntryEnd:1},
       {evidenceWindowIndex:0,evidenceEntryStart:0,evidenceEntryEnd:NaN},
       {evidenceWindowIndex:0,evidenceEntryStart:0,evidenceEntryEnd:2.5},
       {evidenceWindowIndex:0,evidenceEntryStart:0,evidenceEntryEnd:2,dimension:'support'},
      ]){
       const failure={candidateIndex:0,dimension:'counterevidence',reason:'uncertain',...patch};
       const jev={stage:'memory',status:'propose',durationMs:1,...failure,candidateFailures:[failure]};
       const receipt=buildLearningReceipt('manual',{memory:true,harness:false,agents:false,reasons:[]},[{phase:'memory',attempt:0,outcome:'proposed',durationMs:1,operations:0,jev}]);
       rows.push({hints:jevRepairFailureHints(jev),lines:learningSummaryDetails(receipt)});
      }
      const candidateFailures=Array.from({length:128},(_,candidateIndex)=>({candidateIndex,dimension:'counterevidence',reason:'uncertain',evidenceWindowIndex:7,evidenceEntryStart:9007199254740990,evidenceEntryEnd:9007199254740991}));
      const bounded=jevRepairFailureHints({stage:'memory',status:'propose',reason:'uncertain',durationMs:0,candidateFailures});
      console.log(JSON.stringify({rows,bounded}));
    ''')
    assert 'window 0 entries 0-2' in str(value['rows'][0])
    for row in value['rows'][1:]:
        assert 'window ' not in str(row)
        assert 'PRIVATE_LOCATION' not in str(row)
    assert len(value['bounded']) + 1 <= 16
    assert max(map(len, value['bounded'])) <= 400
    assert 'omitted' in value['bounded'][-1]


def test_complete_review_reports_both_body_and_description_holds_to_the_repair_worker() -> None:
    # Given one complete review holds two independent fields, When constructing
    # repair diagnostics, Then neither field's controlled failure is hidden.
    value = isolated_run_bun(r'''
      import {createJevJudge,jevRepairFailureHints} from './packages/continual-learning/extensions/jev-learning.ts';
      const quote='This project uses pnpm.';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:quote}]};
      const candidate={name:'fact.md',kind:'project',classification:'safe',content:`---\nname: fact\ndescription: "${quote}"\ntype: project\n---\n${quote}`,evidence:[{index:0,quote,role:'user'}]};
      const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
        const request=JSON.parse(init.body),answers={};
        for(const [key,q] of Object.entries(request.questions)){
          const held=key==='supported_0'||key==='counter_description_0_0';
          const label=held?'unclear':key.startsWith('supported_')?'grounded':'compatible';
          answers[key]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};
        }
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
      }});
      const result=await judge.validate('memory',snapshot,[candidate],[]);
      console.log(JSON.stringify({result,hints:jevRepairFailureHints(result.telemetry)}));
    ''')
    assert value['result']['decision']=='propose'
    assert value['result']['candidateReview']['complete']
    assert len(value['result']['telemetry']['candidateFailures'])==2
    assert value['result']['telemetry']['candidateFailures'][1]['field']=='description'
    assert 'counterevidence.description:uncertain (window 0 entries 0-0)' in str(value['hints'])
