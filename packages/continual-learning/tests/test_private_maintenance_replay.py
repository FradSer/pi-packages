from support import isolated_run_bun


def test_disposable_settings_use_product_schema(tmp_path) -> None:
    import json
    from live_memory_maintenance import prepare_learning_settings
    prepare_learning_settings(tmp_path)
    file = tmp_path / 'memory/settings.json'
    assert json.loads(file.read_text()) == {'autoMemory': False}
    assert file.stat().st_mode & 0o077 == 0


def test_json_encoding_does_not_turn_source_reference_into_secret() -> None:
    value = isolated_run_bun(r'''
      import {containsSensitiveMemoryMaterial as sensitive} from './packages/continual-learning/extensions/consolidation-run.ts';
      const references=['apiKey: process.env.TYPESAFE_API_KEY', 'token: "placeholder"', 'secret: ${SERVICE_SECRET}', 'authorization:\n\n```sh\n# Read-only example\n```'];
      const actual=['apiKey: abcdef0123456789',JSON.stringify({apiKey:'abcdef0123456789'}),JSON.stringify({nested:{authorization:'Bearer abcdef0123456789'}})];
      for(const child of [0,null,false,{},[]]) actual.push(JSON.stringify({'password: abcdefgh123456':child}));
      console.log(JSON.stringify({plain:references.map(sensitive),encoded:references.map(x=>sensitive(JSON.stringify({text:x}))),actual:actual.map(sensitive)}));
    ''')
    assert value['plain'] == [False] * 4
    assert value['encoded'] == [False] * 4
    assert value['actual'] == [True] * 8


def test_frozen_command_context_preserves_entries_and_rejects_changed_evidence() -> None:
    # Given an actual frozen task, When the native memory handler runs, Then
    # expose the exact retained entries without altering the live manager.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import {createHash} from 'node:crypto';import {mock} from 'bun:test';
      let observed;mock.module('./packages/continual-learning/extensions/inject-memory.ts',()=>({default:pi=>pi.registerCommand('memory',{handler:async(args,ctx)=>{observed={args,entries:ctx.sessionManager.getBranch(),id:ctx.sessionManager.getSessionId()};}})}));
      const fixture=(await import('./packages/continual-learning/tests/memory-maintenance-live-fixture.ts')).default;
      const entries=[{type:'message',message:{role:'user',content:'original task'}},{type:'message',message:{role:'toolResult',content:'original observation'}}];
      const file=path.join(process.env.PI_CODING_AGENT_DIR,'frozen.json');const bytes=JSON.stringify({entries});fs.writeFileSync(file,bytes);
      process.env.PI_MAINTENANCE_SNAPSHOT=file;process.env.PI_MAINTENANCE_SNAPSHOT_SHA256=createHash('sha256').update(bytes).digest('hex');
      const commands={};fixture({registerCommand:(name,options)=>commands[name]=options,on:()=>{}});
      const manager={id:'live',getBranch(){return []},getSessionId(){return this.id}};
      await commands.memory.handler('整理记忆',{sessionManager:manager});
      fs.appendFileSync(file,' ');let rejected=false;try{fixture({registerCommand:()=>{},on:()=>{}})}catch{rejected=true}
      console.log(JSON.stringify({observed,entries,live:manager.getBranch(),rejected}));
    ''')
    assert value['observed'] == {'args': '整理记忆', 'entries': value['entries'], 'id': 'live'}
    assert value['live'] == [] and value['rejected']


def test_json_mode_is_explicit_isolated_opt_in_without_pregranting_privacy() -> None:
    from live_memory_maintenance import private_review_config
    assert private_review_config(False) == {'jev': {'model': 'jev-1.13.0'}}
    assert private_review_config(True) == {'jev': {'model': 'jev-1.13.0'}, 'plannerJsonOutput': True}
    assert 'allowPrivateMemory' not in private_review_config(True)['jev']


def test_structured_mode_is_separate_isolated_opt_in() -> None:
    from live_memory_maintenance import private_review_config
    assert private_review_config(False, True) == {'jev': {'model': 'jev-1.13.0'}, 'plannerStructuredOutput': True}
    assert private_review_config(True, True) == {'jev': {'model': 'jev-1.13.0'}, 'plannerJsonOutput': True, 'plannerStructuredOutput': True}
    assert 'allowPrivateMemory' not in private_review_config(False, True)['jev']


def test_request_accounting_separates_model_and_jev_without_double_counting() -> None:
    from types import SimpleNamespace
    from live_memory_maintenance import inference_request_counts
    assert inference_request_counts(SimpleNamespace(requests=12, jev_requests=3)) == {
        'transportRequests': 12, 'modelRequests': 9, 'jevRequests': 3,
    }
