from support import isolated_run_bun


def test_paid_service_timeout_is_not_scored_as_semantic_correctness() -> None:
    # Given a negative hold with only partial usage and a positive timeout,
    # when calculating paired quality, neither is evidence of a judgment.
    value = isolated_run_bun(r'''
      import {pairedPlanMetrics} from './packages/continual-learning/tests/jev-paired-metrics.ts';
      const good={decision:'allow',telemetry:{stage:'memory',status:'decided',reason:'supported',durationMs:1,model:'jev-1.13.0',inputTokens:10,outputTokens:1}};
      const timed={decision:'propose',telemetry:{stage:'memory',status:'propose',reason:'timeout',durationMs:5000,model:'jev-1.13.0',knownInputTokens:5}};
      const uncertain={...good,decision:'propose',telemetry:{...good.telemetry,status:'propose',reason:'uncertain'}};
      const completeTimeout={...timed,telemetry:{...timed.telemetry,inputTokens:5,outputTokens:1}};
      const rows=[{expectedAllow:false,before:timed,after:timed},{expectedAllow:true,before:timed,after:uncertain},{expectedAllow:true,before:good,after:good},{expectedAllow:false,before:completeTimeout,after:completeTimeout}];
      console.log(JSON.stringify({before:pairedPlanMetrics(rows,'before'),after:pairedPlanMetrics(rows,'after')}));
    ''')
    assert value['before'] == {'evaluatedPlans': 1, 'skippedIncompletePlans': 3, 'falseAccepts': 0, 'falseHolds': 0}
    assert value['after'] == {'evaluatedPlans': 2, 'skippedIncompletePlans': 2, 'falseAccepts': 0, 'falseHolds': 1}


def test_false_accept_and_hold_require_actual_pinned_model_usage() -> None:
    value = isolated_run_bun(r'''
      import {pairedPlanMetrics} from './packages/continual-learning/tests/jev-paired-metrics.ts';
      const verdict=(decision,model='jev-1.13.0',outputTokens=1)=>({decision,telemetry:{stage:'memory',status:'decided',reason:'supported',durationMs:1,model,inputTokens:10,outputTokens}});
      const rows=[{expectedAllow:false,before:verdict('allow'),after:verdict('allow','unknown')},{expectedAllow:true,before:verdict('propose'),after:{...verdict('propose'),telemetry:{...verdict('propose').telemetry,outputTokens:undefined}}}];
      console.log(JSON.stringify({before:pairedPlanMetrics(rows,'before'),after:pairedPlanMetrics(rows,'after')}));
    ''')
    assert value['before']['falseAccepts'] == value['before']['falseHolds'] == 1
    assert value['after']['skippedIncompletePlans'] == 2


def test_paired_complete_does_not_accept_partial_usage_or_service_holds() -> None:
    value = isolated_run_bun(r'''
      import {pairedPlansComplete} from './packages/continual-learning/tests/jev-paired-metrics.ts';
      const good={decision:'allow',telemetry:{stage:'memory',status:'decided',reason:'supported',durationMs:1,model:'jev-1.13.0',inputTokens:10,outputTokens:1}};
      const pair=after=>[{expectedAllow:true,before:good,after}];
      const partial={...good,telemetry:{...good.telemetry,outputTokens:undefined}};
      const timeout={...good,decision:'propose',telemetry:{...good.telemetry,status:'propose',reason:'timeout'}};
      const uncertain={...good,decision:'propose',telemetry:{...good.telemetry,status:'propose',reason:'uncertain'}};
      console.log(JSON.stringify({empty:pairedPlansComplete([]),partial:pairedPlansComplete(pair(partial)),timeout:pairedPlansComplete(pair(timeout)),good:pairedPlansComplete(pair(good)),uncertain:pairedPlansComplete(pair(uncertain))}));
    ''')
    assert value == {'empty': False, 'partial': False, 'timeout': False, 'good': True, 'uncertain': True}
