from support import isolated_run_bun


def test_research_gate_rejects_identity_scope_privacy_and_quote_changes() -> None:
    row = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {checkDurableCoreRepair,DURABLE_CORE_CLARIFICATION} from './packages/continual-learning/tests/durable-core-generator-research.ts';
      const c=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/jev-durable-core-generator-cases.json','utf8')).cases[0];
      const modes=['valid','identity','scope','snapshot','privacy','name','kind','quote','operation','metadata','description'];
      const results=modes.map(mode=>{const plan=structuredClone(c.rejectedPlan);
       if(mode==='identity')plan.runId='other';if(mode==='scope')plan.scopeKey='other';
       if(mode==='snapshot')plan.snapshotDigest='other';if(mode==='privacy')plan.newMemories[0].classification='private';
       if(mode==='name')plan.newMemories[0].name='other.md';if(mode==='kind')plan.newMemories[0].kind='preference';
       if(mode==='quote')plan.newMemories[0].evidence[0].quote='invented evidence';
       if(mode==='operation')plan.operations=[{kind:'delete',name:'existing.md'}];
       if(mode==='metadata')plan.inventory=[];
       if(mode==='description')plan.newMemories[0].content=plan.newMemories[0].content.replace(/description:.*\n/,'');
       return {mode,ready:checkDurableCoreRepair(plan,c).category==='ready'};});
      console.log(JSON.stringify({results,bounded:DURABLE_CORE_CLARIFICATION.length<=800,
       preserves:DURABLE_CORE_CLARIFICATION.includes('explicitly requested historical results'),
       noInvent:DURABLE_CORE_CLARIFICATION.includes('do not invent a durable fact')}));
    ''')
    assert row['results'][0]['ready'] is True
    assert all(not value['ready'] for value in row['results'][1:])
    assert row['bounded'] and row['preserves'] and row['noInvent']


def test_all_prospective_case_quotes_and_hashes_are_parent_valid() -> None:
    row = isolated_run_bun(r'''
      import fs from 'node:fs';import {checkDurableCoreRepair} from './packages/continual-learning/tests/durable-core-generator-research.ts';
      const d=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/jev-durable-core-generator-cases.json','utf8'));
      console.log(JSON.stringify({count:d.cases.length,scenarios:new Set(d.cases.map(c=>c.scenario)).size,
       allReady:d.cases.every(c=>checkDurableCoreRepair(c.rejectedPlan,c).category==='ready'),
       languages:[...new Set(d.cases.map(c=>c.language))].sort()}));
    ''')
    assert row == {'count': 16, 'scenarios': 8, 'allReady': True, 'languages': ['en', 'zh']}


def test_raw_candidate_declarations_and_original_citations_cannot_be_normalized_away() -> None:
    row = isolated_run_bun(r'''
      import fs from 'node:fs';import {checkDurableCoreRepair} from './packages/continual-learning/tests/durable-core-generator-research.ts';
      const cases=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/jev-durable-core-generator-cases.json','utf8')).cases;
      const outputs=[];for(const mode of ['private-to-safe','missing-classification','target-path','nested-inventory','frontmatter-name','frontmatter-type','duplicate-field','short-quote','missing-quote','evidence-metadata']){
       const c=cases.find(c=>c.scenario==='private-conditional-preference'&&c.language==='en');const plan=structuredClone(c.rejectedPlan),m=plan.newMemories[0];
       if(mode==='private-to-safe')m.classification='safe';if(mode==='missing-classification')delete m.classification;
       if(mode==='target-path')m.targetPath='/tmp/unauthorized';if(mode==='nested-inventory')m.inventory=[];
       if(mode==='frontmatter-name')m.content=m.content.replace('name: aurora_fact','name: another_subject');
       if(mode==='frontmatter-type')m.content=m.content.replace('type: preference','type: project');
       if(mode==='duplicate-field')m.content=m.content.replace('name: aurora_fact','name: aurora_fact\nname: another_subject');
       if(mode==='short-quote')m.evidence[0].quote='REPORT_DONE';if(mode==='missing-quote')m.evidence.pop();
       if(mode==='evidence-metadata')m.evidence[0].targetPath='/tmp/unauthorized';
       outputs.push({mode,ready:checkDurableCoreRepair(plan,c).category==='ready'});
      }console.log(JSON.stringify(outputs));
    ''')
    assert all(not value['ready'] for value in row), row


def test_freeze_set_rejects_empty_missing_and_external_sources() -> None:
    row = isolated_run_bun(r'''
      import {validDurableCoreFreezeSet} from './packages/continual-learning/tests/durable-core-generator-research.ts';
      const required=['/opt/experiment/worker.ts','/opt/experiment/guide.ts','/home/node/research/cases.json'];
      const complete=Object.fromEntries(required.map(p=>[p,'a'.repeat(64)]));
      console.log(JSON.stringify({valid:validDurableCoreFreezeSet(complete,required),
       empty:validDurableCoreFreezeSet({},required),
       missing:validDurableCoreFreezeSet({'/opt/experiment/worker.ts':'a'.repeat(64)},required),
       external:validDurableCoreFreezeSet({...complete,'/host/private-file':'a'.repeat(64)},required),
       invalidDigest:validDurableCoreFreezeSet({...complete,[required[2]]:'invalid'},required)}));
    ''')
    assert row == {'valid': True, 'empty': False, 'missing': False, 'external': False, 'invalidDigest': False}
