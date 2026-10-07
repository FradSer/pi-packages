import json
from test_worker_runtime import KIT, run_typescript


def test_failed_terminal_worker_output_discards_partial_text_and_usage() -> None:
    result = run_typescript(fr'''
      import {{parsePiWorkerOutput}} from {json.dumps(KIT)};
      const rows=['error','aborted'].map(stopReason=>parsePiWorkerOutput(JSON.stringify({{type:'message_end',message:{{role:'assistant',stopReason,errorMessage:'PRIVATE',content:[{{type:'text',text:'partial plan'}}],usage:{{input:0,output:0}}}}}})));
      console.log(JSON.stringify(rows));
    ''')
    assert result == [{'text': '', 'failure': 'model-error'}, {'text': '', 'failure': 'cancelled'}]


def test_worker_recovery_does_not_reuse_failed_text_or_failed_usage() -> None:
    result = run_typescript(fr'''
      import {{parsePiWorkerOutput}} from {json.dumps(KIT)};
      const reply=(stopReason,text)=>({{type:'message_end',message:{{role:'assistant',stopReason,content:[{{type:'text',text}}]}}}});
      const rows=[
        [reply('stop','earlier'),reply('error','partial')],
        [reply('error','partial'),reply('stop','recovered')],
        [reply('error','partial'),{{type:'auto_retry_end',success:true}}],
      ].map(events=>parsePiWorkerOutput(events.map(JSON.stringify).join('\n')));
      console.log(JSON.stringify(rows));
    ''')
    assert result == [{'text': '', 'failure': 'model-error'}, {'text': 'recovered'}, {'text': '', 'failure': 'model-error'}]


def test_real_child_exit_zero_with_failed_reply_is_not_success() -> None:
    result = run_typescript(fr'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'kit-failed-model-'));
      const pkg=path.join(root,'package');fs.mkdirSync(pkg);
      fs.writeFileSync(path.join(pkg,'package.json'),JSON.stringify({{name:'@earendil-works/pi-coding-agent'}}));
      const cli=path.join(pkg,'cli.mjs'),prior=process.argv[1];process.argv[1]=cli;
      const {{runPiWorker}}=await import({json.dumps(KIT)});
      const rows=[];
      for(const stopReason of ['error','aborted']){{
        fs.writeFileSync(cli,'console.log('+JSON.stringify(JSON.stringify({{type:'message_end',message:{{role:'assistant',stopReason,errorMessage:'PRIVATE-DO-NOT-RELAY',content:[{{type:'text',text:'partial plan'}}],usage:{{input:0,output:0}}}}}}))+');');
        rows.push(await runPiWorker({{prompt:'inspect',cwd:root,minimal:true,tools:[]}}));
      }}
      process.argv[1]=prior;fs.rmSync(root,{{recursive:true,force:true}});console.log(JSON.stringify(rows));
    ''')
    assert all(row['exitCode'] != 0 and row['text'] == '' and 'usage' not in row for row in result)
    assert [row['cancelled'] for row in result] == [False, True]
    assert all('PRIVATE' not in row['stderr'] for row in result)


def test_retry_bookkeeping_preserves_cancelled_until_a_successful_reply() -> None:
    result = run_typescript(fr'''
      import {{parsePiWorkerOutput}} from {json.dumps(KIT)};
      const reply=stopReason=>({{type:'message_end',message:{{role:'assistant',stopReason,content:[]}}}});
      const rows=[true,false].map(success=>parsePiWorkerOutput([reply('error'),reply('aborted'),{{type:'auto_retry_end',success}}].map(JSON.stringify).join('\n')));
      console.log(JSON.stringify(rows));
    ''')
    assert result == [{'text': '', 'failure': 'cancelled'}] * 2


def test_recovered_reply_does_not_make_unknown_failed_usage_a_known_total() -> None:
    result = run_typescript(fr'''
      import {{parsePiWorkerOutput}} from {json.dumps(KIT)};
      const reply=(stopReason,text,input)=>({{type:'message_end',message:{{role:'assistant',stopReason,content:[{{type:'text',text}}],usage:{{input,output:1,totalTokens:input+1,cost:{{total:.01}}}}}}}});
      console.log(JSON.stringify(parsePiWorkerOutput([reply('error','partial',0),reply('stop','recovered',10)].map(JSON.stringify).join('\n'))));
    ''')
    assert result == {'text': 'recovered'}
