import test from 'node:test';
import assert from 'node:assert/strict';
import {indexById} from '../src/feature.mjs';
test('public semantics and first duplicate',()=>{
 const a=Object.freeze({id:'a',value:1}),duplicate=Object.freeze({id:'a',value:2}),b=Object.freeze({id:'b'});
 assert.deepEqual(indexById(Object.freeze([a,duplicate,b]),['b','missing','a','a']),[b,undefined,a,a]);
 assert.deepEqual(indexById([],['missing']),[undefined]);
});
test('bounded ID reads for many lookups',()=>{
 let reads=0;
 const records=Array.from({length:200},(_,i)=>Object.freeze({get id(){reads++;return i;}}));
 const ids=Array.from({length:20},(_,i)=>199-i);
 const result=indexById(records,ids);
 assert.ok(result.every((row,i)=>row===records[ids[i]]));
 console.log(JSON.stringify({metric:'idReads',observed:reads,budget:records.length*2+ids.length}));
 assert.ok(reads<=records.length*2+ids.length,`observed ${reads} ID reads`);
});

test('strict equality and empty requests remain unchanged',()=>{
 const nan={id:NaN}, zero={id:-0}, duplicate={id:0}, key={}, object={id:key};
 assert.deepEqual(indexById([nan,zero,duplicate,object],[NaN,0,key,{}]),[undefined,zero,object,undefined]);
 assert.deepEqual(indexById([{get id(){throw new Error('empty requests must not read ids');}}],[]),[]);
});
