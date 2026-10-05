import test from 'node:test';
import assert from 'node:assert/strict';
import {canRead} from '../src/feature.mjs';
const doc=Object.freeze({tenantId:'a',ownerId:'u'});
const actor=(role,userId='u',extra={})=>Object.freeze({role,userId,tenantId:'a',active:true,...extra});
test('tenant isolation and role rules',()=>{
 assert.equal(canRead(actor('admin','other'),doc),true);
 assert.equal(canRead(actor('member'),doc),true);
 assert.equal(canRead(actor('member','other'),doc),false);
 assert.equal(canRead(actor('admin','u',{tenantId:'b'}),doc),false);
 assert.equal(canRead(actor('member','u',{tenantId:'b'}),doc),false);
 assert.equal(canRead(actor('guest'),doc),false);
});
test('missing and inactive are denied',()=>{
 assert.equal(canRead(null,doc),false);
 assert.equal(canRead(actor('admin'),null),false);
 assert.equal(canRead(actor('admin','u',{active:false}),doc),false);
});
