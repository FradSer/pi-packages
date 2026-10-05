import test from 'node:test';
import assert from 'node:assert/strict';
import {parseRequest} from '../src/feature.mjs';
const headers={'content-type':'application/json'};
const req=(body,extra={})=>({method:'POST',contentType:'application/json',body,...extra});
test('ordered error boundaries',()=>{
 assert.deepEqual(parseRequest(req('{',{method:'GET'})),{status:405,body:{error:'method'},headers});
 assert.deepEqual(parseRequest(req('{',{contentType:'text/plain'})),{status:415,body:{error:'content-type'},headers});
 for(const body of ['{','null','[]','1','{"name":5}','{"name":"  "}'])
  assert.deepEqual(parseRequest(req(body)),{status:400,body:{error:'body'},headers});
});
test('valid JSON MIME and immutable request',()=>{
 const input=Object.freeze(req('{"name":" Ada ","ignored":true}',{contentType:'Application/JSON; charset=utf-8'}));
 assert.deepEqual(parseRequest(input),{status:201,body:{name:'Ada'},headers});
});
