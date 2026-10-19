from support import isolated_run_bun


def test_normal_review_requests_supported_context_without_changing_frozen_wire():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import {createHash} from 'node:crypto';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const input=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-mutation-references.json','utf8')),out=[];
      for(const mode of ['normal','disabled','bounded']){
        const requests=[];const judge=createJevJudge({enabled:true,apiKey:'fixture',allowPrivateMemory:true,requestConcurrency:1,...(mode==='disabled'?{longContext:false}:{}),...(mode==='bounded'?{maxRequestBytes:64000}:{}),fetch:async(_u,init)=>{
          const wire=String(init.body),r=JSON.parse(wire);requests.push({hash:createHash('sha256').update(wire).digest('hex'),longContext:new Headers(init.headers).get('TypeSafe-Danger-Zone-Long-Context')});
          return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{const labels=Object.keys(q.criteria),choice=['compatible','grounded','consistent','independent','unrelated'].find(x=>labels.includes(x))??labels[0];return[key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(labels.map(x=>[x,+(x===choice)]))}]}))}));
        }});const result=await judge.validate('memory',input.evidence,input.candidates,input.existing,undefined,undefined,undefined,input.memorySources);out.push({mode,requests,complete:result.candidateReview?.complete});
      }console.log(JSON.stringify(out));
    ''')
    normal, disabled, bounded = value
    assert normal['complete'] and disabled['complete'] and bounded['complete']
    assert all(r['longContext'] == 'true' for r in normal['requests'])
    assert all(r['longContext'] is None for r in disabled['requests'] + bounded['requests'])
    assert [r['hash'] for r in normal['requests']] == [r['hash'] for r in disabled['requests']]


def test_actual_capacity_failure_keeps_every_original_entry_and_semantic_holds():
    # Restore the frozen pre-decomposition question and criteria for V40 wire comparison.
    # The actual newer wire differs. This controlled capacity response proves
    # opt-in/coverage only, never current token capacity or semantic acceptance.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import {createHash} from 'node:crypto';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const input=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-jev-context-overflow.json','utf8')),out=[];const sha=s=>createHash('sha256').update(s).digest('hex');
      for(const mode of ['normal','disabled','uncertain']){
        const requests=[];const judge=createJevJudge({enabled:true,apiKey:'fixture',allowPrivateMemory:true,requestConcurrency:1,...(mode==='disabled'?{longContext:false}:{}),fetch:async(_u,init)=>{
          const wire=String(init.body),r=JSON.parse(wire),state=typeof r.state==='string'?JSON.parse(r.state):r.state,hash=sha(wire),long=new Headers(init.headers).get('TypeSafe-Danger-Zone-Long-Context')==='true';
          const historical=JSON.parse(wire);
          const historicalState=typeof historical.state==='string'?JSON.parse(historical.state):historical.state;
          delete historicalState.originalUserEvidence;
          if(historicalState.sourceComparisonEvidence)delete historicalState.sourceComparisonEvidence.exactQuoteComparisons;
          if(historicalState.mutationComparison)delete historicalState.mutationComparison.exactTextComparisons;
          historical.state=typeof historical.state==='string'?JSON.stringify(historicalState):historicalState;
          for(const key of Object.keys(historical.questions))if(key.startsWith('counter_preservation_')||key.startsWith('counter_permission_'))delete historical.questions[key];
          for(const [key,q] of Object.entries(historical.questions))if(key.startsWith('counter_')){q.instructions.question=key.startsWith('counter_description_')?input.historicalDescriptionQuestion:input.historicalCounterQuestion;q.criteria={compatible:'No entry contradicts, retracts or limits the candidate; irrelevant entries and faithful repetitions are compatible.',contradicts:'An entry establishes a conflicting fact, a revoked preference or an exception missing from the candidate.',unclear:'A material potential conflict or limitation cannot be resolved from the available context.'};}
          const historicalWire=JSON.stringify(historical),historicalHash=sha(historicalWire);
          requests.push({keys:Object.keys(r.questions),hash,bytes:Buffer.byteLength(wire),historicalHash,historicalBytes:Buffer.byteLength(historicalWire),long,entries:state.reviewEvidence?.entries?.map(x=>x.index)??[]});
          if(historicalHash===input.historicalFailedWireHash&&!long)return new Response(JSON.stringify({error:'max_tokens_exceeded'}),{status:400});
          const answers=Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{const labels=Object.keys(q.criteria),choice=['compatible','grounded','consistent','independent','unrelated'].find(x=>labels.includes(x))??labels[0],held=mode==='uncertain'&&key==='counter_0_2';return[key,{type:'choice',choice,confidence:held?0.79:1,probabilities:Object.fromEntries(labels.map(x=>[x,x===choice?(held?0.89:1):(held?0.11/(labels.length-1):0)]))}]}));return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:1}}));
        }});const memorySources={evidenceDigest:sha(JSON.stringify(input.evidence)),entryDigests:input.evidence.entries.slice(input.boundSourceEntryStart).map(x=>sha(JSON.stringify(x)))};const result=await judge.validate('memory',input.evidence,input.candidates,input.existing,undefined,undefined,undefined,memorySources);out.push({mode,decision:result.decision,telemetry:result.telemetry,complete:result.candidateReview?.complete,requests,entryCount:input.evidence.entries.length});
      }console.log(JSON.stringify(out));
    ''')
    normal, disabled, uncertain = value
    assert normal['decision'] == 'allow' and normal['complete']
    assert [i for r in normal['requests'] for i in r['entries']] == list(range(normal['entryCount']))
    exact = [r for r in normal['requests'] if r['historicalHash'] == '407827e23f735ae2f8a31d7e24ba2ace211a5c06e63587f79cf8e0ab26005426']
    assert len(exact) == 1 and exact[0]['long'] and exact[0]['historicalBytes'] == 132837
    assert exact[0]['hash'] != exact[0]['historicalHash'] and exact[0]['bytes'] > exact[0]['historicalBytes']
    # One body-only request precedes the four original requests through the failed wire.
    assert disabled['decision'] == 'propose' and len(disabled['requests']) == 5
    assert disabled['requests'][0]['keys'] == ['coherence_0']
    assert all(not any(k.startswith('coherence_') for k in r['keys']) for r in disabled['requests'][1:])
    assert disabled['requests'][-1]['historicalHash'] == exact[0]['historicalHash']
    assert [r['hash'] for r in disabled['requests']] == [r['hash'] for r in normal['requests'][:5]]
    assert disabled['telemetry']['requestCount'] == 5
    assert disabled['telemetry']['completedRequests'] == 4
    assert disabled['telemetry']['httpStatus'] == 400
    assert disabled['telemetry']['knownInputTokens'] == 4
    assert 'inputTokens' not in disabled['telemetry']
    assert 'retriedRequests' not in disabled['telemetry']
    assert uncertain['decision'] == 'propose'
    assert [r['hash'] for r in uncertain['requests']] == [r['hash'] for r in normal['requests']]


def test_long_context_configuration_is_optional_boolean_and_explicitly_preserved():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {readJevConfigState} from './packages/continual-learning/extensions/config.ts';
      const file=path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json'),out=[];
      for(const value of [true,false,'true',null]){fs.writeFileSync(file,JSON.stringify({jev:{longContext:value}}));out.push(readJevConfigState());}console.log(JSON.stringify(out));
    ''')
    assert value[0]['config']['longContext'] is True
    assert value[1]['config']['longContext'] is False
    assert value[2:] == [{'invalid': 'invalid-config'}, {'invalid': 'invalid-config'}]
