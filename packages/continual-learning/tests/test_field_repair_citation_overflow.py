from support import isolated_run_bun


def test_actual_correction_preserves_all_quote_bytes_within_original_citation_bound() -> None:
    # Given the real four-citation proposal and eight-citation correction, When
    # the parent preserves an accepted description, Then a larger verified quote
    # may represent an original contained quote without losing either's bytes.
    result = isolated_run_bun(r'''
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-field-repair-citation-overflow.json').json();
      const {resolveMemoryPlanCitations}=await import('./packages/continual-learning/extensions/memory-citation-locations.ts');
      const {mergeSemanticMemoryRepairDelta}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {normalizeNewMemoryProposals,normalizeSnapshotEvidence}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const before=resolveMemoryPlanCitations(f.originalPlan,f.snapshot),delta=resolveMemoryPlanCitations(f.repairResponse,f.snapshot);
      const fields=Object.fromEntries(before.newMemories.map(x=>[x.name,['body']]));
      const merged=mergeSemanticMemoryRepairDelta(before,delta,before.newMemories.map(x=>x.name),fields,f.snapshot);
      const candidates=normalizeNewMemoryProposals(merged,f.snapshot,[]);
      const old=before.newMemories[0],replacement=delta.newMemories[0],next=merged.newMemories[0];
      const covered=x=>next.evidence.some(y=>x.index===y.index&&x.role===y.role&&y.quote.includes(x.quote));
      console.log(JSON.stringify({oldCount:old.evidence.length,repairedCount:replacement.evidence.length,mergedCount:next.evidence.length,
        oldCovered:old.evidence.every(covered),repairCovered:replacement.evidence.every(covered),
        quotesValid:normalizeSnapshotEvidence(next.evidence,f.snapshot).length===next.evidence.length,
        bodyCorrect:next.content.split('\n---\n')[1]===replacement.content.split('\n---\n')[1],
        headerPreserved:next.content.split('\n---\n')[0]===old.content.split('\n---\n')[0],candidates:candidates.length}));
    ''')
    assert result == {
        'oldCount': 4, 'repairedCount': 8, 'mergedCount': 8,
        'oldCovered': True, 'repairCovered': True, 'quotesValid': True,
        'bodyCorrect': True, 'headerPreserved': True, 'candidates': 2,
    }


def test_citation_enlargement_needs_verified_same_source_and_role() -> None:
    result = isolated_run_bun(r'''
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-field-repair-citation-overflow.json').json();
      const {resolveMemoryPlanCitations}=await import('./packages/continual-learning/extensions/memory-citation-locations.ts');
      const {mergeSemanticMemoryRepairDelta}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const a=resolveMemoryPlanCitations(f.originalPlan,f.snapshot),b=resolveMemoryPlanCitations(f.repairResponse,f.snapshot);
      const old=a.newMemories[0].evidence[2];
      const larger=b.newMemories[0].evidence.find(x=>x.index===old.index&&x.quote!==old.quote&&x.quote.includes(old.quote));
      const rows=[];
      for(const mode of ['valid','different-index','forged-role','fabricated','no-snapshot']){
        const snapshot=structuredClone(f.snapshot),citation=structuredClone(larger);
        if(mode==='different-index'){citation.index=snapshot.entries.length;snapshot.entries.push(structuredClone(snapshot.entries[old.index]));}
        if(mode==='forged-role')citation.role='user';
        if(mode==='fabricated')citation.quote='fabricated '+citation.quote;
        const before={...a,newMemories:[{...a.newMemories[0],evidence:[old]}]},delta={...b,newMemories:[{...b.newMemories[0],evidence:[citation]}]};
        const merged=mergeSemanticMemoryRepairDelta(before,delta,[a.newMemories[0].name],{[a.newMemories[0].name]:['body']},mode==='no-snapshot'?undefined:snapshot);
        rows.push({mode,count:merged.newMemories[0].evidence.length,oldUnchanged:JSON.stringify(merged.newMemories[0].evidence[0])===JSON.stringify(old)});
      }
      console.log(JSON.stringify(rows));
    ''')
    assert result[0] == {'mode': 'valid', 'count': 1, 'oldUnchanged': False}
    assert all(row['count'] == 2 and row['oldUnchanged'] for row in result[1:])
