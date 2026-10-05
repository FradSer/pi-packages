import test from 'node:test';
import assert from 'node:assert/strict';
import {renderField} from '../src/feature.mjs';
test('label association and text input',()=>{
 const html=renderField('Email','Ada','email');
 assert.match(html,/<label\b[^>]*for="email"[^>]*>Email<\/label>/);
 assert.match(html,/<input\b[^>]*id="email"/);
 assert.match(html,/<input\b[^>]*type="text"/);
 assert.match(html,/value="Ada"/);
});
test('user text cannot become markup or break attributes',()=>{
 const html=renderField('姓名 <&>','"><script>&','name');
 assert.ok(html.includes('姓名 &lt;&amp;&gt;'));
 assert.ok(html.includes('value="&quot;&gt;&lt;script&gt;&amp;"'));
 assert.ok(!html.includes('<script>'));
});

import * as api from '../src/feature.mjs';
test('public exports stay unchanged',()=>assert.deepEqual(Object.keys(api),['renderField']));
