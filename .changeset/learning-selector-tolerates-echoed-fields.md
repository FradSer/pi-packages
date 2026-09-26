---
"pi-continual-learning": patch
---

Accept a selector verdict that carries unknown extra fields instead of discarding the run. The selector's eight required fields must all be present and every authoritative field is still type- and value-checked, so an extra key grants nothing; but a model that echoed an input field such as `omittedEntries` used to fail the exact-key check and end the learning run with zero operations and only a formatting complaint. A rejection for a missing required field now names the missing field, and the selector prompt states that slice fields are input, never response fields.
