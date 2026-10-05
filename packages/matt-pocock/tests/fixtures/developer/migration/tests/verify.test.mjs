import test from 'node:test';
import assert from 'node:assert/strict';
import {migrate} from '../src/feature.mjs';
test('rename without loss or mutation',()=>{
 const metadata=Object.freeze({note:'keep'});
 const input=Object.freeze({version:1,fullName:'Ada',metadata,custom:0});
 const result=migrate(input);
 assert.deepEqual(result,{version:2,displayName:'Ada',metadata,custom:0});
 assert.equal(result.metadata,metadata);
 assert.equal(input.fullName,'Ada');
 assert.equal(migrate(result),result);
});
test('v2 identity and unsupported versions',()=>{
 const input=Object.freeze({version:2,displayName:'Ada',custom:false});
 assert.equal(migrate(input),input);
 assert.throws(()=>migrate({version:3}),{message:'Unsupported version'});
});
