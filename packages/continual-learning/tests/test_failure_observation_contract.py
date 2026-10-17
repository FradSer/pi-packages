from support import isolated_run_bun


def test_failure_without_a_verified_fix_remains_eligible_observed_knowledge() -> None:
    result = isolated_run_bun(r'''
      import {buildIncrementalMemoryConsolidatorPrompt} from './packages/continual-learning/extensions/planner-prompts.ts';
      const prompt=buildIncrementalMemoryConsolidatorPrompt({runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'a',dossierPath:'/private/dossier.json'});
      console.log(JSON.stringify({eligible:prompt.includes('A failed task does not require a successful fix before its observed failure can be learned'),
        unresolved:prompt.includes('Keep an unresolved failure explicitly unresolved'),
        noInventedRecovery:prompt.includes('Never invent a cause, a successful correction or a standing user requirement'),
        citations:prompt.includes('actual failure and successful verification')}));
    ''')
    assert result['eligible'] and result['unresolved'] and result['noInventedRecovery']
    assert not result['citations']


def test_harness_does_not_promote_task_execution_restrictions_to_standing_policy() -> None:
    from pathlib import Path
    prompt = (Path(__file__).parents[1] / 'prompts/harness-consolidator.md').read_text()
    assert 'Task execution and isolation restrictions are task-local unless' in prompt
    assert 'Durability of one clause does not transfer to nearby clauses' in prompt


def test_memory_judge_distinguishes_unresolved_source_defects_from_permanent_failures() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const requests=[];let category='grounded';
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const request=JSON.parse(init.body);requests.push(request);
        const answers=Object.fromEntries(Object.entries(request.questions).map(([key,q])=>[key,
          {type:'choice',choice:key.startsWith('coherence_')?'compatible':category,confidence:1,probabilities:Object.fromEntries(
            Object.keys(q.criteria).map(k=>[k,k===(key.startsWith('coherence_')?'compatible':category)?1:0]))}]));
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:10,output_tokens:1}}));
      }});
      const evidence='Inspected index.js exposes onIdle. Inspected index.d.ts omits onIdle. Actual tsd failed: Property onIdle does not exist on type LimitFunction.';
      const candidate={content:'In this inspected p-limit source state, runtime onIdle is absent from public declarations; the observed type failure remains unresolved.'};
      const accepted=await judge.validate('memory',evidence,[candidate],[]);
      const held={};for(const label of ['speculative','transient','unsupported','unclear']){
        category=label;held[label]=await judge.validate('memory',evidence,[candidate],[]);
      }
      console.log(JSON.stringify({question:requests[0].questions.supported_0.instructions.question,
        criteria:requests[0].questions.supported_0.criteria,accepted,held}));
    ''')
    assert 'source-state-bound unresolved defect' in result['question']
    assert 'matching inspected source' in result['question']
    assert 'does not establish a cause, a successful fix, or permanent command failure' in result['question']
    assert result['accepted']['decision'] == 'allow'
    assert all(row['decision'] == 'propose' for row in result['held'].values())


def test_failed_task_planning_prioritizes_observed_pitfalls_over_api_inventory_without_forcing_a_memory() -> None:
    result = isolated_run_bun(r'''
      import {buildIncrementalMemoryConsolidatorPrompt} from './packages/continual-learning/extensions/planner-prompts.ts';
      const prompt=buildIncrementalMemoryConsolidatorPrompt({runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'a',dossierPath:'/private/dossier.json'}).replace(/\s+/g,' ');
      console.log(JSON.stringify({priority:prompt.includes('Prioritize a reusable pitfall evidenced by the actual failed verification'),
        inventory:prompt.includes('An API inventory or source excerpt alone is not a lesson about that failure'),
        noForcedWrite:prompt.includes('If the failure supports no reusable lesson, return no such proposal'),
        noInventedRecovery:prompt.includes('Never invent a cause, a successful correction or a standing user requirement')}));
    ''')
    assert all(result.values())
