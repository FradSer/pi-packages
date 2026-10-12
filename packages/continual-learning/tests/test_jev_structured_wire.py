from support import isolated_run_bun


def test_review_wire_preserves_structured_state_and_shared_exact_citations() -> None:
    """Given quoted source; when reviewing both fields; then send it once, intact."""
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const quote='Observed source contract: '+('"line\\value"\n'.repeat(80));
      const snapshot={contextEnabled:true,entries:[{role:'toolResult',content:quote},{role:'user',content:'Later correction revokes this contract.'}]};
      const candidate={name:'contract.md',kind:'project',classification:'safe',content:'---\nname: contract\ndescription: Observed source contract\ntype: project\n---\nObserved source contract.',evidence:[{index:0,role:'toolResult',quote}]};
      const requests=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const req=JSON.parse(init.body);requests.push(req);
        const answers=Object.fromEntries(Object.entries(req.questions).map(([key,q])=>{
          const choice=key.startsWith('coherence_')?'compatible':key.startsWith('counter')&&req.state.reviewEvidence?.entries.some(e=>e.index===1)?'contradicts':key.startsWith('counter')?'compatible':key.startsWith('relation')?'novel':'grounded';
          return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}];
        }));return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:1}}));
      }});
      const result=await judge.validate('memory',snapshot,[candidate],[]);
      console.log(JSON.stringify({result,requests,snapshot,candidate}));
    ''')
    assert result['requests']
    assert all(isinstance(request['state'], dict) for request in result['requests'])
    assert any('supported_description_0' in request['questions'] for request in result['requests'])
    covered = set()
    for request in result['requests']:
        state = request['state']
        for key, question in request['questions'].items():
            if key.startswith('supported'):
                instructions = question['instructions']
                assert instructions['originalCitationsReference'] == 'originalCitationsByCandidate.0'
                assert 'originalCitationsReference' in instructions['question']
                assert 'originalCitations' not in instructions
                assert state['originalCitationsByCandidate']['0'] == result['candidate']['evidence']
            if key.startswith('counter'):
                covered.update(entry['index'] for entry in state['reviewEvidence']['entries'])
        for name in ('frozenEvidence', 'supportEvidence', 'reviewEvidence'):
            for entry in state.get(name, {}).get('entries', []):
                assert entry['entry'] == result['snapshot']['entries'][entry['index']]
    assert covered == {0, 1}
    assert result['result']['decision'] == 'propose'
    assert result['result']['telemetry']['dimension'] == 'counterevidence'
