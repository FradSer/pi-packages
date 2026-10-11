"""Real child transport regression for large frozen Memory repair prompts."""
import json
from test_pi_kit import SRC, run_typescript


def test_large_utf8_prompt_uses_stdin_and_preserves_exact_bytes(tmp_path):
    result=run_typescript(f'''
      import fs from 'node:fs';import path from 'node:path';import {{createHash}} from 'node:crypto';
      const root={json.dumps(str(tmp_path))},pkg=path.join(root,'fake-package');fs.mkdirSync(pkg);
      fs.writeFileSync(path.join(pkg,'package.json'),JSON.stringify({{name:'@earendil-works/pi-coding-agent'}}));
      const cli=path.join(pkg,'cli.mjs');
      fs.writeFileSync(cli,`import {{createHash}} from 'node:crypto';let text='';process.stdin.setEncoding('utf8');for await(const c of process.stdin)text+=c;const stdinBytes=Buffer.byteLength(text);if(!text)text=process.argv.at(-1);console.log(JSON.stringify({{type:'message_end',message:{{role:'assistant',stopReason:'stop',content:[{{type:'text',text:JSON.stringify({{bytes:Buffer.byteLength(text),digest:createHash('sha256').update(text).digest('hex'),stdinBytes}})}}]}}}}));`);
      process.argv[1]=cli;
      const {{runPiWorker}}=await import({json.dumps((SRC/'index.ts').as_uri())});
      const prompt='冻结证据\\n'.repeat(20000)+'end';
      const worker=await runPiWorker({{prompt,cwd:root,minimal:true,tools:[]}});
      console.log(JSON.stringify({{exit:worker.exitCode,received:worker.text?JSON.parse(worker.text):null,expected:{{bytes:Buffer.byteLength(prompt),digest:createHash('sha256').update(prompt).digest('hex')}}}}));
    ''')
    assert result['exit']==0
    assert result['received']['bytes']==result['expected']['bytes']
    assert result['received']['digest']==result['expected']['digest']
    assert result['received']['stdinBytes']==0


def test_closed_prompt_pipe_returns_failure_without_unhandled_error(tmp_path):
    result=run_typescript(f'''
      import fs from 'node:fs';import path from 'node:path';
      const root={json.dumps(str(tmp_path))},pkg=path.join(root,'fake-package');fs.mkdirSync(pkg);
      fs.writeFileSync(path.join(pkg,'package.json'),JSON.stringify({{name:'@earendil-works/pi-coding-agent'}}));
      const cli=path.join(pkg,'cli.mjs');fs.writeFileSync(cli,'process.exit(2)');process.argv[1]=cli;
      // This executable exits before the bootstrap consumes its pipe.
      const earlyExit=path.join(root,'early-exit');fs.writeFileSync(earlyExit,'#!/usr/bin/env node\\nprocess.exit(2)',{{mode:0o755}});process.execPath=earlyExit;
      const {{runPiWorker}}=await import({json.dumps((SRC/'index.ts').as_uri())});
      const worker=await runPiWorker({{prompt:'x'.repeat(2*1024*1024),cwd:root,minimal:true,tools:[]}});
      console.log(JSON.stringify({{failed:worker.exitCode!==0,text:worker.text,pipeFailed:worker.stderr.includes('prompt delivery failed')}}));
    ''')
    assert result=={'failed':True,'text':'','pipeFailed':True}


def test_actual_pi_preserves_large_prompt_boundary_whitespace(tmp_path):
    result=run_typescript(f'''
      import fs from 'node:fs';import path from 'node:path';import {{createHash}} from 'node:crypto';
      const root={json.dumps(str(tmp_path))},agent=path.join(root,'agent'),capture=path.join(root,'captured.txt');fs.mkdirSync(agent);
      fs.writeFileSync(path.join(agent,'settings.json'),JSON.stringify({{packages:[]}}));
      fs.writeFileSync(path.join(agent,'models.json'),JSON.stringify({{providers:{{fixture:{{baseUrl:'http://127.0.0.1:9/v1',api:'openai-completions',apiKey:'public-test-placeholder',models:[{{id:'fixture',name:'fixture',reasoning:false,input:['text'],contextWindow:1000000,maxTokens:8,cost:{{input:0,output:0,cacheRead:0,cacheWrite:0}}}}]}}}}}}));
      const fixture=path.join(root,'capture.ts');
      fs.writeFileSync(fixture,`import fs from 'node:fs';export default function(pi){{pi.on('before_agent_start',event=>{{fs.writeFileSync(${{JSON.stringify(capture)}},event.prompt);process.exit(0);}});}}`);
      const {{runPiWorker}}=await import({json.dumps((SRC/'index.ts').as_uri())});
      const prompt='  \\n\\t'+'frozen evidence\\n'.repeat(2000)+'\\n\\t  ';
      const worker=await runPiWorker({{prompt,cwd:root,minimal:true,tools:[],model:'fixture/fixture',env:{{HOME:root,PI_CODING_AGENT_DIR:agent}},extraArgs:['--offline','-e',fixture]}});
      const captured=fs.existsSync(capture)?fs.readFileSync(capture,'utf8'):null;
      console.log(JSON.stringify({{exit:worker.exitCode,exact:captured===prompt,bytes:captured?.length,expected:prompt.length}}));
    ''')
    assert result['exit']==0
    assert result['exact'] is True


def test_large_prompt_worker_can_be_cancelled_after_output_event(tmp_path):
    result=run_typescript(f'''
      import fs from 'node:fs';import path from 'node:path';
      const root={json.dumps(str(tmp_path))},pkg=path.join(root,'fake-package');fs.mkdirSync(pkg);
      fs.writeFileSync(path.join(pkg,'package.json'),JSON.stringify({{name:'@earendil-works/pi-coding-agent'}}));
      const cli=path.join(pkg,'cli.mjs'),marker=path.join(root,'pid');
      fs.writeFileSync(cli,`import fs from 'node:fs';fs.writeFileSync(${{JSON.stringify(marker)}},String(process.pid));console.log(JSON.stringify({{type:'message_update',assistantMessageEvent:{{type:'text_delta',delta:'ready'}}}}));setInterval(()=>{{}},1000);`);
      process.argv[1]=cli;const {{runPiWorker}}=await import({json.dumps((SRC/'index.ts').as_uri())});
      const controller=new AbortController();
      const worker=await runPiWorker({{prompt:'x'.repeat(200000),cwd:root,minimal:true,tools:[],signal:controller.signal,onUpdate:update=>{{if(update.text==='ready')controller.abort();}}}});
      let alive=true;try{{process.kill(Number(fs.readFileSync(marker,'utf8')),0);}}catch{{alive=false;}}
      console.log(JSON.stringify({{cancelled:worker.cancelled,failed:worker.exitCode!==0,text:worker.text,alive}}));
    ''')
    assert result=={'cancelled':True,'failed':True,'text':'','alive':False}
