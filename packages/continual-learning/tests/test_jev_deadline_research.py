from support import isolated_run_bun


def test_deadline_options_change_only_timeout_and_keep_zero_retries() -> None:
    value = isolated_run_bun(r'''
      import {deadlineResearchOptions} from './packages/continual-learning/tests/jev-deadline-research.ts';
      const before=deadlineResearchOptions('before'),after=deadlineResearchOptions('after');
      const {timeout:b,...restB}=before,{timeout:a,...restA}=after;
      let refused=false;try{deadlineResearchOptions('unknown')}catch{refused=true}
      console.log(JSON.stringify({b,a,same:JSON.stringify(restB)===JSON.stringify(restA),retry:before.retry,refused}));
    ''')
    assert value == {'b': 5000, 'a': 15000, 'same': True, 'retry': {'maxRetries': 0}, 'refused': True}


def test_deadline_completion_requires_all_original_windows_and_model() -> None:
    value = isolated_run_bun(r'''
      import {completeDeadlineArm} from './packages/continual-learning/tests/jev-deadline-research.ts';
      const telemetry={model:'jev-1.13.0',reason:'supported',requestCount:2,completedRequests:2,evidenceEntries:17,coveredEntries:17,evidenceWindows:2,completedWindows:2,inputTokens:100,durationMs:1};
      const observations=[{valid:true,modelVerified:true},{valid:true,modelVerified:true}];
      const patches=[{}, {reason:'timeout'},{completedRequests:1},{coveredEntries:16},{completedWindows:1},{model:'jev-latest'},{inputTokens:undefined}];
      console.log(JSON.stringify({values:patches.map(p=>completeDeadlineArm({...telemetry,...p},observations)),invalid:completeDeadlineArm(telemetry,[...observations,{valid:true,modelVerified:true}])}));
    ''')
    assert value == {'values': [True, False, False, False, False, False, False], 'invalid': False}


def test_deadline_metrics_do_not_hide_incomplete_or_unsafe_outputs() -> None:
    value = isolated_run_bun(r'''
      import {summarizeDeadlineStudy} from './packages/continual-learning/tests/jev-deadline-research.ts';
      const arm=(decision,complete,wire='same')=>({decision,complete,durationMs:complete?7:5000,wireRequestHashes:[wire]});
      const rows=[{expectedAllow:true,arms:{before:arm('propose',false),after:arm('allow',true)}},{expectedAllow:false,arms:{before:arm('reject',true),after:arm('reject',true)}}];
      const valid=summarizeDeadlineStudy(rows);
      const unsafe=summarizeDeadlineStudy([...rows,{expectedAllow:false,arms:{before:arm('propose',false),after:arm('allow',false)}}]);
      const drift=summarizeDeadlineStudy([{expectedAllow:true,arms:{before:arm('propose',false),after:arm('allow',true,'changed')}}]);
      console.log(JSON.stringify({valid,unsafeSuccess:unsafe.successRuleMet,unsafeCount:unsafe.metrics.after.falseAccepts,driftSuccess:drift.successRuleMet,driftSame:drift.identicalWireRequests}));
    ''')
    assert value['valid']['successRuleMet'] is True
    assert value['valid']['metrics']['before']['incomplete'] == 1
    assert value['valid']['metrics']['before']['falseHolds'] == 0
    assert value['valid']['metrics']['before']['missedValid'] == 1
    assert value['unsafeCount'] == 1
    assert value['unsafeSuccess'] is False
    assert value['driftSuccess'] is False
    assert value['driftSame'] is False


def test_deadline_wire_guard_consumes_exact_hashes_before_paid_send() -> None:
    value = isolated_run_bun(r'''
      import {claimFrozenRequestHash} from './packages/continual-learning/tests/jev-deadline-research.ts';
      const remaining=['same','same','other'];let externalCalls=0;
      const send=(hash)=>{claimFrozenRequestHash(remaining,hash);externalCalls++};
      send('same');send('same');let refused=false;try{send('same')}catch{refused=true}
      let driftRefused=false;try{send('changed')}catch{driftRefused=true}
      send('other');console.log(JSON.stringify({externalCalls,remaining,refused,driftRefused}));
    ''')
    assert value == {'externalCalls': 3, 'remaining': [], 'refused': True, 'driftRefused': True}
