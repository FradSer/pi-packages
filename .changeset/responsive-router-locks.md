---
"pi-skill-router": patch
---

Wait asynchronously for collection registry locks and propagate cancellation from the loading overlay through summary generation. Cancelled operations leave other owners' locks and registry state intact. Close cancelled overlays promptly while authentication or model responses are pending, and ignore late results.
