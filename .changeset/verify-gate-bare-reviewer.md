---
"@fradser/pi-agent-teams": patch
---

Run the verification-gate reviewer as a bare Pi child. `buildVerifyReviewWorkerOptions` now supplies the whole worker options with `minimal: true` and the read-only `VERIFY_REVIEW_TOOLS` grant (read, bash, grep, find, ls), so a gate review no longer loads the project's extensions, skills, prompt templates, context files, or themes, cannot trigger another package's automatic memory learning, and leaves no session record behind.
