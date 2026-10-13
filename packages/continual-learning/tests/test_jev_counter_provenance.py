from support import isolated_run_bun


def test_uncited_counter_results_retain_exact_unique_invocation_across_windows() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const call={type:'toolCall',id:'later-check',name:'bash',arguments:{command:'cd another-project && pnpm test',context:'q'.repeat(21000)}};
      const entries=[{role:'user',content:'The project uses pnpm test.'},
        {role:'assistant',content:[call]},
        {role:'toolResult',toolCallId:'later-check',toolName:'bash',content:'Tests failed in another project.'},
        {role:'assistant',content:[{type:'toolCall',id:'duplicate',name:'bash',arguments:{command:'one'}}]},
        {role:'assistant',content:[{type:'toolCall',id:'duplicate',name:'bash',arguments:{command:'two'}}]},
        {role:'toolResult',toolCallId:'duplicate',toolName:'bash',content:'ambiguous'},
        {role:'assistant',content:[{type:'toolCall',id:'wrong-name',name:'read',arguments:{path:'test.js'}}]},
        {role:'toolResult',toolCallId:'wrong-name',toolName:'bash',content:'mismatched'}];
      const candidate={kind:'project',name:'workflow.md',classification:'safe',content:'The project uses pnpm test.',evidence:[{index:0,role:'user',quote:entries[0].content}]};
      const before=JSON.stringify(entries);let requests=[];
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'offline',fetch:async(_u,init)=>{
        const r=JSON.parse(init.body);requests.push(r);
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{
          const choice=key.startsWith('coherence_')||key.startsWith('counter_')?'compatible':key.startsWith('relation_')?'unrelated':'grounded';
          return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}];
        }))}));
      }});
      const result=await judge.validate('memory',{contextEnabled:true,entries},[candidate],[]);
      const windows=requests.map(r=>r.state.reviewEvidence).filter(Boolean);
      const resultWindow=windows.find(w=>w.entries.some(e=>e.index===2));
      const provenance=resultWindow?.citationToolCalls?.find(p=>p.resultIndex===2);
      console.log(JSON.stringify({decision:result.decision,unchanged:before===JSON.stringify(entries),separated:!resultWindow.entries.some(e=>e.index===1),exact:JSON.stringify(provenance?.toolCall)===JSON.stringify(call),callIndex:provenance?.callIndex,resultIndex:provenance?.resultIndex,invalid:windows.flatMap(w=>w.citationToolCalls??[]).some(p=>p.resultIndex===5||p.resultIndex===7),maxBytes:Math.max(...requests.map(r=>Buffer.byteLength(JSON.stringify(r))))}));
    ''')
    assert value['decision'] == 'allow'
    assert value['unchanged'] and value['separated']
    assert value['exact']
    assert value['callIndex'] == 1 and value['resultIndex'] == 2
    assert not value['invalid']
    assert value['maxBytes'] <= 64_000
