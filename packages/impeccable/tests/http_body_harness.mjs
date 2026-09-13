import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';
import { MAX_JSON_BODY_BYTES, readLiveRequestBody } from '../scripts/live/http-body.mjs';

function reader() {
  const req = new PassThrough();
  const bodies = [];
  const responses = [];
  const res = {
    writeHead(status) { responses.push(status); },
    end(body) { responses.push(JSON.parse(body)); },
  };
  readLiveRequestBody(req, res, (body) => bodies.push(body));
  return { req, bodies, responses };
}

const unicode = reader();
const body = Buffer.from('{"text":"中文"}');
const split = Buffer.from('{"text":"').length + 1;
unicode.req.emit('data', body.subarray(0, split));
unicode.req.emit('data', body.subarray(split));
unicode.req.emit('end');
assert.deepEqual(unicode.bodies, [body.toString()]);

const exact = reader();
exact.req.emit('data', Buffer.alloc(MAX_JSON_BODY_BYTES, 'a'));
exact.req.emit('end');
assert.equal(exact.bodies[0].length, MAX_JSON_BODY_BYTES);
assert.deepEqual(exact.responses, []);

const oversized = reader();
oversized.req.emit('data', Buffer.from('中'.repeat(Math.ceil(MAX_JSON_BODY_BYTES / 3))));
oversized.req.emit('data', Buffer.from('ignored'));
oversized.req.emit('end');
assert.deepEqual(oversized.bodies, []);
assert.deepEqual(oversized.responses, [413, { error: 'Payload too large', maxBytes: MAX_JSON_BODY_BYTES }]);

const aborted = reader();
aborted.req.emit('data', Buffer.from('partial'));
aborted.req.emit('aborted');
aborted.req.emit('error', new Error('client disconnected'));
aborted.req.emit('end');
assert.deepEqual(aborted.bodies, []);
assert.deepEqual(aborted.responses, []);
console.log('ok');
