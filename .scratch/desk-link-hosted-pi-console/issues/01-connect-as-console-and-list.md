# 01 — Connect as a Console and list the desk's Hosted Pi sessions

**What to build:** A Mac Pi session holding a control credential opens a control connection to the desk's Desk Link Service and lists the Hosted Pi sessions that desk hosts. A machine holding only the reporting token keeps behaving exactly as it does today.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] The control connection is its own connection to the desk's existing LAN listener. No second listener and no second port. A list, launch, or history request uses a one-shot connection; a held connection exists only while a Console is attached.
- [ ] The reporting connection is untouched: same records, same backoff, same session ownership. Every existing report-only scenario still passes, and this is where the regression check starts.
- [ ] The handshake carries the protocol version and a Console identity: the driving Pi session's identity plus its machine name. Two Pi sessions on one machine are therefore distinguishable Consoles, never merged into one.
- [ ] The control credential never travels on the wire: the desk challenges with a one-time nonce, the Console answers with an HMAC proof over it, and every control record is refused without that proof.
- [ ] A missing or refused credential degrades that connection to report-only. It never fails the reporting link, and the machine never becomes a Console.
- [ ] The desk accepts a defined window of protocol versions and refuses a mismatch with an explicit reply naming it. Today the service silently discards any record whose version is not 1, so a newer Console looks like a credential failure and reconnects forever.
- [ ] The Desk Link Service gains a configured client to the Pi host's own socket. It must not claim a path it does not have: its only socket is the runtime channel today, and the Pi host is a separate process on its own configured socket. The host keeps owning Pi credentials and session storage, so a service restart cannot kill a live session.
- [ ] A Pi host that is down or a stale host socket produces an explicit failure naming the reason, on both a list and a launch. The connection is never left waiting.
- [ ] Both credential variables and their files are named and provisioned on each side; the documentation states the rotation step and that content is plaintext on a LAN-only link.
- [ ] One time basis covers the handshake, the receipts, and the surface's age reading, and the tolerated skew is stated.
- [ ] The console command's no-argument form opens the same menu in every configuration, with rows for the console, the link status, and the fast paths. An unavailable row names its reason, so an unconfigured machine and a report-only machine see the same shape as a configured Console.
- [ ] Scenarios pinned: the command opens the same menu in every configuration; a reporting-only link stays report-only; an unconfigured machine stays silent; a machine with a Control Credential becomes a Console; the control credential is never transmitted; a refused Control Credential does not break reporting; a version mismatch is refused explicitly; two Pi sessions on one machine are distinguishable Consoles; the desk lists its Hosted Pi sessions; the Pi host being unavailable is answered, not hung; diagnostics stay command-only.