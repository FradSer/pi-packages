from support import isolated_run_bun


def test_jev_directions_relationships_and_failures() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let calls=[];
      let mode='good';
      const judge=createJevJudge({enabled:true,defaultModel:'jev-1.13.0',scopes:['selection','memory','harness'],apiKey:'fixture',fetch:async(url,init)=>{
        const request=JSON.parse(init.body); calls.push(request);
        if(mode==='offline') throw new Error('PRIVATE PROVIDER ERROR');
        const answers={};
        for(const [key,q] of Object.entries(request.questions)) {
          if(q.type==='noul') answers[key]={type:'noul',noul:mode==='uncertain'?0.5:mode==='unsupported'?0.01:key.includes('expands')?(mode==='broad'?0.99:0.01):0.99};
          if(q.type==='score') answers[key]={type:'score',score:2.88,confidence:0.95,probabilities:{0:0.01,1:0.01,2:0.07,3:0.91},legend:{0:"a",1:"b",2:"c",3:"d"}};
          if(q.type==='choice') answers[key]=key.startsWith('expands')?{type:'choice',choice:mode==='broad'?'broader':'same',confidence:0.99,probabilities:{same:mode==='broad'?0:1,narrower:0,broader:mode==='broad'?1:0,unclear:0}}:key.startsWith('supported')?{type:'choice',choice:mode==='unsupported'?'unsupported':'grounded',confidence:0.99,probabilities:{grounded:mode==='unsupported'?0:1,speculative:0,transient:0,unsupported:mode==='unsupported'?1:0,unclear:0}}:{type:'choice',choice:mode==='good'?'supplement':mode,confidence:0.99,
            probabilities:{unrelated:0,duplicate:mode==='duplicate'?1:0,supplement:mode==='good'?1:0,conflict:mode==='conflict'?1:0,unclear:0}};
        }
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:100,output_tokens:20}}));
      }});
      const metadata=[{name:'test.md',classification:'safe',type:'project',description:'Test command'}];
      const evidence={entries:[{message:{role:'user',content:'This project uses pnpm. Never push without permission.'}}]};
      const selected=await judge.select(evidence,metadata,false);
      const candidate={name:'test.md',content:'Use pnpm test.'};
      const existing=[{...metadata[0],content:'Use pnpm.'}];
      const supplementary=await judge.validate('memory',evidence,[candidate],existing);
      mode='duplicate'; const duplicate=await judge.validate('memory',evidence,[candidate],existing);
      mode='conflict'; const conflict=await judge.validate('memory',evidence,[candidate],existing);
      mode='broad'; const broad=await judge.validate('harness',evidence,[{rule:{bash:'.*',action:'block'}}],[]);
      mode='unsupported'; const unsupported=await judge.validate('memory',evidence,[candidate],[]);
      mode='uncertain'; const uncertain=await judge.select(evidence,metadata,true);
      mode='offline'; const offline=await judge.validate('harness',evidence,[{op:'add',rule:{bash:'.*',action:'block'}}],[]);
      console.log(JSON.stringify({selected,supplementary,duplicate,conflict,broad,unsupported,uncertain,offline,calls:calls.length,
        firstQuestions:Object.keys(calls[0].questions),leaks:JSON.stringify(offline).includes('PRIVATE')}));
    ''')
    assert result['selected']['selection']['memory'] and result['selected']['selection']['harness']
    assert result['selected']['selection']['selected'] == ['test.md']
    assert result['supplementary']['decision'] == 'allow'
    assert result['broad']['decision'] == 'propose' and result['broad']['telemetry']['reason'] == 'scope-expansion'
    assert result['unsupported']['decision'] == 'propose' and result['unsupported']['telemetry']['reason'] == 'unsupported'
    assert result['duplicate']['decision'] == result['conflict']['decision'] == 'propose'
    assert result['uncertain']['selection'] is None
    assert result['uncertain']['telemetry']['reason'] == 'uncertain'
    assert result['offline']['decision'] == 'propose' and not result['leaks']
    assert result['selected']['telemetry']['model'] == 'jev-1.13.0'
    assert len(result['firstQuestions']) == 3


def test_parent_checks_precede_jev_and_explicit_memory_is_never_silently_dropped() -> None:
    from pathlib import Path
    from support import run_bun_script
    fixture = Path(__file__).with_name('learning-policy-harness.ts')
    invalid = run_bun_script(fixture, 'remember-invalid', env={'CL_JEV_FIXTURE': 'supported'})
    assert invalid['jevValidations'] == [] and invalid['registryReceipt']['operations'] == 0
    for reason in ('uncertain', 'unavailable', 'unsupported', 'duplicate', 'conflict'):
        value = run_bun_script(fixture, 'remember-private', env={'CL_JEV_FIXTURE': reason})
        assert value['planners'] == ['memory'] and value['jevValidations'] == ['memory'] * (2 if reason in ('uncertain', 'unsupported') else 1), value
        assert 'concise.md' not in value['privateFiles'] and not value['harnessExists']
        assert value['registryReceipt']['operations'] == 0
        assert any(a['outcome'] == 'proposed' and a['jev']['reason'] == reason
                   for a in value['registryReceipt']['attempts'] if a['phase'] == 'memory'), value
        assert value['agentsUnchanged'] and not value['lock']
    proposal = run_bun_script(fixture, 'memory-propose', env={'CL_JEV_FIXTURE': 'supported'})
    assert proposal['jevValidations'] == ['memory'] and 'concise.md' not in proposal['privateFiles']
    applied = run_bun_script(fixture, 'remember-shared', env={'CL_JEV_FIXTURE': 'supported'})
    assert applied['memoryMirrored'] and applied['registryReceipt']['operations'] == 1
    harness = run_bun_script(fixture, 'harness-propose', env={'CL_JEV_FIXTURE': 'scope-expansion'})
    assert harness['jevValidations'] == ['harness'] and not harness['harnessExists']
    receipts = [run['receipt'] for run in harness['runs'] if run.get('receipt')]
    assert receipts and receipts[-1]['operations'] == 0
    assert any(a.get('jev', {}).get('reason') == 'scope-expansion' for a in receipts[-1]['attempts'])


def test_adapter_keeps_unknown_timeouts_and_input_bounds_out_of_noop() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let calls=0;
      const fetch=async()=>{calls++;return new Response(JSON.stringify({model:'jev-1.13.0',answers:{},usage:{input_tokens:1,output_tokens:1}}))};
      const judge=createJevJudge({enabled:true,defaultModel:'jev-1.13.0',scopes:['selection','memory','harness'],apiKey:'fixture',fetch});
      const tooLarge=await judge.select('x'.repeat(70000),[],false);
      const secret=await judge.validate('memory','api_key: abcdefghijklmnop',['fact'],[]);
      const invalid=await judge.select('durable',[],false);
      const aborted=await judge.select('durable',[],false,AbortSignal.abort());
      const disabled=await createJevJudge({enabled:false,fetch}).select('durable',[],false);
      const timeout=await createJevJudge({enabled:true,defaultModel:'jev-1.13.0',scopes:['selection','memory','harness'],apiKey:'fixture',timeout:5,fetch:async(_url,init)=>new Promise((_resolve,reject)=>init.signal.addEventListener('abort',()=>reject(new Error('private timeout'))))}).validate('harness','evidence',['rule'],[]);
      console.log(JSON.stringify({tooLarge,secret,invalid,aborted,disabled,timeout,calls}));
    ''')
    assert value['tooLarge']['telemetry']['reason'] == 'bounds'
    assert value['secret']['telemetry']['reason'] == 'sensitive'
    assert value['invalid']['telemetry']['reason'] == 'invalid-response'
    assert value['invalid']['telemetry']['model'] == 'jev-1.13.0'
    assert value['invalid']['telemetry']['inputTokens'] == 1
    assert value['aborted']['telemetry']['reason'] == 'cancelled'
    assert value['disabled']['telemetry']['status'] == 'disabled'
    assert value['timeout']['telemetry']['reason'] == 'timeout' and value['timeout']['decision'] == 'propose'
    assert value['calls'] == 1


def test_selector_fallback_and_empty_index_do_not_send_jev_or_drop_memory() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import {execFileSync} from 'node:child_process';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'cl-jev-selector-'));
      try {
        const cwd=path.join(root,'project');fs.mkdirSync(cwd);execFileSync('git',['init','-q',cwd]);
        let legacyCalls=0,jevCalls=0;
        const kit=await import('./packages/kit/src/index.ts');
        mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async({prompt})=>{
          legacyCalls++;return {exitCode:0,stderr:'',text:JSON.stringify({kind:'incremental-memory-selection',version:1,
            contextDigest:'frozen',selected:[],memory:false,harness:true,agents:true,reason:'legacy'})};
        }}));
        const {selectIncrementalLearning}=await import('./packages/continual-learning/extensions/incremental-learning.ts');
        const jevJudge={enabled:true,select:async()=>{jevCalls++;return {selection:null,telemetry:{stage:'selection',status:'fallback',reason:'unavailable',durationMs:2}}}};
        const input={cwd,taskSlice:{kind:'learning-task-slice',version:1,entries:[{message:{role:'user',content:'Remember this preference.'}}]},
          contextDigest:'frozen',outputDir:path.join(root,'out'),memoryOnly:true,allowEmptyIndexRouting:true,jevJudge};
        const cold=await selectIncrementalLearning(input);
        const before={jevCalls,legacyCalls};
        fs.mkdirSync(path.join(cwd,'.memory'));fs.writeFileSync(path.join(cwd,'.memory','known.md'),'---\nname: known\ndescription: Project fact\ntype: project\n---\nExisting body\n');
        const fallback=await selectIncrementalLearning(input);
        console.log(JSON.stringify({cold,before,fallback,jevCalls,legacyCalls}));
      } finally {fs.rmSync(root,{recursive:true,force:true})}
    ''')
    assert value['before'] == {'jevCalls': 0, 'legacyCalls': 0}
    assert value['cold']['selection']['memory']
    assert value['fallback']['selection']['memory'] and not value['fallback']['selection']['harness']
    assert not value['fallback']['selection']['agents']
    assert value['jevCalls'] == value['legacyCalls'] == 1
    assert value['fallback']['jev']['reason'] == 'unavailable'
    assert 'legacy selector' in value['fallback']['diagnostic']


def test_unified_config_or_environment_key_enables_jev_with_explicit_disable() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      delete process.env.TYPESAFE_API_KEY;
      let calls=0;const fetch=async()=>{calls++;throw new Error('should not be called')};
      const absent=await createJevJudge({fetch}).select('evidence',[],false);
      process.env.TYPESAFE_API_KEY='fixture';
      const environment=await createJevJudge({fetch}).select('evidence',[],false);
      fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json'),JSON.stringify({jev:{model:'jev-1.13.0',scopes:['harness']}}));
      const scoped=createJevJudge({fetch});
      const selection=await scoped.select('evidence',[],false);
      const memory=await scoped.validate('memory','evidence',['candidate'],[]);
      const privateMemory=await scoped.validate('harness','evidence',['rule'],[{name:'private.md',classification:'private',type:'feedback',description:'Private preference',content:'Private body'}]);
      fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json'),JSON.stringify({jev:{model:'jev-1.13.0',scopes:['write-files']}}));
      const invalid=await createJevJudge({fetch}).select('evidence',[],false);
      fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json'),JSON.stringify({jev:false}));
      const disabled=await createJevJudge({fetch}).select('evidence',[],false);
      console.log(JSON.stringify({absent,environment,selection,memory,privateMemory,invalid,disabled,calls}));
    ''')
    # Justification: the environment-key case is the only reachable request, and
    # its connection-level failure is now retried once, so one reachable failure
    # costs two attempts. Every other case still makes zero requests.
    assert value['calls'] == 2
    assert value['absent']['telemetry']['reason'] == 'missing-config'
    assert value['environment']['telemetry']['reason'] == 'unavailable'
    assert value['disabled']['telemetry']['reason'] == 'disabled'
    assert value['selection']['telemetry']['reason'] == value['memory']['telemetry']['reason'] == 'scope-denied'
    assert value['privateMemory']['telemetry']['reason'] == 'private-memory-denied'
    assert value['invalid']['telemetry']['reason'] == 'invalid-config'


def test_semantic_selection_can_find_opportunities_missed_by_keyword_screen() -> None:
    from pathlib import Path
    from support import run_bun_script
    fixture = Path(__file__).with_name('learning-policy-harness.ts')
    value = run_bun_script(fixture, 'semantic-opportunity', env={'CL_JEV_FIXTURE': 'discover'})
    assert value['selectors'] == 0 and value['planners'] == ['memory'], value
    assert value['jevValidations'] == ['memory']
    assert not value['harnessExists'] and 'concise.md' not in value['privateFiles']


def test_credentials_are_checked_before_json_encoding_or_any_external_request() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let calls=0;
      const judge=createJevJudge({enabled:true,defaultModel:'jev-1.13.0',scopes:['selection','memory','harness'],apiKey:'fixture',
        fetch:async()=>{calls++;throw new Error('Must not send');}});
      const results=[];
      for (const evidence of ['password\n=\nopaquecredential123456789',
        {entries:[{message:{role:'toolResult',content:'{"password":"opaquecredential123456789"}'}}]},
        {entries:[{message:{role:'toolResult',content:{api_key:'opaquecredential123456789'}}}]}]) {
        results.push(await judge.select(evidence,[],false));
      }
      results.push(await judge.validate('memory','Public evidence',[{content:'password\n=\nopaquecredential123456789'}],[]));
      console.log(JSON.stringify({calls,reasons:results.map(r=>r.telemetry.reason)}));
    ''')
    assert value['calls'] == 0
    assert value['reasons'] == ['sensitive'] * 4


def test_unified_jev_section_supplies_auth_model_and_scope_without_environment() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      delete process.env.TYPESAFE_API_KEY;
      const file=path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json');
      const raw=JSON.stringify({memory:{other:'preserve'},jev:{model:'jev-latest',scopes:['memory'],apiKey:'fixture'}});
      fs.writeFileSync(file,raw);
      let calls=0,requestedModel;
      const fetch=async(_url,init)=>{calls++;const q=JSON.parse(init.body);requestedModel=q.model;
        return new Response(JSON.stringify({model:'jev-1.13.0',answers:{supported_0:{type:'choice',choice:'grounded',confidence:0.99,probabilities:{grounded:1,speculative:0,transient:0,unsupported:0,unclear:0}}},usage:{input_tokens:10,output_tokens:1}}));};
      const judge=createJevJudge({fetch});
      const denied=await judge.select('Public evidence',[],false);
      const allowed=await judge.validate('memory','Public evidence',[{content:'Public fact'}],[]);
      const unchanged=fs.readFileSync(file,'utf8')===raw;
      fs.writeFileSync(file,JSON.stringify({jev:{enabled:false}}));
      process.env.TYPESAFE_API_KEY='fixture';
      const disabled=await createJevJudge({fetch}).select('Public evidence',[],false);
      console.log(JSON.stringify({calls,requestedModel,denied,allowed,disabled,unchanged}));
    ''')
    assert value['calls'] == 1 and value['requestedModel'] == 'jev-latest'
    assert value['denied']['telemetry']['reason'] == 'scope-denied'
    assert value['allowed']['decision'] == 'allow'
    assert value['allowed']['telemetry']['model'] == 'jev-1.13.0'
    assert value['disabled']['telemetry']['reason'] == 'disabled'

    assert value['unchanged'] is True


def test_adjacent_relevance_levels_share_one_decision_and_semantic_content_excludes_bookkeeping() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const calls=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const request=JSON.parse(init.body);calls.push(request);
        const answers={};for(const [key,q] of Object.entries(request.questions)) {
          answers[key]=key.startsWith('expands')?{type:'choice',choice:'same',confidence:0.99,probabilities:{same:1,narrower:0,broader:0,unclear:0}}:q.type==='choice'?{type:'choice',choice:'grounded',confidence:0.99,probabilities:{grounded:1,speculative:0,transient:0,unsupported:0,unclear:0}}:q.type==='score'?{type:'score',score:2.44,confidence:0.44,legend:{0:'Unrelated',1:'Generic',2:'Useful',3:'Direct'},probabilities:{0:0.01,1:0.09,2:0.36,3:0.54}}:{type:'noul',noul:key.startsWith('expands')?0.01:0.99};
        }
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:10,output_tokens:1}}));
      }});
      const selected=await judge.select('Project fact',[{name:'known.md',classification:'safe',type:'project',description:'Related fact'}],false);
      await judge.validate('memory','The project uses pnpm.',[{name:'candidate.md',content:'---\nname: candidate\ndescription: Administrative label\ntype: project\n---\nThe project uses pnpm.',evidence:[{index:0,quote:'The project uses pnpm.'}]}],[]);
      await judge.validate('harness','Never push',[{op:'addRule',rule:{id:'rule',tool:'bash',commandPattern:'git push'},cases:{positive:[{bash:'git push production'}]}}],[]);
      await judge.validate('memory','Updated command',[{kind:'rewrite',name:'known.md',preservedIn:['archive.md'],observations:['Updated command'],content:'Updated command'}],[]);
      const secret=await judge.validate('memory','public',[{content:'Public fact',password:'opaquecredential123456789'}],[]);
      console.log(JSON.stringify({selected,requests:calls,secret}));
    ''')
    assert value['selected']['selection']['selected'] == ['known.md']
    memory_question = value['requests'][1]['questions']['supported_0']['instructions']
    assert memory_question['candidate']['content'] == 'The project uses pnpm.'
    assert 'evidence' not in memory_question['candidate']
    harness_question = value['requests'][2]['questions']['supported_0']['instructions']
    assert 'cases' not in harness_question['candidate']
    assert harness_question['candidate']['behaviorExamples']['blocked'][0]['bash'] == 'git push production'
    assert value['secret']['telemetry']['reason'] == 'sensitive'
    rewrite = value['requests'][3]['questions']['supported_0']['instructions']['candidate']
    assert rewrite['action'] == 'rewrite' and rewrite['target'] == 'known.md'
    assert rewrite['preservedIn'] == ['archive.md'] and rewrite['observations'] == ['Updated command']
    assert 'current project shared Harness layer' in value['requests'][2]['state']
    assert len(value['requests']) == 4


def test_compatible_choice_probability_mass_does_not_reject_grounded_knowledge() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async()=>new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:{supported_0:{type:'choice',choice:'grounded',confidence:0.97,probabilities:{grounded:0.98,speculative:0,transient:0,unsupported:0.02,unclear:0}},relation_0:{type:'choice',choice:'supplement',confidence:0.59,probabilities:{unrelated:0.32,supplement:0.68,duplicate:0,conflict:0,unclear:0}}}}))});
      console.log(JSON.stringify(await judge.validate('memory','Verified command',[{content:'Verified command'}],[{name:'known.md',classification:'safe',type:'project',description:'Dependency manager',content:'Uses pnpm'}])));
    ''')
    assert value['decision'] == 'allow'


def test_exact_command_scope_is_proved_in_code_but_authorization_stays_semantic() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let calls=[];let supported=true;
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const request=JSON.parse(init.body);calls.push(request);const answers={};
        for(const key of Object.keys(request.questions)) answers[key]=key.startsWith('expands')?{type:'choice',choice:'unclear',confidence:0.99,probabilities:{same:0,narrower:0,broader:0,unclear:1}}:key.startsWith('explanation')?{type:'choice',choice:'faithful',confidence:0.99,probabilities:{faithful:1,extra:0,invented:0,unclear:0}}:key.startsWith('authority')?{type:'choice',choice:supported?'lasting':'conditional',confidence:0.99,probabilities:{lasting:supported?0.99:0.01,conditional:supported?0.01:0.99,temporary:0,elsewhere:0,absent:0}}:{type:'noul',noul:key.startsWith('expands')?0.2:supported?0.99:0.01};
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:10,output_tokens:1}}));
      }});
      const op=(bash)=>({op:'addRule',rule:{id:'r',bash,action:'block',message:'Never execute the forbidden command.'},cases:{positive:[{bash:'printf SAMPLE'}],negative:[{bash:'printf ALLOWED'}]}});
      const exact=await judge.validate('harness','Never run printf SAMPLE in future tasks in this project.',[op('^printf SAMPLE$(?![\\s\\S])')],[]);
      supported=false;
      const conditional=await judge.validate('harness','Do not run printf SAMPLE without approval.',[op('^printf SAMPLE$(?![\\s\\S])')],[]);
      const temporary=await judge.validate('harness','Only for this task, do not run printf SAMPLE.',[op('^printf SAMPLE$(?![\\s\\S])')],[]);
      supported=true;
      const patterns=['printf SAMPLE','^printf.*$','^printf (SAMPLE|OTHER)$','^printf SAMPLE\\s+.*$','^printf SAMPLE$|echo','^printf SAMPLE\\n.*$'];
      const complex=[];for(const p of patterns)complex.push(await judge.validate('harness','Never run printf SAMPLE.',[op(p)],[]));
      console.log(JSON.stringify({exact,conditional,temporary,complex,calls}));
    ''')
    assert value['exact']['decision'] == 'allow'
    assert value['conditional']['decision'] == value['temporary']['decision'] == 'propose'
    assert all(v['decision'] == 'propose' for v in value['complex'])
    assert list(value['calls'][0]['questions']) == ['authority_0', 'explanation_0']
    meaning = value['calls'][0]['questions']['authority_0']['instructions']['candidate']
    assert meaning['command'] == 'printf SAMPLE'
    assert meaning['action'] == 'block' and meaning['scope'] == 'current project, lasting'


def test_literal_authority_does_not_skip_message_or_unicode_scope() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const requests=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const r=JSON.parse(init.body);requests.push(r);const answers={};
        for(const [key,q] of Object.entries(r.questions))answers[key]=key.startsWith('expands')?{type:'choice',choice:'broader',confidence:0.99,probabilities:{same:0,narrower:0,broader:1,unclear:0}}:key.startsWith('explanation')?{type:'choice',choice:'extra',confidence:0.99,probabilities:{faithful:0,extra:1,invented:0,unclear:0}}:q.type==='choice'?{type:'choice',choice:'lasting',confidence:0.99,probabilities:{lasting:1,conditional:0,temporary:0,elsewhere:0,absent:0}}:{type:'noul',noul:key.startsWith('expands')?0.99:r.questions.authority_0?0.01:0.99};
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:10,output_tokens:1}}));
      }});
      const candidate=(bash,message)=>({op:'addRule',rule:{id:'r',bash,action:'block',message}});
      const unsafe=await judge.validate('harness','Never run printf SAMPLE.',[candidate('^printf SAMPLE\\s*$','Do not run this command.')],[]);
      const broadMessage=await judge.validate('harness','Never run printf SAMPLE.',[candidate('^printf SAMPLE$(?![\\s\\S])','Never use any printf command or request approval.')],[]);
      const weakEnd=await judge.validate('harness','Never run printf SAMPLE.',[candidate('^printf SAMPLE$','Do not run this command.')],[]);
      console.log(JSON.stringify({unsafe,broadMessage,weakEnd,requests}));
    ''')
    assert value['unsafe']['decision'] == value['broadMessage']['decision'] == value['weakEnd']['decision'] == 'propose'
    assert value['unsafe']['telemetry']['reason'] == value['weakEnd']['telemetry']['reason'] == 'scope-expansion'
    assert 'authority_0' not in value['requests'][0]['questions']
    assert 'authority_0' not in value['requests'][2]['questions']
    assert value['requests'][1]['questions']['explanation_0']['instructions']['candidate']['explanation'] == 'Never use any printf command or request approval.'


def test_literal_authority_classes_and_unknowns_are_proposals() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let kind='lasting';let confidence=0.99;
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async()=>new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:10,output_tokens:1},answers:{
        authority_0:{type:'choice',choice:kind,confidence,probabilities:Object.fromEntries(['lasting','conditional','temporary','elsewhere','absent'].map(k=>[k,k===kind?1:0]))},
        explanation_0:{type:'choice',choice:'faithful',confidence:0.99,probabilities:{faithful:1,extra:0,invented:0,unclear:0}}}}))});
      const candidate={op:'addRule',rule:{id:'r',bash:'^echo PUBLIC$(?![\\s\\S])',action:'block',message:'Do not execute echo PUBLIC.'}};
      const results={};for(const c of ['lasting','conditional','temporary','elsewhere','absent']){kind=c;results[c]=await judge.validate('harness','Public source',[candidate],[]);}
      kind='lasting';confidence=0.4;results.unknown=await judge.validate('harness','Public source',[candidate],[]);
      console.log(JSON.stringify(results));
    ''')
    assert value['lasting']['decision'] == 'allow'
    for kind in ('conditional', 'temporary', 'elsewhere', 'absent'):
        assert value[kind]['decision'] == 'propose' and value[kind]['telemetry']['reason'] == 'unsupported'
    assert value['unknown']['decision'] == 'propose' and value['unknown']['telemetry']['reason'] == 'uncertain'


def test_memory_grounding_uses_explicit_evidence_categories() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let category='grounded';const requests=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        requests.push(JSON.parse(init.body));return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:10,output_tokens:1},answers:{supported_0:{type:'choice',choice:category,confidence:0.99,probabilities:Object.fromEntries(['grounded','speculative','transient','unsupported','unclear'].map(k=>[k,k===category?1:0]))}}}));
      }});
      const results={};for(const c of ['grounded','speculative','transient','unsupported','unclear']){category=c;results[c]=await judge.validate('memory','Public facts',[{content:'The project uses uv.'}],[]);}
      console.log(JSON.stringify({results,requests}));
    ''')
    assert value['results']['grounded']['decision'] == 'allow'
    assert all(value['results'][k]['decision'] == 'propose' for k in ('speculative','transient','unsupported','unclear'))
    assert value['requests'][0]['questions']['supported_0']['type'] == 'choice'


def test_generic_harness_scope_groups_same_and_narrower_without_allowing_broadening() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let broad=false;
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async()=>new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:10,output_tokens:1},answers:{
        supported_0:{type:'noul',noul:0.99},expands_0:{type:'choice',choice:broad?'broader':'same',confidence:broad?0.99:0.61,probabilities:{same:broad?0:0.7,narrower:broad?0:0.28,broader:broad?1:0.01,unclear:broad?0:0.01}}}}))});
      const candidate={op:'addRule',rule:{id:'r',bash:'^git\\s+push(?:\\s|$)',action:'block',message:'Do not push in this repository.'}};
      const narrow=await judge.validate('harness','Never push in future tasks in this repository.',[candidate],[]);
      broad=true;const expanded=await judge.validate('harness','Never push only to production without approval.',[candidate],[]);
      console.log(JSON.stringify({narrow,expanded}));
    ''')
    assert value['narrow']['decision'] == 'allow'
    assert value['expanded']['decision'] == 'propose' and value['expanded']['telemetry']['reason'] == 'scope-expansion'


def test_command_family_proof_preserves_exact_only_authority_and_shell_boundaries() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let requests=[],scope='authorized';
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const request=JSON.parse(init.body);requests.push(request);const answers={};
        for(const [key,q] of Object.entries(request.questions)){
          if(q.type==='noul'){answers[key]={type:'noul',noul:0.5};continue}
          const selected=key.startsWith('authority')?'lasting':key.startsWith('explanation')?'faithful':key.startsWith('family')?scope:'unclear';
          answers[key]={type:'choice',choice:selected,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===selected?1:0]))};
        }
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:10,output_tokens:3}}));
      }});
      const candidate={op:'addRule',rule:{bash:'^git[ \\t]+push(?:[ \\t]|$(?![\\s\\S]))',action:'block',message:'Do not push from this repository.'}};
      const evidence={entries:[{message:{role:'user',content:'Never run git push in this project.'}}]};
      const allowed=await judge.validate('harness',evidence,[candidate],[]);
      scope='extra';const exact=await judge.validate('harness',{entries:[{message:{role:'user',content:'Never run exactly git push; arguments are permitted.'}}]},[candidate],[]);
      const broad=await judge.validate('harness',evidence,[{...candidate,rule:{...candidate.rule,bash:'^git\\s+push(?:\\s|$)'}}],[]);
      scope='authorized';const weakEnd=await judge.validate('harness',evidence,[{...candidate,rule:{...candidate.rule,bash:'^git[ \\t]+push(?:[ \\t]|$)'}}],[]);
      console.log(JSON.stringify({allowed,exact,broad,weakEnd,questions:Object.keys(requests[0].questions),command:requests[0].questions.authority_0?.instructions?.candidate?.command}));
    ''')
    assert value['allowed']['decision'] == 'allow'
    assert value['exact']['decision'] == 'propose'
    assert value['broad']['decision'] == 'propose'
    assert value['command'] == 'git push'
    assert value['questions'] == ['authority_0', 'explanation_0', 'family_0']

    assert value['weakEnd']['decision'] == 'propose'


def test_equivalent_metadata_format_repair_retains_grounding_and_privacy_checks() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let requests=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const request=JSON.parse(init.body);requests.push(request);const answers={};
        for(const [key,q] of Object.entries(request.questions)){
          const selected=key.startsWith('supported')?'grounded':'duplicate';
          answers[key]={type:'choice',choice:selected,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===selected?1:0]))};
        }
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:10,output_tokens:3}}));
      }});
      const content='---\nname: test\ndescription: Verified test command\n  type: project\n---\nUse pnpm test.\n';
      const old={name:'test.md',classification:'safe',type:'',description:'Verified test command',content};
      const candidate={kind:'rewrite',name:'test.md',classification:'safe',content:content.replace('  type:','type:')};
      const evidence={entries:[{message:{role:'user',content:'The verified project test command is pnpm test.'}}]};
      const format=await judge.validate('memory',evidence,[candidate],[old]);
      const body=await judge.validate('memory',evidence,[{...candidate,content:candidate.content.replace('Use pnpm','Always use pnpm')}],[old]);
      const metadata=await judge.validate('memory',evidence,[{...candidate,content:candidate.content.replace('Verified test command','A different claim')}],[old]);
      const privacy=await judge.validate('memory',evidence,[{...candidate,classification:'private'}],[old]);
      const unchanged=await judge.validate('memory',evidence,[{...candidate,content}],[old]);
      const degraded=await judge.validate('memory',evidence,[{...candidate,content}],[{...old,content:candidate.content}]);
      console.log(JSON.stringify({format,body,metadata,privacy,unchanged,degraded,questions:requests.map(r=>Object.keys(r.questions))}));
    ''')
    assert value['format']['decision'] == 'allow'
    assert value['body']['decision'] == value['metadata']['decision'] == value['privacy']['decision'] == 'propose'
    assert value['questions'][0] == ['supported_0', 'supported_description_0']
    assert value['questions'][1] == value['questions'][2] == ['supported_0', 'relation_0', 'supported_description_0', 'relation_description_0']

    assert value['unchanged']['decision'] == value['degraded']['decision'] == 'propose'


def test_literal_confirmation_judges_per_run_authority_without_weakening_a_ban() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let authority='lasting';let explanation='faithful';const questions=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const request=JSON.parse(init.body);questions.push(Object.keys(request.questions));const answers={};
        for(const [key,q] of Object.entries(request.questions)){
          if(q.type==='noul')answers[key]={type:'noul',noul:.71};
          else{
            const selected=key.startsWith('authority')?authority:key.startsWith('explanation')?explanation:'narrower';
            answers[key]={type:'choice',choice:selected,confidence:key.startsWith('expands')?.56:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===selected?1:0]))};
          }
        }
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:10,output_tokens:2}}));
      }});
      const evidence={entries:[{message:{role:'user',content:'For future tasks, this exact command requires my explicit approval before every run.'}}]};
      const candidate={op:'addRule',rule:{id:'confirm',bash:'^printf APPROVAL$(?![\\s\\S])',action:'confirm',message:'This exact command requires explicit approval before each run.'}};
      const good=await judge.validate('harness',evidence,[candidate],[]);
      authority='blocked';const ban=await judge.validate('harness',evidence,[candidate],[]);
      authority='absent';const oneTime=await judge.validate('harness',evidence,[candidate],[]);
      authority='temporary';const temporary=await judge.validate('harness',evidence,[candidate],[]);
      authority='conditional';const scoped=await judge.validate('harness',evidence,[candidate],[]);
      authority='lasting';explanation='extra';const extra=await judge.validate('harness',evidence,[candidate],[]);
      console.log(JSON.stringify({good,ban,oneTime,temporary,scoped,extra,questions}));
    ''')
    assert value['good']['decision'] == 'allow'
    assert value['questions'][0] == ['authority_0', 'explanation_0']
    for key in ('ban', 'oneTime', 'temporary', 'scoped', 'extra'):
        assert value[key]['decision'] == 'propose'
    assert value['extra']['telemetry']['candidateIndex'] == 0
    assert value['extra']['telemetry']['dimension'] == 'explanation'
    assert value['ban']['telemetry']['dimension'] == 'authority'


def test_semantic_memory_repair_uses_one_shared_slot_and_rechecks_privacy() -> None:
    from pathlib import Path
    from support import run_bun_script
    fixture = Path(__file__).with_name('learning-policy-harness.ts')
    accepted = run_bun_script(fixture, 'remember-shared', env={'CL_JEV_FIXTURE': 'repair-supported'})
    assert accepted['semanticRepairs'] == 1 and accepted['receivedFailureHints']
    assert accepted['jevValidations'] == ['memory', 'memory']
    assert accepted['memoryMirrored'] and accepted['registryReceipt']['operations'] == 1
    attempts = [a for a in accepted['registryReceipt']['attempts'] if a['phase'] == 'memory']
    assert [a['outcome'] for a in attempts] == ['proposed', 'applied']
    assert [a['jev']['reason'] for a in attempts] == ['uncertain', 'supported']
    denied = run_bun_script(fixture, 'remember-shared', env={'CL_JEV_FIXTURE': 'repair-private'})
    assert denied['semanticRepairs'] == 1 and denied['jevValidations'] == ['memory']
    assert not denied['memoryMirrored'] and denied['registryReceipt']['operations'] == 0
    assert any(a['outcome'] == 'proposed' for a in denied['registryReceipt']['attempts'])
    for reason in ('unavailable', 'timeout', 'duplicate', 'conflict'):
        held = run_bun_script(fixture, 'remember-shared', env={'CL_JEV_FIXTURE': reason})
        assert held['semanticRepairs'] == 0 and held['jevValidations'] == ['memory']
        assert not held['memoryMirrored']


def test_semantic_memory_repair_guards_shared_quota_retention_and_frozen_state() -> None:
    from pathlib import Path
    from support import run_bun_script
    fixture = Path(__file__).with_name('learning-policy-harness.ts')
    structural = run_bun_script(fixture, 'remember-shared', env={'CL_JEV_FIXTURE': 'structural-held'})
    assert structural['totalRepairs'] == 1 and structural['semanticRepairs'] == 0
    assert structural['jevValidations'] == ['memory'] and not structural['memoryMirrored']
    held = run_bun_script(fixture, 'remember-shared', env={'CL_JEV_FIXTURE': 'repair-held'})
    assert held['semanticRepairs'] == 1 and held['jevValidations'] == ['memory', 'memory']
    assert not held['memoryMirrored'] and held['registryReceipt']['operations'] == 0
    assert held['originalProposalRetained']
    cancelled = run_bun_script(fixture, 'remember-shared', env={'CL_JEV_FIXTURE': 'repair-cancel'})
    assert not cancelled['memoryMirrored'] and 'concise.md' not in cancelled['privateFiles']
    assert 'registryReceipt' not in cancelled and not cancelled['lock']  # Superseded pipeline cannot emit a completed receipt.
    for reason in ('tamper-first', 'tamper-second', 'tamper-repair', 'tamper-queue', 'tamper-dossier'):
        value = run_bun_script(fixture, 'remember-shared', env={'CL_JEV_FIXTURE': reason})
        assert not value['memoryMirrored'] and value['registryReceipt']['operations'] == 0, reason
        assert not any(c['target']['name'] == 'concise.md' for h in value['history'] if h['status'] == 'applied' for c in h['changes']), reason
        assert not any(a['outcome'] == 'proposed' for a in value['registryReceipt']['attempts'] if a['phase'] == 'memory'), reason


def test_legal_family_batch_is_atomic_bounded_and_accounts_partial_failures() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const candidates=Array.from({length:12},(_,i)=>({rule:{bash:`^git[ \\t]+op${i}(?:[ \\t]|$(?![\\s\\S]))`,action:'block',message:`Never run git op${i}.`}}));
      let mode='good', calls=[], active=0, peak=0;
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const r=JSON.parse(init.body);calls.push(r);active++;peak=Math.max(peak,active);
        await new Promise(resolve=>setTimeout(resolve,5));active--;
        if(mode==='failure' && Object.keys(r.questions).includes('family_11')) throw new Error('private provider text');
        const answers={};for(const [key,q] of Object.entries(r.questions)){
          const choice=key.startsWith('authority')?'lasting':key.startsWith('explanation')?'faithful':'authorized';
          answers[key]={type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))};
        }
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:100,output_tokens:20}}));
      }});
      const good=await judge.validate('harness','Never run any of these git commands in future project tasks.',candidates,[]);
      const goodCalls=calls;calls=[];mode='failure';
      const partial=await judge.validate('harness','Never run any of these git commands in future project tasks.',candidates,[]);
      calls=[];const sensitive=await judge.validate('harness','evidence', [...candidates.slice(0,11),{...candidates[11],rule:{...candidates[11].rule,message:'api_key: abcdefghijklmnop'}}],[]);
      const oversized=await judge.validate('harness','x'.repeat(70000),candidates,[]);
      console.log(JSON.stringify({good,partial,sensitive,oversized,goodCalls:goodCalls.map(r=>({size:Buffer.byteLength(JSON.stringify(r)),keys:Object.keys(r.questions),state:r.state})),peak,preflightCalls:calls.length}));
    ''')
    assert value['good']['decision'] == 'allow', value
    assert len(value['goodCalls']) == 2 and value['peak'] == 2
    assert all(len(c['keys']) <= 32 and c['size'] <= 64000 for c in value['goodCalls'])
    assert len({c['state'] for c in value['goodCalls']}) == 1
    assert sum(len(c['keys']) for c in value['goodCalls']) == 36
    assert value['good']['telemetry']['inputTokens'] == 200
    assert value['partial']['decision'] == 'propose'
    assert value['partial']['telemetry']['reason'] == 'unavailable'
    assert 'candidateFailures' not in value['partial']['telemetry']
    assert 'inputTokens' not in value['partial']['telemetry']
    assert value['partial']['telemetry']['knownInputTokens'] == 100
    assert value['partial']['telemetry']['completedRequests'] == 1
    assert value['preflightCalls'] == 0
    assert value['sensitive']['telemetry']['reason'] == 'sensitive'
    assert value['oversized']['telemetry']['reason'] == 'bounds'


def test_observed_score_rounding_boundary_preserves_uncertainty_not_invalid_response() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const observed=[{score:.92,probabilities:{0:.64,1:.06,2:.06,3:.24}},{score:1.06,probabilities:{0:.36,1:.32,2:.2,3:.12}},
        {score:.99,probabilities:{0:.57,1:.11,2:.06,3:.26}},{score:.64,probabilities:{0:.74,1:.06,2:.04,3:.16}}];
      let current=observed[0];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async()=>new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:551,output_tokens:53},
        answers:{memory:{type:'noul',noul:.8},harness:{type:'noul',noul:.4},related_0:{type:'score',confidence:.1,...current}}}))});
      const metadata=[{name:'known.md',classification:'safe',type:'project',description:'Public fixture'}];
      const rows=[];for(const answer of observed){current=answer;rows.push(await judge.select('public evidence',metadata,false));}
      current={...observed[0],score:2.9};const inconsistent=await judge.select('public evidence',metadata,false);
      current={score:-.01,probabilities:{0:1,1:0,2:0,3:0}};const outOfRange=await judge.select('public evidence',metadata,false);
      console.log(JSON.stringify({rows,inconsistent,outOfRange}));
    ''')
    assert all(row['telemetry']['reason'] == 'uncertain' and row['selection'] is None for row in value['rows']), value
    assert value['inconsistent']['telemetry']['reason'] == 'invalid-response'
    assert value['outOfRange']['telemetry']['reason'] == 'invalid-response'


def test_parallel_batch_never_accepts_mixed_versions_or_invalid_late_answers() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const candidates=Array.from({length:12},(_,i)=>({rule:{bash:`^git[ \\t]+op${i}(?:[ \\t]|$(?![\\s\\S]))`,action:'block',message:`Never run git op${i}.`}}));
      let mode='mixed', calls=0;
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        calls++;const r=JSON.parse(init.body),late='family_11' in r.questions,answers={};
        for(const [key,q] of Object.entries(r.questions)){
          const choice=key.startsWith('authority')?'lasting':key.startsWith('explanation')?'faithful':'authorized';
          answers[key]={type:'choice',choice,confidence:mode==='uncertain'&&late?.5:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))};
        }
        if(mode==='invalid'&&late) delete answers.family_11;
        return new Response(JSON.stringify({model:mode==='mixed'&&late?'jev-1.12.0':'jev-1.13.0',answers,usage:{input_tokens:100,output_tokens:20}}));
      }});
      const mixed=await judge.validate('harness','public evidence',candidates,[]);
      mode='invalid';const invalid=await judge.validate('harness','public evidence',candidates,[]);
      mode='uncertain';const uncertain=await judge.validate('harness','public evidence',candidates,[]);
      const before=calls;const tooMany=await judge.validate('harness','public evidence',Array(50).fill(candidates[0]),[]);
      console.log(JSON.stringify({mixed,invalid,uncertain,tooMany,extraCalls:calls-before}));
    ''')
    assert value['mixed']['decision'] == value['invalid']['decision'] == value['uncertain']['decision'] == 'propose'
    assert value['mixed']['telemetry']['reason'] == value['invalid']['telemetry']['reason'] == 'invalid-response'
    assert 'model' not in value['mixed']['telemetry']
    assert value['invalid']['telemetry']['inputTokens'] == 200
    assert value['uncertain']['telemetry']['reason'] == 'uncertain'
    assert value['tooMany']['telemetry']['reason'] == 'bounds' and value['extraCalls'] == 0


def test_realistic_frozen_tool_evidence_is_preserved_with_bounded_transport() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const evidence={entries:[{message:{role:'user',content:'The request timeout is 17 seconds.'}},
        ...Array.from({length:40},(_,i)=>({message:{role:'toolResult',toolCallId:`call${i}`,toolName:'read',isError:false,content:[{type:'text',text:'Public code observation '+i+' '+ 'a'.repeat(1000)}]}})),
        {message:{role:'user',content:'Correction: the timeout is now 31 seconds, superseding the earlier value.'}}]};
      let sent;
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        sent=JSON.parse(init.body);return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:11000,output_tokens:20},answers:{supported_0:{type:'choice',choice:'unsupported',confidence:1,
          probabilities:{grounded:0,speculative:0,transient:0,unsupported:1,unclear:0}}}}));
      }});
      const result=await judge.validate('memory',evidence,[{name:'fact.md',content:'The timeout is 17 seconds.'}],[]);
      console.log(JSON.stringify({result,retainedEqual:sent?JSON.stringify(JSON.parse(sent.state).frozenEvidence)===JSON.stringify(evidence):false,bytes:sent?Buffer.byteLength(JSON.stringify(sent)):null}));
    ''')
    assert value['retainedEqual'], value
    assert 24000 < value['bytes'] <= 64000
    assert value['result']['telemetry']['reason'] == 'unsupported'
    assert value['result']['decision'] == 'propose'


def test_transport_byte_bound_includes_sdk_model_field() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let sizes=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        sizes.push(Buffer.byteLength(init.body));const r=JSON.parse(init.body);return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.keys(r.questions).map(k=>[k,{type:'noul',noul:0}]))}));
      }});
      await judge.select('',[],false);
      const emptySize=sizes[0];sizes=[];
      const over=await judge.select('x'.repeat(64000-emptySize+20),[],false);
      const overSizes=[...sizes];sizes=[];const exact=await judge.select('x'.repeat(64000-emptySize),[],false);
      console.log(JSON.stringify({over,exact,sizes,overSizes}));
    ''')
    assert value['over']['telemetry']['reason'] == 'supported'
    assert len(value['overSizes']) == 2 and max(value['overSizes']) <= 64000
    assert value['sizes'] == [64000]
    assert value['exact']['telemetry']['reason'] == 'supported'


def test_private_memory_judgment_knows_the_parent_bound_storage_scope() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let sent;
      const judge=createJevJudge({enabled:true,apiKey:'fixture',allowPrivateMemory:true,fetch:async(_url,init)=>{sent=JSON.parse(init.body);
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:100,output_tokens:20},answers:{supported_0:{type:'choice',choice:'grounded',confidence:1,probabilities:{grounded:1,speculative:0,transient:0,unsupported:0,unclear:0}}}}));
      }});
      const result=await judge.validate('memory','For my private reports always finish with PUBLIC_SYNTHETIC_MARKER. Keep it out of project files.',
        [{name:'preference.md',kind:'preference',classification:'private',content:'Finish my reports with PUBLIC_SYNTHETIC_MARKER.'}],[]);
      console.log(JSON.stringify({result,meaning:sent.questions.supported_0.instructions.candidate}));
    ''')
    assert value['meaning'].get('storageScope') == 'Parent-validated private Memory; never mirrored to project files.'
    assert value['result']['decision'] == 'allow'


def test_delete_without_body_still_requires_knowledge_preservation_judgment() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let sent;
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{sent=JSON.parse(init.body);
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:100,output_tokens:20},answers:{supported_0:{type:'choice',choice:'unsupported',confidence:1,probabilities:{grounded:0,speculative:0,transient:0,unsupported:1,unclear:0}}}}));
      }});
      const result=await judge.validate('memory','Retain the release procedure.',[{op:'delete',name:'release.md',preservedIn:['replacement.md']}],[]);
      console.log(JSON.stringify({result,question:sent.questions.supported_0.instructions.question,candidate:sent.questions.supported_0.instructions.candidate}));
    ''')
    assert 'deletion/preservation' in value['question']
    assert 'missing content field' in value['question']
    assert value['candidate']['preservedIn'] == ['replacement.md']
    assert value['result']['decision'] == 'propose'


def test_all_candidate_failures_are_reported_without_partial_permission() -> None:
    # Given two independent failures in a fully returned batch,
    # when judging it, retain both repair locations and keep the whole plan held.
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let requests=0;
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        requests++;const request=JSON.parse(init.body);const answers={};
        for(const [key,q] of Object.entries(request.questions)){
          const selected=key==='supported_0'?'unclear':'unsupported';
          answers[key]={type:'choice',choice:selected,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===selected?1:0]))};
        }
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:10,output_tokens:2}}));
      }});
      const result=await judge.validate('memory',{entries:[{message:{role:'user',content:'Synthetic evidence'}}]},[{name:'PRIVATE-NAME-A.md',content:'Candidate A'},{name:'PRIVATE-NAME-B.md',content:'Candidate B'}],[]);
      console.log(JSON.stringify({result,requests}));
    ''')
    assert value['result']['decision'] == 'propose'
    assert value['requests'] == 1
    telemetry = value['result']['telemetry']
    assert telemetry['reason'] == 'uncertain' and telemetry['candidateIndex'] == 0
    assert telemetry['candidateFailures'] == [
        # Justification: a held dimension must record its controlled label and the
        # chosen probability, so a threshold artefact is distinguishable from a
        # classification artefact. The fields stay controlled vocabulary and
        # numbers, so no model prose or private name enters the receipt.
        {'candidateIndex': 0, 'dimension': 'support', 'reason': 'uncertain', 'choice': 'unclear', 'probability': 1, 'confidence': 1},
        {'candidateIndex': 1, 'dimension': 'support', 'reason': 'unsupported', 'choice': 'unsupported', 'probability': 1, 'confidence': 1},
    ]
    assert 'PRIVATE-NAME' not in str(telemetry)


def test_all_failure_hints_fit_existing_repair_limits() -> None:
    value = isolated_run_bun(r'''
      import {jevRepairFailureHints} from './packages/continual-learning/extensions/jev-learning.ts';
      const candidateFailures=Array.from({length:128},(_,candidateIndex)=>({candidateIndex,dimension:'counterevidence',reason:'scope-expansion'}));
      const hints=jevRepairFailureHints({stage:'memory',status:'propose',reason:'uncertain',durationMs:0,candidateFailures});
      console.log(JSON.stringify({hints,maximum:Math.max(...hints.map(x=>x.length))}));
    ''')
    assert len(value['hints']) + 1 <= 16 and value['maximum'] <= 400
    assert all(f'{index}:counterevidence:scope-expansion' in ','.join(value['hints']) for index in range(128))


def test_proven_finite_git_matching_is_separate_from_support_and_authorization() -> None:
    # Given the exact researched grammar, when production reviews it, only
    # scope/counter receive the proven syntax description; support stays exact.
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const sample=(await Bun.file('./packages/continual-learning/tests/fixtures/jev-harness-support-corpus.json').json())[0];
      const requests=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',defaultModel:'jev-1.13.0',scopes:['harness'],fetch:async(_url,init)=>{
        const r=JSON.parse(String(init.body));requests.push(r);const answers={};
        for(const [key,q] of Object.entries(r.questions)) {
          if(q.type==='noul') answers[key]={type:'noul',noul:.99};
          else {const label=key.startsWith('counter')?'compatible':'same';answers[key]={type:'choice',choice:label,confidence:.99,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===label?1:0]))};}
        }
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
      }});
      const original=JSON.stringify(sample);
      const verdict=await judge.validate('harness',sample.snapshot,sample.plan.operations,[],undefined,sample.plan.evidence);
      const questions=Object.assign({},...requests.map(r=>r.questions));
      const unknown=structuredClone(sample);unknown.plan.operations[0].rule.bash+='|.*';requests.length=0;
      await judge.validate('harness',unknown.snapshot,unknown.plan.operations,[],undefined,unknown.plan.evidence);
      const unknownQuestions=Object.assign({},...requests.map(r=>r.questions));
      const skipped=[];
      for(const mode of ['disabled','replace']) {
        const changed=structuredClone(sample);if(mode==='disabled')changed.plan.operations[0].rule.enabled=false;else changed.plan.operations[0].op='replaceRule';
        requests.length=0;await judge.validate('harness',changed.snapshot,changed.plan.operations,[],undefined,changed.plan.evidence);
        skipped.push(Object.assign({},...requests.map(r=>r.questions)));
      }
      console.log(JSON.stringify({questions,unknownQuestions,skipped,verdict,inputUnchanged:original===JSON.stringify(sample)}));
    ''')
    assert value['inputUnchanged']
    questions = value['questions']
    assert 'bash' in questions['supported_0']['instructions']['candidate']['rule']
    for key in ('expands_0', 'counter_0_0'):
        rule = questions[key]['instructions']['candidate']['rule']
        assert 'bash' not in rule and 'matching' in rule
        assert rule['action'] == 'block'
    assert 'bash' in value['unknownQuestions']['expands_0']['instructions']['candidate']['rule']
    assert 'bash' in value['unknownQuestions']['counter_0_0']['instructions']['candidate']['rule']
    for questions in value['skipped']:
        assert 'bash' in questions['expands_0']['instructions']['candidate']['rule']
        assert 'bash' in questions['counter_0_0']['instructions']['candidate']['rule']


def test_finite_git_proof_never_bypasses_semantic_holds_or_service_failure() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const sample=(await Bun.file('./packages/continual-learning/tests/fixtures/jev-harness-support-corpus.json').json())[0];
      const outcomes=[];
      for(const action of ['block','confirm']) for(const mode of ['supported','unsupported','uncertain','scope','counter','unavailable']) {
        const plan=structuredClone(sample.plan);plan.operations[0].rule.action=action;
        const judge=createJevJudge({enabled:true,apiKey:'fixture',defaultModel:'jev-1.13.0',scopes:['harness'],fetch:async(_url,init)=>{
          if(mode==='unavailable')throw Error('fixture service unavailable');
          const r=JSON.parse(String(init.body));const answers={};
          for(const [key,q] of Object.entries(r.questions)) {
            if(q.type==='noul') answers[key]={type:'noul',noul:mode==='unsupported'?.01:mode==='uncertain'?.5:.99};
            else {const label=key.startsWith('counter')?(mode==='counter'?'contradicts':'compatible'):(mode==='scope'?'broader':'same');answers[key]={type:'choice',choice:label,confidence:.99,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===label?1:0]))};}
          }
          return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
        }});
        outcomes.push({action,mode,...await judge.validate('harness',sample.snapshot,plan.operations,[],undefined,plan.evidence)});
      }
      console.log(JSON.stringify(outcomes));
    ''')
    for row in value:
        if row['mode'] == 'supported':
            assert row['decision'] == 'allow'
        else:
            assert row['decision'] == 'propose'
            assert row['telemetry']['reason'] != 'supported'


def test_http_failures_keep_only_trusted_status_and_preserve_proposal() -> None:
    # Given an SDK HTTP failure, When judging a candidate, Then a numeric
    # status diagnoses unavailability without raw error text or authorization.
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const rows=[];
      for(const status of [400,401,403,429,500,503]){
        const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async()=>new Response(JSON.stringify({error:'PRIVATE_DIAGNOSTIC_DO_NOT_LOG'}),{status})});
        rows.push({status,result:await judge.validate('memory','evidence',['candidate'],[])});
      }
      const generic=createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async()=>{throw Object.assign(new Error('PRIVATE_DIAGNOSTIC_DO_NOT_LOG'),{status:429});}});
      const unknown=await generic.validate('memory','evidence',['candidate'],[]);
      const selection=await createJevJudge({enabled:true,apiKey:'fixture',scopes:['selection'],fetch:async()=>new Response('PRIVATE_DIAGNOSTIC_DO_NOT_LOG',{status:429})}).select('For future tasks remember this project fact.',[],true);
      console.log(JSON.stringify({rows,unknown,selection}));
    ''')
    for row in value['rows']:
        assert row['result']['decision'] == 'propose'
        assert row['result']['telemetry']['reason'] == 'unavailable'
        assert row['result']['telemetry']['httpStatus'] == row['status']
        assert row['result']['telemetry']['completedRequests'] == 0
    assert value['unknown']['decision'] == 'propose'
    assert 'httpStatus' not in value['unknown']['telemetry']
    assert value['selection']['selection'] is None
    assert value['selection']['telemetry']['status'] == 'fallback'
    assert value['selection']['telemetry']['httpStatus'] == 429
    assert 'PRIVATE_DIAGNOSTIC' not in str(value)


def test_http_status_survives_split_and_cited_partial_failures() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let kind='split';
      const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory','harness'],fetch:async(_url,init)=>{
        const r=JSON.parse(String(init.body));
        if((kind==='split'&&Object.hasOwn(r.questions,'family_11'))||(kind==='cited'&&Object.hasOwn(r.questions,'counter_0_1')))
          return new Response('PRIVATE_DIAGNOSTIC_DO_NOT_LOG',{status:503});
        const answers={};for(const [key,q]of Object.entries(r.questions)){
          if(q.type==='noul')answers[key]={type:'noul',noul:.99};else{
            const label=['lasting','faithful','authorized','grounded','compatible','same'].find(x=>Object.hasOwn(q.criteria,x));
            answers[key]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};
          }
        }return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:100,output_tokens:20}}));
      }});
      const candidates=Array.from({length:12},(_,i)=>({rule:{bash:`^git[ \\t]+op${i}(?:[ \\t]|$(?![\\s\\S]))`,action:'block',message:`Never run git op${i}.`}}));
      const split=await judge.validate('harness','Never run these commands in future project work.',candidates,[]);
      kind='cited';const quote='For future work, this project uses pnpm test.';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:quote},{role:'user',content:'context '+ 'x'.repeat(17000)},{role:'toolResult',content:'context '+ 'x'.repeat(17000)}]};
      const candidate={name:'fact.md',kind:'project',classification:'safe',content:'---\nname: Fact\ndescription: This project uses pnpm test\ntype: project\n---\n'+quote,evidence:[{index:0,quote,role:'user'}]};
      const cited=await judge.validate('memory',snapshot,[candidate],[]);
      console.log(JSON.stringify({split,cited}));
    ''')
    for key in ('split', 'cited'):
        result = value[key]
        assert result['decision'] == 'propose', (key, result)
        assert result['telemetry']['reason'] == 'unavailable'
        assert result['telemetry']['httpStatus'] == 503
        assert result['telemetry']['completedRequests'] < result['telemetry']['requestCount']
        assert 'inputTokens' not in result['telemetry']
        assert result['telemetry']['knownInputTokens'] > 0
        assert 'candidateFailures' not in result['telemetry']
    assert 'PRIVATE_DIAGNOSTIC' not in str(value)


def test_held_candidate_records_the_controlled_choice_and_probability() -> None:
    # Given a held support judgment, When the judge reports the failure, Then the
    # telemetry records the question's own label and the chosen probability, so a
    # threshold artefact is distinguishable from a classification artefact, and
    # no model prose enters the receipt.
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const evidence={entries:[{message:{role:'user',content:'This project uses pnpm.'}}]};
      const candidate={name:'test.md',content:'Use pnpm test.'};
      const build=(choice,distribution,confidence)=>createJevJudge({enabled:true,defaultModel:'jev-1.13.0',scopes:['memory'],apiKey:'fixture',fetch:async(_url,init)=>{
        const request=JSON.parse(init.body);const answers={};
        for(const [key,q] of Object.entries(request.questions)){
          if(q.type==='noul')answers[key]={type:'noul',noul:0.99};
          if(q.type==='score')answers[key]={type:'score',score:2.88,confidence:0.95,probabilities:{0:0.01,1:0.01,2:0.07,3:0.91},legend:{0:"a",1:"b",2:"c",3:"d"}};
          if(q.type==='choice'){
            if(key.startsWith('supported_')) answers[key]={type:'choice',choice,confidence,probabilities:distribution};
            else answers[key]={type:'choice',choice:'supplement',confidence:0.99,probabilities:{unrelated:0,duplicate:0,supplement:1,conflict:0,unclear:0}};
          }
        }
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:100,output_tokens:20}}));
      }});
      const subThreshold=await build('grounded',{grounded:0.85,speculative:0.10,transient:0,unsupported:0.05,unclear:0},0.99).validate('memory',evidence,[candidate],[]);
      const speculative=await build('speculative',{grounded:0.01,speculative:0.99,transient:0,unsupported:0,unclear:0},0.99).validate('memory',evidence,[candidate],[]);
      const confident=await build('grounded',{grounded:0.99,speculative:0.01,transient:0,unsupported:0,unclear:0},0.99).validate('memory',evidence,[candidate],[]);
      console.log(JSON.stringify({subThreshold,speculative,confident}));
    ''')
    assert value['confident']['decision'] == 'allow'
    sub = value['subThreshold']['telemetry']['candidateFailures'][0]
    assert value['subThreshold']['decision'] == 'propose'
    assert sub['dimension'] == 'support' and sub['reason'] == 'uncertain'
    assert sub['choice'] == 'grounded' and sub['probability'] == 0.85
    spec = value['speculative']['telemetry']['candidateFailures'][0]
    assert spec['dimension'] == 'support' and spec['reason'] == 'unsupported'
    assert spec['choice'] == 'speculative' and spec['probability'] == 0.99



def test_support_definitions_ground_a_successful_run_and_reject_a_transient_one() -> None:
    # Given the support question the judge sends for a Memory candidate, When a
    # successful tool result and a transient failure are both possible readings,
    # Then the instructions distinguish them, so a legitimate verified-observation
    # hold does not depend on a noisy probability gate alone. Measured evidence:
    # the negative transient sample was classified grounded at 0.68-0.73 while a
    # legitimate supplement sat at 0.73-0.86, so the probability cannot separate
    # the classes and the criteria must.
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / 'extensions' / 'jev-learning.ts'
    text = source.read_text(encoding='utf-8')
    assert 'A successful tool result that ran the command grounds the claim that the command works for this project' in text
    assert 'does not ground a lasting claim about the command' in text
    assert 'A successful tool result that ran the command counts as that verified observation' in text


def test_placeholder_credentials_in_tool_output_do_not_refuse_a_review() -> None:
    # Given a project tool result that contains a documentation-style placeholder
    # credential, When the judge preflights a Memory review, Then the review runs;
    # And a realistic secret in the same position still refuses, so the guard
    # keeps its strength. Measured evidence: iniconfig's own tracked source holds
    # `passwd: <password>`, which refused both of its reviews with zero requests
    # and lost both Memory and Harness learning.
    value = isolated_run_bun(r'''
      import {containsSensitiveMemoryMaterial} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const placeholderEvidence={entries:[{message:{role:'toolResult',content:'Configuration sample:\n  passwd: <password>'}}]};
      const realEvidence={entries:[{message:{role:'toolResult',content:'Configuration:\n  password = hunter2long'}}]};
      let requests=0;
      const judge=createJevJudge({enabled:true,defaultModel:'jev-1.13.0',scopes:['memory'],apiKey:'fixture',fetch:async(_url,init)=>{
        requests++;
        const request=JSON.parse(init.body);const answers={};
        for(const [key,q] of Object.entries(request.questions)){
          if(q.type==='noul')answers[key]={type:'noul',noul:0.99};
          if(q.type==='score')answers[key]={type:'score',score:2.88,confidence:0.95,probabilities:{0:0.01,1:0.01,2:0.07,3:0.91},legend:{0:"a",1:"b",2:"c",3:"d"}};
          if(q.type==='choice')answers[key]=key.startsWith('supported_')
            ?{type:'choice',choice:'grounded',confidence:0.99,probabilities:{grounded:1,speculative:0,transient:0,unsupported:0,unclear:0}}
            :{type:'choice',choice:'supplement',confidence:0.99,probabilities:{unrelated:0,duplicate:0,supplement:1,conflict:0,unclear:0}};
        }
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:10,output_tokens:2}}));
      }});
      const placeholder=await judge.validate('memory',placeholderEvidence,[{name:'fact.md',content:'Use pnpm test.'}],[]);
      const requestsAfterPlaceholder=requests;
      const real=await judge.validate('memory',realEvidence,[{name:'fact.md',content:'Use pnpm test.'}],[]);
      console.log(JSON.stringify({samples:[
        containsSensitiveMemoryMaterial('passwd: <password>'),
        containsSensitiveMemoryMaterial('password = hunter2long'),
        containsSensitiveMemoryMaterial('sk-'+'a'.repeat(20)),
        containsSensitiveMemoryMaterial('AKIA'+'B'.repeat(16)),
      ],placeholder,requestsAfterPlaceholder,real,requests}));
    ''')
    assert value['samples'] == [False, True, True, True]
    assert value['placeholder']['decision'] == 'allow'
    assert value['requestsAfterPlaceholder'] == 1
    assert value['real']['decision'] == 'propose'
    assert value['real']['telemetry']['reason'] == 'sensitive'
    assert value['requests'] == 1
