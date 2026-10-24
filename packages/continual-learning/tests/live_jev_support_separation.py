#!/usr/bin/env python3
"""Prepare source-support diagnostics; paid execution requires an owning proxy.

This authored corpus diagnoses one production question, not learning benefit or
threshold calibration. Full Memory approval still requires every original gate.
The preflight captures production requests with an offline SDK transport. Paid
mode sends only the captured support question, once per case, without retry.
An exclusive accounting owner must provide the loopback proxy and retain costs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

PKG = Path(__file__).resolve().parents[1]
REPO = PKG.parents[1]
CORPUS = PKG / 'tests/jev-support-separation-corpus.json'
MODEL = 'jev-1.14.0'


def corpus() -> dict:
    data = json.loads(CORPUS.read_text())
    cases = data.get('cases')
    if data.get('kind') != 'jev-support-separation-corpus' or data.get('version') != 2:
        raise ValueError('Expected the reviewed version 2 corpus')
    if not isinstance(cases, list) or len(cases) != 12:
        raise ValueError('Expected the fixed twelve-case diagnostic')
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or case.get('expected') not in {'grounded', 'negative'}:
            raise ValueError('Invalid case expectation')
        if not isinstance(case.get('id'), str) or not case['id'] or case['id'] in seen:
            raise ValueError('Missing or duplicate case identity')
        seen.add(case['id'])
        if not isinstance(case.get('candidate'), str) or not case['candidate'].strip():
            raise ValueError('Missing candidate')
        evidence = case.get('evidence')
        if not isinstance(evidence, list) or not evidence or any(
            not isinstance(e, dict) or e.get('role') not in {'user', 'toolResult'}
            or not isinstance(e.get('quote'), str) or not e['quote'].strip() for e in evidence
        ):
            raise ValueError('Missing original evidence')
    return data


def bun(script: str, payload: dict, *, owner: bool = False) -> dict:
    with tempfile.TemporaryDirectory(prefix='cl-support-separation-agent-') as agent:
        env = {**os.environ, 'PI_CODING_AGENT_DIR': agent}
        for name in ['TYPESAFE_API_KEY', 'TYPESAFE_BASE_URL']:
            env.pop(name, None)
        if not owner:
            env.pop('CL_SEPARATION_PROXY_URL', None)
            env.pop('CL_SEPARATION_PROXY_TOKEN', None)
        result = subprocess.run(['bun', '-e', script, json.dumps(payload)], cwd=REPO,
                                env=env, capture_output=True, text=True, timeout=240)
        if result.returncode:
            raise RuntimeError('Support diagnostic child failed; no service response inferred')
        return json.loads(result.stdout.strip().splitlines()[-1])


def prepare_jobs(cases: list[dict]) -> dict:
    """Capture the unchanged production support question with zero external calls."""
    return bun(r'''
      import {createHash} from 'node:crypto';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const input=JSON.parse(process.argv.at(-1)); const jobs=[];
      for(const c of input.cases){
        const requests=[];
        const judge=createJevJudge({enabled:true,apiKey:'fixture',defaultModel:input.model,
          scopes:['memory'],requestConcurrency:1,fetch:async(_url,init)=>{
            const request=JSON.parse(init.body);requests.push(request);const answers={};
            for(const [key,q]of Object.entries(request.questions)){
              if(q.type!=='choice')throw Error('Unexpected production primitive');
              const keys=Object.keys(q.criteria);
              const choice=keys.includes('grounded')?'grounded':keys.includes('compatible')?'compatible':keys[0];
              answers[key]={type:'choice',choice,confidence:1,
                probabilities:Object.fromEntries(keys.map(k=>[k,k===choice?1:0]))};
            }
            return Response.json({model:input.model,answers,usage:{input_tokens:0,output_tokens:0}});
          }});
        const candidateContent=`---\nname: Observed knowledge\ntype: project\n---\n${c.candidate}`;
        const evidence={contextEnabled:true,entries:c.evidence.map(e=>({message:{role:e.role,content:e.quote}}))};
        const candidate={name:'candidate.md',kind:'project',classification:'safe',content:candidateContent,
          evidence:c.evidence.map((e,index)=>({index,role:e.role,quote:e.quote}))};
        await judge.validate('memory',evidence,[candidate],[]);
        const source=requests.filter(r=>Object.hasOwn(r.questions,'supported_0'));
        if(source.length!==1||Object.keys(source[0].questions).join(',')!=='supported_0')
          throw Error('Production support request shape changed');
        const request=source[0];const text=JSON.stringify(request);
        if(text.includes(c.id)||text.includes('"expected"'))throw Error('Label leaked into model input');
        jobs.push({id:c.id,expected:c.expected,candidateContent,request,
          requestSha256:createHash('sha256').update(text).digest('hex')});
      }
      console.log(JSON.stringify({model:input.model,externalRequests:0,jobs}));
    ''', {'model': MODEL, 'cases': cases})


def run_judge(jobs: list[dict]) -> dict:
    """Use only an exclusive owner's proxy; do not discover ambient credentials."""
    address = os.environ.get('CL_SEPARATION_PROXY_URL', '')
    token = os.environ.get('CL_SEPARATION_PROXY_TOKEN', '')
    url = urlsplit(address)
    if url.scheme != 'http' or url.hostname != '127.0.0.1' or not url.port or url.username or url.password or url.query or url.fragment or not token:
        raise RuntimeError('Paid mode requires an exclusive accounting owner and its loopback proxy')
    if not 1 <= len(jobs) <= 12:
        raise ValueError('Expected at most twelve prepared jobs')
    return bun(r'''
      import fs from 'node:fs';
      import {createHash} from 'node:crypto';
      import {jevSdk,loadJevSdk} from './packages/continual-learning/extensions/jev-sdk.ts';
      import {observeMemoryJudgments} from './packages/continual-learning/tests/jev-memory-support-research.ts';
      if(!await loadJevSdk())throw Error('SDK unavailable');
      const input=JSON.parse(process.argv.at(-1));
      const ownerOrigin=new URL(process.env.CL_SEPARATION_PROXY_URL).origin;
      let physicalRequests=0;
      const client=new jevSdk.TypeSafeClient({apiKey:process.env.CL_SEPARATION_PROXY_TOKEN,
        baseURL:process.env.CL_SEPARATION_PROXY_URL,defaultModel:input.model,
        timeout:15000,retry:{maxRetries:0},compression:false,logLevel:'off',
        fetch:async(url,init)=>{
          if(new URL(String(url)).origin!==ownerOrigin||physicalRequests!==0)
            throw Error('Owner transport boundary refused');
          physicalRequests++;
          return fetch(url,{...init,redirect:'error'});
        }});
      const rows=[];
      for(const job of input.jobs){
        if(job.request.model!==input.model||Object.keys(job.request.questions).join(',')!=='supported_0'
          ||createHash('sha256').update(JSON.stringify(job.request)).digest('hex')!==job.requestSha256)
          throw Error('Prepared request binding changed');
        physicalRequests=0;
        const started=Date.now();
        let row={id:job.id,expected:job.expected,requestSha256:job.requestSha256,
          logicalAttempts:1,requestCount:0,completedRequests:0,status:'unavailable',sourceGatePassed:false,
          actualModel:null,answer:null,usage:null,costComplete:false};
        try{
          const r=await client.systemOne(job.request,{headers:{'TypeSafe-Danger-Zone-Long-Context':'true'}});
          const knownModel=/^jev-[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$/.test(r.model);
          const observed=knownModel?observeMemoryJudgments(job.request,r,r.model):undefined;
          const numeric=observed?.valid?observed.judgments[0]:undefined;
          const answer=numeric?.type==='choice'?{type:numeric.type,choice:numeric.choice,
            confidence:numeric.confidence,probabilities:numeric.probabilities}:null;
          const usage=r.usage&&['input_tokens','output_tokens'].every(k=>
            Number.isSafeInteger(r.usage[k])&&r.usage[k]>=0)?{
              input_tokens:r.usage.input_tokens,output_tokens:r.usage.output_tokens}:null;
          row={...row,actualModel:knownModel?r.model:null,answer,usage,
            status:r.model!==input.model?'model-mismatch':answer?'completed':'invalid-response',completedRequests:1,
            sourceGatePassed:r.model===input.model&&answer!==null&&answer.choice==='grounded'
              &&answer.probabilities.grounded>=0.9&&answer.confidence>=0.8};
          if(!knownModel)row.actualModelSha256=createHash('sha256').update(String(r.model)).digest('hex');
        }catch(e){row.errorCategory=e instanceof jevSdk.APITimeoutError?'timeout':
          e instanceof jevSdk.APIError?'http':e instanceof jevSdk.APIConnectionError?'connection':'unavailable';
          if(e instanceof jevSdk.APIError)row.httpStatus=e.status;}
        row.requestCount=physicalRequests;row.durationMs=Date.now()-started;rows.push(row);
        fs.appendFileSync(input.rowsFile,JSON.stringify(row)+'\n',{mode:0o600});
      }
      console.log(JSON.stringify({model:input.model,rows}));
    ''', {'model': MODEL, 'jobs': jobs, 'rowsFile': os.environ['CL_SEPARATION_ROWS_FILE']}, owner=True)


def summarize(rows: list[dict]) -> dict:
    completed = [r for r in rows if r['status'] == 'completed']
    positive = [r for r in completed if r['expected'] == 'grounded']
    negative = [r for r in completed if r['expected'] == 'negative']
    return {'cases': len(rows), 'completedCases': len(completed),
            'serviceFailures': len(rows) - len(completed),
            'falseAllows': sum(r['sourceGatePassed'] for r in negative),
            'falseHolds': sum(not r['sourceGatePassed'] for r in positive),
            'requests': sum(r['requestCount'] for r in rows),
            'completedRequests': sum(r['completedRequests'] for r in rows)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to reuse an output directory')
    data = corpus()
    prepared = prepare_jobs(data['cases'])
    args.output.mkdir(parents=True, mode=0o700)
    (args.output/'prepared-jobs.json').write_text(json.dumps(prepared, indent=2)+'\n')
    report = {'kind': 'jev-support-separation', 'version': 2, 'model': MODEL,
              'corpusSha256': hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
              'cases': len(data['cases']), 'positives': sum(c['expected']=='grounded' for c in data['cases']),
              'negatives': sum(c['expected']=='negative' for c in data['cases']),
              'externalRequests': 0, 'paid': False,
              'mutationAuthority': False, 'fullMemoryApproval': False, 'thresholdChanges': False,
              'boundary': 'Authored support-question diagnostic only, not full Memory approval, calibration, threshold authority or learning benefit.'}
    if args.preflight_only:
        (args.output/'preflight.json').write_text(json.dumps(report, indent=2)+'\n')
    else:
        os.environ['CL_SEPARATION_ROWS_FILE'] = str((args.output/'rows.jsonl').resolve())
        result = run_judge(prepared['jobs'])
        report.update(paid=True, rows=result['rows'], summary=summarize(result['rows']))
        report['clientFetchAttempts'] = report['summary']['requests']
        # Only the owning proxy knows which attempts reached the real service.
        report['externalRequests'] = None
        report['accountingOwnerMustSettleTransport'] = True
        report['costComplete'] = False
        (args.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
