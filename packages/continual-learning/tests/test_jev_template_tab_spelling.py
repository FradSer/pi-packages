from support import isolated_run_bun


def test_template_recognizes_only_literal_or_escaped_tab_slots() -> None:
    row = isolated_run_bun(r'''
      import {projectPushTemplate,matchesProjectPushTemplate} from './packages/continual-learning/extensions/harness-command-coverage.ts';
      const root='/work/a.b',canonical=projectPushTemplate(root)!;
      const slots=canonical.split(String.raw`\t`);
      let accepted=0;
      for(let bits=0;bits<2**(slots.length-1);bits++){
        const pattern=slots.map((s,i)=>i===0?s:((bits&(1<<(i-1)))?'\t':String.raw`\t`)+s).join('');
        if(!matchesProjectPushTemplate(pattern,root))throw Error('Equivalent tab spelling rejected');
        const a=new RegExp(canonical),b=new RegExp(pattern);
        for(const command of ['git push','git\tpush --dry-run','cd /work/a.b && git -C . push',
          'echo git push','cd /work/other && git push','git\npush','git\u00a0push','git push\r']){
          if(a.test(command)!==b.test(command))throw Error('Changed matching semantics');
        }
        accepted++;
      }
      const tabs=canonical.replaceAll(String.raw`\t`,'\t');
      const rejects=[undefined,{},tabs+'|.*',tabs.replace('push','pull'),tabs.replace('[ \t]','[\t]'),
        tabs.replace('[ \t]','[ \\s]'),tabs.replace('a\\.b','axb'),tabs.replace('&&',';'),tabs.replace('\\.','.'),
        tabs.replace('push(?:','push.*(?:'),tabs.replace('\t','\n')];
      console.log(JSON.stringify({accepted,rejected:rejects.every(p=>!matchesProjectPushTemplate(p,root)),
        foreign:!matchesProjectPushTemplate(tabs,'/work/other'),unsafe:!matchesProjectPushTemplate(tabs,'/work/a\tb')}));
    ''')
    assert row == {'accepted': 256, 'rejected': True, 'foreign': True, 'unsafe': True}


def test_literal_tab_route_keeps_authority_counter_and_parent_checks() -> None:
    rows = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      import {projectPushTemplate} from './packages/continual-learning/extensions/harness-command-coverage.ts';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const quote='Never run git push in this project in future tasks.';
      const snapshot={contextEnabled:true,runId:'r',scopeKey:'s',entries:[{role:'user',content:quote}]};
      const original={op:'addRule',rule:{id:'no-push',bash:projectPushTemplate('/work/project')!.replaceAll(String.raw`\t`,'\t'),action:'block',message:quote}};
      const binding={repoRoot:'/work/project',runId:'r',scopeKey:'s',evidenceDigest:createHash('sha256').update(JSON.stringify(snapshot)).digest('hex')};
      const outputs=[];
      for(const mode of ['valid','conditional','temporary','elsewhere','absent','arguments','counter','unavailable',
        'missing','stale','foreign','update','confirm','disabled','unknown']){
        const candidate=structuredClone(original),parent=mode==='missing'?undefined:{...binding};
        if(mode==='stale')parent!.evidenceDigest='0'.repeat(64);
        if(mode==='foreign')parent!.repoRoot='/work/elsewhere';
        if(mode==='update')candidate.op='updateRule';
        if(mode==='confirm')candidate.rule.action='confirm';
        if(mode==='disabled')candidate.rule.enabled=false;
        if(mode==='unknown')candidate.rule.bash+='|.*';
        const before=JSON.stringify(candidate),keys=[];
        const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['harness'],fetch:async(_url,init)=>{
          if(mode==='unavailable')throw Error('offline unavailable');
          const request=JSON.parse(String(init.body)),answers={};
          for(const [key,q]of Object.entries(request.questions)){
            keys.push(key);const label=key.startsWith('authority')?(['conditional','temporary','elsewhere','absent'].includes(mode)?mode:'lasting')
              :key.startsWith('family')?(mode==='arguments'?'extra':'authorized'):key.startsWith('explanation')?'faithful'
              :key.startsWith('expands')?'broader':mode==='counter'?'contradicts':'compatible';
            answers[key]=q.type==='noul'?{type:'noul',noul:.99}:{type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===label?1:0]))};
          }
          return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
        }});
        const result=await judge.validate('harness',snapshot,[candidate],[],undefined,[{index:0,source:'user',quote,count:1,eventIndex:0}],parent);
        outputs.push({mode,result,keys,unchanged:before===JSON.stringify(candidate)});
      }
      console.log(JSON.stringify(outputs));
    ''')
    for row in rows:
        assert row['unchanged']
        assert row['result']['decision'] == ('allow' if row['mode'] == 'valid' else 'propose')
        if row['mode'] == 'valid':
            assert 'authority_0' in row['keys'] and 'family_0' in row['keys']
            assert 'expands_0' not in row['keys']
            assert row['result']['telemetry']['coveredEntries'] == 1
        elif row['mode'] in {'missing', 'stale', 'foreign', 'update', 'confirm', 'disabled', 'unknown'}:
            assert 'family_0' not in row['keys']
