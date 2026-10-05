# performance

indexById(records,ids) returns the original record objects for requested ids in request order, with undefined for missing ids and first occurrence winning duplicate record ids. Repeated requested ids repeat the same object. Build a linear index: at most two id-property reads per input record plus the request count. Preserve all behavior and input identities. Measure operation counts, not wall-clock speed; do not claim timing improvement from this fixture.
Given duplicate records, then first wins. Given many lookups, then property-read work fits the stated linear budget. Given unknown ids, then preserve undefined output positions.

Preserve strict === ID matching, including NaN never matching and object IDs matching by identity. Empty requests read no record IDs.

JavaScript strict equality treats -0 and +0 as equal. They share the first matching record; only NaN needs special handling compared with Map equality. Report test-case counts from the actual test-run summary, not counts inferred from source assertions.
