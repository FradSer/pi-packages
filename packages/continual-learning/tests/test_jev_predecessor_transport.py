from support import isolated_run_bun


def test_predecessor_reference_is_exact_complete_and_does_not_mutate_evidence() -> None:
    result = isolated_run_bun(r'''
      import {compactMemoryPredecessors} from './packages/continual-learning/extensions/jev-memory-predecessors.ts';
      import {createHash} from 'node:crypto';
      const body='Old contract.\n中文😀\nKeep every constraint.\n'.repeat(30);
      const state={existingMemories:[{name:'old.md',content:body,classification:'private'},{name:'partial.md',content:body+'missing'}],reviewEvidence:{entries:[{index:9,entry:{message:{role:'toolResult',content:[{type:'text',text:'😀 prefix '+body+' tail'}]}}}]}};
      const before=JSON.stringify(state),compact=compactMemoryPredecessors(state),ref=compact.existingMemories[0].contentReference;
      let text=compact;for(const key of ref.statePath)text=text[key];const restored=text.slice(ref.start,ref.end);
      const tiny={existingMemories:[{name:'tiny.md',content:'fact'}],reviewEvidence:{entries:[{entry:{content:'fact'}}]}};const tinyUnchanged=compactMemoryPredecessors(tiny)===tiny;
      const absent=compactMemoryPredecessors({...state,reviewEvidence:{entries:[{entry:{message:{content:[{type:'image',text:body}]}}}]}});
      console.log(JSON.stringify({tinyUnchanged,ref,restored,body,hash:createHash('sha256').update(restored).digest('hex'),unchanged:before===JSON.stringify(state),evidenceUnchanged:JSON.stringify(compact.reviewEvidence)===JSON.stringify(state.reviewEvidence),partialInline:compact.existingMemories[1].content===body+'missing',nonTextInline:absent.existingMemories[0].content===body,inlineRemoved:!('content' in compact.existingMemories[0])}));
    ''')
    assert result['restored'] == result['body']
    assert result['ref']['sha256'] == result['hash']
    assert result['ref']['units'] == 'UTF-16'
    assert all(result[key] for key in ['tinyUnchanged', 'unchanged', 'evidenceUnchanged', 'partialInline', 'nonTextInline', 'inlineRemoved'])


def test_wire_dedup_preserves_complete_counterevidence_and_negative_judgment() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const old='Required old contract. '+'complete knowledge '.repeat(1050);
      const entries=[{role:'user',content:'Correct the old note using current source; preserve required knowledge.'},{role:'toolResult',content:'Memory readback: '+old+'\n'+'context '.repeat(3500)},{role:'user',content:'Correction: do not discard the required old contract.'}];
      const existing=[{name:'old.md',classification:'safe',type:'project',description:'old contract',content:old}];
      const candidates=[{name:'old.md',kind:'rewrite',classification:'safe',content:'New claim that drops the required old contract.',evidence:[{index:0,quote:'Correct the old note using current source; preserve required knowledge.'}]}];
      let calls=[],exact=true,seen=new Set(),references=0;
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async(_u,init)=>{
        const r=JSON.parse(init.body),s=typeof r.state==='string'?JSON.parse(r.state):r.state;calls.push(r);
        for(const m of s.existingMemories??[]){if(m.contentReference){references++;const ref=m.contentReference;let text=s;for(const key of ref.statePath)text=text[key];exact&&=text.slice(ref.start,ref.end)===old;exact&&=Object.values(r.questions).every(q=>q.instructions.question.includes('UTF-16'));}else exact&&=m.content===old;}
        s.reviewEvidence?.entries.forEach(e=>seen.add(e.index));
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{const choice=key.startsWith('counter_')&&s.reviewEvidence.entries.some(e=>e.index===2)?'contradicts':key.startsWith('counter_')||key.startsWith('coherence_')?'compatible':'grounded';return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}]}))}));
      }});
      const before=JSON.stringify({entries,existing,candidates}),verdict=await judge.validate('memory',{contextEnabled:true,entries},candidates,existing);
      console.log(JSON.stringify({verdict,calls:calls.length,maxBytes:Math.max(0,...calls.map(r=>Buffer.byteLength(JSON.stringify(r)))),exact,references,seen:[...seen].sort(),unchanged:before===JSON.stringify({entries,existing,candidates})}));
    ''')
    assert result['calls'] > 0
    assert result['references'] > 0 and result['exact'] and result['unchanged']
    assert result['maxBytes'] <= 64_000
    assert result['seen'] == [0, 1, 2]
    assert result['verdict']['decision'] == 'propose'
    assert result['verdict']['telemetry']['dimension'] == 'counterevidence'
