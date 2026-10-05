import test from 'node:test';
import assert from 'node:assert/strict';
import {createCache} from '../src/cache.mjs';
test('failure retry preserves concurrency and cached success', async () => {
  let calls = 0, otherCalls = 0;
  const cache = createCache(async key => { if(key === 'other') otherCalls++; if(key === 'bad' && ++calls === 1) throw Error('temporary'); return key; });
  assert.equal(await cache.get('other'),'other');
  const a=cache.get('bad'), b=cache.get('bad');
  assert.equal(a,b);
  await assert.rejects(a, /temporary/); await assert.rejects(b, /temporary/);
  assert.equal(await cache.get('other'),'other');
  assert.equal(await cache.get('bad'),'bad');
  assert.equal(await cache.get('bad'),'bad');
  assert.equal(calls,2);
  assert.equal(otherCalls,1);
});
test('synchronous loader throws are retriable rejections', async () => {
  let calls=0;
  const cache=createCache(() => { if(++calls===1) throw Error('sync'); return 0; });
  await assert.rejects(cache.get('k'),/sync/);
  assert.equal(await cache.get('k'),0);
  assert.equal(calls,2);
});
test('a different in-flight key survives rejection', async () => {
  let finish, calls = 0;
  const waiting = new Promise(resolve => { finish = resolve; });
  const cache = createCache(key => {
    if (key === 'bad') throw Error('temporary');
    calls++;
    return waiting;
  });
  const first = cache.get('slow');
  await assert.rejects(cache.get('bad'), /temporary/);
  const second = cache.get('slow');
  assert.equal(first, second);
  assert.equal(calls, 1);
  finish('ready');
  assert.equal(await first, 'ready');
  assert.equal(await second, 'ready');
  assert.equal(await cache.get('slow'), 'ready');
  assert.equal(calls, 1);
});
