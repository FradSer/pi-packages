from support import isolated_run_bun


def test_complete_citation_catalog_is_encoded_once_without_weakening_schema() -> None:
    result = isolated_run_bun(r'''
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      import {Value} from 'typebox/value';
      const domain={indices:[0],refs:Array.from({length:2000},(_,i)=>`e0.b0.l${i+1}`)};
      const schema=learningOutputSchema('memory-delta',domain),encoded=JSON.stringify(schema);
      const occurrences=encoded.split('"e0.b0.l2000"').length-1;
      const content='---\nname: p\ndescription: Unverified candidate\ntype: project\n---\nClaim';
      const base={kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'x',operations:[],newMemories:[{name:'p.md',kind:'preference',content,evidence:[{ref:domain.refs.at(-1)}]}]};
      const valid=Value.Check(schema,base),invalid=Value.Check(schema,{...base,newMemories:[{...base.newMemories[0],evidence:[{ref:'e0.b0.l2001'}]}]});
      console.log(JSON.stringify({occurrences,complete:schema.$defs?.memorySourceReference.enum.length===domain.refs.length,valid,invalid,bytes:Buffer.byteLength(encoded)}));
    ''')
    assert result['occurrences'] == 1
    assert result['complete'] and result['valid'] and not result['invalid']


def test_real_generation_schema_expansion_retains_every_legacy_constraint_and_reference() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      const old=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-generation-schema.json','utf8')).schema;
      const refs=old.properties.operations.items.anyOf[0].properties.evidence.items.properties.ref.enum;
      const domain={indices:[...new Set(refs.map(ref=>Number(/^e(\d+)/.exec(ref)[1])))],refs,fileRefs:refs};
      const current=learningOutputSchema('memory-delta',domain);
      // When every synthetic catalog position is file-capable, the original two
      // branches remain equivalent after expansion. Real fileRefs is a strict
      // parent-derived subset; the new producer source unit is a distinct capability.
      const legacy=structuredClone(current);
      const added=legacy.properties.newMemories.items.anyOf.splice(1);
      // Fresh project source excerpts moved to atomic knowledge; legacy remains unchanged.
      legacy.properties.newMemories.items.anyOf.push(old.properties.newMemories.items.anyOf[1]);
      const projectProducerMoved=JSON.stringify(legacy.properties.newMemories.items.anyOf[0].properties.kind.enum)==='["preference"]';
      // Only the initial producer's project representation moves to knowledge.
      // Restore this declared difference for the exact legacy constraint check.
      legacy.properties.newMemories.items.anyOf[0].properties.kind=old.properties.newMemories.items.anyOf[0].properties.kind;
      const expand=value=>{
        if(Array.isArray(value))return value.map(expand);
        if(!value||typeof value!=='object')return value;
        if(value.$ref){const key=value.$ref.slice('#/$defs/'.length);if(!['memorySourceReference','memoryFileSourceReference'].includes(key))throw Error('Unexpected ref');return current.$defs[key];}
        return Object.fromEntries(Object.entries(value).filter(([key])=>key!=='$defs').map(([key,item])=>[key,expand(item)]));
      };
      const sort=value=>Array.isArray(value)?value.map(sort):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,sort(value[key])])):value;
      console.log(JSON.stringify({equivalent:JSON.stringify(sort(expand(legacy)))===JSON.stringify(sort(old)),
        projectProducerMoved,addedProjectSourceBranch:added.length===1&&JSON.stringify(added[0].properties.classification.enum)==='["safe","private"]'
          &&added[0].properties.kind.const==='project'&&added[0].required.includes('knowledge'),
        refs:refs.length,oldBytes:Buffer.byteLength(JSON.stringify(old)),newBytes:Buffer.byteLength(JSON.stringify(current)),
        occurrences:JSON.stringify(current).split(JSON.stringify(refs.at(-1))).length-1}));
    ''')
    assert result['equivalent'] and result['projectProducerMoved'] and result['addedProjectSourceBranch'] and result['refs'] > 0
    assert result['occurrences'] == 1
    assert result['newBytes'] < result['oldBytes'] / 2
