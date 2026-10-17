from support import isolated_run_bun


def test_generation_thinking_is_explicit_scoped_and_fails_closed():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {learningPlannerArgs} from './packages/continual-learning/extensions/planner-prompts.ts';
      const file=path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json');
      const absent=learningPlannerArgs();const levels={};
      for(const level of ['off','minimal','low','medium','high','xhigh']){
        fs.writeFileSync(file,JSON.stringify({plannerThinkingLevel:level}));
        const args=learningPlannerArgs('memory-delta');levels[level]=args[args.indexOf('--thinking')+1];
      }
      const rejected=[];for(const val of ['invalid',1,null,{},'low --no-tools']){
        fs.writeFileSync(file,JSON.stringify({plannerThinkingLevel:val}));
        try{learningPlannerArgs();rejected.push(false)}catch{rejected.push(true)}
      }
      fs.writeFileSync(file,'{"jev":{"apiKey":"test-only-parser-canary" broken}}');
      let sanitized;try{learningPlannerArgs()}catch(error){sanitized=error.message}
      fs.writeFileSync(file,JSON.stringify({plannerStructuredOutput:true}));const unchanged=learningPlannerArgs();
      fs.unlinkSync(file);const target=path.join(process.env.PI_CODING_AGENT_DIR,'external.json');fs.writeFileSync(target,JSON.stringify({plannerThinkingLevel:'low'}));fs.symlinkSync(target,file);
      let unsafe=false;try{learningPlannerArgs()}catch{unsafe=true}
      console.log(JSON.stringify({absent,levels,rejected,unchanged,unsafe,sanitized}));
    ''', temp_dirs=('PI_CODING_AGENT_DIR',))
    assert '--thinking' not in value['absent'] and '--thinking' not in value['unchanged']
    assert value['levels']=={level:level for level in ['off','minimal','low','medium','high','xhigh']}
    assert all(value['rejected']) and value['unsafe']

    assert value['sanitized']=='Invalid learning planner configuration'
