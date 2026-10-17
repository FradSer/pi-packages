from support import isolated_run_bun


def test_correction_explains_both_matchers_without_new_rule_shortcuts_or_authority():
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const quote='Correction of the prior permanent project constraint: npm --version is now allowed; only Bash commands starting npm test must be blocked. Replace the old broad npm restriction permanently, do not add a second conflicting rule.';
      const priorRule={id:'block-npm-first-executable',bash:'^[ \\t]*npm(?:[ \\t\\n;|&<>]|$(?![\\s\\S]))',action:'block',message:'Permanently block npm first-executable commands.'};
      const rule={...priorRule,bash:'^[ \\t]*npm[ \\t]+test(?:[ \\t\\n;|&<>]|$(?![\\s\\S]))',message:'Only Bash commands starting npm test are blocked; npm --version is allowed.'};
      const baseCandidate={op:'updateRule',rule,priorRule,correction:{eventIndex:0,quote,priorRevision:'a'.repeat(64)},cases:{positive:[{bash:'npm test',expected:'block'}],negative:[{bash:'npm --version',expected:'no-match'}]}};
      const evidence={contextEnabled:true,entries:[{role:'user',content:quote}]},citation=[{index:0,source:'user',quote,count:1}];const results=[];
      for(const mode of ['normal','bounded','uncertain','retired','unknown']){
        const candidate=mode==='retired'?{...baseCandidate,rule:{...rule,enabled:false}}:mode==='unknown'?{...baseCandidate,rule:{...rule,bash:'^npm.*$'},priorRule:{...priorRule,bash:'npm'}}:baseCandidate;
        const requests=[];const judge=createJevJudge({enabled:true,apiKey:'fixture',requestConcurrency:1,...(mode==='bounded'?{maxRequestBytes:64000}:{}),fetch:async(_u,init)=>{
          const r=JSON.parse(init.body);requests.push(r);return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{if(q.type==='noul')return[key,{type:'noul',noul:mode==='uncertain'?.87:1}];const labels=Object.keys(q.criteria),choice=['same','compatible','grounded','independent','unrelated'].find(x=>labels.includes(x))??labels[0];return[key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(labels.map(x=>[x,+(x===choice)]))}]}))}));
        }});const before=JSON.stringify(candidate);const result=await judge.validate('harness',evidence,[candidate],[],undefined,citation);results.push({mode,decision:result.decision,unchanged:before===JSON.stringify(candidate),candidates:requests.flatMap(r=>Object.values(r.questions).map(q=>q.instructions.candidate)),questions:requests.flatMap(r=>Object.keys(r.questions)),rawRule:rule,priorRule});
      }console.log(JSON.stringify(results));
    ''')
    normal, bounded, uncertain, retired, unknown = value
    assert normal['decision'] == 'allow' and normal['unchanged']
    assert 'supported_0' in normal['questions'] and 'expands_0' in normal['questions']
    assert any(q.startswith('counter_') for q in normal['questions'])
    assert not any(q.startswith(('authority_', 'general_arguments_')) for q in normal['questions'])
    for candidate in normal['candidates']:
        assert candidate['rule'] == normal['rawRule']
        assert candidate['priorRule'] == normal['priorRule']
        assert candidate['selectorMatching']['replacement']['commandWords'] == 'npm test'
        assert candidate['selectorMatching']['predecessor']['commandWords'] == 'npm'
        assert 'never authorization' in candidate['selectorMatching']['meaning']
        assert 'identity' in candidate['recordIdentity']
    assert all('selectorMatching' not in candidate for candidate in bounded['candidates'])
    assert bounded['decision'] == 'allow'
    assert uncertain['decision'] == 'propose'

    assert retired['decision'] == 'allow' and retired['unchanged']
    for candidate in retired['candidates']:
        assert candidate['rule']['enabled'] is False
        assert 'disabled rule does not restrict' in candidate['selectorMatching']['meaning']
    assert unknown['decision'] == 'allow' and unknown['unchanged']
    for candidate in unknown['candidates']:
        assert candidate['rule']['bash'] == '^npm.*$'
        assert candidate['priorRule']['bash'] == 'npm'
        assert 'selectorMatching' not in candidate
    for row in (retired, unknown):
        assert 'supported_0' in row['questions'] and 'expands_0' in row['questions']
        assert any(q.startswith('counter_') for q in row['questions'])
        assert not any(q.startswith(('authority_', 'general_arguments_')) for q in row['questions'])
