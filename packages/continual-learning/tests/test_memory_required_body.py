from support import isolated_run_bun


def test_real_frontmatter_only_proposal_requires_actual_knowledge_body() -> None:
    # Given the original completed real plan has only discovery metadata,
    # When parent normalizes it before body/Jev review, Then reject it as a
    # structural error without turning the description into knowledge.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {normalizeNewMemoryProposals} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-frontmatter-only.json','utf8'));
      const original=JSON.stringify(fixture.plan);
      const plan=resolveMemoryPlanCitations(fixture.plan,fixture.snapshot);
      let error;try{normalizeNewMemoryProposals(plan,fixture.snapshot)}catch(e){error=e.message}
      console.log(JSON.stringify({error,unchanged:original===JSON.stringify(fixture.plan)}));
    ''')
    assert value.get('error') and 'non-empty Memory body' in value['error']
    assert value['unchanged']


def test_generation_and_repair_schemas_require_body_after_metadata() -> None:
    value = isolated_run_bun(r'''
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      const delta=learningOutputSchema('memory-delta');
      const amendment=learningOutputSchema('memory-amendment');
      const fields=[delta.properties.newMemories.items.anyOf[0].properties.content,
        delta.properties.operations.items.anyOf[0].properties.content,
        amendment.properties.replacements.items.properties.content];
      const empty='---\nname: fact\ndescription: Discovery metadata\ntype: project\n---\n  \t\n';
      const complete=empty+'Actual grounded body.\n';
      console.log(JSON.stringify(fields.map(field=>({pattern:field.pattern,
        emptyAccepted:field.pattern===undefined||new RegExp(field.pattern).test(empty),
        completeAccepted:field.pattern===undefined||new RegExp(field.pattern).test(complete)}))));
    ''')
    assert all(item.get('pattern') and not item['emptyAccepted'] and item['completeAccepted'] for item in value)


def test_parent_and_independent_validator_agree_on_metadata_only_writes() -> None:
    import importlib.util
    import json
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "validate-consolidate.py"
    spec = importlib.util.spec_from_file_location("memory_body_validator", script)
    assert spec and spec.loader
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    header = "---\nname: fact\ndescription: Discovery metadata\ntype: project\n---\n"
    documents = [header, header + " \t\n", "\ufeff" + header.replace("\n", "\r\n") + "\u00a0\ufeff", "", "\t\n",
                 header + "Grounded knowledge.\n", "Legacy knowledge without frontmatter.\n"]
    results = []
    for content in documents:
        try:
            validator.require_memory_body(content, "candidate")
            results.append(True)
        except validator.ValidationError as error:
            assert "non-empty Memory body" in str(error)
            results.append(False)
    actual = isolated_run_bun(r'''
      import {assertMemoryBodyContent} from './packages/continual-learning/extensions/consolidation-run.ts';
      const documents=''' + json.dumps(documents) + r''';
      console.log(JSON.stringify(documents.map(content=>{try{assertMemoryBodyContent(content,'candidate');return true}catch{return false}})));
    ''')
    assert actual == results == [False] * 5 + [True, True]
    # The independent validator must enforce the rule on actual mutation operations.
    for kind in ("create", "rewrite"):
        try:
            validator.validate_operations([{"name": "fact.md", "kind": kind, "classification": "private", "content": header}],
                ["fact.md"], {"fact.md": {"classification": "private"}}, {"fact.md": {"verdict": "KEEP"}}, None, [])
        except validator.ValidationError as error:
            assert "non-empty Memory body" in str(error)
        else:
            raise AssertionError("Independent validator admitted a metadata-only write")


def test_actual_pi_structural_repair_has_source_and_keeps_parent_intent(tmp_path) -> None:
    import json
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';import {spawnSync} from 'node:child_process';import fs from 'node:fs';import path from 'node:path';
      const kit=await import('./packages/kit/src/index.ts');const root=ROOT;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        const env={PATH:process.env.PATH,HOME:root,PI_CODING_AGENT_DIR:path.join(root,'agent'),PI_OFFLINE:'1'};
        const native=spawnSync('node',[path.resolve('node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js'),'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-tools','-e',path.resolve('packages/continual-learning/tests/memory-amendment-live-fixture.ts'),'--missing-memory-body','enabled','--provider','amendment-fixture','--model','fixed','--thinking','off','--no-session','--print','--mode','json',input.prompt],{cwd:root,env,encoding:'utf8',timeout:40000});
        fs.writeFileSync(path.join(root,'native-pi-output.jsonl'),native.stdout);
        if(native.status!==0)throw new Error(native.stderr+'\n'+native.stdout);
        return {...kit.parsePiWorkerOutput(native.stdout),exitCode:0,stderr:'',cancelled:false};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {normalizeNewMemoryProposals}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const snapshot={contextEnabled:true,entries:[{type:'message',message:{role:'toolResult',content:'Correct claim'}}]};
      const candidate={name:'fact.md',kind:'project',classification:'private',content:'---\nname: fact\ndescription: Discovery only\ntype: project\n---\n',evidence:[{index:0,quote:'Correct claim'}]};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[candidate]};
      const input={identity,rejectedPlan:original,errors:['candidate requires a non-empty Memory body'],selectedNames:[],structuralCorrection:true,semanticContext:{frozenEvidence:snapshot,existingMemories:[]}};
      const result=await repairIncrementalMemoryPlan(input);
      const normalized=result.plan?normalizeNewMemoryProposals(result.plan,snapshot):[];
      console.log(JSON.stringify({result,normalized,original,wroteMemory:fs.existsSync(path.join(root,'.memory'))}));
    '''.replace('ROOT', json.dumps(str(tmp_path))))
    assert value['result']['outcome'] == 'repaired', value['result']
    old = value['original']['newMemories'][0]
    corrected = value['result']['plan']['newMemories'][0]
    assert all(corrected[key] == old[key] for key in ('name', 'kind', 'classification', 'evidence'))
    assert corrected['content'] == old['content'] + 'Correct claim\n'
    assert len(value['normalized']) == 1 and not value['wroteMemory']
    # This proves the native structural correction interface, not semantic approval or task benefit.
