# Local configuration cleanup

Simplify parseConfig(env) without changing its public API or behavior. Missing FEATURE_ENABLED is false; only the exact strings true/false are accepted. Missing PORT is 3000; ASCII decimal integer strings from 1 through 65535 are accepted, including leading zeros; empty, signed, decimal and whitespace values are rejected. Preserve error messages and input immutability. Do not add trimming, case normalization, truthiness coercion, dependencies or environment reads.
