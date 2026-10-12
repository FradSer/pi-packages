from __future__ import annotations

import json
from pathlib import Path
from support import run_bun


def test_real_guidance_and_retirement_examples_do_not_claim_blocking() -> None:
    frozen = json.loads(Path(__file__).with_name('fixtures').joinpath('real-guidance-case-preview.json').read_text())
    value = run_bun(f'''
      import {{createJevJudge}} from './packages/continual-learning/extensions/jev-learning.ts';
      import {{previewHarnessRuleCases}} from './packages/continual-learning/extensions/harness-consolidation.ts';
      const frozen={json.dumps(frozen,ensure_ascii=False)},requests=[];
      const judge=createJevJudge({{enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{{
        const q=JSON.parse(init.body);requests.push(q);const answers={{}};
        for(const [key,question] of Object.entries(q.questions)) answers[key]=question.type==='noul'?{{type:'noul',noul:0.99}}:
          {{type:'choice',choice:key.startsWith('expands')?'same':'compatible',confidence:0.99,
           probabilities:key.startsWith('expands')?{{same:1,narrower:0,broader:0,unclear:0}}:{{compatible:1,contradicts:0,unclear:0}}}};
        return new Response(JSON.stringify({{model:'jev-1.13.0',answers,usage:{{input_tokens:10,output_tokens:1}}}}));
      }}}});
      const guidance={{op:'addRule',rule:frozen.rule,cases:frozen.cases}};
      const confirmation={{op:'addRule',rule:{{id:'confirm-command',bash:'^npm test$',action:'confirm',message:'Request confirmation'}},
        cases:{{positive:[{{bash:'npm test',expected:'confirm'}}],negative:[{{bash:'pnpm test'}}]}}}};
      const priorRule={{id:'retire-command',bash:'^npm test$',action:'block',message:'Original restriction'}};
      const retired={{op:'updateRule',rule:{{...priorRule,enabled:false}},priorRule,
        correction:{{eventIndex:0,quote:'Retire the old rule.',priorRevision:'parent-bound-revision'}},
        cases:{{positive:[{{bash:'npm test',expected:'execute'}}],negative:[{{bash:'pnpm test'}}]}}}};
      const candidates=[guidance,confirmation,retired],original=JSON.stringify(candidates);
      for(const candidate of candidates) await judge.validate('harness',{{contextEnabled:true,entries:[{{role:'user',content:'Retire the old rule. Relevant complete project evidence.'}}]}},[candidate],[],undefined,
        [{{index:0,source:'user',eventIndex:0,quote:'Retire the old rule.',count:1}}]);
      const meanings=requests.flatMap(q=>Object.values(q.questions).map(x=>x.instructions?.candidate)).filter(x=>x?.behaviorExamples);
      const questionBindings=requests.flatMap(q=>Object.entries(q.questions).map(([key,x])=>({{key,id:x.instructions?.candidate?.rule?.id}})));
      console.log(JSON.stringify({{guidancePreview:previewHarnessRuleCases(guidance.rule,guidance.cases),candidates,meanings,questionBindings,unchanged:JSON.stringify(candidates)===original}}));
    ''')
    assert value['guidancePreview']['passed']
    assert value['unchanged']
    assert value['meanings'], 'Must inspect actual encoded semantic request candidates'
    for candidate in value['candidates']:
        keys = {binding['key'] for binding in value['questionBindings'] if binding.get('id') == candidate['rule']['id']}
        assert {'supported_0', 'expands_0', 'counter_0_0'} <= keys
    for meaning in value['meanings']:
        original = next(c for c in value['candidates'] if c['rule']['id'] == meaning['rule']['id'])
        assert meaning['behaviorExamples'] == {
            'selectorMatches': original['cases']['positive'],
            'selectorDoesNotMatch': original['cases']['negative'],
        }
        if original.get('correction'):
            assert meaning['priorRule'] == original['priorRule']
            assert meaning['correction'] == original['correction']
