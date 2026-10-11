"""AGENTS receives the evidence it is required to read; failures stay visible."""
from support import run_bun


def test_agents_child_can_read_supplied_dossier_but_not_its_sibling():
    result=run_bun(r'''
      import {mock} from 'bun:test';
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import {createHash} from 'node:crypto';import {EventEmitter} from 'node:events';
      const base=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'agents-dossier-')));
      const cwd=path.join(base,'project'),runDir=path.join(base,'run');fs.mkdirSync(cwd);fs.mkdirSync(runDir);
      fs.writeFileSync(path.join(cwd,'AGENTS.md'),'# Rules\n');
      const snapshotPath=path.join(runDir,'snapshot.json');const snapshot=JSON.stringify({entries:[]});fs.writeFileSync(snapshotPath,snapshot);
      const digest=createHash('sha256').update(snapshot).digest('hex');
      const dossier=path.join(runDir,'dossier.json');fs.writeFileSync(dossier,'{"verified":"project evidence"}');
      const sibling=path.join(runDir,'unapproved.json');fs.writeFileSync(sibling,'not authorized');
      const {readPlannerFile}=await import('./packages/continual-learning/extensions/planner-read-scope.ts');
      const kit=await import('./packages/kit/src/index.ts');let readable=false,blocked=false;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,spawnPiChild:(_command,args)=>{
        const child=new EventEmitter();child.stdout=new EventEmitter();child.stderr=new EventEmitter();
        setTimeout(async()=>{
          const scopeFile=args.find(a=>typeof a==='string'&&a.includes('planner-read-')&&a.endsWith('.mjs'));
          const code=fs.readFileSync(scopeFile,'utf8');const scope=JSON.parse(code.match(/registerPlannerRead\(pi, (.+)\);/)[1]);
          try{readable=(await readPlannerFile(dossier,scope)).includes('project evidence');}catch{}
          try{await readPlannerFile(sibling,scope);}catch{blocked=true;}
          const text=readable?JSON.stringify({kind:'agents-md-consolidation-plan',version:1,schemaVersion:1,runId:'run',scopeDigest:'scope',artifactHash:digest,operations:[]}):'Cannot produce a plan: the required dossier read was refused';
          child.stdout.emit('data',Buffer.from(JSON.stringify({type:'message_end',message:{role:'assistant',stopReason:'stop',content:[{type:'text',text}]}})+'\n'));child.emit('close',0);
        },0);return child;
      }}));
      const {planAgentsMdConsolidationPhase}=await import('./packages/continual-learning/extensions/agents-md-consolidation.ts');
      const run={manifest:{runId:'run',scopeDigest:'scope',snapshotDigest:digest,snapshotPath,cwd,runDir},paths:{snapshotFile:snapshotPath}};
      const planned=await planAgentsMdConsolidationPhase({cwd,ui:{notify(){}}},{active:true,generation:1,cancelled:false},{pkgDir:process.cwd(),cwd,reason:'test',budgetBytes:16384,disabled:false,explorationPath:dossier},run,1);
      fs.rmSync(base,{recursive:true,force:true});console.log(JSON.stringify({readable,blocked,outcome:planned.outcome}));
    ''')
    assert result == {'readable':True,'blocked':True,'outcome':'noop'}


def test_agents_diagnostics_are_bounded_filtered_and_wired_into_receipts():
    result=run_bun(r'''
      import {agentsAttemptDiagnostic} from './packages/continual-learning/extensions/inject-memory.ts';
      console.log(JSON.stringify({normal:agentsAttemptDiagnostic('child output did not contain a structured consolidation plan'),secret:agentsAttemptDiagnostic('api_key=THIS_IS_A_SYNTHETIC_SECRET'),long:agentsAttemptDiagnostic('x'.repeat(5000)),private:agentsAttemptDiagnostic('customer notes: synthetic private business text'),missing:agentsAttemptDiagnostic(undefined)??null}));
    ''')
    assert result['normal']=='AGENTS planner returned no structured plan'
    assert result['private']=='AGENTS phase failed; unclassified diagnostic'
    assert result['long']=='AGENTS phase failed; unclassified diagnostic'
    assert 'THIS_IS_A_SYNTHETIC_SECRET' not in result['secret']
    assert len(result['long']) <= 800
    assert result['missing'] is None
