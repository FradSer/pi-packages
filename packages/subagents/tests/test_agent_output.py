"""Typed bounded management projections; final answers stay outside this module."""
from __future__ import annotations

from pathlib import Path

from subagents_helpers import run_node

PREAMBLE = """
import assert from 'node:assert/strict';
import {Value} from 'typebox/value';
import * as output from './src/agent-output.ts';
const valid=result=>assert.ok(Value.Check(output.AGENT_TOOL_OUTPUT_SCHEMA,result.structuredContent),
  JSON.stringify([...Value.Errors(output.AGENT_TOOL_OUTPUT_SCHEMA,result.structuredContent)]));
const bounded=result=>{
  assert.ok(Buffer.byteLength(result.content[0].text)<=16384);
  assert.ok(result.content[0].text.split(/\\r\\n|\\r|\\n/).length<=200);
  assert.ok(Buffer.byteLength(JSON.stringify(result.details))<=32768);
  assert.ok(Buffer.byteLength(JSON.stringify(result.structuredContent))<=32768);valid(result);
};
const view=(i=0)=>({name:`reader-${i}`,session:`session:reader-${i}:exact-${i}`,status:'stopped',scope:'session',tools:['read'],sequenceEnded:true});
"""


def run(script: str, tmp_path: Path) -> None:
    result = run_node(PREAMBLE + script,env_overrides={
        'HOME':str(tmp_path),'PI_CODING_AGENT_DIR':str(tmp_path/'agent'),'PI_TEST_CWD':str(tmp_path),
    })
    assert result['ok'] is True


def test_unicode_bytes_and_lines_include_visible_marker(tmp_path: Path) -> None:
    run("""
      for(const raw of ['证据'.repeat(30000),'𐐀'.repeat(20000),'line\\n'.repeat(2000),'x'.repeat(20000)]){
        const preview=output.boundedToolText(raw);assert.ok(preview.truncation);
        assert.ok(Buffer.byteLength(preview.text)<=16384);assert.ok(preview.text.split('\\n').length<=200);
        assert.equal(preview.truncation.originalBytes,Buffer.byteLength(raw));
        assert.equal(preview.truncation.outputBytes,Buffer.byteLength(preview.text));
        assert.ok(preview.text.endsWith(preview.truncation.marker));assert.ok(!preview.text.includes('�'));
      }
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_schema_rejects_missing_handles_and_mismatched_outcomes(tmp_path: Path) -> None:
    run("""
      const base={ok:true,operation:'start',outcome:'started',state:'working',nextActor:'runtime',prompted:true};
      assert.deepEqual(output.CHILD_OPERATIONS,['start','input','list','stop']);
      assert.equal(Value.Check(output.AGENT_TOOL_OUTPUT_SCHEMA,base),false);
      assert.equal(Value.Check(output.AGENT_TOOL_OUTPUT_SCHEMA,{...base,name:'r',session:'session:r:s'}),true);
      assert.equal(Value.Check(output.AGENT_TOOL_OUTPUT_SCHEMA,{...base,operation:'list',outcome:'stopped'}),false);
      assert.equal(Value.Check(output.AGENT_TOOL_OUTPUT_SCHEMA,{ok:false,operation:'input',outcome:'error',state:'unknown',nextActor:'caller'}),false);
      const failure=output.createAgentFailure('invalid-bogus','invalid-action','wrong action');bounded(failure);
      assert.equal(failure.structuredContent.requestedOperation,'invalid-bogus');assert.equal(failure.structuredContent.operation,'invalid');
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_large_roster_record_retains_raw_state_and_idempotent_diagnostic(tmp_path: Path) -> None:
    run("""
      const raw={...view(),liveText:'证据\\n'.repeat(10000),error:'\\u001b[31m'+ 'e'.repeat(20000)};
      const before=JSON.stringify(raw);const result=output.createAgentListPage([raw],[]);bounded(result);
      assert.equal(result.structuredContent.state,'read-only');assert.equal(result.structuredContent.nextActor,'caller');
      const listed=result.details.sessions[0];assert.ok(listed.truncation.fields.length>=1);
      // A roster entry is a status summary, so it never carries the child's
      // output; the diagnostic beside it is bounded rather than dropped with it.
      assert.equal(listed.liveText,undefined);
      assert.ok(result.content[0].text.includes(listed.error));
      assert.equal(JSON.stringify(raw),before);
      const repeated=output.createAgentResult(result.content[0].text,result.structuredContent);bounded(repeated);
      assert.deepEqual(repeated.structuredContent,result.structuredContent);
      assert.equal(listed.error,'e'.repeat(1000)+'… [diagnostic truncated]');
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_pages_across_sessions_and_definitions_without_result_bodies(tmp_path: Path) -> None:
    run("""
      const sessions=Array.from({length:72},(_,i)=>({...view(i),liveText:'x'.repeat(16000),error:'e'.repeat(20000)}));
      const definitions=Array.from({length:13},(_,i)=>({name:`saved-${i}`,status:'offline',scope:'user',description:'d'.repeat(10000),tools:[]}));
      const before=JSON.stringify({sessions,definitions});const seen=[];let offset=0;
      do{
        const result=output.createAgentListPage(sessions,definitions,{offset,limit:50});bounded(result);
        assert.equal(result.structuredContent.total,85);assert.equal(result.structuredContent.count,72);
        for(const item of [...result.details.agents,...result.details.definitions]){
          assert.ok(!seen.includes(item.name));seen.push(item.name);assert.equal(item.liveText,undefined);
        }
        assert.equal(result.details.page.returned,result.details.sessions.length+result.details.definitions.length);
        offset=result.details.page.nextOffset;
      }while(offset!==undefined);
      assert.equal(seen.length,85);assert.equal(JSON.stringify({sessions,definitions}),before);
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_untrusted_truncation_metadata_cannot_disable_the_preview_budget(tmp_path: Path) -> None:
    run("""
      const raw={...view(),liveText:'x'.repeat(12000),error:'e'.repeat(2000),truncation:{omittedFields:[],fields:[
        {field:'liveText',truncated:true,reason:'bytes',originalBytes:12000,originalLines:1,outputBytes:1,outputLines:1,marker:'already bounded'},
        {field:'error',truncated:true,reason:'diagnostic',originalBytes:2000,originalLines:1,outputBytes:1,outputLines:1,marker:'already bounded'}]}};
      const before=JSON.stringify(raw);const result=output.createAgentListPage([raw],[]);bounded(result);
      const listed=result.details.sessions[0];
      // A forged "already bounded" claim restores neither field: the roster omits
      // output outright, and the diagnostic is bounded by the real budget.
      assert.equal(listed.liveText,undefined);
      assert.ok(listed.truncation.omittedFields.includes('liveText'));
      assert.ok(listed.truncation.fields.some(field=>field.field==='liveText'&&field.reason==='summary'));
      assert.ok(listed.error.length<=1024);assert.ok(listed.error.includes('diagnostic truncated'));
      assert.equal(JSON.stringify(raw),before);console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_required_input_preview_cannot_be_removed_to_fake_a_valid_success(tmp_path: Path) -> None:
    run("""
      const raw={operation:'input',delivery:'next',ok:true,outcome:'prompted',name:'reader',session:'session:reader:exact',
        state:'working',nextActor:'runtime',prompt:'x'.repeat(6000),prompted:true,grant:['g'.repeat(31000)]};
      const result=output.createAgentResult('Input accepted',raw);bounded(result);
      assert.ok(result.structuredContent.ok?typeof result.structuredContent.prompt==='string':result.structuredContent.code==='output-limit');
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_failure_and_exact_authority_limit_are_not_process_outcomes(tmp_path: Path) -> None:
    run("""
      const error=output.createAgentFailure('input','delivery-failed','\\u001b[31m'+ '证'.repeat(100000),
        {session:'session:reader:exact',state:'starting',dispatched:true,controlOutcome:'uncertain',pendingIntent:'input',nextActor:'caller'});
      bounded(error);assert.equal(error.structuredContent.controlOutcome,'uncertain');
      assert.equal(error.structuredContent.operation,'input');
      assert.equal(error.structuredContent.pendingIntent,'input');assert.ok(!error.content[0].text.includes('\\u001b'));
      const raw={...view(),assignment:{id:'task','kind':'task',resources:['x'.repeat(50000)]}};
      const before=JSON.stringify(raw);const limit=output.createAgentListPage([raw],[]);bounded(limit);
      assert.equal(limit.structuredContent.code,'output-limit');assert.equal(limit.structuredContent.session,raw.session);
      assert.ok(limit.structuredContent.limit.omittedFields.includes('assignment'));assert.equal(JSON.stringify(raw),before);
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)
