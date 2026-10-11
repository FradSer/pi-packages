"""Evidence checks for the real study; these never create learned state."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path


def verifier_observation(task: str, verification: dict, output: Path, source_hashes: dict, session: bytes) -> dict:
    logs={name:(output/(name+'.log')).read_text() for name in ('hidden','types','upstream') if (output/(name+'.log')).exists()}
    if sum(len(text.encode()) for text in logs.values()) > 1_000_000:
        raise ValueError('Verifier evidence exceeds bound; do not truncate it')
    return {'kind':'actual-project-verification','task':task,'verification':verification,'logs':logs,
            'sourceHashes':source_hashes,'sessionDigest':hashlib.sha256(session).hexdigest(),
            'logsDigest':hashlib.sha256(json.dumps(logs,sort_keys=True).encode()).hexdigest()}


def continuous_coverage(report: dict) -> dict:
    stages=report.get('stages',[])
    arms={stage['id']:stage.get('arms',{}).get('with-learning',{}) for stage in stages}
    first=arms.get('orientation',{})
    entries=first.get('learning',{}).get('memoryEntries',[])
    old_contract=[e for e in entries if 'limitFunction' in e.get('content','') and 'PromiseLike' in e.get('content','')]
    used=False
    for stage in stages[1:]:
        arm=stage.get('arms',{}).get('with-learning',{})
        if any(ref.get('filename')==entry['filename'] and ref.get('revision')==entry['revision']
               for ref in arm.get('inference',{}).get('deliveredMemoryEntries',[]) for entry in entries):used=True
    corrected=arms.get('repair-and-sync-wrapper',{}).get('learning',{}).get('memoryEntries',[])
    next_refs=arms.get('wrapper-map',{}).get('inference',{}).get('deliveredMemoryEntries',[])
    audits=arms.get('repair-and-sync-wrapper',{}).get('memoryAudits',[])
    corrected_used=any(old['filename']==new['filename'] and old['revision']!=new['revision']
                       and hashlib.sha256(new.get('content','').encode()).hexdigest()==new['revision']
                       and any(audit.get('passed') is True and audit.get('filename')==new['filename'] and audit.get('priorRevision')==old['revision'] and audit.get('revision')==new['revision'] for audit in audits)
                       and any(ref.get('filename')==new['filename'] and ref.get('revision')==new['revision'] for ref in next_refs)
                       for old in old_contract for new in corrected)
    h0=first.get('harness',{});h2=arms.get('cancellable-idle',{}).get('harness',{});h3=arms.get('clear-reason',{}).get('harness',{})
    owned=h0.get('ownedRevisions',{})
    def history_link(arm: dict, before: str, after: str) -> bool:
        reachable={before}
        changes=[change for record in arm.get('learning',{}).get('history',[]) if record.get('phase')=='harness' and record.get('status')=='applied'
                 for change in record.get('changes',[]) if change.get('target')=={'root':'project','name':'.pi/harness.json'}]
        for _ in range(len(changes)+1):
            for change in changes:
                prior=(change.get('before') or {}).get('digest');current=(change.get('after') or {}).get('digest')
                if prior in reachable:reachable.add(current)
        return before!=after and after in reachable
    corrected_harness=False;retired=False;others_preserved=False
    for id,revision in owned.items():
        next_revision=h2.get('ownedRevisions',{}).get(id)
        if not next_revision or next_revision==revision:continue
        narrowed=next((r for r in h2.get('document',{}).get('rules',[]) if r.get('id')==id),None)
        tombstone=next((r for r in h3.get('document',{}).get('rules',[]) if r.get('id')==id),None)
        corrected_harness=bool(narrowed and narrowed.get('enabled') is not False and h2.get('passed')
                               and history_link(arms.get('cancellable-idle',{}),h0.get('documentDigest'),h2.get('documentDigest')))
        retired=bool(tombstone and tombstone.get('enabled') is False and id in h3.get('ownedRevisions',{}) and h3.get('passed')
                     and history_link(arms.get('clear-reason',{}),h2.get('documentDigest'),h3.get('documentDigest')))
        baseline=[r for r in h0.get('rules',[]) if r.get('id')!=id]
        others_preserved=all([r for r in h.get('rules',[]) if r.get('id')!=id]==baseline for h in (h2,h3))
        if corrected_harness and retired and others_preserved:break
    def failure_backfilled(arm: dict, *, learned: bool) -> bool:
        feedback=arm.get('verifierFeedback') or {};observation=feedback.get('observation',{});queued=feedback.get('queuedFailure') or {};learning=arm.get('learning',{})
        if not (observation.get('verification',{}).get('passed') is False and feedback.get('originalObservationsPreserved') is True
                and feedback.get('verifierObserved') is True and feedback.get('taskSourceUnchanged') is True and arm.get('explicitRecovery')
                and bool(feedback.get('originalEntryIds')) and queued.get('id') in learning.get('completedBacklog',{}) and learning.get('pendingLearningJobs')==0):return False
        completed=[attempt for attempt in learning.get('attempts',[]) if attempt.get('outcome')=='completed' and attempt.get('receipt',{}).get('input',{}).get('backlogId')==queued['id']
                   and bool(attempt.get('receiptDigest')) and learning['completedBacklog'][queued['id']]==attempt['receiptDigest']]
        complete=bool(completed)
        observed=any(dossier.get('taskSliceDigest')==queued.get('digest') and set(feedback.get('originalEntryIds',[])).issubset(dossier.get('entryIds',[]))
                     and any(item.get('sessionDigest')==observation.get('sessionDigest') and item.get('logsDigest')==observation.get('logsDigest') for item in dossier.get('observations',[]))
                     for dossier in learning.get('dossiers',[]))
        if not complete or not observed:return False
        if not learned:return True
        batches={a['receipt'].get('batchId') for a in completed if a['receipt'].get('operations',0)>0 and a['receipt'].get('batchId')}
        changed=[change for record in learning.get('history',[]) if record.get('status')=='applied' and record.get('batchId') in batches
                 for change in record.get('changes',[]) if change.get('after') and (change.get('before') or {}).get('digest')!=change['after'].get('digest')]
        # Delivery and execution are evidence of consumption, not a claim of benefit.
        later=False
        for stage in stages:
            candidate=stage.get('arms',{}).get('with-learning',{})
            if candidate is arm:later=True;continue
            if not later:continue
            for change in changed:
                target=change.get('target',{});digest=change['after'].get('digest')
                if target.get('root') in ('public','private') and target.get('name')!='MEMORY.md':
                    if any(ref.get('filename')==target.get('name') and ref.get('revision')==digest for ref in candidate.get('inference',{}).get('deliveredMemoryEntries',[])):return True
                if target=={'root':'project','name':'.pi/harness.json'} and candidate.get('harness',{}).get('documentDigest')==digest and candidate.get('harness',{}).get('passed'):return True
        return False
    processed=any(failure_backfilled(arm,learned=False) for arm in arms.values())
    backfilled=any(failure_backfilled(arm,learned=True) for arm in arms.values())
    pairs=[]
    for stage in stages[1:]:
        pair=stage.get('arms',{});a=pair.get('without-learning',{});b=pair.get('with-learning',{})
        if not a or not b or not stage.get('validPairInput'):continue
        pairs.append({'task':stage['id'],'outcome':'tie' if bool(a.get('passed'))==bool(b.get('passed')) else 'win' if b.get('passed') else 'loss'})
    result={'memoryLearned':bool(entries),'originalTypeContractLearned':bool(old_contract),'memoryUsed':used,'memoryCorrectedAndUsed':corrected_used,
            'harnessCorrected':corrected_harness,'harnessRetired':retired,'otherRulesPreserved':others_preserved,'failedTaskProcessed':bool(processed),'failedTaskBackfilled':bool(backfilled),
            'pairedOutcomes':pairs,'learningValid':bool(stages) and all(s.get('arms',{}).get('with-learning',{}).get('validLearning') for s in stages)}
    result['coverageComplete']=len(stages)==6 and all(result[k] for k in ('memoryLearned','originalTypeContractLearned','memoryUsed','memoryCorrectedAndUsed','harnessCorrected','harnessRetired','otherRulesPreserved','failedTaskBackfilled','learningValid'))
    result['improvementObserved']=result['coverageComplete'] and sum(x['outcome']=='win' for x in pairs)>sum(x['outcome']=='loss' for x in pairs)
    return result
