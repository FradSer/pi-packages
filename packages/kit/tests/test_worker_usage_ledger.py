import json
from test_worker_runtime import KIT, run_typescript


def test_worker_ledger_sums_requests_and_keeps_unknown_failures_separate() -> None:
    result = run_typescript(fr'''
      import {{parsePiWorkerUsageLedger,parsePiWorkerOutput}} from {json.dumps(KIT)};
      const reply=(stopReason,input,cost)=>({{type:'message_end',message:{{role:'assistant',stopReason,content:[{{type:'text',text:'final'}}],usage:{{input,output:2,cacheRead:3,cacheWrite:0,totalTokens:input+5,cost:{{total:cost}}}}}}}});
      const events=[reply('toolUse',10,.01),reply('stop',20,.02)];
      const output=events.map(JSON.stringify).join('\n');
      const good=parsePiWorkerUsageLedger(output);
      const failed=parsePiWorkerUsageLedger(output+'\n'+JSON.stringify({{type:'message_end',message:{{role:'assistant',stopReason:'error',usage:{{input:0,output:0}}}}}}));
      const partial=parsePiWorkerUsageLedger(output+'\n{{"type":"message_end"');
      const missingField=parsePiWorkerUsageLedger(JSON.stringify({{type:'message_end',message:{{role:'assistant',stopReason:'stop',usage:{{input:7,output:2,cost:{{total:.04}}}}}}}}));
      const missing=parsePiWorkerUsageLedger(output+'\n'+JSON.stringify({{type:'message_end',message:{{role:'assistant',stopReason:'stop'}}}}));
      console.log(JSON.stringify({{good,failed,partial,missing,missingField,legacy:parsePiWorkerOutput(output)}}));
    ''')
    assert result['good']['complete']
    assert result['good']['knownUsage'] == {'input': 30, 'output': 4, 'cacheRead': 6, 'cacheWrite': 0, 'totalTokens': 40, 'cost': 0.03}
    assert result['good']['assistantMessages'] == 2
    for name in ('failed', 'partial', 'missing'):
        assert not result[name]['complete']
        assert result[name]['knownUsage'] == result['good']['knownUsage']
    assert result['legacy']['usage']['input'] == 20
    assert not result['missingField']['complete']
    assert result['missingField']['knownUsage']['input'] == 7
    assert result['missingField']['knownUsage']['cost'] == 0.04


def test_actual_worker_result_reports_cumulative_usage() -> None:
    result = run_typescript(fr'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'kit-summed-cost-')),pkg=path.join(root,'package');fs.mkdirSync(pkg);
      fs.writeFileSync(path.join(pkg,'package.json'),JSON.stringify({{name:'@earendil-works/pi-coding-agent'}}));
      const cli=path.join(pkg,'cli.mjs'),prior=process.argv[1];process.argv[1]=cli;
      const events=[10,20].map(input=>({{type:'message_end',message:{{role:'assistant',stopReason:'stop',content:[{{type:'text',text:'done'}}],usage:{{input,output:1,cacheRead:0,cacheWrite:0,totalTokens:input+1,cost:{{total:.01}}}}}}}}));
      fs.writeFileSync(cli,events.map(event=>'console.log('+JSON.stringify(JSON.stringify(event))+');').join('\n'));
      try {{const {{runPiWorker}}=await import({json.dumps(KIT)});console.log(JSON.stringify(await runPiWorker({{prompt:'inspect',cwd:root,minimal:true,tools:[]}})));}}
      finally{{process.argv[1]=prior;fs.rmSync(root,{{recursive:true,force:true}})}}
    ''')
    assert result['usage']['input'] == 30
    assert result['usage']['totalTokens'] == 32
    assert result['usage']['cost'] == 0.02
