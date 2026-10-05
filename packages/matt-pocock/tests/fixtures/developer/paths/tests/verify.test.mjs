import test from 'node:test';
import assert from 'node:assert/strict';
import {isWithin} from '../src/feature.mjs';
test('prefix and traversal boundaries',()=>{
 assert.equal(isWithin('/work/app','/work/app2/file'),false);
 assert.equal(isWithin('/work/app','/work/app/../private'),false);
 assert.equal(isWithin('/work/app/','/work/app/file'),true);
 assert.equal(isWithin('/work/app','/work/app'),true);
 assert.equal(isWithin('/work/app','/work/app/a/../b'),true);
 assert.equal(isWithin('/','/work/app'),true);
});

test('dot-prefixed child names stay inside',()=>{
 assert.equal(isWithin('/work/app','/work/app/..notes'),true);
 assert.equal(isWithin('/work/app','/work/app/sub/..foo'),true);
});
