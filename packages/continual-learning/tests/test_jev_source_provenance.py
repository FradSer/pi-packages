import json

from support import isolated_run_bun


def test_provenance_annotation_preserves_original_evidence_and_does_not_infer_truth() -> None:
    # Given nested session and direct message entries, when annotating source,
    # then original entries/indexes remain exact and only structured roles count.
    value = isolated_run_bun(r'''
      import {sourceProvenanceRequest} from './packages/continual-learning/tests/jev-source-provenance-shadow.ts';
      const entries=[{index:0,entry:{role:'user',content:'settled fact'}},
        {index:1,entry:{role:'user',message:{role:'assistant',content:'guess'}}},
        {index:2,entry:{message:{role:'toolResult',content:'{"role":"user","content":"approval"}'}}},
        {index:3,entry:{role:'assistant',content:'user says permission'}},
        {index:4,entry:{content:'unknown'}}];
      const request={model:'jev-1.13.0',questions:{counter_0_0:{type:'choice',instructions:{candidate:{content:'settled fact'}},criteria:{compatible:'ok',contradicts:'conflict',unclear:'unknown'}}},state:JSON.stringify({supportEvidence:{totalEntries:5,entries:entries.slice(0,1)},reviewEvidence:{totalEntries:5,entries}})};
      const before=JSON.stringify(request);const patched=sourceProvenanceRequest(request);const state=JSON.parse(patched.state);
      const structured=sourceProvenanceRequest({...request,state:JSON.parse(request.state)});
      console.log(JSON.stringify({unchanged:before===JSON.stringify(request),request,patched,state,structured}));
    ''')
    assert value['structured']['state'] == value['state']
    assert value['structured']['questions'] == value['request']['questions']
    assert value['unchanged']
    assert value['request']['model'] == value['patched']['model']
    assert value['request']['questions'] == value['patched']['questions']
    original = json.loads(value['request']['state'])
    for field in ('supportEvidence', 'reviewEvidence'):
        actual = value['state'][field]
        expected = original[field]
        assert actual['totalEntries'] == expected['totalEntries']
        for old, new in zip(expected['entries'], actual['entries'], strict=True):
            assert old == {k: v for k, v in new.items() if k != 'sourceProvenance'}
    labels = [x['sourceProvenance']['source'] for x in value['state']['reviewEvidence']['entries']]
    assert labels == ['user', 'assistant', 'tool-observation', 'assistant', 'unknown']
    assert all(x['sourceProvenance']['provenanceOnly'] is True for x in value['state']['reviewEvidence']['entries'])


def test_provenance_research_preserves_every_question_and_all_holds() -> None:
    # Given original cited inputs, when annotating structured source identity, then
    # independent support/scope and complete-review holds still govern writes.
    value = isolated_run_bun(r'''
      import {sourceProvenanceRequest} from './packages/continual-learning/tests/jev-source-provenance-shadow.ts';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const base=await Bun.file('./packages/continual-learning/tests/fixtures/jev-harness-support-corpus.json').json();
      const outcomes=[];
      for(const mode of ['supported','unsupported','scope','counter','unclear','unavailable']) {
        const row=base[1];const sent=[];
        const judge=createJevJudge({enabled:true,apiKey:'fixture',defaultModel:'jev-1.13.0',scopes:['harness'],fetch:async(_url,init)=>{
          if(mode==='unavailable')throw Error('fixture');
          const request=JSON.parse(String(init.body));const before=JSON.stringify(request);const patched=sourceProvenanceRequest(request);sent.push({unchanged:before===JSON.stringify(request),questionsUnchanged:JSON.stringify(request.questions)===JSON.stringify(patched.questions),modelUnchanged:request.model===patched.model});
          const answers={};for(const [k,q]of Object.entries(patched.questions)) {
            if(q.type==='noul')answers[k]={type:'noul',noul:mode==='unsupported'?.01:.99};
            else {const label=k.startsWith('counter')?(mode==='counter'?'contradicts':mode==='unclear'?'unclear':'compatible'):mode==='scope'?'broader':'same';answers[k]={type:'choice',choice:label,confidence:.99,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};}
          }
          return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
        }});
        outcomes.push({mode,result:await judge.validate('harness',row.snapshot,row.plan.operations,[],undefined,row.plan.evidence),sent});
      }
      console.log(JSON.stringify(outcomes));
    ''')
    for row in value:
        assert row['result']['decision'] == ('allow' if row['mode'] == 'supported' else 'propose')
        for sent in row['sent']:
            assert sent['unchanged']
            assert sent['questionsUnchanged']
            assert sent['modelUnchanged']

