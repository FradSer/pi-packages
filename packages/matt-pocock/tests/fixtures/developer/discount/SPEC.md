# Receipt discount

Agreed product decisions: the discount is a whole-receipt percentage in [0,100]; inputs are already validated. Apply it after summing unrounded price times quantity, and round only the discounted final total to cents. Zero is the default. Preserve the existing makeReceipt(items) shape and input array identity; pass its optional second argument through. Do not add validation, line discounts, taxes, currency conversion, external trackers or remote PRs.

Given a subtotal of 25 and a discount of 20, when finalized, then the total is 20. Given 100 percent, then total is zero. Given no discount, then previous behavior is preserved. Given two 0.335 lines with 50 percent off, then total is 0.34.
