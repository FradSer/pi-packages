from support import isolated_run_bun


def test_actual_mislearned_description_enters_independent_complete_record_review() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-description-body-conflict.json').json();
      const kit=await import('./packages/kit/src/index.ts');let request;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        request=input;return {exitCode:0,text:JSON.stringify({reviews:{'0':{verdict:'contradictory',conflictingQuotes:[
          "wrapper returns Promise & Pick<LimitFunction,'clearQueue'>",
          'The returned callable produces `Promise<ReturnType>`.']}}}),usageLedger:{complete:true}};
      }}));
      const {reviewMemoryBodies,memoryBodiesAllow,memoryBodyRepairFields}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const review=await reviewMemoryBodies({candidates:[{name:f.filename,content:f.content}],retained:[]});
      const target=JSON.parse(request.prompt.split('\n').at(-1)).targets[0];
      console.log(JSON.stringify({review,target,allowed:memoryBodiesAllow(review),fields:memoryBodyRepairFields(review),tools:request.tools,full:target.content===f.content}));
    ''')
    assert value['full'] and value['tools'] == []
    assert value['target']['independentlyRetrievedDescription'].endswith("wrapper returns Promise & Pick<LimitFunction,'clearQueue'>")
    assert value['review']['judgments'][0]['verdict'] == 'contradictory'
    assert not value['allowed']
    # A contradiction touches the description; body-only repair must not lock it.
    assert value['fields'] == {'limit-function-type-contract.md': ['body', 'description']}
    assert all(span['text'] in value['target']['content'] for span in value['review']['judgments'][0]['witnesses'])


def test_whole_record_hold_cannot_certify_unquoted_description_as_passed() -> None:
    value = isolated_run_bun(r'''
      import {prepareMemoryBodyTargets,bindMemoryBodySelections,memoryBodyRepairFields} from './packages/continual-learning/extensions/memory-body-review.ts';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-description-body-conflict.json').json();
      const targets=prepareMemoryBodyTargets([{name:f.filename,content:f.content}],[]);
      // Actual retained worker selected these two body spans while its explanation
      // identified a description conflict. No parent authority comes from prose.
      const judgments=bindMemoryBodySelections(targets,{reviews:{'0':{verdict:'contradictory',conflictingQuotes:[
        ": ((...arguments_: Arguments) => Promise<ReturnType>) & Pick<LimitFunction, 'clearQueue'>;",
        '- The returned callable produces `Promise<ReturnType>`.']}}});
      const fields=memoryBodyRepairFields({status:'reviewed',targets,judgments,calls:1,durationMs:1,usageComplete:true});
      console.log(JSON.stringify({fields,exact:judgments[0].witnesses.every(w=>f.content.slice(w.start,w.end)===w.text)}));
    ''')
    assert value['exact']
    assert value['fields'] == {'limit-function-type-contract.md': ['body', 'description']}
