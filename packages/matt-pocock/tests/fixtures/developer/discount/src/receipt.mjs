export function calculateTotal(items, discountPercent = 0) {
  return Math.round(items.reduce((sum, item) => sum + item.price * item.quantity, 0) * 100) / 100;
}
export function makeReceipt(items, discountPercent = 0) {
  return { total: calculateTotal(items, discountPercent), items };
}
