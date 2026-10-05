# test-design

checkAdder(add) is a reusable behavioral regression checker for add(a,b) over small integers. Return true for a correct adder and false for a throwing or wrong implementation. Test through this public function, not internal mocks or snapshots. The acceptance file includes correct and faulty candidate functions. Cover zero, mixed signs, negative sums and more than one positive sum; do not hardcode function source or fixture names.
Given a correct adder, then accept. Given off-by-one, absolute-value, multiplication, constant-zero, or throwing candidates, then reject.
