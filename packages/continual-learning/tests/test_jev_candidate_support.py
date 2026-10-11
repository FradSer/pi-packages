from support import isolated_run_bun


def test_memory_batches_keep_candidate_citations_and_complete_global_counterreview() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const entries=[{role:'user',content:'Maintain these observed source contracts.'}];
      for(let i=0;i<3;i++) {
        entries.push({role:'assistant',content:[{type:'toolCall',id:`read-${i}`,name:'read',arguments:{path:`source-${i}.ts`,context:'p'.repeat(2000)}}]});
        entries.push({role:'toolResult',toolCallId:`read-${i}`,toolName:'read',content:`Source contract ${i}: `+'x'.repeat(19000)});
      }
      entries.push(...Array.from({length:20},(_,i)=>({role:'toolResult',content:`Other observation ${i}: `+'y'.repeat(1200)})));
      entries.push({role:'user',content:'Correction: contract zero is revoked.'});
      const snapshot={contextEnabled:true,entries};
      const candidates=Array.from({length:3},(_,i)=>({name:`contract-${i}.md`,kind:i===0?'rewrite':'project',classification:'safe',
        content:`---\nname: contract-${i}\ndescription: Source contract ${i}\n---\nSource contract ${i}.`,
        evidence:[{index:2+i*2,role:'toolResult',quote:`Source contract ${i}:`}]}));
      const existing=[{name:'contract-0.md',classification:'safe',type:'project',description:'old contract',content:'Old exact body.'}];
      let mode='good',calls=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const req=JSON.parse(init.body);calls.push(req);const state=JSON.parse(req.state);
        const answers=Object.fromEntries(Object.entries(req.questions).map(([key,q])=>{
          const conflict=mode==='conflict'&&/^counter(?:_description)?_0_/.test(key)&&state.reviewEvidence.entries.some(e=>e.index===entries.length-1);
          const selected=key.startsWith('counter_')?(conflict?'contradicts':'compatible'):key.startsWith('relation_')?'supplement':'grounded';
          return [key,{type:'choice',choice:selected,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===selected?1:0]))}];
        }));
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers}));
      }});
      const good=await judge.validate('memory',snapshot,candidates,existing);const requests=calls;
      calls=[];mode='conflict';const conflict=await judge.validate('memory',snapshot,candidates,existing);
      calls=[];const sensitive=await judge.validate('memory',{...snapshot,entries:[...entries,{role:'toolResult',content:'OPENAI_API_KEY=sk-'+'a'.repeat(48)}]},candidates,existing);
      const sensitiveCalls=calls.length;
      calls=[];const oversizedEntries=[{...entries[2],content:'Source contract 0: '+'\n'.repeat(23000)}];
      const oversized=await judge.validate('memory',{contextEnabled:true,entries:oversizedEntries},[{...candidates[0],evidence:[{index:0,role:'toolResult',quote:'Source contract 0:'}]}],existing);
      console.log(JSON.stringify({good,conflict,sensitive,sensitiveCalls,oversized,oversizedCalls:calls.length,
        entries:entries.length,candidates,existing,maxBytes:Math.max(0,...requests.map(r=>Buffer.byteLength(JSON.stringify(r)))),
        requests:requests.map(r=>{
          const state=JSON.parse(r.state);const support=state.frozenEvidence??state.supportEvidence;
          const fullCitations=support.entries.every(e=>JSON.stringify(e.entry)===JSON.stringify(entries[e.index]));
          const fullReview=!state.reviewEvidence||state.reviewEvidence.entries.every(e=>JSON.stringify(e.entry)===JSON.stringify(entries[e.index]));
          support.citationToolCalls=support.citationToolCalls.map(c=>({...c,toolCall:{...c.toolCall,arguments:{...c.toolCall.arguments,contextIntact:c.toolCall.arguments.context==='p'.repeat(2000),context:undefined}}}));
          support.entries=support.entries.map(e=>({index:e.index}));
          if(state.reviewEvidence)state.reviewEvidence.entries=state.reviewEvidence.entries.map(e=>({index:e.index}));
          return {state,keys:Object.keys(r.questions),fullCitations,fullReview};
        })}));
    ''')
    assert result['good']['decision'] == 'allow'
    assert result['maxBytes'] <= 64_000
    assert len(result['requests']) <= 68
    coverage = {i: set() for i in range(3)}
    for request in result['requests']:
        assert request['fullCitations'] and request['fullReview']
        state = request['state']
        assert state['existingMemories'] == result['existing']
        assert state['proposedMemoryOperations'] == result['candidates']
        support = state.get('frozenEvidence', state.get('supportEvidence'))
        indexes = {entry['index'] for entry in support['entries']} | set(support.get('reviewEntryIndexes', []))
        expected = set()
        for key in request['keys']:
            parts = key.replace('_description', '').split('_')
            candidate = int(parts[1])
            expected.add(2 + candidate * 2)
            if parts[0] == 'counter':
                coverage[candidate].update(entry['index'] for entry in state['reviewEvidence']['entries'])
        assert indexes == expected
        assert {call['resultIndex'] for call in support['citationToolCalls']} == expected
        for call in support['citationToolCalls']:
            assert call['toolCall']['arguments']['contextIntact']
    assert all(indexes == set(range(result['entries'])) for indexes in coverage.values())
    assert result['conflict']['decision'] == 'propose'
    assert result['conflict']['telemetry']['dimension'] == 'counterevidence'
    assert result['sensitive']['telemetry']['reason'] == 'sensitive'
    assert result['sensitiveCalls'] == 0
    assert result['oversized']['decision'] == 'propose'
    assert result['oversizedCalls'] == 0
