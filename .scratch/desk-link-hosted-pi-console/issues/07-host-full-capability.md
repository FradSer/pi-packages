# 07 — Give a Hosted Pi the host's full capability

**What to build:** The edit-and-test-only instruction disappears from the host's session instructions, so a Hosted Pi may commit, push, install, deploy, and restart services as the desk's Pi host user. Intake, receipts, and the concurrency cap are untouched.

**Blocked by:** 02 — Launch a Hosted Pi on the desk from the Mac.

**Status:** ready-for-agent

- [ ] The edit-and-test-only instruction is removed from the host's session instructions. The host still loads no extensions, skills, or prompt templates, so the resulting capability is the host's tool set rather than everything a full Pi installation could do.
- [ ] The scenario that pinned the edit-and-test-only policy has already been replaced in the feature file; the remaining work here is the session instruction itself, the prose, and the assertions that pin their text.
- [ ] The host prose that claims tasks are not interactive and do not take over sessions is corrected.
- [ ] The assertions that pin the policy text are updated in the same change, or they fail for the right reason.
- [ ] The scenario and the instruction agree on the prohibited list, including release activation, which the instruction names and the scenario omits.
- [ ] Admission, the durable receipt written before execution, the host-wide cap, the no-automatic-retry rule, and the no-replay-after-restart rule are untouched.
- [ ] The documentation says honestly that these were system-prompt instructions over an unrestricted tool set, so removing them changes the likelihood of a mutation rather than creating the capability, and it records that a mis-transcribed voice request now reaches the same capability.
- [ ] Scenario pinned: Hosted Pi capability is the host's tool set.