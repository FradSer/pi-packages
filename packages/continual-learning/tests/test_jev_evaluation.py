from support import isolated_run_bun


def test_evaluation_counts_transport_requests_not_judge_invocations() -> None:
    value = isolated_run_bun(r'''
      import {evaluateJevSamples} from './packages/continual-learning/tests/jev-evaluation.ts';
      const telemetry={stage:'memory',status:'decided',reason:'supported',durationMs:1,model:'jev-1.13.0',inputTokens:300,outputTokens:20,estimatedCostUsd:0.0000126};
      const judge={enabled:true,selectionEnabled:true,
        select:async()=>({selection:{memory:true,harness:false,selected:[]},telemetry:{...telemetry,stage:'selection',requestCount:1}}),
        validate:async()=>({decision:'allow',telemetry:{...telemetry,requestCount:3}})};
      const samples=[{id:'fixture',language:'en',evidence:'The public event is billing.settled.',memory:true,harness:false,stage:'memory',candidate:{content:'The public event is billing.settled.'},allow:true}];
      console.log(JSON.stringify(await evaluateJevSamples(samples,'simulated-jev-inference',judge)));
    ''')
    assert value['calls'] == 4


def test_evaluation_preserves_partial_usage_and_stops_before_second_call() -> None:
    value = isolated_run_bun(r'''
      import {evaluateJevSamples} from './packages/continual-learning/tests/jev-evaluation.ts';
      import samples from './packages/continual-learning/tests/fixtures/jev-learning.json';
      let selections=0,validations=0;
      const judge={enabled:true,selectionEnabled:true,
        select:async()=>{selections++;return {selection:null,telemetry:{stage:'selection',status:'fallback',reason:'timeout',durationMs:20}}},
        validate:async()=>{validations++;throw new Error('Must stop before this call');}};
      const report=await evaluateJevSamples(samples,'simulated-jev-inference',judge);
      const offline=await evaluateJevSamples(samples,'offline-baseline-only');
      console.log(JSON.stringify({report,offline,selections,validations}));
    ''')
    assert value['selections'] == 1 and value['validations'] == 0
    report = value['report']
    assert report['evidence'] == 'simulated-jev-inference'
    assert report['stopReason'] == 'timeout' and not report['complete']
    assert report['costKnown'] is False and report['inputTokens'] is None
    assert report['rows'][0]['after']['selectionTelemetry']['reason'] == 'timeout'
    assert report['metrics']['en']['after']['candidateFalseAccepts'] is None
    offline = value['offline']
    assert offline['complete'] and len(offline['rows']) == 18
    assert offline['metrics']['en']['baseline']['extraDirections'] == 4
    assert offline['metrics']['zh']['baseline']['extraDirections'] == 2
    assert offline['metrics']['en']['after'] is None


def test_evaluation_stops_on_unpriced_model_but_preserves_known_tokens() -> None:
    value = isolated_run_bun(r'''
      import {evaluateJevSamples} from './packages/continual-learning/tests/jev-evaluation.ts';
      import samples from './packages/continual-learning/tests/fixtures/jev-learning.json';
      let calls=0;
      const judge={enabled:true,selectionEnabled:true,
        select:async()=>{calls++;return {selection:{memory:true,harness:true,selected:[]},
          telemetry:{stage:'selection',status:'decided',reason:'supported',model:'jev-1.14.0',inputTokens:3,outputTokens:1,durationMs:1}}},
        validate:async()=>{calls++;throw new Error('No second call when cost unknown')}};
      console.log(JSON.stringify({report:await evaluateJevSamples(samples,'simulated-jev-inference',judge),calls}));
    ''')
    assert value['calls'] == 1
    report = value['report']
    assert report['stopReason'] == 'unknown-cost' and not report['complete']
    assert not report['costKnown'] and report['usageKnown']
    assert report['inputTokens'] == 3 and report['estimatedCostUsd'] is None
    assert report['actualModels'] == ['jev-1.14.0']


def test_evaluation_stops_on_incomplete_usage_and_retains_known_cost() -> None:
    value = isolated_run_bun(r'''
      import {evaluateJevSamples} from './packages/continual-learning/tests/jev-evaluation.ts';
      import samples from './packages/continual-learning/tests/fixtures/jev-learning.json';
      let calls=0;
      const judge={enabled:true,selectionEnabled:true,
        select:async()=>{calls++;return {selection:null,
          telemetry:{stage:'selection',status:'fallback',reason:'invalid-response',model:'jev-1.13.0',inputTokens:3,estimatedCostUsd:0.000000126,durationMs:1}}},
        validate:async()=>{calls++;throw new Error('No second call when usage incomplete')}};
      console.log(JSON.stringify({report:await evaluateJevSamples(samples,'simulated-jev-inference',judge),calls}));
    ''')
    assert value['calls'] == 1
    report = value['report']
    assert report['stopReason'] == 'incomplete-usage' and not report['complete']
    assert report['costKnown'] and not report['usageKnown']
    assert report['knownInputTokens'] == 3 and report['inputTokens'] is None
    assert report['estimatedCostUsd'] == 0.000000126


def test_unknown_cost_does_not_hide_incomplete_usage() -> None:
    value = isolated_run_bun(r'''
      import {evaluateJevSamples} from './packages/continual-learning/tests/jev-evaluation.ts';
      import samples from './packages/continual-learning/tests/fixtures/jev-learning.json';
      const judge={enabled:true,selectionEnabled:true,
        select:async()=>({selection:null,telemetry:{stage:'selection',status:'fallback',reason:'invalid-response',model:'jev-1.14.0',inputTokens:3,durationMs:1}}),
        validate:async()=>{throw new Error('Must stop')}};
      console.log(JSON.stringify(await evaluateJevSamples(samples,'simulated-jev-inference',judge)));
    ''')
    assert value['stopReason'] == 'unknown-cost' and not value['complete']
    assert not value['usageKnown'] and not value['costKnown']
    assert value['inputTokens'] is None and value['knownInputTokens'] == 3


def test_evaluation_preserves_actual_harness_cases() -> None:
    value = isolated_run_bun(r'''
      import {evaluateJevSamples} from './packages/continual-learning/tests/jev-evaluation.ts';
      const samples=[{id:'exact',language:'en',evidence:'In future tasks never run echo PUBLIC_DENY in this project.',memory:true,harness:true,stage:'harness',allow:true,
        candidate:{rule:{bash:'^echo PUBLIC_DENY$',action:'block',message:'Do not run the exact command.'},cases:{positive:[{bash:'echo PUBLIC_DENY',expected:'block'}],negative:[{bash:'echo PUBLIC_ALLOW'}]}}}];
      console.log(JSON.stringify(await evaluateJevSamples(samples,'offline-baseline-only')));
    ''')
    assert value['complete'] and value['rows'][0]['codeValidation'] == 'passed'


def test_improvement_gate_rejects_false_holds_missing_results_and_mock_evidence() -> None:
    value = isolated_run_bun(r'''
      import {candidateImprovementGate} from './packages/continual-learning/tests/jev-evaluation.ts';
      const good={id:'good',expected:{candidateAllowed:true},baseline:{candidateAllowed:true},after:{candidateAllowed:true}};
      const risk={id:'risk',expected:{candidateAllowed:false},baseline:{candidateAllowed:true},after:{candidateAllowed:false}};
      const base={complete:true,evidence:'real-jev-inference',rows:[good,risk]};
      console.log(JSON.stringify({pass:candidateImprovementGate(base),held:candidateImprovementGate({...base,rows:[{...good,after:{candidateAllowed:false}},risk]}),missing:candidateImprovementGate({...base,rows:[good,{...risk,after:null}]}),mock:candidateImprovementGate({...base,evidence:'simulated-jev-inference'})}));
    ''')
    assert value['pass']['passed']
    assert not value['held']['passed'] and not value['missing']['passed'] and not value['mock']['passed']
