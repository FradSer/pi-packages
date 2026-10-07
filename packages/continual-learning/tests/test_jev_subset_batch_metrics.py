from support import isolated_run_bun


def test_subset_metrics_count_valid_holds_unsafe_writes_and_lost_indexes() -> None:
    # Given fixed per-candidate labels, when subset simulation is compared with
    # the unchanged whole-plan gate, then count errors rather than only recovery.
    value = isolated_run_bun(r'''
      import {subsetBatchMetrics} from './packages/continual-learning/tests/subset-batch-metrics.ts';
      console.log(JSON.stringify(subsetBatchMetrics([
        {eligible:[true,false,true],whole:[],subset:[0,2]},
        {eligible:[true,false,true],whole:[0,1,2],subset:[2]},
        {eligible:[true,true,false],whole:[],subset:[]}
      ])));
    ''')
    assert value['whole'] == {'validAccepted': 2, 'erroneousAccepted': 1, 'validHeld': 4}
    assert value['subset'] == {'validAccepted': 3, 'erroneousAccepted': 0, 'validHeld': 3}
    assert value['newErroneousAccepted'] == 0
    assert value['newValidHolds'] == 1
    assert value['recoveredValid'] == 2


def test_invalid_or_repeated_candidate_indexes_do_not_improve_metrics() -> None:
    value = isolated_run_bun(r'''
      import {subsetBatchMetrics} from './packages/continual-learning/tests/subset-batch-metrics.ts';
      const out=[];for(const subset of [[0,0],[3],[-1],[.5]]){
        try{subsetBatchMetrics([{eligible:[true,false],whole:[],subset}]);out.push(false);}catch{out.push(true);}}
      console.log(JSON.stringify(out));
    ''')
    assert value == [True, True, True, True]
