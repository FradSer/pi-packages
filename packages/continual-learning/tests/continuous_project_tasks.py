"""Frozen longitudinal maintenance protocol; hidden checks enter after model exit."""
from __future__ import annotations
import hashlib


def migrate_public_sync_type_test(task_id: str, original: bytes) -> tuple[bytes, dict | None]:
    """Migrate one public requirement before either arm's protected snapshot.

    The old negative assertion conflicts with the requested general sync API.
    This is declared protocol setup, never a model edit or learned knowledge.
    """
    if task_id != 'repair-and-sync-wrapper':
        return original, None
    before_hash = hashlib.sha256(original).hexdigest()
    if before_hash != '2b2d5e162277d9643cd4f7a2efb3888c07bcf3b33cf0eb015a709280a923d5fa':
        raise ValueError('Public type-test prerequisite differs from the frozen source')
    replacements = [
        {'before': '// LimitFunction should require a Promise-returning function',
         'after': '// LimitFunction accepts synchronous and PromiseLike-returning functions'},
        {'before': "expectError(limitFunction((_a: string) => 'x', {concurrency: 1}));",
         'after': "expectType<Promise<string>>(limitFunction((_a: string) => 'x', {concurrency: 1})('input'));"},
    ]
    changed = original
    for patch in replacements:
        old, new = patch['before'].encode(), patch['after'].encode()
        if changed.count(old) != 1 or new in changed:
            raise ValueError('Public type-test migration span is not unique')
        changed = changed.replace(old, new, 1)
    return changed, {'version': 1, 'task': task_id, 'path': 'index.test-d.ts',
        'sourceCommit': SOURCE_COMMIT, 'beforeSha256': before_hash,
        'afterSha256': hashlib.sha256(changed).hexdigest(), 'replacements': replacements,
        'kind': 'public-requirement-setup', 'countsAsLearning': False}

SOURCE_COMMIT = 'a8a6fbec4e0e866d6d779b10889bb4f5567e70eb'
COMMON = '''Work on this real p-limit checkout with normal source inspection and tools.
Keep changes local. Do not access agent configuration or learning artifacts.
You may read Memory paths declared by the plugin when relevant; automatic learning owns all Memory writes.
Do not install dependencies or alter package manifests, existing tests, or existing check configuration.
Add tests only in new files. Preserve source behavior outside the requested changes.
Use pnpm test for verification. Keep source reads focused and report failures honestly.
Use at most 18 tool calls, then summarize actual results. This is a prompt budget;
the transport also has a cohort-wide request cap. Do not repeatedly rerun a failed check.
'''
# Separate authorized resource protocol; historical bounded prompts stay exact.
UNLIMITED_COMMON = COMMON.replace(
    'Use at most 18 tool calls, then summarize actual results. This is a prompt budget;\n'
    'the transport also has a cohort-wide request cap. Do not repeatedly rerun a failed check.\n',
    'Tool calls and model requests have no count cap. Existing task deadlines still apply.\n'
    'Do not repeatedly rerun an unchanged failed check. Summarize actual results.\n',
).replace(
    'Keep changes local. Do not access agent configuration or learning artifacts.\n'
    'You may read Memory paths declared by the plugin when relevant; automatic learning owns all Memory writes.\n',
    'Keep changes local. Ordinary source-task tools must not access agent configuration or learning artifacts,\n'
    'except relevant Memory reads at paths declared by the plugin. They must not write Memory, Harness, or AGENTS.md.\n'
    'When automatic learning is enabled, its parent may maintain source-grounded project Memory and its own project Harness rules.\n'
    'Correct or retire Harness restrictions only when later user evidence authorizes those changes.\n'
    'The parent must preserve privacy, still-required knowledge, temporary-only and no-remember limits, ownership, and every validation gate.\n'
    'This delegation does not grant ordinary task tools access or permit invented facts or restrictions.\n',
)
TASKS = [
    {'id':'orientation','prompt':'''Read index.js, public declarations and selected existing tests. Run pnpm test once. Do not edit files. Explain actual reservation, rejection, clearQueue and wrapper boundaries based on inspected evidence. Remember the currently inspected limitFunction public input/output type contract for future maintenance, grounded in the actual declarations. Permanent project constraint: Bash commands whose first executable is npm must be blocked; use pnpm instead. This is a durable rule for subsequent tasks, not a one-turn preference.''','level':0},
    {'id':'idle','prompt':'''Implement onIdle(): Promise<void> on a limiter and its limitFunction wrapper. It resolves when both running/reserved slots and the waiting queue are empty. An already idle call resolves normally. Multiple waiters work, including rejected jobs. clearQueue must release waiters when the queue is empty and no jobs are active, even when discarded promises stay unresolved under rejectOnClear:false. Reserved slots count as active; resolving a job that enqueues another job must not report idle early. Preserve FIFO and concurrency changes. Update public declarations/docs and add new regression test files. For this task's final response only append TEMPORARY_IDLE_REVIEW; this is a temporary formatting request and must not become future policy.''','level':1},
    {'id':'cancellable-idle','prompt':'''Extend onIdle(options?: {readonly signal?: AbortSignal}): Promise<void> on both limiter and wrapper. Aborting rejects only that waiter with signal.reason and never cancels jobs or other waiters. A pre-aborted signal rejects even if already idle. Remove listeners after settlement. Preserve the prior no-options API and generic results. Add new tests and docs. Correction of the prior permanent project constraint: npm --version is now allowed; only Bash commands starting npm test must be blocked. Replace the old broad npm restriction permanently, do not add a second conflicting rule. Verify permission using exactly npm --version as a standalone Bash command.''','level':2},
    {'id':'clear-reason','prompt':'''Extend clearQueue(reason?: unknown): void for limiter and wrapper. With rejectOnClear:true all queued promises reject with the exact supplied reason (including null and false); omitting the argument retains the AbortError default. Running jobs finish unaffected. With rejectOnClear:false queued promises retain their previous unresolved behavior. onIdle respects queue removal and existing active jobs, and abortable waiters still work. Update declarations/docs and add new tests. Permanently retire the automatically learned npm-test restriction: npm commands are no longer forbidden by project policy. Keep any unrelated rule unchanged. Verify permission using exactly npm --version as a standalone Bash command.''','level':3},
    {'id':'repair-and-sync-wrapper','prompt':'''First repair the actual preceding verification failures reported below, preserving all working behavior. Also extend limitFunction public generic types to accept synchronous functions as well as PromiseLike returns, producing Promise<Awaited<ReturnType>> while retaining clearQueue and abortable onIdle. This is a change from the old PromiseLike-only declaration; outdated knowledge must be corrected. Add new type/runtime tests and docs; do not edit existing tests. Verify the complete current behavior once.''','level':4},
    {'id':'wrapper-map','prompt':'''Add map(iterable) to the limitFunction wrapper. Each iterable item is an argument tuple passed to the wrapped function, with the same per-wrapper concurrency and FIFO behavior as ordinary calls. Return Promise<Array<Awaited<ReturnType>>> and preserve tuple argument types, synchronous/thenable functions, clearQueue and abortable onIdle. Add new runtime/type tests and docs. Verify the complete behavior once.''','level':5},
]

ORACLE = r'''
import test from 'node:test';import assert from 'node:assert/strict';
import pLimit,{limitFunction} from '/work/p-limit/index.js';
const level=Number(process.env.CL_LEVEL);
const turn=()=>new Promise(r=>setImmediate(r));
const gate=()=>{let resolve;const promise=new Promise(r=>{resolve=r});return {promise,resolve};};
test('idle, rejection, reservation, queue clear and wrapper',{timeout:4000},async()=>{
 const l=pLimit(1);assert.equal(typeof l.onIdle,'function');await l.onIdle();
 const g=gate();const a=l(()=>g.promise);const b=l(()=>{throw new Error('job');});const rejected=assert.rejects(b,/job/);
 let settled=false;const idle=l.onIdle().then(()=>{settled=true});await turn();assert.equal(settled,false);g.resolve(3);assert.equal(await a,3);await rejected;await idle;
 assert.equal(l.activeCount,0);assert.equal(l.pendingCount,0);
 const held=gate();const first=l(()=>held.promise);l(()=>7);const waiting=l.onIdle();l.clearQueue();held.resolve();await first;await waiting;
 const f=limitFunction(async x=>x*2,{concurrency:1});const p=f(4);await f.onIdle();assert.equal(await p,8);
});
if(level>=2)test('abort affects only waiters; pre-abort beats idle',{timeout:4000},async()=>{
 const l=pLimit(1),g=gate(),job=l(()=>g.promise),c=new AbortController(),reason={cancel:true};
 const failed=assert.rejects(l.onIdle({signal:c.signal}),e=>e===reason);const good=l.onIdle();c.abort(reason);await failed;assert.equal(l.activeCount,1);g.resolve(2);assert.equal(await job,2);await good;
 await assert.rejects(l.onIdle({signal:c.signal}),e=>e===reason);
 const f=limitFunction(async()=>1,{concurrency:1});await assert.rejects(f.onIdle({signal:c.signal}),e=>e===reason);
});
if(level>=3)test('clear exact false/null reason and keep active jobs',{timeout:4000},async()=>{
 for(const reason of [false,null,{reason:true}]){
  const l=pLimit({concurrency:1,rejectOnClear:true}),g=gate(),a=l(()=>g.promise);await turn();const b=l(()=>9);const observed=b.then(()=>{throw Error('should reject')},e=>{assert.equal(e,reason)});l.clearQueue(reason);await observed;g.resolve(5);assert.equal(await a,5);await l.onIdle();
 }
 const f=limitFunction(async x=>x,{concurrency:1,rejectOnClear:true});const p=f(1);const b=f(2);const reject=b.then(()=>{throw Error('should reject')},e=>assert.equal(e,false));f.clearQueue(false);await p;await reject;await f.onIdle();
});
if(level>=4)test('sync wrapper and thenable values',{timeout:4000},async()=>{
 const f=limitFunction(x=>x+1,{concurrency:1});assert.equal(await f(2),3);await f.onIdle();
 const bad=limitFunction(()=>{throw Error('sync')},{concurrency:1});await assert.rejects(bad(),/sync/);await bad.onIdle();
});
if(level>=5)test('wrapper map accepts argument tuples and shares limiter',{timeout:4000},async()=>{
 const f=limitFunction((a,b)=>a+b,{concurrency:1});assert.equal(typeof f.map,'function');assert.deepEqual(await f.map([[1,2],[3,4]]),[3,7]);await f.onIdle();
 const g=gate();let active=0,max=0;const limited=limitFunction(async x=>{active++;max=Math.max(max,active);await g.promise;active--;return x*2},{concurrency:1});
 const first=limited(2),mapped=limited.map([[3],[4]]);await turn();assert.equal(max,1);g.resolve();assert.equal(await first,4);assert.deepEqual(await mapped,[6,8]);await limited.onIdle();assert.equal(max,1);
});

'''
TYPES = '''import {expectType} from 'tsd';
import pLimit,{limitFunction} from './index.js';
const l=pLimit(1);expectType<Promise<void>>(l.onIdle());
const f=limitFunction(async (x:number)=>x,{concurrency:1});expectType<Promise<number>>(f(2));expectType<Promise<void>>(f.onIdle());
'''
SIGNAL_TYPES = '''expectType<Promise<void>>(l.onIdle({signal:new AbortController().signal}));expectType<Promise<void>>(f.onIdle({signal:new AbortController().signal}));\n'''
REASON_TYPES = '''l.clearQueue(false);f.clearQueue(null);\n'''
SYNC_TYPES = '''const sync=limitFunction((x:number)=>x+1,{concurrency:1});expectType<Promise<number>>(sync(2));expectType<Promise<void>>(sync.onIdle());sync.clearQueue(false);\n'''

MAP_TYPES = "const mapped=limitFunction((a:number,b:number)=>a+b,{concurrency:1});expectType<Promise<number[]>>(mapped.map([[1,2],[3,4]]));\n"
