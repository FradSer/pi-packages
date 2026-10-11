"""Frozen real-source tasks and post-task behavioral oracles, not model fixtures."""
from __future__ import annotations

PROJECTS = {
    'p-limit': {'commit': 'a8a6fbec4e0e866d6d779b10889bb4f5567e70eb',
                'check': ['pnpm', 'test'],
                'training': 'Orient yourself for future maintenance by reading the actual index.js, public declarations and existing tests, then run pnpm test once. Inspect scheduler, concurrency, clearQueue, map and wrapper boundaries. Use at most twelve tool calls; do not write or change any source, tests or configuration, and do not run exploratory probes. Summarize only architecture and verification facts supported by actual source reads or successful tool results. Automatic learning decides what to retain; this task contains no future feature request.',
                'task': '''Implement pause/resume queue lifecycle support. A limiter exposes pause(): void, resume(): void and readonly isPaused: boolean (initially false). Pause prevents queued or subsequently submitted jobs starting; active or already reserved slots may finish. Completion and changing concurrency, including Infinity, must not start queued work while paused. Counts stay accurate. Resume is idempotent and fills available capacity in FIFO order. map obeys pause. clearQueue preserves pause and existing rejectOnClear behavior; new submissions remain paused. limitFunction forwards pause/resume/isPaused and preserves its generic call result and clearQueue. Update public TypeScript declarations, documentation and add tests in new files; preserve all existing tests and manifests. Run pnpm test.'''},
    'pluggy': {'commit': '60b15251ee18560f781c557b6b9ef3de4d786bee',
               'check': ['uv', 'run', '--no-sync', 'pytest', '-q'],
               'training': 'Orient yourself for future maintenance by reading the actual manager and hooks implementations and existing tests, then run uv run --no-sync pytest -q once. Inspect register/unregister, blocked names, descriptor inspection and historic replay boundaries. Use at most twelve tool calls; do not write or change any source, tests or configuration, and do not run exploratory probes. Summarize only architecture and verification facts supported by actual source reads or successful tool results. Automatic learning decides what to retain; this task contains no future feature request.',
               'task': '''Implement a typed PluginManager.temporary_plugin(plugin, name=None) context manager yielding the registered name. During the context normal hooks are available. On normal exit or body exceptions remove only this context's registration and propagate the original exception. Blocked names raise ValueError without removing the block; existing plugin/name collisions preserve existing registrations. If the body unregisters the original, replaces that name, or moves the original to another name, cleanup must preserve those new registrations. Nested different plugins work; a failed same-plugin inner context preserves the outer registration. If registration throws during historic replay, clean this context's partial registration and hook implementations while preserving preexisting plugins. Preserve static descriptor inspection safety. Explain that historical callback side effects cannot be undone. Add documentation and tests in new files; preserve existing tests and manifests. Run uv run --no-sync pytest -q.'''},
}

COMMON = ('Work on this real public project checkout using normal source inspection and tools. '
          'Do not access agent settings or write Memory directly; automatic learning owns it. '
          'Keep work local, do not push or install extra dependencies. Do not weaken existing checks. '
          'Report actual verification results and unresolved problems honestly. ')

P_LIMIT_READONLY_PROBE = r'''
function assertReadonlyPause(target) {
 const original=target.isPaused;
 try { target.isPaused=!original; } catch(error) { assert.ok(error instanceof TypeError); }
 assert.equal(target.isPaused,original);
}
'''

P_LIMIT_ORACLE = r'''
import test from 'node:test';
import assert from 'node:assert/strict';
import pLimit, {limitFunction} from '/work/p-limit/index.js';
''' + P_LIMIT_READONLY_PROBE + r'''
const deferred = () => {let resolve; const promise = new Promise(r => {resolve=r}); return {promise, resolve};};
const turn = () => new Promise(resolve => setImmediate(resolve));
test('pause, FIFO, counts and idempotence', {timeout:5000}, async () => {
 const l=pLimit(1); assert.equal(l.isPaused,false); assert.equal(l.pause(),undefined); l.pause(); assertReadonlyPause(l);
 const seen=[]; const a=l(()=>{seen.push(1);return 1}), b=l(()=>{seen.push(2);return 2});
 await turn(); assert.deepEqual(seen,[]); assert.equal(l.activeCount,0); assert.equal(l.pendingCount,2);
 assert.equal(l.resume(),undefined); l.resume(); assert.deepEqual(await Promise.all([a,b]),[1,2]);
 assert.deepEqual(seen,[1,2]); await turn(); assert.equal(l.activeCount,0); assert.equal(l.pendingCount,0);
 assertReadonlyPause(l);
});
test('active completion and increased capacity cannot unpause', {timeout:5000}, async () => {
 const l=pLimit(1), gate=deferred(), started=deferred(); let second=false;
 const a=l(async()=>{started.resolve();await gate.promise;return 'a'}); await started.promise;
 l.pause(); const b=l(()=>{second=true;return 'b'}); l.concurrency=Infinity;
 await turn(); assert.equal(second,false); gate.resolve(); await a; await turn();
 assert.equal(second,false); assert.equal(l.pendingCount,1); assert.equal(l.activeCount,0);
 l.resume(); assert.equal(await b,'b'); assert.equal(l.isPaused,false);
});
test('resume fills capacity and preserves reject handling', {timeout:5000}, async () => {
 const l=pLimit(2), gate=deferred(); const seen=[]; l.pause();
 const jobs=[1,2,3].map(n=>l(async()=>{seen.push(n);await gate.promise;return n}));
 l.resume(); await turn(); assert.deepEqual(seen,[1,2]); assert.equal(l.activeCount,2); assert.equal(l.pendingCount,1);
 gate.resolve(); assert.deepEqual(await Promise.all(jobs),[1,2,3]);
 l.pause(); const bad=l(()=>{throw new Error('expected')}); const checked=assert.rejects(bad,/expected/); const good=l(()=>42);
 l.resume(); await checked; assert.equal(await good,42); await turn(); assert.equal(l.activeCount,0);
});
test('clear rejects queued work and leaves active work and pause intact', {timeout:5000}, async () => {
 const l=pLimit({concurrency:1,rejectOnClear:true}), gate=deferred(), started=deferred();
 const active=l(async()=>{started.resolve();await gate.promise;return 7}); await started.promise; l.pause();
 const pending=l(()=>99); const rejected=assert.rejects(pending,{name:'AbortError'}); l.clearQueue(); await rejected;
 assert.equal(l.isPaused,true); assert.equal(l.pendingCount,0); assert.equal(l.activeCount,1); gate.resolve(); assert.equal(await active,7);
 let called=false; const fresh=l(()=>{called=true;return 8}); await turn(); assert.equal(called,false); l.resume(); assert.equal(await fresh,8);
});
test('map and wrapper use the same paused scheduler', {timeout:5000}, async () => {
 const l=pLimit(2); l.pause(); const seen=[]; const mapped=l.map([4,5],(n,i)=>{seen.push(n);return n+i});
 await turn(); assert.deepEqual(seen,[]); assert.equal(l.pendingCount,2); l.resume(); assert.deepEqual(await mapped,[4,6]);
 const f=limitFunction(async(n)=>n*2,{concurrency:1,rejectOnClear:true}); assert.equal(f.isPaused,false); f.pause(); f.pause(); assertReadonlyPause(f);
 const dropped=f(3); const checked=assert.rejects(dropped,{name:'AbortError'}); f.clearQueue(); await checked;
 assert.equal(f.isPaused,true); const answer=f(5); await turn(); f.resume(); f.resume(); assert.equal(await answer,10);
 assertReadonlyPause(f);
});
'''

PLUGGY_ORACLE = r'''
import pytest
from pluggy import PluginManager, HookspecMarker, HookimplMarker
spec=HookspecMarker('oracle'); impl=HookimplMarker('oracle')
class Specs:
    @spec
    def value(self): pass
class Plugin:
    @impl
    def value(self): return 'ok'
def manager():
    m=PluginManager('oracle'); m.add_hookspecs(Specs); return m
def test_normal_and_body_exception():
    m=manager(); p=Plugin()
    with m.temporary_plugin(p, 'temporary') as name:
        assert name=='temporary' and m.hook.value()==['ok']
    assert m.get_plugin('temporary') is None and m.hook.value()==[]
    with pytest.raises(RuntimeError,match='body'):
        with m.temporary_plugin(p): raise RuntimeError('body')
    assert not m.is_registered(p) and m.hook.value()==[]
def test_block_and_collisions():
    m=manager(); m.set_blocked('blocked'); p=Plugin()
    with pytest.raises(ValueError):
        with m.temporary_plugin(p,'blocked'): pass
    assert m.is_blocked('blocked')
    m.register(p,'existing')
    for candidate,name in [(p,'new'),(Plugin(),'existing')]:
        with pytest.raises(ValueError):
            with m.temporary_plugin(candidate,name): pass
        assert m.get_plugin('existing') is p and m.hook.value()==['ok']
def test_replacement_and_move_are_preserved():
    m=manager(); p=Plugin(); replacement=Plugin()
    with m.temporary_plugin(p,'slot'):
        m.unregister(p); m.register(replacement,'slot')
    assert m.get_plugin('slot') is replacement
    with m.temporary_plugin(p,'original'):
        m.unregister(p); m.register(p,'moved')
    assert m.get_plugin('moved') is p
def test_nesting_and_same_plugin_failure():
    m=manager(); a=Plugin(); b=Plugin()
    with m.temporary_plugin(a,'outer'):
        with pytest.raises(ValueError):
            with m.temporary_plugin(a,'inner'): pass
        assert m.is_registered(a)
        with m.temporary_plugin(b,'inner'): assert len(m.hook.value())==2
        assert m.hook.value()==['ok']
    assert m.hook.value()==[]
def test_historic_registration_failure_is_cleaned():
    class Historic:
        @spec(historic=True)
        def replay(self): pass
    class Bad(Plugin):
        @impl
        def replay(self): raise RuntimeError('historic')
    m=manager(); m.add_hookspecs(Historic); good=Plugin(); m.register(good,'good'); m.hook.replay.call_historic()
    bad=Bad()
    with pytest.raises(RuntimeError,match='historic'):
        with m.temporary_plugin(bad,'partial'): pass
    assert m.get_plugin('partial') is None and not m.is_registered(bad)
    assert m.hook.value()==['ok'] and m.get_plugin('good') is good
    assert all(h.plugin is not bad for h in m.hook.replay.get_hookimpls())
def test_descriptor_is_not_executed():
    class Safe(Plugin):
        @property
        def trap(self): raise AssertionError('descriptor executed')
    m=manager()
    with m.temporary_plugin(Safe()): assert m.hook.value()==['ok']
    assert m.hook.value()==[]
'''

P_LIMIT_TYPES = '''import {expectType} from 'tsd';
import pLimit, {limitFunction} from './index.js';
const l=pLimit(2); expectType<void>(l.pause()); expectType<void>(l.resume()); expectType<boolean>(l.isPaused);
// @ts-expect-error read only
l.isPaused=true;
const f=limitFunction(async (s: string)=>s.length,{concurrency:1});
expectType<Promise<number>>(f('a')); expectType<void>(f.pause()); expectType<void>(f.resume()); expectType<boolean>(f.isPaused);
// @ts-expect-error read only
f.isPaused=true;
'''
