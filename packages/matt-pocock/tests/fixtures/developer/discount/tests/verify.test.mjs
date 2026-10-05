import test from 'node:test';
import assert from 'node:assert/strict';
import {calculateTotal, makeReceipt} from '../src/receipt.mjs';
test('whole receipt discount including endpoints and default', () => {
  const items = [{price: 10, quantity: 2}, {price: 5, quantity: 1}];
  assert.equal(calculateTotal(items, 20), 20);
  assert.equal(calculateTotal(items, 100), 0);
  assert.equal(calculateTotal(items), 25);
  const receipt = makeReceipt(items, 20);
  assert.deepEqual(receipt, {total:20, items});
  assert.equal(receipt.items, items);
  assert.equal(calculateTotal([], 20), 0);
});
test('round once after discount', () => {
  assert.equal(calculateTotal([{price:0.335, quantity:2}], 50), 0.34);
});
