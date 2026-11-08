"""The learning backlog: settled work that was never learned from.

Learning is opportunistic today. A task is learned when it settles, if
auto-learning is on and the zero-token screen finds durable evidence. Everything
else is dropped, and a heuristic screen making an irreversible discard is the gap
this closes.

Two properties matter and are asserted rather than assumed. The backlog stores
**references, not content** — a session file and entry indices, never the text —
so it is an index over conversations rather than a second copy of them. And an
entry whose session file has been removed is **reported as unlearnable**, never
silently dropped or reconstructed, because a backlog that looks drained when it
was not is worse than one that never existed.
"""

from __future__ import annotations

from support import isolated_run_bun

SNIPPET = r"""
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const B = await import('./packages/continual-learning/extensions/learning-backlog.ts');
      const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'backlog-')));
      const cwd = path.join(root,'project'), agent = path.join(root,'agent');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(agent,{recursive:true});
      const session = path.join(root,'session.jsonl');
      const writeSession = (lines) => fs.writeFileSync(session, lines.join('\n')+'\n');
      writeSession([JSON.stringify({message:{role:'user',content:'a'}})]);

      // Two tasks queued while their session existed.
      B.enqueueBacklog({cwd, sessionFile:session, from:0, to:2, digest:'d1', reason:'screen-found-nothing', agentDir:agent});
      B.enqueueBacklog({cwd, sessionFile:session, from:3, to:5, digest:'d2', reason:'settled-learning-off', agentDir:agent});
      // One whose session file will not survive.
      const gone = path.join(root,'deleted.jsonl');
      fs.writeFileSync(gone, '{}\n');
      B.enqueueBacklog({cwd, sessionFile:gone, from:0, to:1, digest:'d3', reason:'settled-learning-off', agentDir:agent});
      fs.unlinkSync(gone);

      const beforeCursor = B.backlogStatus(cwd, agent);
      const raw = fs.readFileSync(B.backlogFile(cwd, agent), 'utf-8');
      B.advanceCursor(cwd, 1, agent);
      const afterCursor = B.backlogStatus(cwd, agent);
      // An entry with no session reference is refused rather than queued blind.
      const noSession = B.enqueueBacklog({cwd, sessionFile:undefined, from:0, to:1, digest:'d4', reason:'no-session-reference', agentDir:agent});
      const insideMemoryRoot = B.backlogFile(cwd, agent).includes(path.join('memory', path.sep));
      console.log(JSON.stringify({
        beforeCursor, afterCursor, noSession,
        insideMemoryRoot,
        relative: path.relative(agent, B.backlogFile(cwd, agent)),
        // The decisive property: no conversation text anywhere in the file.
        carriesContent: /"content"|"message"|"role"/.test(raw),
        entryKeys: Object.keys(JSON.parse(raw.split('\n')[0])),
        reasons: raw.split('\n').filter(Boolean).map((l) => JSON.parse(l).reason),
      }));
"""


def test_the_backlog_stores_references_and_never_content() -> None:
    value = isolated_run_bun(SNIPPET)
    # An index over conversations, not a copy of them.
    assert value["carriesContent"] is False, value
    assert value["entryKeys"] == ["version", "sessionFile", "from", "to", "digest", "reason", "queuedAt", "scopeKey"], value
    # A task with no session reference cannot be queued blind.
    assert value["noSession"] is False, value


def test_a_missing_session_file_is_reported_not_silently_dropped() -> None:
    value = isolated_run_bun(SNIPPET)
    assert value["beforeCursor"]["unlearnable"] == 1, value
    assert value["beforeCursor"]["pending"] == 2, value
    assert value["beforeCursor"]["reason"] == "ready", value


def test_the_cursor_advances_without_losing_or_re_queuing() -> None:
    value = isolated_run_bun(SNIPPET)
    assert value["afterCursor"]["consumed"] == 1, value
    # Consumed entries are not deleted: the backlog is evidence, and re-reading
    # it must still show what was there.
    assert value["afterCursor"]["unlearnable"] == 1, value


def test_the_backlog_never_lands_inside_a_memory_root() -> None:
    value = isolated_run_bun(SNIPPET)
    # A Memory root admits only regular `.md` children; a JSONL backlog beside
    # them fails privacy validation and aborts consolidation.
    assert value["insideMemoryRoot"] is False, value
    assert value["relative"].startswith("learning/"), value


def test_legacy_reason_rows_do_not_disable_replay_binding_for_other_scopes() -> None:
    # Given a global backlog file with old "auto-memory-off" rows from a 2026-11-03
    # rename, When the current scope has no malformed rows, Then replay binding
    # stays available. A genuinely malformed row in the SAME scope still fails
    # closed, so the compatibility read never weakens the fail-closed gate.
    value = isolated_run_bun(r"""
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const B = await import('./packages/continual-learning/extensions/learning-backlog.ts');
      const R = await import('./packages/continual-learning/extensions/learning-replay.ts');
      const {resolveMemoryPaths} = await import('./packages/continual-learning/extensions/memory-paths.ts');
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'backlog-legacy-')));
      const cwd=path.join(root,'project'),agent=path.join(root,'agent');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(agent,{recursive:true});
      const session=path.join(root,'session.jsonl');
      fs.writeFileSync(session,JSON.stringify({message:{role:'user',content:'a'}})+'\n');
      const file=B.backlogFile(cwd,agent);fs.mkdirSync(path.dirname(file),{recursive:true});
      const scope=resolveMemoryPaths(cwd,agent).scopeKey;
      const other='--other--';
      const legacy=row=>JSON.stringify({version:1,sessionFile:session,from:0,to:1,digest:row,reason:'auto-memory-off',queuedAt:new Date().toISOString(),scopeKey:other});
      fs.writeFileSync(file,[legacy('one'),legacy('two')].join('\n')+'\n');
      const clean=B.readBacklog(cwd,agent),status=B.backlogStatus(cwd,agent);
      // A current-scope pending row must still bind and be retryable.
      const input={cwd,sessionFile:session,from:2,to:3,digest:'current-task',reason:'settled-learning-off',agentDir:agent};
      const queued=B.enqueueBacklog(input),pending=B.readBacklog(cwd,agent).pendingEntries.map(({entry})=>entry);
      const bound=pending.length?R.beginBacklogAttempt(cwd,pending[0],agent):false;
      // A genuinely malformed row in the SAME scope still fails closed.
      fs.appendFileSync(file,'{ not json\n');
      const broken=B.readBacklog(cwd,agent);
      const boundAfter=bound?R.beginBacklogAttempt(cwd,pending[0],agent):false;
      console.log(JSON.stringify({cleanMalformed:clean.malformed,cleanError:clean.error??null,
        quarantined:clean.quarantined,legacyPending:clean.pending,scope,
        statusMalformed:status.malformed,queued,pendingCount:pending.length,bound,boundAfter,
        brokenMalformed:broken.malformed}));
    """)
    assert value["cleanMalformed"] == 0, value
    assert value["cleanError"] is None, value
    assert value["quarantined"] == 2, value
    assert value["legacyPending"] == 0, value
    assert value["statusMalformed"] == 0, value
    assert value["queued"] is True and value["pendingCount"] == 1, value
    assert value["bound"] is True, value
    assert value["brokenMalformed"] >= 1, value
    assert value["boundAfter"] is False, value
