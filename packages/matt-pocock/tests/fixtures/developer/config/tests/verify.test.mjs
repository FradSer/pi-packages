import test from 'node:test';
import assert from 'node:assert/strict';
import {parseConfig} from '../src/config.mjs';
test('public defaults and accepted values', () => {
  assert.deepEqual(parseConfig({}),{enabled:false,port:3000});
  for(const port of ['1','65535','003000']) {
    const env=Object.freeze({FEATURE_ENABLED:'true',PORT:port});
    assert.deepEqual(parseConfig(env),{enabled:true,port:Number(port)});
  }
  assert.equal(parseConfig({FEATURE_ENABLED:'false'}).enabled,false);
});
test('strict flags and port grammar retain exact errors', () => {
  for(const flag of [null, '', 'TRUE', '1', ' false '])
    assert.throws(()=>parseConfig({FEATURE_ENABLED:flag}), {message:'FEATURE_ENABLED must be true or false'});
  for(const port of [null, '', '0', '65536', '-1', '+1', '1.5', ' 80 ', '1e2', 'Infinity'])
    assert.throws(()=>parseConfig({PORT:port}), {message:'PORT must be an integer from 1 to 65535'});
});
