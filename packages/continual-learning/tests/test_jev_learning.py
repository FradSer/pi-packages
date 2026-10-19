from support import isolated_run_bun


def test_jev_directions_relationships_and_failures() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let calls=[];
      let mode='good';
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,defaultModel:'jev-1.13.0',scopes:['selection','memory','harness'],apiKey:'fixture',fetch:async(url,init)=>{
        const request=JSON.parse(init.body); calls.push(request);
        if(mode==='offline') throw new Error('PRIVATE PROVIDER ERROR');
        const answers={};
        for(const [key,q] of Object.entries(request.questions)) {
          if(key.startsWith('coherence_')){answers[key]={type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}};continue;}
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
        # The fixture returns the unchanged plan. Its original hold remains;
        # uncertainty does not authorize another draw of the same judgment.
        assert value['planners'] == ['memory'] and value['jevValidations'] == ['memory'], value
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
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,defaultModel:'jev-1.13.0',scopes:['selection','memory','harness'],apiKey:'fixture',fetch});
      const tooLarge=await judge.select('x'.repeat(70000),[],false);
      const secret=await judge.validate('memory','api_key: abcdefghijklmnop',['fact'],[]);
      const invalid=await judge.select('durable',[],false);
      const aborted=await judge.select('durable',[],false,AbortSignal.abort());
      const disabled=await createJevJudge({maxRequestBytes:64_000,enabled:false,fetch}).select('durable',[],false);
      const timeout=await createJevJudge({maxRequestBytes:64_000,enabled:true,defaultModel:'jev-1.13.0',scopes:['selection','memory','harness'],apiKey:'fixture',timeout:5,fetch:async(_url,init)=>new Promise((_resolve,reject)=>init.signal.addEventListener('abort',()=>reject(new Error('private timeout'))))}).validate('harness','evidence',['rule'],[]);
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
      const absent=await createJevJudge({maxRequestBytes:64_000,fetch}).select('evidence',[],false);
      process.env.TYPESAFE_API_KEY='fixture';
      const environment=await createJevJudge({maxRequestBytes:64_000,fetch}).select('evidence',[],false);
      fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json'),JSON.stringify({jev:{model:'jev-1.13.0',scopes:['harness']}}));
      const scoped=createJevJudge({maxRequestBytes:64_000,fetch});
      const selection=await scoped.select('evidence',[],false);
      const memory=await scoped.validate('memory','evidence',['candidate'],[]);
      const privateMemory=await scoped.validate('harness','evidence',['rule'],[{name:'private.md',classification:'private',type:'feedback',description:'Private preference',content:'Private body'}]);
      fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json'),JSON.stringify({jev:{model:'jev-1.13.0',scopes:['write-files']}}));
      const invalid=await createJevJudge({maxRequestBytes:64_000,fetch}).select('evidence',[],false);
      fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json'),JSON.stringify({jev:false}));
      const disabled=await createJevJudge({maxRequestBytes:64_000,fetch}).select('evidence',[],false);
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
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,defaultModel:'jev-1.13.0',scopes:['selection','memory','harness'],apiKey:'fixture',
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
        return new Response(JSON.stringify({model:'jev-1.13.0',answers:{coherence_0:{type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}},supported_0:{type:'choice',choice:'grounded',confidence:0.99,probabilities:{grounded:1,speculative:0,transient:0,unsupported:0,unclear:0}}},usage:{input_tokens:10,output_tokens:1}}));};
      const judge=createJevJudge({maxRequestBytes:64_000,fetch});
      const denied=await judge.select('Public evidence',[],false);
      const allowed=await judge.validate('memory','Public evidence',[{content:'Public fact'}],[]);
      const unchanged=fs.readFileSync(file,'utf8')===raw;
      fs.writeFileSync(file,JSON.stringify({jev:{enabled:false}}));
      process.env.TYPESAFE_API_KEY='fixture';
      const disabled=await createJevJudge({maxRequestBytes:64_000,fetch}).select('Public evidence',[],false);
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
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const request=JSON.parse(init.body);calls.push(request);
        const answers={};for(const [key,q] of Object.entries(request.questions)) {
          if(key.startsWith('coherence_')){answers[key]={type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}};continue;}
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
    assert 'source branch eligibility guards' in memory_question['question']
    assert memory_question['candidate']['content'] == 'The project uses pnpm.'
    assert 'evidence' not in memory_question['candidate']
    harness_question = value['requests'][2]['questions']['supported_0']['instructions']
    assert 'cases' not in harness_question['candidate']
    assert harness_question['candidate']['behaviorExamples']['selectorMatches'][0]['bash'] == 'git push production'
    assert value['secret']['telemetry']['reason'] == 'sensitive'
    rewrite = value['requests'][3]['questions']['supported_0']['instructions']['candidate']
    assert rewrite['action'] == 'rewrite' and rewrite['target'] == 'known.md'
    assert rewrite['preservedIn'] == ['archive.md'] and rewrite['observations'] == ['Updated command']
    assert 'current project shared Harness layer' in value['requests'][2]['state']['executionScope']
    assert len(value['requests']) == 4


def test_compatible_choice_probability_mass_does_not_reject_grounded_knowledge() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async()=>new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:{coherence_0:{type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}},supported_0:{type:'choice',choice:'grounded',confidence:0.97,probabilities:{grounded:0.98,speculative:0,transient:0,unsupported:0.02,unclear:0}},relation_0:{type:'choice',choice:'supplement',confidence:0.59,probabilities:{unrelated:0.32,supplement:0.68,duplicate:0,conflict:0,unclear:0}}}}))});
      console.log(JSON.stringify(await judge.validate('memory','Verified command',[{content:'Verified command'}],[{name:'known.md',classification:'safe',type:'project',description:'Dependency manager',content:'Uses pnpm'}])));
    ''')
    assert value['decision'] == 'allow'


def test_exact_command_scope_is_proved_in_code_but_authorization_stays_semantic() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let calls=[];let supported=true;
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
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
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
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
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async()=>new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:10,output_tokens:1},answers:{
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
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        requests.push(JSON.parse(init.body));return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:10,output_tokens:1},answers:{coherence_0:{type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}},supported_0:{type:'choice',choice:category,confidence:0.99,probabilities:Object.fromEntries(['grounded','speculative','transient','unsupported','unclear'].map(k=>[k,k===category?1:0]))}}}));
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
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async()=>new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:10,output_tokens:1},answers:{
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
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const request=JSON.parse(init.body);requests.push(request);const answers={};
        for(const [key,q] of Object.entries(request.questions)){
          if(key.startsWith('coherence_')){answers[key]={type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}};continue;}
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


def test_rewrite_still_requires_grounding_and_private_review_without_self_novelty() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let requests=[];
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const request=JSON.parse(init.body);requests.push(request);const answers={};
        for(const [key,q] of Object.entries(request.questions)){
          if(key.startsWith('coherence_')){answers[key]={type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}};continue;}
          const content=q.instructions?.candidate?.content??'';
          const selected=String(content).includes('Always use') || String(content).includes('A different claim')?'unsupported':'grounded';
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
    assert value['questions'][0] == ['coherence_0', 'supported_0', 'supported_description_0']
    assert value['questions'][1] == value['questions'][2] == ['coherence_0', 'supported_0', 'supported_description_0']
    assert value['privacy']['telemetry']['reason'] == 'private-memory-denied'

    # Parent structural validation owns malformed metadata; novelty is not that gate.
    assert value['unchanged']['decision'] == value['degraded']['decision'] == 'allow'


def test_literal_confirmation_judges_per_run_authority_without_weakening_a_ban() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let authority='lasting';let explanation='faithful';const questions=[];
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const request=JSON.parse(init.body);questions.push(Object.keys(request.questions));const answers={};
        for(const [key,q] of Object.entries(request.questions)){
          if(key.startsWith('coherence_')){answers[key]={type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}};continue;}
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


def test_semantic_memory_repair_guards_phase_quotas_retention_and_frozen_state() -> None:
    from pathlib import Path
    from support import run_bun_script
    fixture = Path(__file__).with_name('learning-policy-harness.ts')
    structural = run_bun_script(fixture, 'remember-shared', env={'CL_JEV_FIXTURE': 'structural-held'})
    assert structural['totalRepairs'] == 2 and structural['semanticRepairs'] == 1
    assert structural['jevValidations'] == ['memory', 'memory'] and not structural['memoryMirrored']
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
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const r=JSON.parse(init.body);calls.push(r);active++;peak=Math.max(peak,active);
        await new Promise(resolve=>setTimeout(resolve,5));active--;
        if(mode==='failure' && Object.keys(r.questions).includes('family_11')) throw new Error('private provider text');
        const answers={};for(const [key,q] of Object.entries(r.questions)){
          if(key.startsWith('coherence_')){answers[key]={type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}};continue;}
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
    assert len({str(c['state']) for c in value['goodCalls']}) == 1
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
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async()=>new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:551,output_tokens:53},
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
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        calls++;const r=JSON.parse(init.body),late='family_11' in r.questions,answers={};
        for(const [key,q] of Object.entries(r.questions)){
          if(key.startsWith('coherence_')){answers[key]={type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}};continue;}
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
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        sent=JSON.parse(init.body);return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:11000,output_tokens:20},answers:{coherence_0:{type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}},supported_0:{type:'choice',choice:'unsupported',confidence:1,
          probabilities:{grounded:0,speculative:0,transient:0,unsupported:1,unclear:0}}}}));
      }});
      const result=await judge.validate('memory',evidence,[{name:'fact.md',content:'The timeout is 17 seconds.'}],[]);
      console.log(JSON.stringify({result,retainedEqual:sent?JSON.stringify((typeof sent.state === "string" ? JSON.parse(sent.state) : sent.state).frozenEvidence)===JSON.stringify(evidence):false,bytes:sent?Buffer.byteLength(JSON.stringify(sent)):null}));
    ''')
    assert value['retainedEqual'], value
    assert 24000 < value['bytes'] <= 64000
    assert value['result']['telemetry']['reason'] == 'unsupported'
    assert value['result']['decision'] == 'propose'


def test_transport_byte_bound_includes_sdk_model_field() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let sizes=[];
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
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
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',allowPrivateMemory:true,fetch:async(_url,init)=>{sent=JSON.parse(init.body);
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:100,output_tokens:20},answers:{coherence_0:{type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}},supported_0:{type:'choice',choice:'grounded',confidence:1,probabilities:{grounded:1,speculative:0,transient:0,unsupported:0,unclear:0}}}}));
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
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{sent=JSON.parse(init.body);
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
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        requests++;const request=JSON.parse(init.body);const answers={};
        for(const [key,q] of Object.entries(request.questions)){
          if(key.startsWith('coherence_')){answers[key]={type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}};continue;}
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
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',defaultModel:'jev-1.13.0',scopes:['harness'],fetch:async(_url,init)=>{
        const r=JSON.parse(String(init.body));requests.push(r);const answers={};
        for(const [key,q] of Object.entries(r.questions)) {
          if(key.startsWith('coherence_')){answers[key]={type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}};continue;}
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
        const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',defaultModel:'jev-1.13.0',scopes:['harness'],fetch:async(_url,init)=>{
          if(mode==='unavailable')throw Error('fixture service unavailable');
          const r=JSON.parse(String(init.body));const answers={};
          for(const [key,q] of Object.entries(r.questions)) {
          if(key.startsWith('coherence_')){answers[key]={type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}};continue;}
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
        const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async()=>new Response(JSON.stringify({error:'PRIVATE_DIAGNOSTIC_DO_NOT_LOG'}),{status})});
        rows.push({status,result:await judge.validate('memory','evidence',['candidate'],[])});
      }
      const generic=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async()=>{throw Object.assign(new Error('PRIVATE_DIAGNOSTIC_DO_NOT_LOG'),{status:429});}});
      const unknown=await generic.validate('memory','evidence',['candidate'],[]);
      const selection=await createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',scopes:['selection'],fetch:async()=>new Response('PRIVATE_DIAGNOSTIC_DO_NOT_LOG',{status:429})}).select('For future tasks remember this project fact.',[],true);
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
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',scopes:['memory','harness'],fetch:async(_url,init)=>{
        const r=JSON.parse(String(init.body));
        if((kind==='split'&&Object.hasOwn(r.questions,'family_11'))||(kind==='cited'&&Object.hasOwn(r.questions,'counter_0_1')))
          return new Response('PRIVATE_DIAGNOSTIC_DO_NOT_LOG',{status:503});
        const answers={};for(const [key,q]of Object.entries(r.questions)){
          if(key.startsWith('coherence_')){answers[key]={type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}};continue;}
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
      const build=(choice,distribution,confidence)=>createJevJudge({maxRequestBytes:64_000,enabled:true,defaultModel:'jev-1.13.0',scopes:['memory'],apiKey:'fixture',fetch:async(_url,init)=>{
        const request=JSON.parse(init.body);const answers={};
        for(const [key,q] of Object.entries(request.questions)){
          if(key.startsWith('coherence_')){answers[key]={type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}};continue;}
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
    assert 'The failure alone does not establish a cause, a successful fix, or permanent command failure' in text
    assert 'matching inspected source' in text
    assert 'temporary service fault' in text.lower()
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
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,defaultModel:'jev-1.13.0',scopes:['memory'],apiKey:'fixture',fetch:async(_url,init)=>{
        requests++;
        const request=JSON.parse(init.body);const answers={};
        for(const [key,q] of Object.entries(request.questions)){
          if(key.startsWith('coherence_')){answers[key]={type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}};continue;}
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


def test_bounds_refusal_names_the_specific_bound_without_content() -> None:
    # Given a request that exceeds one specific review bound, When the judge
    # refuses before any transport, Then the telemetry names which bound and how
    # much, so the cause is read rather than inferred, and no evidence text enters
    # the receipt. Measured need: a weak generator returned reason bounds with no
    # counters, so the bound could not be identified from the retained artifacts.
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const offline=async()=>{throw new Error('NO TRANSPORT EXPECTED FOR A BOUNDS REFUSAL');};
      const evidence={entries:[{message:{role:'user',content:'This project uses pnpm.'}}]};
      const candidate=i=>({name:'fact'+i+'.md',content:'Use pnpm test for verification '+i+'.',evidence:[{index:0,quote:'This project uses pnpm.',role:'user'}]});
      const plain=()=>createJevJudge({maxRequestBytes:64_000,enabled:true,defaultModel:'jev-1.13.0',scopes:['memory'],apiKey:'fixture',fetch:offline});
      const huge={entries:[{message:{role:'user',content:'x'.repeat(70000)}}]};
      const bytes=await plain().validate('memory',huge,[candidate(0)],[]);
      // Windows are built from CITED entries, so many citations are needed to
      // reach the window cap; one cited index would trip the question-byte bound.
      const texts=Array.from({length:120},(_,i)=>'y'.repeat(2000)+' '+i);
      const many={entries:texts.map(content=>({message:{role:'user',content}}))};
      const cited={name:'fact.md',content:'Use pnpm test.',evidence:texts.map((quote,index)=>({index,quote,role:'user'}))};
      const windows=await plain().validate('memory',many,[cited],[]);
      console.log(JSON.stringify({bytes,windows}));
    ''')
    assert value['bytes']['telemetry']['reason'] == 'bounds'
    assert value['bytes']['telemetry']['boundsKind'] == 'question-bytes'
    assert value['bytes']['telemetry']['boundsCount'] > 64000
    assert value['windows']['telemetry']['reason'] == 'bounds'
    # Finding, recorded rather than asserted away: citing many entries makes every
    # window question exceed the request bound, because the cited support set is
    # carried in full in each question. The per-question byte bound is therefore the
    # binding constraint and the window cap of eight is never reached. A later step
    # must shrink the request, not the window count.
    assert value['windows']['telemetry']['boundsKind'] == 'question-bytes'
    assert value['windows']['telemetry']['boundsCount'] > 64000
    assert 'NO TRANSPORT EXPECTED' not in str(value)


def test_one_fixed_candidate_set_shows_the_judge_is_the_only_support_gate() -> None:
    # Controlled comparison. ONE fixed candidate set goes through the same judge
    # interface in both arms, so nothing but the judge differs. The parent applies a
    # plan when the decision is "allow" (inject-memory.ts) and skips the judge
    # entirely when it is disabled. Off arm: the disabled judge answers allow, so the
    # well-formed speculation is applied. On arm: a fixture judge reproduces the
    # recorded real-Jev behaviour and holds the speculation. The real-Jev side of
    # that class is measured separately on the frozen corpus, where 10 of 10
    # negatives are held with 0 false allows.
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const evidence={entries:[
        {message:{role:'user',content:'I think this project might build with make build, but I have not checked.'}},
        {message:{role:'toolResult',content:'pnpm test passed: 8 tests.'}},
      ]};
      const legitimate={name:'test-command.md',content:'Use pnpm test to verify this project.',evidence:[{index:1,quote:'pnpm test passed: 8 tests.',role:'toolResult'}]};
      const speculation={name:'build-command.md',content:'This project builds with make build.',evidence:[{index:0,quote:'I think this project might build with make build, but I have not checked.',role:'user'}]};
      const candidates=[legitimate,speculation];
      const requestCounts={off:0,on:0};
      const off=await createJevJudge({maxRequestBytes:64_000,enabled:false,defaultModel:'jev-1.13.0',scopes:['memory'],apiKey:'fixture',fetch:async()=>{requestCounts.off++;throw new Error('OFF ARM MUST NOT TRANSPORT');}}).validate('memory',evidence,candidates,[]);
      const on=await createJevJudge({maxRequestBytes:64_000,enabled:true,defaultModel:'jev-1.13.0',scopes:['memory'],apiKey:'fixture',fetch:async(_url,init)=>{
        requestCounts.on++;const request=JSON.parse(init.body);const answers={};
        for(const [key,q] of Object.entries(request.questions)){
          if(key.startsWith('coherence_')){answers[key]={type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}};continue;}
          if(q.type==='noul')answers[key]={type:'noul',noul:0.99};
          if(q.type==='score')answers[key]={type:'score',score:2.88,confidence:0.95,probabilities:{0:0.01,1:0.01,2:0.07,3:0.91},legend:{0:"a",1:"b",2:"c",3:"d"}};
          if(q.type==='choice')answers[key]=key.startsWith('supported_1')
            ?{type:'choice',choice:'speculative',confidence:0.99,probabilities:{grounded:0.01,speculative:0.99,transient:0,unsupported:0,unclear:0}}
            :key.startsWith('supported_0')
              ?{type:'choice',choice:'grounded',confidence:0.99,probabilities:{grounded:0.99,speculative:0.01,transient:0,unsupported:0,unclear:0}}
              :{type:'choice',choice:'supplement',confidence:0.99,probabilities:{unrelated:0,duplicate:0,supplement:1,conflict:0,unclear:0}};
        }
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:10,output_tokens:2}}));
      }}).validate('memory',evidence,candidates,[]);
      const applied=(verdict)=>verdict.decision==='allow'?candidates.length:candidates.length-1;
      console.log(JSON.stringify({off,on,requestCounts,
        offAppliedCandidates:applied(off), onAppliedCandidates:applied(on),
        counts:{candidates:candidates.length,offApplied:applied(off),onApplied:applied(on),prevented:applied(off)-applied(on)}}));
    ''')
    assert value['counts']['candidates'] == 2
    assert value['off']['decision'] == 'allow' and value['off']['telemetry']['status'] == 'disabled'
    assert value['off']['telemetry']['reason'] == 'disabled'
    assert value['counts']['offApplied'] == 2
    assert value['on']['decision'] == 'propose'
    assert value['on']['telemetry']['reason'] == 'unsupported'
    assert value['counts']['onApplied'] == 1
    assert value['counts']['prevented'] == 1
    assert value['requestCounts']['off'] == 0 and value['requestCounts']['on'] >= 1


def test_complete_small_windows_fit_without_unsafe_count_merging() -> None:
    # Given an evidence set with 10 entries of 13 KB each (total 130 KB, well within context)
    # When ten complete windows are required, keep them separate within the
    # bounded review budget rather than merging raw entries without wire overhead.
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const offline=async()=>{throw new Error('NO TRANSPORT');};
      const plain=()=>createJevJudge({maxRequestBytes:64_000,enabled:true,defaultModel:'jev-1.13.0',scopes:['memory'],apiKey:'fixture',fetch:offline});
      // 10 entries of 13 KB each:
      const entries=Array.from({length:10},(_,i)=>({message:{role:'user',content:'entry_'+i+'_'+'z'.repeat(13000)}}));
      const candidate={name:'fact.md',kind:'project',classification:'safe',content:'Use pnpm test.',evidence:[{index:0,quote:'entry_0',role:'user'}]};
      const res=await plain().validate('memory',{contextEnabled:true,entries},[candidate],[]);
      console.log(JSON.stringify({reason:res.telemetry.reason,windows:res.telemetry.evidenceWindows,boundsKind:res.telemetry.boundsKind}));
    ''')
    assert value['reason'] != 'bounds'


def test_full_review_budget_counts_batches_per_window_without_skipping_late_evidence() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const evidence={contextEnabled:true,entries:Array.from({length:10},(_,i)=>({message:{role:'user',content:`FACT_${i} `+'z'.repeat(13000)}}))};
      const candidates=Array.from({length:7},(_,i)=>({name:`fact_${i}.md`,kind:'project',classification:'safe',
        content:`---\nname: fact_${i}\ndescription: FACT_${i} is documented in the project\ntype: project\n---\n`+'A documented project fact. '.repeat(96),
        evidence:[{index:0,quote:'FACT_0',role:'user'},{index:1,quote:'FACT_1',role:'user'}]}));
      let mode='allow',active=0,peak=0; const requests=[];
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        active++;peak=Math.max(peak,active); const r=JSON.parse(init.body);requests.push(r);await Promise.resolve();
        const state=(typeof r.state === "string" ? JSON.parse(r.state) : r.state),late=state.reviewEvidence?.entries.some(e=>e.index===9),answers={};
        for(const [k,q] of Object.entries(r.questions)){
          if(k.startsWith('coherence_')){answers[k]={type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}};continue;}
          let choice='grounded' in q.criteria?'grounded':'compatible';
          if(mode==='late-conflict'&&late&&k.startsWith('counter_description_0_'))choice='contradicts';
          answers[k]={type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(label=>[label,label===choice?1:0]))};
        }
        active--;if(mode==='late-error'&&late)throw new Error('Local fixture transport failure');
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:100,output_tokens:10}}));
      }});
      const allowed=await judge.validate('memory',evidence,candidates,[]); const first=[...requests];requests.length=0;
      mode='late-conflict';const conflict=await judge.validate('memory',evidence,candidates,[]);
      mode='late-error';const error=await judge.validate('memory',evidence,candidates,[]);
      console.log(JSON.stringify({allowed,conflict,error,count:first.length,peak,
        bounded:first.every(r=>Buffer.byteLength(JSON.stringify(r))<=64000&&Object.keys(r.questions).length<=32),
        descriptionSupport:first.flatMap(r=>Object.keys(r.questions)).filter(k=>k.startsWith('supported_description_')).length,
        descriptionWindows:[...new Set(first.flatMap(r=>Object.keys(r.questions)).filter(k=>k.startsWith('counter_description_')).map(k=>k.split('_').at(-1)))].length,
        indexes:[...new Set(first.flatMap(r=>(typeof r.state === "string" ? JSON.parse(r.state) : r.state).reviewEvidence?.entries.map(e=>e.index)??[]))].sort((a,b)=>a-b)}));
    ''')
    assert value['allowed']['decision'] == 'allow', value
    assert 12 < value['count'] <= 68
    assert value['peak'] <= 4 and value['bounded'] is True
    assert value['indexes'] == list(range(10))
    assert value['descriptionSupport'] == 7
    assert value['descriptionWindows'] == value['allowed']['telemetry']['evidenceWindows']
    assert value['conflict']['decision'] == value['error']['decision'] == 'propose'


def test_real_pluggy_trace_preserves_complete_evidence_within_actual_wire_budget() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const {evidence,candidates}=await Bun.file('./packages/continual-learning/tests/fixtures/real-project-wire.json').json();
      let mode='allow',active=0,peak=0;const calls=[];
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        active++;peak=Math.max(peak,active);const r=JSON.parse(init.body);calls.push(r);await Promise.resolve();
        const state=(typeof r.state === "string" ? JSON.parse(r.state) : r.state),late=state.reviewEvidence?.entries.some(e=>e.index===204),answers={};
        for(const [k,q]of Object.entries(r.questions)){
          if(k.startsWith('coherence_')){answers[k]={type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}};continue;}
          let choice='grounded' in q.criteria?'grounded':'compatible';
          if(((mode==='conflict'&&late)||(mode==='cited-conflict'&&state.reviewEvidence?.entries.some(e=>e.index===6)))&&k.startsWith('counter_description_0_'))choice='contradicts';
          answers[k]={type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===choice?1:0]))};
        }
        active--;if(mode==='error'&&late)throw new Error('fixture failure');
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:100,output_tokens:10}}));
      }});
      const allowed=await judge.validate('memory',evidence,candidates,[]);const first=[...calls];
      mode='conflict';const conflict=await judge.validate('memory',evidence,candidates,[]);
      mode='error';const error=await judge.validate('memory',evidence,candidates,[]);
      mode='cited-conflict';const citedConflict=await judge.validate('memory',evidence,candidates,[]);
      const citedIndexes=[...new Set(candidates.flatMap(c=>c.evidence.map(e=>e.index)))].sort((a,b)=>a-b);
      const supportUnchanged=first.every(r=>{
        const s=(typeof r.state === "string" ? JSON.parse(r.state) : r.state);if(!s.reviewEvidence)return true;
        const relocated=(s.supportEvidence.reviewEntryIndexes??[]).map(index=>s.reviewEvidence.entries.find(e=>e.index===index));
        const all=[...s.supportEvidence.entries,...relocated];
        const batchCandidates=[...new Set(Object.keys(r.questions).map(key=>Number(/^counter(?:_description)?_(\d+)_/.exec(key)?.[1])))];
        const batchCitations=[...new Set(batchCandidates.flatMap(index=>candidates[index].evidence.map(e=>e.index)))].sort((a,b)=>a-b);
        return JSON.stringify(all.map(e=>e?.index).sort((a,b)=>a-b))===JSON.stringify(batchCitations)
          &&all.every(e=>e&&JSON.stringify(e.entry)===JSON.stringify(evidence.entries[e.index]))
          &&(!s.supportEvidence.reviewEntryIndexes||s.supportEvidence.entries.every(e=>!s.reviewEvidence.entries.some(w=>w.index===e.index)));
      });
      const reviewed=first.flatMap(r=>(typeof r.state === "string" ? JSON.parse(r.state) : r.state).reviewEvidence?.entries??[]);
      console.log(JSON.stringify({allowed,conflict,error,citedConflict,supportUnchanged,peak,count:first.length,maxWire:Math.max(0,...first.map(r=>Buffer.byteLength(JSON.stringify(r)))),
        indexes:[...new Set(reviewed.map(x=>x.index))].sort((a,b)=>a-b),
        unchanged:reviewed.every(x=>JSON.stringify(x.entry)===JSON.stringify(evidence.entries[x.index])),
        descriptions:first.flatMap(r=>Object.keys(r.questions)).filter(k=>k.startsWith('counter_description_')).length}));
    ''')
    assert value['allowed']['decision'] == 'allow', value
    # Original index 1 is the extension's injected reference, never source evidence.
    assert value['indexes'] == [i for i in range(205) if i != 1] and value['unchanged'] is True
    assert value['maxWire'] <= 64000 and value['peak'] <= 4
    assert value['supportUnchanged'] is True
    assert value['citedConflict']['decision'] == 'propose'
    assert value['descriptions'] == 5 * value['allowed']['telemetry']['evidenceWindows']
    assert value['conflict']['decision'] == value['error']['decision'] == 'propose'


def test_wire_bounds_diagnostic_reports_the_encoded_request_size():
    value=isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let calls=0;
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async()=>{calls++;throw new Error('must preflight first');}});
      const evidence={contextEnabled:true,entries:[{message:{role:'toolResult',content:'Known project fact '+String.fromCharCode(92).repeat(30000)}}]};
      const candidate={name:'fact.md',kind:'project',classification:'safe',content:'Known project fact '+('x'.repeat(5000)),evidence:[{index:0,quote:'Known project fact'}]};
      const result=await judge.validate('memory',evidence,[candidate],[]);
      console.log(JSON.stringify({result,calls}));
    ''')
    assert value['calls']==0
    assert value['result']['decision']=='propose'
    assert value['result']['telemetry']['boundsKind']=='question-bytes'
    assert value['result']['telemetry']['boundsCount']>64000


def test_pinned_jev_version_requires_matching_response_and_keeps_usage() -> None:
    # Given an explicitly pinned judge version, When the service returns another
    # version, Then hold the result while retaining actual model and usage.
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const rows=[];
      for(const [requested,returned] of [['jev-1.14.0','jev-1.13.0'],['jev-1.14.0','jev-1.14.0'],['jev-1.13.0','jev-1.14.0'],['jev-latest','jev-1.14.0'],['jev-preview','jev-1.14.0']]) {
        let calls=0;
        const judge=createJevJudge({enabled:true,defaultModel:requested,apiKey:'fixture',fetch:async(_url,init)=>{
          const wire=JSON.parse(init.body);if(wire.model!==requested)throw Error('Wrong requested model');calls++;
          return new Response(JSON.stringify({model:returned,usage:{input_tokens:100,output_tokens:20},answers:Object.fromEntries(Object.entries(wire.questions).map(([key,q])=>{
            const label=key.startsWith('supported_')?'grounded':key.startsWith('relation_')?'unrelated':'compatible';
            return [key,{type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===label?1:0]))}];
          }))}));
        }});
        const evidence={contextEnabled:true,entries:[{role:'user',content:'This project uses pnpm.'}]};
        const result=await judge.validate('memory',evidence,[{name:'workflow.md',kind:'project',classification:'safe',content:'This project uses pnpm.',evidence:[{index:0,quote:'This project uses pnpm.'}]}],[]);
        rows.push({requested,returned,calls,result});
      }
      console.log(JSON.stringify(rows));
    ''')
    for row in value:
        result = row['result']
        assert row['calls'] > 0
        assert result['telemetry']['model'] == row['returned']
        assert result['telemetry']['inputTokens'] >= 100
        assert result['telemetry']['estimatedCostUsd'] > 0
        if row['requested'].startswith('jev-1.') and row['requested'] != row['returned']:
            assert result['decision'] == 'propose', row
            assert result['telemetry']['reason'] == 'invalid-response', row
            assert 'candidateReview' not in result and 'incompleteReview' not in result
        else:
            assert result['decision'] == 'allow', row


def test_documentation_placeholders_in_text_are_allowed_while_quoted_real_values_refuse() -> None:
    # Given a tool result printing a JSON config sample with a documentation
    # placeholder, When the judge preflight and the Memory guard judge the same
    # text, Then the placeholder is not sensitive; a realistic value in that same
    # position, a punctuation-bearing quoted value, a provider key and a
    # credential-named argument key all stay sensitive in both detectors.
    value = isolated_run_bun(r'''
      import {sensitiveValue} from './packages/continual-learning/extensions/jev-learning.ts';
      import {containsSensitiveMemoryMaterial} from './packages/continual-learning/extensions/consolidation-run.ts';
      const both=(sample)=>[sensitiveValue(sample),typeof sample==='string'?containsSensitiveMemoryMaterial(sample):null];
      const rows={
        placeholderText:both('Config sample:\n{"passwd": "<password>"}'),
        plainPlaceholder:both('passwd: <password>'),
        providerKey:both('Config:\n{"apiKey": "sk-aaaaaaaaaaaaaaaaaaaa"}'),
        realJsonText:both('Config:\n{"password": "hunter2long"}'),
        commaValue:both('Config:\n{"password": "My,Secret1"}'),
        semicolonValue:both('Config:\n{"password": "My;Secret1"}'),
        questionValue:both('Config:\n{"password": "P@ss?word123"}'),
        slashValue:both('Config:\n{"password": "abc//defgh"}'),
        bareQuoted:both('"password":"My,Secret1"'),
        unquotedKeyQuotedValue:both('Config: {api_key: "Xq7b,N2mP4kL9vR3s"}'),
        unquotedKeySlashValue:both('Config: {api_key: "Xq7b//N2mP4kL9vR3s"}'),
        unquotedKeySemicolonValue:both('Config: {api_key: "Xq7b;N2mP4kL9vR3s"}'),
        apostropheValue:both('Config: {"password": "a\'b,cd123"}'),
        escapedQuoteValue:both('Config: {"password": "ab\\"cd,efgh"}'),
        equalsQuotedValue:both('token = "Xq7b//N2mP4kL9vR3s"'),
        quotedUrlValue:both('Auth: "https://login.example.com/oauth"'),
        unquotedUrlUnderKey:both('Auth: https://login.example.com/oauth'),
        plainUrlMember:both('{"authorization": "https://login.example.com/oauth"}'),
        urlShapedSecret:both('{"password": "https://Xq7bN2mP4kL9vR3s"}'),
        urlUserinfoSecret:both('{"password": "https://Xq7bN2mP4kL9vR3s@host"}'),
        urlWebhookSecret:both('{"password": "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"}'),
        credentialUrlWithoutScheme:both('{"password": "://Xq7bN2mP4kL9vR3s"}'),
        credentialUserinfoUrl:both('{"password": "mongodb+srv://user:Xq7bN2mP4kL9vR3s@h/db"}'),
        unknownSchemeSecret:both('{"password": "Xq7bN2mP4kL9vR3s://x"}'),
        midStringSlashes:both('token: abc//defgh'),
        parsedObjectMember:[sensitiveValue({apiKey:'sampledata99'}),containsSensitiveMemoryMaterial('{"apiKey": "sampledata99"}')],
        envReference:both('apiKey: process.env.API_KEY'),
        expression:both('secret: a ? b : c'),
        placeholderState:[sensitiveValue({entries:[{message:{role:'toolResult',content:'Config sample:\n{"passwd": "<password>"}'}}]}),null],
        realJsonState:[sensitiveValue({entries:[{message:{role:'toolResult',content:'Config:\n{"password": "hunter2long"}'}}]}),null],
        argumentPlaceholder:[sensitiveValue({args:{password:'<password>'}}),null],
        argumentReal:[sensitiveValue({args:{password:'hunter2long'}}),null],
        argumentSamplePrefixed:[sensitiveValue({args:{secret:'sampledata99'}}),null],
        argumentTestPrefixed:[sensitiveValue({args:{apiKey:'test1a2b3c4d'}}),null],
        argumentQuestion:[sensitiveValue({args:{password:'S3cr3t?Key99'}}),null],
        argumentAmpersand:[sensitiveValue({args:{token:'a&&bcd123'}}),null],
        argumentRepeated:[sensitiveValue({args:{password:'aaaaaaaa'}}),null],
      };
      console.log(JSON.stringify(rows));
    ''')
    # A documentation placeholder in text is not a credential in either detector.
    assert value['placeholderText'] == [False, False]
    assert value['plainPlaceholder'] == [False, False]
    assert value['placeholderState'][0] is False
    # A quoted realistic value is refused by both, including one whose value
    # contains punctuation the plain pattern stops at.
    assert value['realJsonText'] == [True, True]
    assert value['realJsonState'][0] is True
    assert value['commaValue'] == [True, True]
    assert value['semicolonValue'] == [True, True]
    assert value['questionValue'] == [True, True]
    assert value['slashValue'] == [True, True]
    assert value['bareQuoted'] == [True, True]
    assert value['unquotedKeyQuotedValue'] == [True, True]
    assert value['unquotedKeySlashValue'] == [True, True]
    assert value['unquotedKeySemicolonValue'] == [True, True]
    assert value['apostropheValue'] == [True, True]
    assert value['escapedQuoteValue'] == [True, True]
    assert value['equalsQuotedValue'] == [True, True]
    assert value['providerKey'] == [True, True]
    # A credential-named key has NO URL exemption: a URL under such a key can
    # itself be the credential, so it is refused in both key forms and in both
    # detectors, matching the pre-change preflight on the quoted forms.
    assert value['quotedUrlValue'] == [True, True]
    assert value['unquotedUrlUnderKey'] == [True, True]
    assert value['plainUrlMember'] == [True, True]
    assert value['urlShapedSecret'] == [True, True]
    assert value['urlUserinfoSecret'] == [True, True]
    assert value['urlWebhookSecret'] == [True, True]
    # A value that merely starts with or contains `://` is not a URL: a secret
    # with no scheme, a credential-bearing connection string and an unknown
    # scheme are all refused, matching the pre-change preflight.
    assert value['credentialUrlWithoutScheme'] == [True, True]
    assert value['credentialUserinfoUrl'] == [True, True]
    assert value['unknownSchemeSecret'] == [True, True]
    assert value['midStringSlashes'] == [True, True]
    # A credential-named member of a parsed object is strict in BOTH detectors,
    # so they cannot disagree about the same record.
    assert value['parsedObjectMember'] == [True, True]
    # A credential-named structured key stays strict: an argument or parsed
    # record is not ordinary tracked-source prose, so even a bracketed
    # placeholder, a fixture-style prefix or a punctuation-bearing value is
    # refused there.
    assert value['argumentPlaceholder'][0] is True
    assert value['argumentReal'][0] is True
    assert value['argumentSamplePrefixed'][0] is True
    assert value['argumentTestPrefixed'][0] is True
    assert value['argumentQuestion'][0] is True
    assert value['argumentAmpersand'][0] is True
    assert value['argumentRepeated'][0] is True
    # A code, env or expression reference stays ordinary.
    assert value['envReference'] == [False, False]
    assert value['expression'] == [False, False]
