"""Given/When/Then regression gates for the simplified Tasks contract."""
from task_helpers import run_node

def test_given_legacy_records_when_restored_then_four_states_and_evidence_remain():
    r=run_node('''
    import * as t from './index.ts';
    t.loadTasks({old:{id:'old',subject:'Old',status:'recovery_hold',result:'Failure evidence',recoveryNote:'Prior recovery',dependsOn:[],resources:[],createdAt:1,updatedAt:1},replaced:{id:'replaced',subject:'Replaced',status:'superseded',supersededBy:'replacement',dependsOn:[],resources:[],createdAt:2,updatedAt:2},replacement:{id:'replacement',subject:'New',status:'pending',dependsOn:[],resources:[],createdAt:3,updatedAt:3}});
    console.log(JSON.stringify({states:t.TASK_STATUSES,old:t.getTask('old'),replaced:t.getTask('replaced'),take:t.takeTask('replaced','main')}));
    ''')
    assert r['states']==['pending','in_progress','blocked','completed','cancelled']
    assert r['old']['status']=='blocked' and r['old']['result']=='Failure evidence'
    assert r['old']['recoveryNote']=='Prior recovery'
    assert r['replaced']['status'] in r['states'] and r['replaced']['supersededBy']=='replacement'
    assert not r['take']['ok']

def test_given_many_tasks_when_paging_then_all_are_accessible():
    r=run_node('''
    import * as t from './index.ts';
    for(let i=1;i<=41;i++)t.createTask({subject:'Task '+i});
    const first=await t.executeTaskList({});const next=await t.executeTaskList({cursor:first.details.cursor});
    console.log(JSON.stringify({first:first.details,next:next.details}));
    ''')
    assert r['first'].get('cursor')
    assert len(r['first']['tasks'])==40 and len(r['next']['tasks'])==1
    assert len({x['id'] for x in r['first']['tasks']+r['next']['tasks']})==41

def test_given_long_task_when_rendered_then_the_collapsed_row_hides_the_body_and_expansion_shows_it():
    r=run_node('''
    import * as t from './index.ts';
    const tools=new Map();t.default({registerTool(x){tools.set(x.name,x)},on(){},events:{emit(){}}});
    const style={fg:(_,x)=>x,bg:(_,x)=>x,bold:x=>x};
    const created=await t.executeTaskCreate({subject:'Long task',description:'Long description. '.repeat(80)+'DESCRIPTION_TAIL',verify:'Check conditions. '.repeat(50)+'VERIFY_TAIL'});
    const id=created.details.id;await t.executeTaskUpdate({id,status:'in_progress'});
    const done=await t.executeTaskUpdate({id,status:'completed',outcome:'success',verdict:'pass',result:'All checks passed. EVIDENCE_TAIL'});
    const render=(name,r,e)=>tools.get(name).renderResult(r,{expanded:e,isPartial:false},style,{isError:!!r.isError}).render(40).join('\\n');
    console.log(JSON.stringify({created:render('create_task',created,false),createdExpanded:render('create_task',created,true),done:render('update_task',done,false),doneExpanded:render('update_task',done,true)}));
    ''')
    assert 'DESCRIPTION_TAIL' in r['createdExpanded'] and 'VERIFY_TAIL' in r['createdExpanded']
    assert 'EVIDENCE_TAIL' in r['doneExpanded']
    assert 'DESCRIPTION_TAIL' not in r['created'] and 'VERIFY_TAIL' not in r['created']
    assert 'EVIDENCE_TAIL' not in r['done']
    assert 'to expand' in r['created'] and 'to expand' in r['done']
    done_lines = [line for line in r['done'].split('\n') if line.strip()]
    assert 1 <= len(done_lines) <= 3, 'the collapsed completion row wraps instead of eliding'
    assert done_lines[-1].rstrip().endswith('to expand'), 'the hint follows the wrapped headline'
    assert '(completed)' in ' '.join(done_lines), 'the trailing status stays visible'
    assert '...' not in ' '.join(done_lines), 'the headline is never elided'
    create_lines = [line for line in r['created'].split('\n') if line.strip()]
    assert 1 <= len(create_lines) <= 3, 'the collapsed create row wraps instead of eliding'
    assert 'Long task' in ' '.join(' '.join(create_lines).split()), 'the full task name stays visible'

def test_given_effective_work_when_settling_then_only_runnable_work_continues():
    r=run_node('''
    import * as t from './index.ts';
    t.createTask({id:'one',subject:'Task title '.repeat(40)+'TITLE_TAIL'});
    const check=new t.TaskStopCheck();
    const event={outcome:'completed',entries:[],continue:false,context:{pendingMessages:[]}};
    const options={caller:'main',hasUI:true};
    const idle=check.check(event,options);
    const work=check.check(event,{...options,performedWork:true});
    const again=check.check(event,options);
    const input=check.check(event,{...options,performedWork:true,pendingInput:true});
    const long=t.taskStatusSpec(work.entries.at(-1).details);
    t.takeTask('one','other');
    const unavailable=new t.TaskStopCheck().check(event,{...options,performedWork:true});
    console.log(JSON.stringify({idle,work,again,input,long,unavailable}));
    ''')
    assert r['idle']['continue'] is False
    assert r['work']['continue'] is True
    assert r['again']['continue'] is False
    assert 'input' not in r
    assert r['unavailable']['continue'] is False
    assert r['unavailable']['entries'][-1]['details']['status']=='waiting'
    assert 'TITLE_TAIL' in '\n'.join(r['long']['summary'])
    assert r['long']['expandedSummary'] is True
    assert r['long'].get('fullSummary') is not True

def test_given_tool_receipts_when_repeated_then_metadata_and_reads_do_not_buy_continuations():
    r=run_node('''
    import * as t from './index.ts';
    const handlers=new Map();t.default({registerTool(){},on(n,h){handlers.set(n,h)},events:{emit(){}}});
    t.createTask({id:'one',subject:'Work'});
    const ctx={hasUI:true,hasPendingMessages:()=>false};
    const event={outcome:'completed',entries:[],continue:false,context:{pendingMessages:[]}};
    const run=async(name,args,result)=>{
      await handlers.get('agent_start')({},ctx);
      await handlers.get('tool_execution_start')({toolCallId:'id',toolName:name,args},ctx);
      await handlers.get('tool_execution_end')({toolCallId:'id',toolName:name,result,isError:false},ctx);
      return handlers.get('agent_before_settle')(event,ctx);
    };
    const first=await run('read',{path:'file'},{content:[{type:'text',text:'Original'}]});
    const repeat=await run('read',{path:'file'},{content:[{type:'text',text:'Original'}]});
    const metadata=await run('update_task',{id:'one',description:'Changed'},{content:[{type:'text',text:'OK'}]});
    const changed=await run('read',{path:'file'},{content:[{type:'text',text:'Changed'}]});
    const more=await run('write',{path:'file',content:'New'},{content:[{type:'text',text:'OK'}]});
    const exhausted=await run('write',{path:'file',content:'Another'},{content:[{type:'text',text:'OK'}]});
    console.log(JSON.stringify({first,repeat,metadata,changed,more,exhausted}));
    ''')
    assert r['first']['continue'] is True
    assert r['repeat']['continue'] is False
    assert 'metadata' not in r, 'identical waiting reminders are suppressed'
    assert r['changed']['continue'] is True and r['more']['continue'] is True
    assert r['exhausted']['continue'] is False
    details=r['exhausted']['entries'][-1]['details']
    assert details['status']=='waiting' and 'limit' in details['reason']

def test_given_a_blocker_when_recorded_then_it_can_be_recovered_and_evidence_survives():
    r=run_node('''
    import * as t from './index.ts';
    const c=await t.executeTaskCreate({subject:'Recoverable'});const id=c.details.id;
    const blocked=await t.executeTaskUpdate({id,status:'blocked',reason:'Missing dependency BLOCKER_TAIL'});
    const refused=await t.executeTaskUpdate({id,status:'in_progress'});
    const resumed=await t.executeTaskUpdate({id,status:'in_progress',reason:'Dependency installed'});
    const failed=await t.executeTaskUpdate({id,status:'completed',outcome:'failed',result:'Fail evidence'});
    const recovered=await t.executeTaskUpdate({id,status:'in_progress',reason:'Failure fixed'});
    const done=await t.executeTaskUpdate({id,status:'completed',outcome:'success',result:'Success evidence'});
    const reopened=await t.executeTaskUpdate({id,status:'pending'});
    console.log(JSON.stringify({blocked,refused,resumed,failed,recovered,done,reopened}));
    ''')
    assert r['blocked']['details']['status']=='blocked'
    assert r['blocked']['details']['task']['blockedReason'].endswith('BLOCKER_TAIL')
    assert r['refused']['isError'] is True
    assert r['resumed']['details']['status']=='in_progress'
    assert r['done']['details']['task']['failureEvidence']=='Fail evidence'
    assert 'blockedReason' not in r['done']['details']['task']
    assert r['reopened']['details']['task']['result']=='Success evidence'

def test_given_a_cursor_when_the_snapshot_changes_then_it_is_explicitly_refused():
    r=run_node('''
    import * as t from './index.ts';
    for(let i=0;i<42;i++)t.createTask({subject:'Task '+i});
    const first=await t.executeTaskList({limit:2,statusFilter:['pending']});
    const mismatch=await t.executeTaskList({cursor:first.details.cursor,statusFilter:['blocked']});
    const bad=await t.executeTaskList({cursor:'bad'});
    t.createTask({subject:'New record'});
    const stale=await t.executeTaskList({cursor:first.details.cursor});
    console.log(JSON.stringify({mismatch,bad,stale}));
    ''')
    for key in ['mismatch','bad','stale']:
        assert r[key]['isError'] is True
        assert 'cursor' in r[key]['content'][0]['text'].lower()

def test_given_foreign_or_replaced_work_when_blocked_then_ownership_is_preserved():
    r=run_node('''
    import * as t from './index.ts';
    t.createTask({id:'held',subject:'Held'});t.takeTask('held','other');
    const foreign=t.blockTask('held','main','Cannot take over');
    const original=t.createTask({id:'original',subject:'Original'});t.takeTask('original','main');
    t.createTask({id:'replacement',subject:'Replacement',supersedes:['original']});
    const blocked=t.blockTask('original','main','Cannot reenter');
    const complete=t.completeTaskWithOutcome('original','main','success','No');
    const claim=t.takeTask('original','main');
    console.log(JSON.stringify({foreign,holder:t.getTask('held').claimedBy,blocked,complete,claim,pending:t.pendingTasks().map(x=>x.id)}));
    ''')
    assert r['holder']=='other'
    for key in ['foreign','blocked','complete','claim']:
        assert r[key]['ok'] is False
    assert 'original' not in r['pending']

def test_given_legacy_failure_when_recovered_then_success_retains_the_old_evidence():
    r=run_node('''
    import * as t from './index.ts';
    t.loadTasks({old:{id:'old',subject:'Legacy failure',status:'recovery_hold',result:'LEGACY_FAILURE_TAIL',dependsOn:[],resources:[],createdAt:1,updatedAt:1}});
    t.takeTask('old','main',{reason:'Legacy blocker fixed'});
    t.completeTaskWithOutcome('old','main','success','New verification');
    console.log(JSON.stringify(t.getTask('old')));
    ''')
    assert r['failureEvidence']=='LEGACY_FAILURE_TAIL'
    assert r['result']=='New verification'

def test_given_reordered_read_arguments_when_repeated_then_it_is_not_new_work():
    r=run_node('''
    import * as t from './index.ts';
    const handlers=new Map();t.default({registerTool(){},on(n,h){handlers.set(n,h)},events:{emit(){}}});
    t.createTask({subject:'Work'});const ctx={hasUI:true,hasPendingMessages:()=>false};
    const event={outcome:'completed',entries:[],continue:false,context:{pendingMessages:[]}};
    const read=async(args,part)=>{
      await handlers.get('agent_start')({},ctx);
      await handlers.get('tool_execution_start')({toolCallId:'id',toolName:'read',args},ctx);
      await handlers.get('tool_execution_end')({toolCallId:'id',toolName:'read',result:{content:[part]},isError:false},ctx);
      return handlers.get('agent_before_settle')(event,ctx);
    };
    const first=await read({path:'file',offset:1},{type:'text',text:'Content'});
    const repeated=await read({offset:1,path:'file'},{text:'Content',type:'text'});
    console.log(JSON.stringify({first,repeated}));
    ''')
    assert r['first']['continue'] is True
    assert r['repeated']['continue'] is False

def test_given_a_stopped_holder_when_failure_evidence_exceeds_budget_then_its_lease_is_released():
    r=run_node('''
    import * as t from './index.ts';
    t.createTask({id:'small',subject:'Small',});t.setTaskContext('small',{budgetBytes:100});t.takeTask('small','main');
    const reason='Failure diagnostic '.repeat(20)+'FAILURE_TAIL';
    const released=t.failTasksHeldBy('main',reason);
    console.log(JSON.stringify({released:released.length,task:t.getTask('small'),reason}));
    ''')
    assert r['released']==1
    assert r['task']['status']=='blocked' and 'claimedBy' not in r['task']
    assert r['task']['result']==r['reason']

def test_given_replaced_history_when_discarded_then_the_record_remains():
    r=run_node('''
    import * as t from './index.ts';
    t.createTask({id:'old',subject:'History'});t.createTask({id:'new',subject:'New',supersedes:['old']});
    const discarded=t.discardTask('old','main');
    console.log(JSON.stringify({discarded,task:t.getTask('old')}));
    ''')
    assert r['discarded'] is False
    assert r['task']['supersededBy']=='new'

def test_given_recovery_when_rendered_then_the_saved_reason_is_visible():
    r=run_node('''
    import * as t from './index.ts';
    t.createTask({id:'one',subject:'Work'});t.blockTask('one','main','Initial blocker');
    const resumed=await t.executeTaskUpdate({id:'one',status:'in_progress',reason:'RECOVERY_REASON_TAIL'});
    console.log(JSON.stringify(t.TASK_ROW_SPEC(resumed)));
    ''')
    assert 'RECOVERY_REASON_TAIL' in '\n'.join(r['summary'])

def test_given_legacy_replacement_without_a_target_when_restored_then_it_cannot_reenter_work():
    r=run_node('''
    import * as t from './index.ts';
    t.loadTasks({bad:{id:'bad',subject:'Broken replacement',status:'superseded',dependsOn:[],resources:[],createdAt:1,updatedAt:1}});
    const dependent=t.createTask({subject:'Dependent',dependsOn:['bad']});
    const take=t.takeTask('bad','main',{reason:'Inspection alone cannot recover an obsolete task'});
    const discard=t.discardTask('bad','main');
    console.log(JSON.stringify({dependent,take,discard,task:t.getTask('bad'),notice:t.storeNotice()}));
    ''')
    assert r['dependent']['ok'] is False and r['take']['ok'] is False
    assert 'undefined' not in r['take']['reason']
    assert r['discard'] is False
    assert r['task']['replacementUnresolved'] is True
    assert 'inspection' in r['notice']

def test_given_waiting_work_when_blocker_or_notice_changes_then_the_new_information_is_shown():
    r=run_node('''
    import * as t from './index.ts';
    t.createTask({id:'one',subject:'Work'});t.blockTask('one','main','Initial reason');
    const check=new t.TaskStopCheck();const event={outcome:'completed',entries:[],continue:false,context:{pendingMessages:[]}};
    const options={caller:'main',hasUI:true};
    const first=check.check(event,options);
    t.blockTask('one','main','NEW_BLOCKER_TAIL');const changed=check.check(event,options);
    t.setStoreNotice('NEW_NOTICE_TAIL');const notice=check.check(event,options);
    console.log(JSON.stringify({first,changed,notice}));
    ''')
    assert r['changed']['entries'][0]['details']['tasks'][0]['blockedReason']=='NEW_BLOCKER_TAIL'
    assert r['notice']['entries'][0]['details']['notice']=='NEW_NOTICE_TAIL'
    assert all(r[key]['continue'] is False for key in ['first','changed','notice'])

def test_given_long_errors_and_notices_when_rendered_then_the_collapsed_row_hides_the_tails_and_expansion_keeps_them():
    r=run_node('''
    import * as t from './index.ts';import {visibleWidth} from '@earendil-works/pi-tui';
    const tools=new Map();t.default({registerTool(x){tools.set(x.name,x)},on(){},events:{emit(){}}});
    const style={fg:(_,x)=>x,bg:(_,x)=>x,bold:x=>x};
    const result={isError:true,content:[{type:'text',text:'Long error context. '.repeat(50)+'ERROR_TAIL'}],details:{tool:'update_task',ok:false,notice:'Persistence notice. '.repeat(50)+'NOTICE_TAIL'}};
    const rendered=[40,80].map(width=>{
      const collapsed=tools.get('update_task').renderResult(result,{expanded:false,isPartial:false},style,{isError:true}).render(width);
      const expanded=tools.get('update_task').renderResult(result,{expanded:true,isPartial:false},style,{isError:true}).render(width);
      return {width,collapsed:collapsed.join('\\n'),expanded:expanded.join('\\n'),widths:[...collapsed,...expanded].map(visibleWidth)};
    });console.log(JSON.stringify({rendered}));
    ''')
    for item in r['rendered']:
        assert 'ERROR_TAIL' in item['expanded'] and 'NOTICE_TAIL' in item['expanded']
        assert 'ERROR_TAIL' not in item['collapsed'] and 'NOTICE_TAIL' not in item['collapsed']
        assert 'to expand' in item['collapsed']
        assert max(item['widths'])<=item['width']

def test_given_abandoned_work_when_cancelled_then_it_leaves_the_board_and_keeps_the_record():
    r=run_node('''
    import * as t from './index.ts';
    t.loadTasks({});
    t.createTask({id:'premise',subject:'Premise'});
    t.createTask({id:'dependent',subject:'Built on it',dependsOn:['premise']});
    t.createTask({id:'finished',subject:'Finished'});
    t.takeTask('finished','main');
    t.completeTaskWithOutcome('finished','main','success','Finished',{checks:[],result:'Finished'});
    const noReason=t.cancelTask('premise','main',undefined);
    const cancelled=t.cancelTask('premise','main','The user changed direction');
    const cancelledOk=cancelled.ok;
    const cancelledStatus=cancelled.ok?cancelled.task.status:null;
    const cancelledReason=cancelled.ok?cancelled.task.cancelReason:null;
    const refuseCompleted=t.cancelTask('finished','main','abandon');
    // Snapshot the cancelled state before reopening mutates the same record.
    const afterCancelStatus=t.getTask('premise').status;
    const dependentStatus=t.getTask('dependent').status;
    const claimable=t.claimableTasks().map(x=>x.id);
    const blockedBy=t.blockedDependencies(t.getTask('dependent'));
    const reopened=t.reopenTask('premise');
    const afterReopen=t.getTask('premise');
    console.log(JSON.stringify({states:t.TASK_STATUSES,noReason:noReason.ok,cancelledOk,cancelledStatus,cancelledReason,
      refuseCompleted:refuseCompleted.ok,afterCancelStatus,dependentStatus,claimable,blockedBy,
      reopened:reopened.ok,reopenedStatus:afterReopen.status,reopenedReason:afterReopen.cancelReason??null}));
    ''')
    assert 'cancelled' in r['states']
    assert r['noReason'] is False, 'a cancellation without a reason is refused'
    assert r['refuseCompleted'] is False, 'completed work is not cancelled; it is reopened'
    assert r['cancelledOk'] is True
    assert r['cancelledStatus']=='cancelled'
    assert r['cancelledReason']=='The user changed direction'
    assert r['afterCancelStatus']=='cancelled'
    assert r['claimable']==[], 'cancelled work is not claimable'
    assert r['dependentStatus']=='pending'
    assert r['blockedBy']==['premise'], 'a cancelled prerequisite does not satisfy a dependency'
    assert r['reopened'] is True
    assert r['reopenedStatus']=='pending' and r['reopenedReason'] is None
