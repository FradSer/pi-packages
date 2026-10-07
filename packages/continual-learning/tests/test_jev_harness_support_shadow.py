from support import isolated_run_bun


def test_support_shadow_changes_only_new_command_rule_support() -> None:
    # Given a support question mixed with executable syntax, when decomposing,
    # preserve every independent gate and every frozen state byte.
    value = isolated_run_bun(r'''
      import {harnessSupportShadow} from './packages/continual-learning/tests/jev-harness-support-shadow.ts';
      const candidate={action:'addRule',rule:{id:'public',bash:'^git +push',action:'block',message:'Never run git push.'},behaviorExamples:{blocked:['git push']}};
      const original={state:'{"frozenEvidence":"keep every original byte"}',model:'jev-1.13.0',questions:{
        supported_0:{kind:'noul',instructions:{question:'original',candidate},criteria:{true:'yes',false:'no'}},
        expands_0:{kind:'choice',instructions:{candidate},criteria:{same:'same',broader:'broader'}},
        counter_0_0:{kind:'choice',instructions:{candidate},criteria:{compatible:'same',contradicts:'changed'}}}};
      const init={body:JSON.stringify(original),headers:{test:'preserve'},method:'POST'};
      const after=harnessSupportShadow(init);
      console.log(JSON.stringify({before:original,after:JSON.parse(String(after.body)),unchangedInput:init.body===JSON.stringify(original),sameHeaders:after.headers===init.headers}));
    ''')
    assert value['after']['state'] == value['before']['state']
    assert value['unchangedInput'] and value['sameHeaders']
    assert value['after']['questions']['expands_0'] == value['before']['questions']['expands_0']
    assert value['after']['questions']['counter_0_0'] == value['before']['questions']['counter_0_0']
    support = value['after']['questions']['supported_0']
    assert support['instructions']['candidate'] == {'action': 'addRule', 'rule': {'action': 'block', 'message': 'Never run git push.'}}
    assert support['criteria'] == value['before']['questions']['supported_0']['criteria']


def test_support_shadow_does_not_strip_rewrite_delete_or_guidance_context() -> None:
    value = isolated_run_bun(r'''
      import {harnessSupportShadow} from './packages/continual-learning/tests/jev-harness-support-shadow.ts';
      const candidates=[{action:'deleteRule',rule:{bash:'x',action:'block',message:'keep'}},{action:'replaceRule',rule:{bash:'x',action:'confirm',message:'keep'}},{action:'addRule',rule:{skill:'review',instructions:'keep'}}];
      const request={state:'original',model:'jev-1.13.0',questions:Object.fromEntries(candidates.map((candidate,i)=>['supported_'+i,{instructions:{candidate},criteria:{true:'yes',false:'no'}}]))};
      const before=JSON.stringify(request);
      console.log(JSON.stringify({unchanged:String(harnessSupportShadow({body:before}).body)===before}));
    ''')
    assert value['unchanged']


def test_support_diagnostics_keep_only_controlled_finite_probabilities() -> None:
    value = isolated_run_bun(r'''
      import {harnessSupportAnswers} from './packages/continual-learning/tests/jev-harness-support-shadow.ts';
      const raw={answers:{supported_0:{type:'noul',noul:.94,text:'PRIVATE_RAW'},supported_1:{type:'noul',noul:Infinity},supported_2:{type:'noul',noul:1.1},private_label:{type:'noul',noul:.2}}};
      console.log(JSON.stringify(harnessSupportAnswers(raw,{supported_0:{type:'noul'},supported_1:{type:'noul'},supported_2:{type:'noul'},private_label:{type:'noul'}})));
    ''')
    assert value == {'supported_0': {'noul': .94}}


def test_proven_git_scope_shadow_preserves_unknown_regex_and_all_evidence() -> None:
    # Given an exact finite matcher, describe its proven language to the judge;
    # unknown operators and every authorization/support gate remain unchanged.
    value = isolated_run_bun(r'''
      import {harnessGitScopeShadow} from './packages/continual-learning/tests/jev-harness-git-scope-shadow.ts';
      const corpus=await Bun.file('./packages/continual-learning/tests/fixtures/jev-harness-support-corpus.json').json();
      const candidate={action:'addRule',rule:corpus[0].plan.operations[0].rule};
      const request={state:'KEEP_FROZEN_BYTES',questions:{supported_0:{type:'noul',instructions:{candidate}},expands_0:{type:'choice',instructions:{candidate},criteria:{same:'same',narrower:'narrower',broader:'broader',unclear:'unclear'}},counter_0_0:{type:'choice',instructions:{candidate}}}};
      const initial=JSON.stringify(request);const after=JSON.parse(String(harnessGitScopeShadow({body:initial}).body));
      const unknown=structuredClone(request);unknown.questions.expands_0.instructions.candidate.rule.bash+='|.*';unknown.questions.counter_0_0.instructions.candidate.rule.bash+='|.*';
      const unknownText=JSON.stringify(unknown);
      console.log(JSON.stringify({before:request,after,inputUnchanged:initial===JSON.stringify(request),unknownUnchanged:String(harnessGitScopeShadow({body:unknownText}).body)===unknownText}));
    ''')
    assert value['inputUnchanged'] and value['unknownUnchanged']
    assert value['after']['state'] == value['before']['state']
    assert value['after']['questions']['supported_0'] == value['before']['questions']['supported_0']
    assert value['after']['questions']['expands_0']['criteria'] == value['before']['questions']['expands_0']['criteria']
    projected = value['after']['questions']['expands_0']['instructions']['candidate']
    assert 'bash' not in projected['rule']
    assert 'matching' in projected['rule']
    assert projected['rule']['action'] == 'block'
    assert projected['rule']['message'] == value['before']['questions']['expands_0']['instructions']['candidate']['rule']['message']


def test_research_validation_passes_exact_plan_citations_to_production_judge() -> None:
    value = isolated_run_bun(r'''
      import {validateHarnessResearch} from './packages/continual-learning/tests/jev-harness-research-validation.ts';
      const input={snapshot:{contextEnabled:true,entries:[{role:'user',content:'original'}]},plan:{operations:[{op:'addRule'}],evidence:[{index:0,source:'user',quote:'original',count:1}]}};
      let passed=false;
      const judge={validate:async (...args)=>{passed=args[0]==='harness'&&args[1]===input.snapshot&&args[2]===input.plan.operations&&args[5]===input.plan.evidence;return {decision:'propose',telemetry:{reason:'uncertain'}}}};
      await validateHarnessResearch(judge,input);console.log(JSON.stringify({passed}));
    ''')
    assert value['passed']


def test_live_heldout_research_requires_report_file_before_any_request() -> None:
    value = isolated_run_bun(r'''
      // Isolate output-contract tests from the historical study's code freeze.
      // Real inference uses the unmodified frozen manifest, never this stub.
      const fs=(await import('node:fs/promises')).default;const readFile=fs.readFile.bind(fs);
      fs.readFile=async (...args)=>{const raw=await readFile(...args);if(String(args[0]).endsWith('jev-harness-git-scope-heldout-study-manifest.json'))return JSON.stringify({...JSON.parse(String(raw)),codeHashes:{}});return raw;};
      process.argv.push('--live');process.env.TYPESAFE_API_KEY='test-not-a-real-key';
      let requests=0;globalThis.fetch=async()=>{requests++;throw Error('No external call authorized in this regression');};
      let message='';try {await import('./packages/continual-learning/tests/evaluate_jev_harness_git_scope_heldout.ts');}catch(error){message=String(error.message);}
      console.log(JSON.stringify({requests,message}));
    ''')
    assert value == {'requests': 0, 'message': 'Live research requires a saved report path before any inference'}


def test_bad_report_destination_stops_before_paid_inference() -> None:
    value = isolated_run_bun(r'''
      // Isolate output-contract tests from the historical study's code freeze.
      // Real inference uses the unmodified frozen manifest, never this stub.
      const fs=(await import('node:fs/promises')).default;const readFile=fs.readFile.bind(fs);
      fs.readFile=async (...args)=>{const raw=await readFile(...args);if(String(args[0]).endsWith('jev-harness-git-scope-heldout-study-manifest.json'))return JSON.stringify({...JSON.parse(String(raw)),codeHashes:{}});return raw;};
      process.argv.push('--live','--output',process.env.PI_CODING_AGENT_DIR+'/missing-parent/report.json');process.env.TYPESAFE_API_KEY='test-not-a-real-key';
      let requests=0;globalThis.fetch=async()=>{requests++;throw Error('No external call authorized');};
      let failed=false;try {await import('./packages/continual-learning/tests/evaluate_jev_harness_git_scope_heldout.ts');}catch{failed=true;}
      console.log(JSON.stringify({requests,failed}));
    ''')
    assert value == {'requests': 0, 'failed': True}


def test_research_preserves_existing_report_without_paid_inference() -> None:
    value = isolated_run_bun(r'''
      const path=process.env.PI_CODING_AGENT_DIR+'/report.json';await Bun.write(path,'PRESERVE_EXISTING');
      // Isolate output-contract tests from the historical study's code freeze.
      // Real inference uses the unmodified frozen manifest, never this stub.
      const fs=(await import('node:fs/promises')).default;const readFile=fs.readFile.bind(fs);
      fs.readFile=async (...args)=>{const raw=await readFile(...args);if(String(args[0]).endsWith('jev-harness-git-scope-heldout-study-manifest.json'))return JSON.stringify({...JSON.parse(String(raw)),codeHashes:{}});return raw;};
      process.argv.push('--live','--output',path);process.env.TYPESAFE_API_KEY='test-not-a-real-key';
      let requests=0;globalThis.fetch=async()=>{requests++;throw Error('No external call authorized');};
      let failed=false;try {await import('./packages/continual-learning/tests/evaluate_jev_harness_git_scope_heldout.ts');}catch{failed=true;}
      console.log(JSON.stringify({requests,failed,preserved:await Bun.file(path).text()}));
    ''')
    assert value == {'requests': 0, 'failed': True, 'preserved': 'PRESERVE_EXISTING'}
