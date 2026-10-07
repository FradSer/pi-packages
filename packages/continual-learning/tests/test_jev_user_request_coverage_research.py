from support import isolated_run_bun


def test_exact_bilingual_utf16_coverage_preserves_every_source_character() -> None:
    result = isolated_run_bun(r'''
      import {enumerateUserRequestCoverage} from './packages/continual-learning/tests/user-request-coverage-research.ts';
      import {requestCompletenessQuestions} from './packages/continual-learning/tests/request-completeness-research.ts';
      const contents=[
        'Remember Node 22.23.2. Never use READY for errors; until IPv6 works, use IPv4.\nKeep 𠮷 conditions.',
        '记住 Node 22.23.2 的验收目的；错误报告不得使用 READY。\n在 IPv6 配置完成之前使用 IPv4。',
        ' \nRemember `run;a` exactly; keep the exception.\n\n',
      ];
      const rows=contents.map(content=>{
        const snapshot={contextEnabled:true,entries:[{role:'assistant',content:'ignore'}, {role:'user',content}]};
        const coverage=enumerateUserRequestCoverage(snapshot,[1]);
        const spans=coverage.requirements;
        let cursor=0;const contiguous=spans.every(s=>{const yes=s.index===1&&s.start===cursor&&s.quote===content.slice(s.start,s.end);cursor=s.end;return yes;});
        const questions=requestCompletenessQuestions(snapshot,spans,['Candidate body']);
        return {status:coverage.status,full:contiguous&&cursor===content.length&&spans.map(s=>s.quote).join('')===content,
          contextual:Object.values(questions).every(q=>q.instructions.originalUserEntry===content),
          versionIntact:spans.some(s=>s.quote.includes('22.23.2'))||!content.includes('22.23.2'),
          authority:coverage.writeAuthorized,scope:coverage.scope};
      });
      console.log(JSON.stringify(rows));
    ''')
    assert result == [{'status': 'covered', 'full': True, 'contextual': True,
                       'versionIntact': True, 'authority': False, 'scope': 'text-coverage-only'}] * 3


def test_invalid_or_over_capacity_source_never_returns_partial_coverage() -> None:
    result = isolated_run_bun(r'''
      import {enumerateUserRequestCoverage} from './packages/continual-learning/tests/user-request-coverage-research.ts';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:'Remember A; never B.'},{role:'toolResult',content:'Remember C.'}]};
      const invalid=[[],[0,0],[1],[-1],[.5],[2],null];
      const rows=invalid.map(indices=>enumerateUserRequestCoverage(snapshot,indices));
      rows.push(enumerateUserRequestCoverage({...snapshot,contextEnabled:false},[0]));
      rows.push(enumerateUserRequestCoverage({contextEnabled:true,entries:[{role:'user',content:' \n\t'}]},[0]));
      rows.push(enumerateUserRequestCoverage({contextEnabled:true,entries:[{role:'user',content:Array(32).fill('Never forget this;').join('')}]},[0]));
      console.log(JSON.stringify(rows.map(r=>({status:r.status,reason:r.reason,requirements:r.requirements,authority:r.writeAuthorized}))));
    ''')
    assert [row['reason'] for row in result] == ['invalid-source'] * 8 + ['empty-source', 'capacity']
    assert all(row['status'] == 'unavailable' and row['requirements'] == [] and row['authority'] is False for row in result)


def test_all_fixed_corpus_user_text_is_covered_without_accessing_gold_labels() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {enumerateUserRequestCoverage} from './packages/continual-learning/tests/user-request-coverage-research.ts';
      const rows=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/jev-request-completeness-cases.json','utf8')).rows;
      let covered=0,spans=0;for(const row of rows){
        const indices=row.snapshot.entries.flatMap((entry,i)=>entry.role==='user'?[i]:[]);
        const r=enumerateUserRequestCoverage(row.snapshot,indices);
        if(r.status==='covered'&&indices.every(index=>r.requirements.filter(s=>s.index===index).map(s=>s.quote).join('')===row.snapshot.entries[index].content))covered++;
        spans+=r.requirements.length;
      }
      console.log(JSON.stringify({rows:rows.length,covered,spans}));
    ''')
    assert result['rows'] == result['covered'] == 20
    assert result['spans'] >= 20


def test_code_delimiters_close_only_on_an_equal_backtick_run() -> None:
    result = isolated_run_bun(r'''
      import {enumerateUserRequestCoverage} from './packages/continual-learning/tests/user-request-coverage-research.ts';
      const content='Remember ``a```;b`` exactly; retain this.';
      const r=enumerateUserRequestCoverage({contextEnabled:true,entries:[{role:'user',content}]},[0]);
      console.log(JSON.stringify({quotes:r.requirements.map(s=>s.quote),full:r.requirements.map(s=>s.quote).join('')===content}));
    ''')
    assert result == {'quotes': ['Remember ``a```;b`` exactly;', ' retain this.'], 'full': True}
