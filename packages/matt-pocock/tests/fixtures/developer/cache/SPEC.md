# Async cache incident

An upstream failure currently poisons a cache key forever. Keep the public createCache(load).get(key) API. A failed load must be retriable on the next get, successful values remain cached, concurrent callers share one in-flight load, keys are independent, and synchronous throws are rejected promises with the same retry behavior. No timers, TTL, cancellation, eviction policy, dependency, network, or unrelated receipt changes.

Given a first failed request, when the next get arrives, then invoke load again. Given concurrent requests for a key, then invoke load once. Given another key, then its success survives this key failure.

A success cached before another key rejects must remain cached; an independent in-flight promise must remain shared. Failure retry affects only the failed key.
