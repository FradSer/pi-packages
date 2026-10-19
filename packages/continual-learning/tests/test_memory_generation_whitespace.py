import pytest
from support import isolated_run_bun


def test_real_selected_rewrite_recovers_only_json_string_whitespace() -> None:
    # Given a real strict-schema rewrite containing raw JSON string controls,
    # When initial generation is parsed, Then all original mutation intent and
    # exact string values survive, without granting semantic acceptance.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import crypto from 'node:crypto';
      import {parseMemoryGenerationResponse} from './packages/continual-learning/extensions/inject-memory.ts';
      import {normalizeJsonStringWhitespace} from './packages/continual-learning/extensions/json-string-whitespace.ts';
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-generation-raw-whitespace.json','utf8'));
      const original=fixture.content;
      const normalized=normalizeJsonStringWhitespace(original,512000);
      const recovered=parseMemoryGenerationResponse(original);
      const expected=JSON.parse(normalized.text);
      const negatives=[original+'\n{}',original.slice(0,-1),original.replace('name:', 'name:\u0001'),original.replace('name:', 'name:\\q'), 'prefix '+original];
      console.log(JSON.stringify({digest:crypto.createHash('sha256').update(original).digest('hex')===fixture.provenance.contentSha256,
        exact:JSON.stringify(recovered.plan)===JSON.stringify(expected),counts:recovered.normalization.counts,
        unchanged:original===fixture.content,kind:recovered.plan.operations[0].kind,
        negatives:negatives.map(text=>parseMemoryGenerationResponse(text).plan===undefined),
        normal:parseMemoryGenerationResponse(JSON.stringify(expected)).normalization===undefined}));
    ''')
    assert result['digest'] and result['exact'] and result['unchanged']
    assert result['kind'] == 'rewrite'
    assert result['counts']['newline'] > 0 and result['counts']['tab'] > 0
    assert all(result['negatives']) and result['normal']


@pytest.mark.parametrize("native_retry", [False, True])
def test_actual_pi_generation_delivers_frozen_response_to_parent_parser(tmp_path, native_retry) -> None:
    import json
    result = isolated_run_bun(r'''
      import {spawnSync} from 'node:child_process';import fs from 'node:fs';import path from 'node:path';
      import {parsePiWorkerOutput} from './packages/kit/src/index.ts';
      import {recoverMemoryGenerationFromChild} from './packages/continual-learning/extensions/inject-memory.ts';
      import {validatePlanIdentity} from './packages/continual-learning/extensions/consolidation-run.ts';
      const root=ROOT;const nativeRetry=NATIVE_RETRY;
      fs.mkdirSync(path.join(root,'agent'),{recursive:true});
      fs.writeFileSync(path.join(root,'agent/settings.json'),JSON.stringify({retry:{enabled:true,maxRetries:1,baseDelayMs:1}}));
      const native=spawnSync('node',[path.resolve('node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js'),
        '--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-tools',
        '-e',path.resolve('packages/continual-learning/tests/memory-amendment-live-fixture.ts'),
        '--generation-json-whitespace','enabled',...(nativeRetry?['--generation-native-retry','enabled']:[]),'--provider','amendment-fixture','--model','fixed','--thinking','off',
        '--no-session','--print','--mode','json','frozen generation serialization'],
        {cwd:root,env:{PATH:process.env.PATH,HOME:root,PI_CODING_AGENT_DIR:path.join(root,'agent'),PI_OFFLINE:'1'},encoding:'utf8',timeout:40000});
      fs.writeFileSync(path.join(root,'native-generation-output.jsonl'),native.stdout);
      if(native.status!==0)throw Error(native.stderr+'\n'+native.stdout);
      const text=parsePiWorkerOutput(native.stdout).text;
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-generation-raw-whitespace.json','utf8'));
      const {plan,normalization}=recoverMemoryGenerationFromChild(native.stdout);
      const identity=Object.fromEntries(['runId','scopeDigest','snapshotDigest'].map(k=>[k,plan[k]]));
      console.log(JSON.stringify({retryClosed:native.stdout.includes('auto_retry_end'),exact:text===fixture.content,counts:normalization.counts,
        valid:validatePlanIdentity(plan,identity),foreign:validatePlanIdentity({...plan,runId:'foreign'},identity),
        wroteMemory:fs.existsSync(path.join(root,'.memory')),kind:plan.operations[0].kind}));
    '''.replace('ROOT', json.dumps(str(tmp_path))).replace('NATIVE_RETRY', str(native_retry).lower()))
    assert result['retryClosed'] == native_retry
    assert result['exact'] and result['counts']['newline'] > 0
    assert result['kind'] == 'rewrite'
    assert result['valid'] == [] and result['foreign'] == ['plan run id mismatch']
    assert not result['wroteMemory']


def test_complete_transport_recovery_preserves_drafts_limits_and_failure() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {recoverMemoryGenerationFromChild} from './packages/continual-learning/extensions/inject-memory.ts';
      import {normalizeJsonStringWhitespace} from './packages/continual-learning/extensions/json-string-whitespace.ts';
      const raw=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-generation-raw-whitespace.json','utf8')).content;
      const plan=JSON.parse(normalizeJsonStringWhitespace(raw,512000).text);
      const frame=(text,stopReason='stop')=>JSON.stringify({type:'message_end',message:{role:'assistant',stopReason,content:[{type:'text',text}]}});
      const line=frame(raw),valid=frame(JSON.stringify(plan));
      const thought={type:'thinking',thinking:'untrusted analysis',thinkingSignature:'reasoning_content'};
      const withThinking=JSON.stringify({type:'message_end',message:{role:'assistant',stopReason:'stop',content:[thought,{type:'text',text:raw}]}});
      const identity={runId:plan.runId,scopeDigest:plan.scopeDigest,artifactHash:plan.artifactHash};
      const recover=(stdout,opts={})=>recoverMemoryGenerationFromChild(stdout,{expectedIdentity:identity,...opts});
      const negatives=[recover(valid+'\n'+valid),recover(line+'\n'+line),recover(line+'\n'+valid),
        recover(frame(raw,'error')),recover(frame(raw,'aborted')),recover(frame(raw,'length')),
        recover(line+'\n'+frame(raw,'error')),recover(line.slice(0,-1)),recover(frame(raw.slice(0,-1))),
        recover(line,{maxOutputBytes:10}),recover(line,{maxLineBytes:10}),recover(line+'\n{}',{maxLines:1}),
        recover(line,{maxPlanBytes:10}),recover(line,{expectedIdentity:{...identity,runId:'foreign'}}),
        recover(JSON.stringify({type:'message_end',message:{role:'assistant',stopReason:'stop',content:[{type:'toolCall',id:'x',name:'read',arguments:{}},{type:'text',text:raw}]}})),
        recover(JSON.stringify({type:'message_end',message:{role:'assistant',stopReason:'stop',content:[{type:'thinking',thinking:42},{type:'text',text:raw}]}}))];
      console.log(JSON.stringify({thinking:JSON.stringify(recover(withThinking).plan)===JSON.stringify(plan),positive:JSON.stringify(recover(line).plan)===JSON.stringify(plan),
        rejects:negatives.map(value=>value.plan===undefined)}));
    ''')
    assert result['thinking'] and result['positive'] and all(result['rejects'])


def test_successful_native_retry_keeps_failed_responses_and_all_parent_bounds() -> None:
    # Given the real worker lifecycle errors followed by an explicit successful
    # native retry, When its final JSON has raw string controls, Then recovery
    # matches ordinary valid-JSON extraction without adding any retry or cost.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {recoverMemoryGenerationFromChild} from './packages/continual-learning/extensions/inject-memory.ts';
      const raw=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-generation-raw-whitespace.json','utf8')).content;
      const message=(stopReason,text)=>JSON.stringify({type:'message_end',message:{role:'assistant',stopReason,content:[{type:'thinking',thinking:'untrusted analysis'},{type:'text',text}]}});
      const error=message('error','incomplete discarded provider output');
      const start=JSON.stringify({type:'auto_retry_start',attempt:1});
      const end=JSON.stringify({type:'auto_retry_end',success:true});
      const done=message('stop',raw),full=[error,start,error,start,done,end].join('\n');
      const original=full;
      const negative=[[error,done,end],[error,start,done],[error,start,done,JSON.stringify({type:'auto_retry_end',success:false})],
        [message('aborted','cancelled'),start,done,end],[done,error,start,done,end]];
      const recovered=recoverMemoryGenerationFromChild(full);
      console.log(JSON.stringify({positive:recovered.plan?.kind==='incremental-memory-plan',unchanged:full===original,
        counts:recovered.normalization?.counts,rejects:negative.map(rows=>!recoverMemoryGenerationFromChild(rows.join('\n')).plan),
        limit:!recoverMemoryGenerationFromChild(full,{maxOutputBytes:10}).plan}));
    ''')
    assert result['positive'] and result['unchanged'] and result['limit']
    assert result['counts']['newline'] > 0 and all(result['rejects'])


def test_generation_archive_suppresses_encoded_secrets_in_all_worker_messages() -> None:
    result = isolated_run_bun(r'''
      import {generationOutputContainsSensitiveMaterial} from './packages/continual-learning/extensions/inject-memory.ts';
      const fake='api_key=sk-'+'x'.repeat(40);
      const encoded=[...fake].map(c=>'\\u'+c.charCodeAt(0).toString(16).padStart(4,'0')).join('');
      const broken='{"note":"line\nraw","value":"'+encoded+'"}';
      const frame=(text,type='text')=>JSON.stringify({type:'message_end',message:{role:'assistant',stopReason:'error',content:[type==='text'?{type,text}:{type,thinking:text}]}});
      const values=[frame(broken),frame(broken,'thinking'),frame(JSON.stringify({nested:broken})),frame('benign')+'\n'+frame(broken)];
      console.log(JSON.stringify({rejected:values.map(text=>generationOutputContainsSensitiveMaterial(text,{})),
        normalized: generationOutputContainsSensitiveMaterial(frame('benign'),{value:fake}),
        benign:generationOutputContainsSensitiveMaterial(frame('ordinary observation'),{kind:'incremental-memory-plan'})}));
    ''')
    assert all(result['rejected']) and result['normalized']
    assert not result['benign']
