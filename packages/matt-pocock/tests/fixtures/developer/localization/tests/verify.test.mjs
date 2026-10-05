import test from 'node:test';
import assert from 'node:assert/strict';
import {fileCount} from '../src/feature.mjs';
test('English plural and fallback',()=>{
 assert.equal(fileCount('en',1),'1 file');
 assert.equal(fileCount('en-US',0),'0 files');
 assert.equal(fileCount('en',2),'2 files');
 assert.equal(fileCount('fr',1),'1 file');
});
test('Chinese preserves Unicode and zero',()=>{
 for(const locale of ['zh','zh-CN']) for(const count of [0,1,2])
  assert.equal(fileCount(locale,count),`${count} 个文件`);
});
