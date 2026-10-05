import test from 'node:test';
import assert from 'node:assert/strict';
import {checkAdder} from '../src/feature.mjs';
test('accept correct public implementations',()=>{
 assert.equal(checkAdder((a,b)=>a+b),true);
 assert.equal(checkAdder((a,b)=>b+a),true);
});
test('kill behavioral mutations and exceptions',()=>{
 for(const bad of [(a,b)=>a+b+1,(a,b)=>Math.abs(a+b),(a,b)=>a*b,()=>0,()=>{throw Error('bad');}])
  assert.equal(checkAdder(bad),false);
});
