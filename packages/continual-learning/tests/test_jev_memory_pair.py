from support import isolated_run_bun


def test_pair_judgment_retains_original_thresholds_and_unknowns() -> None:
    # Given a read-only pair judgment, When probability/confidence is insufficient
    # or response structure is invalid, Then it never asserts independence.
    rows = isolated_run_bun(r'''
      import {interpretMemoryPair, memoryPairQuestion} from './packages/continual-learning/tests/jev-memory-pair-judgment.ts';
      const labels=Object.keys(memoryPairQuestion().criteria);const out=[];
      for(const [choice,p,c]of [['independent',.9,.8],['independent',.89,1],['independent',1,.79],['dependent',1,1],['duplicate',1,1],['conflict',1,1],['unclear',1,1]]){
       const answer={type:'choice',choice,confidence:c,probabilities:Object.fromEntries(labels.map(k=>[k,k===choice?p:(1-p)/4]))};out.push(interpretMemoryPair(answer));
      }
      out.push(interpretMemoryPair({type:'choice',choice:'private-original-error',confidence:1,probabilities:{}}));
      out.push(interpretMemoryPair({type:'choice',choice:'independent',confidence:1,probabilities:{independent:1}}));console.log(JSON.stringify(out));
    ''')
    assert rows[0]['independenceObserved'] is True
    assert all(not r['independenceObserved'] for r in rows[1:])
    assert [r['status'] for r in rows] == ['decided', 'uncertain', 'uncertain', 'decided', 'decided', 'decided', 'uncertain', 'invalid-response', 'invalid-response']
    assert 'private-original-error' not in str(rows)


def test_pair_research_uses_complete_production_privacy_preflight() -> None:
    # Given public evidence, an object-key placeholder and uncited realistic
    # credential shapes, When preparing a research call, Then only safe public
    # evidence reaches transport. A credential-named structured key is judged
    # strictly: the documentation-placeholder rule applies to text, not to an
    # object argument where a real assigned secret travels.
    rows = isolated_run_bun(r'''
      import {ensureMemoryPairResearchPreflight} from './packages/continual-learning/tests/jev-memory-pair-judgment.ts';
      const quote='This project uses pnpm.';const candidates=[0,1].map(i=>({name:'fact-'+i+'.md',kind:'project',classification:'safe',content:'---\nname: fact\ndescription: '+quote+'\ntype: project\n---\n'+quote,evidence:[{index:0,quote,role:'user'}]}));
      const rows=[];for(const mode of ['public','public-placeholder','uncited-secret','quoted-secret','private-candidate']){
       // This generated value is a shape-only negative control, never a key.
       const credentialShape='pA7mQ2zX9rK4vN8sU6dF3gH5jL0cB1eR';
       const snapshot={contextEnabled:true,entries:[{role:'user',content:quote}],
        ...(mode==='public-placeholder'?{uncitedMetadata:{api_key:'fixture-private-original-123'}}:{}),
        ...(mode==='uncited-secret'?{uncitedMetadata:{api_key:credentialShape}}:{}),
        ...(mode==='quoted-secret'?{uncitedMetadata:JSON.stringify({api_key:credentialShape})}:{})};
       const inputs=structuredClone(candidates);if(mode==='private-candidate')inputs[0].classification='private';
       try{const requests=await ensureMemoryPairResearchPreflight(snapshot,inputs);rows.push({mode,accepted:true,mockRequests:requests});}catch{rows.push({mode,accepted:false});}
      }console.log(JSON.stringify(rows));
    ''')
    assert [row['mode'] for row in rows] == ['public','public-placeholder','uncited-secret','quoted-secret','private-candidate']
    assert rows[0]['accepted'] and rows[0]['mockRequests'] > 0
    assert all(not row['accepted'] for row in rows[1:])
