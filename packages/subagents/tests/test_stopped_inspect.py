"""Stopped inspect regression: features/resident-execution.feature.

Read-only inspection accepts a known stopped exact roster entry. It does not
relax the living resolver used by process controls or introduce history storage.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from resident_support import run


@pytest.mark.parametrize("answer", ["2", "word " * 4000 + "COMPLETE_RESULT_TAIL"], ids=["short", "bounded-long"])
def test_stopped_inspection_reads_existing_bounded_facts_without_side_effects(
    tmp_path: Path, answer: str,
) -> None:
    run("""
      const start = await call({name:"calculator",prompt:"1+1",tools:[]});
      const session = start.details.session;
      const answer = ANSWER;
      final(0,answer);
      const stopped = await call({operation:"stop",session});
      assert.equal(stopped.details.outcome,"stopped");
      const before = JSON.stringify(roster.listAgents());
      const counts = [spawns.length,prompts.length,steers.length,notices.length,workspaces.length];
      const inspected = await call({operation:"inspect",session}, {
        terminate:async()=>assert.fail("inspection cannot terminate a process"),
      });
      assert.equal(inspected.details.ok,true,inspected.content[0].text);
      assert.notEqual(inspected.isError,true);
      assert.equal(inspected.details.outcome,"inspected");
      const [view] = inspected.details.sessions;
      assert.equal(view.session,session);assert.equal(view.status,"stopped");
      assert.equal(view.sequenceEnded,true);assert.equal(view.resultKind,"result");
      assert.ok(inspected.content[0].text.includes("calculator · stopped"));
      const listed = await call({operation:"list"});
      // agent-output.feature makes list status-only, while inspect keeps the
      // bounded individual answer; exact identity/status remain consistent.
      assert.equal(view.session,listed.details.sessions[0].session);
      assert.equal(view.status,listed.details.sessions[0].status);
      assert.equal(listed.details.sessions[0].liveText,undefined);
      if(answer.length<=8000) assert.equal(view.liveText,answer);
      else {
        assert.ok(answer.startsWith(view.liveText.split("\\n")[0]));
        assert.ok(Buffer.byteLength(view.liveText)<=8192);
        assert.match(view.liveText,/preview truncated/);
        assert.equal(notices[0].text,answer);
      }
      assert.equal(JSON.stringify(roster.listAgents()),before,"inspect must not change roster state");
      assert.deepEqual([spawns.length,prompts.length,steers.length,notices.length,workspaces.length],counts);
      console.log(JSON.stringify({ok:true}));
    """.replace("ANSWER", json.dumps(answer)), tmp_path)


def test_unexpectedly_closed_exact_incarnation_retains_diagnostics(tmp_path: Path) -> None:
    run("""
      const start=await call({name:"closed",prompt:"Review",tools:[]});
      spawns[0].onExit({pid:42,exitCode:1,signal:null,stdout:"",stderr:"LOCAL_CHILD_FAILURE"});
      const original=roster.getAgent("closed");
      assert.equal(original.status,"stopped");assert.ok(original.error);
      const before=JSON.stringify(original);
      const inspected=await call({operation:"inspect",session:start.details.session});
      assert.equal(inspected.details.ok,true,inspected.content[0].text);
      assert.notEqual(inspected.isError,true);
      assert.equal(inspected.details.sessions[0].status,"stopped");
      assert.equal(inspected.details.sessions[0].error,original.error);
      assert.ok(inspected.content[0].text.includes("error · "+original.error));
      assert.equal(JSON.stringify(original),before);assert.equal(spawns.length,1);
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


@pytest.mark.parametrize("origin", ["startup-failure", "runtime-error"])
def test_long_stopped_error_is_bounded_on_both_read_surfaces_without_mutating_roster(
    tmp_path: Path, origin: str,
) -> None:
    run("""
      const raw="\\u001b[31mLOCAL_ERROR_HEAD\\u001b[0m\\u0007"+" x".repeat(12000)+"RAW_ERROR_TAIL";
      const origin=ORIGIN;
      const started=await call({name:"long-error",prompt:"Review",tools:[]},origin==="startup-failure"
        ? {spawn:()=>({error:raw})}:{});
      if(origin==="runtime-error") {
        final(0,"original final answer");
        spawns[0].onError(new Error(raw));
        await new Promise(resolve=>setImmediate(resolve));
      }
      const original=roster.getAgent("long-error");
      assert.equal(original.status,"stopped");assert.equal(original.error,raw);
      const before=JSON.stringify(roster.listAgents());
      const counts=[spawns.length,prompts.length,steers.length,notices.length,workspaces.length];
      const {exactSessionRoute}=await import("file://"+process.cwd()+"/src/session-route.ts");
      const session=exactSessionRoute(original.name,original.spawnId);
      const inspected=await call({operation:"inspect",session});
      const listed=await call({operation:"list"});
      assert.equal(inspected.details.ok,true,inspected.content[0].text.slice(0,300));
      assert.notEqual(inspected.isError,true);
      const expected=("LOCAL_ERROR_HEAD"+" x".repeat(12000)+"RAW_ERROR_TAIL").slice(0,1000)+"… [diagnostic truncated]";
      for(const [read,view] of [[inspected,inspected.details.sessions[0]],[listed,listed.details.sessions[0]]]) {
        assert.equal(view.error.length,expected.length,"returned diagnostic must have a finite budget");
        assert.equal(view.error,expected);assert.equal(view.session,session);assert.equal(view.status,"stopped");
        assert.ok(read.content[0].text.includes("error · "+expected));
        assert.ok(!read.content[0].text.includes("RAW_ERROR_TAIL"));
        assert.ok(!JSON.stringify(read.details).includes("RAW_ERROR_TAIL"));
        assert.ok(!read.content[0].text.includes("\\u001b")&&!read.content[0].text.includes("\\u0007"));
        assert.ok(read.content[0].text.length<1800,"a single diagnostic cannot swamp context");
      }
      assert.equal(inspected.details.sessions[0].session,listed.details.sessions[0].session);
      assert.equal(inspected.details.sessions[0].status,listed.details.sessions[0].status);
      assert.equal(listed.details.sessions[0].liveText,undefined);
      assert.equal(JSON.stringify(roster.listAgents()),before);assert.equal(original.error,raw);
      assert.deepEqual([spawns.length,prompts.length,steers.length,notices.length,workspaces.length],counts);
      if(origin==="runtime-error") assert.equal(inspected.details.sessions[0].liveText,"original final answer");
      else assert.equal(started.details.ok,false);
      console.log(JSON.stringify({ok:true}));
    """.replace("ORIGIN",json.dumps(origin)),tmp_path)


@pytest.mark.parametrize("raw", ["short diagnosis", "x" * 1000, "x" * 1001, "\x1b[31mshort diagnosis\x1b[0m\x07"],
    ids=["short", "at-limit", "over-limit", "sanitized-short"])
def test_stopped_error_boundary_does_not_truncate_short_diagnostics(tmp_path: Path, raw: str) -> None:
    run("""
      const start=await call({name:"diagnostic-boundary",tools:[]});
      await call({operation:"stop",session:start.details.session});
      const raw=RAW;roster.updateAgent("diagnostic-boundary",{error:raw});
      const before=JSON.stringify(roster.listAgents());
      const safe=raw.includes("\\u001b")?"short diagnosis":raw;
      const expected=safe.length>1000?safe.slice(0,1000)+"… [diagnostic truncated]":safe;
      const read=await call({operation:"inspect",session:start.details.session});
      assert.equal(read.details.sessions[0].error,expected);
      assert.ok(read.content[0].text.includes("error · "+expected));
      assert.equal(JSON.stringify(roster.listAgents()),before);
      console.log(JSON.stringify({ok:true}));
    """.replace("RAW",json.dumps(raw)),tmp_path)


def test_stopped_read_does_not_relax_exact_control_resolution(tmp_path: Path) -> None:
    run("""
      const start=await call({name:"controls",prompt:"1+1",tools:[]});
      final(0,"2");await call({operation:"stop",session:start.details.session});
      const before=JSON.stringify(roster.listAgents());
      const counts=[spawns.length,prompts.length,steers.length,notices.length];
      const inspected=await call({operation:"inspect",session:start.details.session});
      assert.equal(inspected.details.ok,true,inspected.content[0].text);
      const {resolveExactSession}=await import("file://"+process.cwd()+"/src/session-route.ts");
      assert.equal(resolveExactSession(start.details.session,roster.listAgents()),undefined);
      for(const action of ["send","interrupt","stop"]) {
        const refused=await call({action,session:start.details.session,prompt:"Do not revive"}, {
          terminate:async()=>assert.fail("a stopped handle cannot invoke termination"),
        });
        assert.equal(refused.details.ok,false,JSON.stringify(refused));assert.equal(refused.isError,true);
      }
      assert.equal(JSON.stringify(roster.listAgents()),before);
      assert.deepEqual([spawns.length,prompts.length,steers.length,notices.length],counts);
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_unknown_and_replaced_inspection_does_not_substitute_a_successor(tmp_path: Path) -> None:
    run("""
      const first=await call({name:"replacement",prompt:"First",tools:[]});
      final(0,"FIRST_ONLY");await call({operation:"stop",session:first.details.session});
      const second=await call({name:"replacement",prompt:"Second",tools:[]});
      final(1,"SECOND_ONLY");
      const before=JSON.stringify(roster.listAgents());
      for(const session of [first.details.session,"session:missing:unknown"]) {
        const missing=await call({operation:"inspect",session});
        assert.equal(missing.details.ok,false);assert.equal(missing.isError,true);
        assert.ok(missing.content[0].text.includes(`No known session "${session}".`),missing.content[0].text);
        assert.ok(!missing.content[0].text.includes("SECOND_ONLY"));
        assert.equal(missing.details.sessions,undefined);
      }
      const live=await call({operation:"inspect",session:second.details.session});
      assert.equal(live.details.ok,true);assert.equal(live.details.sessions[0].liveText,"SECOND_ONLY");
      assert.equal(JSON.stringify(roster.listAgents()),before);assert.equal(spawns.length,2);
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)
