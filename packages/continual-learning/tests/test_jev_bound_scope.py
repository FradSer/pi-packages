import pytest
from support import isolated_run_bun


@pytest.mark.parametrize("variant", ["v1", "v2", "production"])
def test_parent_bound_template_routes_only_with_matching_frozen_identity(variant: str) -> None:
    # Given a parent-bound template, When its frozen identity is verified,
    # Then exact syntax becomes code context, never user authorization.
    rows = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      import {projectPushTemplate} from './packages/continual-learning/extensions/harness-command-coverage.ts';
      import {createJevJudge as productionJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      import {loadBoundScopeJudge, boundScopeSourceV2} from './packages/continual-learning/tests/jev-bound-scope-shadow.ts';
      const research=await loadBoundScopeJudge();const outputs=[];
      try {
        if (research.directory?.startsWith(process.cwd()+"/")) throw Error("Research scratch must stay outside the source checkout");
        const quote='Never run git push in this project, including --dry-run, in future tasks.';
        const snapshot={contextEnabled:true,runId:'run_fixture',scopeKey:'fixture',entries:[{role:'user',content:quote}]};
        const candidate={op:'addRule',rule:{id:'no-push',bash:projectPushTemplate('/work/project'),action:'block',message:quote},cases:{positive:[{bash:'git push --dry-run'}],negative:[{bash:'echo git push --dry-run'}]}};
        const citation=[{index:0,source:'user',quote,count:1,eventIndex:0}];
        const binding={repoRoot:'/work/project',runId:snapshot.runId,scopeKey:snapshot.scopeKey,evidenceDigest:createHash('sha256').update(JSON.stringify(snapshot)).digest('hex')};
        for(const mode of ['valid','missing','foreign-root','wrong-run','wrong-scope','wrong-digest','changed-snapshot','existing-rule','approval-rule']) {
          const parent=mode==='missing'?undefined:{...binding,...(mode==='foreign-root'?{repoRoot:'/work/elsewhere'}:{}),...(mode==='wrong-run'?{runId:'another'}:{}),...(mode==='wrong-scope'?{scopeKey:'another'}:{}),...(mode==='wrong-digest'?{evidenceDigest:'0'.repeat(64)}:{})};
          const original=structuredClone(candidate);if(mode==='existing-rule')original.op='updateRule';if(mode==='approval-rule')original.rule.action='confirm';
          const evidence=mode==='changed-snapshot'?{...snapshot,entries:[...snapshot.entries,{role:'user',content:'Keep an exception.'}]}:snapshot;
          const keys=[];const matching=[];let calls=0;const judge=research.createJevJudge({enabled:true,apiKey:'fixture',scopes:['harness'],fetch:async(_url,init)=>{
            calls++;const request=JSON.parse(String(init.body));const answers={};
            for(const [key,q]of Object.entries(request.questions)) {
              keys.push(key);if(q.instructions.candidate?.matching)matching.push(q.instructions.candidate.matching);
              if(q.instructions.candidate?.rule?.matching)matching.push(q.instructions.candidate.rule.matching);
              const label=key.startsWith('authority')?'lasting':key.startsWith('family')?'authorized':key.startsWith('explanation')?'faithful':key.startsWith('expands')?'broader':'compatible';
              answers[key]=q.type==='noul'?{type:'noul',noul:.99}:{type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===label?1:0]))};
            }
            return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
          }});
          const before=JSON.stringify(original);const result=await judge.validate('harness',evidence,[original],[],undefined,citation,parent);
          outputs.push({mode,keys,result,matching,calls,unchanged:before===JSON.stringify(original)});
        }
      }finally{await research.dispose();}
      console.log(JSON.stringify(outputs));
    '''.replace('await loadBoundScopeJudge()', 'await loadBoundScopeJudge(boundScopeSourceV2)' if variant == 'v2' else '{createJevJudge:productionJudge,dispose:async()=>{}}' if variant == 'production' else 'await loadBoundScopeJudge()'))
    for row in rows:
        assert row['unchanged']
        assert row['result']['decision'] == ('allow' if row['mode'] == 'valid' else 'propose')
        if row['mode'] == 'valid':
            assert 'authority_0' in row['keys'] and 'family_0' in row['keys']
            assert 'expands_0' not in row['keys']
            assert row['matching'] and all('parent-bound' in text for text in row['matching'])
            assert row['result']['telemetry']['coveredEntries'] == 1
        else:
            assert 'family_0' not in row['keys']


@pytest.mark.parametrize("variant", ["v1", "v2", "production"])
def test_matching_proof_never_supplies_permission_or_ignores_counterevidence(variant: str) -> None:
    rows = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      import {projectPushTemplate} from './packages/continual-learning/extensions/harness-command-coverage.ts';
      import {createJevJudge as productionJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      import {loadBoundScopeJudge, boundScopeSourceV2} from './packages/continual-learning/tests/jev-bound-scope-shadow.ts';
      const research=await loadBoundScopeJudge();const outputs=[];
      try {
        const quote='Never run git push in this project in future tasks.';
        const snapshot={contextEnabled:true,runId:'run_fixture',scopeKey:'fixture',entries:[{role:'user',content:quote},{role:'user',content:'Except with my approval.'}]};
        const candidate={op:'addRule',rule:{id:'no-push',bash:projectPushTemplate('/work/project'),action:'block',message:quote}};
        const citations=[{index:0,source:'user',quote,count:1,eventIndex:0}];
        const binding={repoRoot:'/work/project',runId:snapshot.runId,scopeKey:snapshot.scopeKey,evidenceDigest:createHash('sha256').update(JSON.stringify(snapshot)).digest('hex')};
        for(const mode of ['conditional','temporary','elsewhere','absent','exact-arguments','uncertain','counter','unavailable']) {
          const keys=[];const judge=research.createJevJudge({enabled:true,apiKey:'fixture',scopes:['harness'],fetch:async(_url,init)=>{
            if(mode==='unavailable')throw Error('fixture unavailable');const request=JSON.parse(String(init.body));const answers={};
            for(const [key,q]of Object.entries(request.questions)) {
              keys.push(key);const label=key.startsWith('authority')?(['conditional','temporary','elsewhere','absent'].includes(mode)?mode:'lasting'):key.startsWith('family')?(mode==='exact-arguments'?'extra':mode==='uncertain'?'unclear':'authorized'):key.startsWith('explanation')?'faithful':mode==='counter'?'contradicts':'compatible';
              answers[key]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===label?1:0]))};
            }
            return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
          }});
          outputs.push({mode,keys,result:await judge.validate('harness',snapshot,[candidate],[],undefined,citations,binding)});
        }
      }finally{await research.dispose();}
      console.log(JSON.stringify(outputs));
    '''.replace('await loadBoundScopeJudge()', 'await loadBoundScopeJudge(boundScopeSourceV2)' if variant == 'v2' else '{createJevJudge:productionJudge,dispose:async()=>{}}' if variant == 'production' else 'await loadBoundScopeJudge()'))
    for row in rows:
        assert row['result']['decision'] == 'propose'
        if row['mode'] == 'exact-arguments':
            assert row['result']['telemetry']['reason'] == 'scope-expansion'
        if row['mode'] == 'counter':
            assert row['result']['telemetry']['reason'] == 'conflict'
            assert 'counter_0_0' in row['keys']


@pytest.mark.parametrize("variant", ["v1", "v2", "production"])
def test_bound_scope_keeps_memory_wire_and_privacy_preflight_unchanged(variant: str) -> None:
    row = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      import {createJevJudge as productionJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      import {loadBoundScopeJudge, boundScopeSourceV2} from './packages/continual-learning/tests/jev-bound-scope-shadow.ts';
      const r=await loadBoundScopeJudge();const sent=[[],[]];const results=[];
      try {
        const quote='This project uses pnpm.';
        const candidate={name:'fact.md',kind:'project',classification:'safe',content:'---\nname: fact\ndescription: '+quote+'\ntype: project\n---\n'+quote,evidence:[{index:0,quote,role:'user'}]};
        for(const [i,factory]of [r.baselineCreateJevJudge,r.createJevJudge].entries()){
          const judge=factory({enabled:true,apiKey:'fixture',scopes:['memory','harness'],fetch:async(_url,init)=>{
            sent[i].push(String(init.body));const req=JSON.parse(String(init.body));const answers={};for(const [k,q]of Object.entries(req.questions)){
              const label=k.startsWith('supported')?'grounded':'compatible';answers[k]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};
            }return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
          }});
          await judge.validate('memory',{contextEnabled:true,entries:[{role:'user',content:quote}]},[candidate],[]);
          const before=sent[i].length;
          const result=await judge.validate('memory',{contextEnabled:true,entries:[{role:'user',content:'api_key=sk-'+'a'.repeat(45)}]},[candidate],[]);
          results.push({result,outbound:sent[i].length-before});
        }
      }finally{await r.dispose();}
      // Compare each frozen research transform with its own original source.
      // Current production contracts are covered in test_learning_failure_recovery.py.
      console.log(JSON.stringify({sameWire:JSON.stringify(sent[0])===JSON.stringify(sent[1]),results}));
    '''.replace('await loadBoundScopeJudge()', 'await loadBoundScopeJudge(boundScopeSourceV2)' if variant == 'v2' else '{createJevJudge:productionJudge,baselineCreateJevJudge:productionJudge,dispose:async()=>{}}' if variant == 'production' else 'await loadBoundScopeJudge()'))
    assert row['sameWire']
    assert all(r['outbound'] == 0 and r['result']['telemetry']['reason'] == 'sensitive' for r in row['results'])
