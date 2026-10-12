"""Contract: features/current-task-read.feature; public task tools."""
from task_helpers import run_node


def test_new_blocker_is_in_model_text_with_historical_recovery() -> None:
    result = run_node("""
      import {createTask,executeTaskUpdate,executeTaskGet} from './index.ts';
      createTask({id:'task',subject:'Reconcile machines'});
      await executeTaskUpdate({id:'task',status:'in_progress',reason:'Previous access restored'});
      await executeTaskUpdate({id:'task',status:'blocked',reason:'Remote host is unreachable'});
      const read=await executeTaskGet({id:'task'});
      console.log(JSON.stringify({text:read.content.map(x=>x.text).join('\\n')}));
    """)
    assert 'BLOCKED · Remote host is unreachable' in result['text']
    assert 'Previous recovery: Previous access restored' in result['text']


def test_missing_outcome_reports_retained_mixed_edit() -> None:
    result = run_node("""
      import {createTask,executeTaskUpdate,getTask} from './index.ts';
      createTask({id:'task',subject:'Reconcile machines'});
      const update=await executeTaskUpdate({id:'task',description:'Only remote work remains',status:'completed'});
      console.log(JSON.stringify({details:update.details,text:update.content.map(x=>x.text).join('\\n'),stored:getTask('task')}));
    """)
    assert result['details']['ok'] is False
    assert result['stored']['description'] == 'Only remote work remains'
    assert result['stored']['status'] == 'pending'
    assert result['details']['task']['description'] == 'Only remote work remains'
    assert 'recorded' in result['text']
