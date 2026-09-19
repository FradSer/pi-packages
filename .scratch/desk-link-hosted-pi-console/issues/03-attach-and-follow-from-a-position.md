# 03 — Attach and follow a Hosted Pi from a position

**What to build:** Entering a Hosted Pi attaches the Mac session to it. It reads what it missed from the session's own history up to a boundary, then consumes live events from that boundary onward, so nothing is repeated and nothing is skipped. The Hosted Pi keeps running when the Console goes away.

**Blocked by:** 02 — Launch a Hosted Pi on the desk from the Mac.

**Status:** ready-for-agent

- [ ] Wire events are built from complete SDK messages mapped onto the existing Session Event bounds. Deltas serve the console surface's own liveness locally and do not go on the wire; tool partials are not streamed.
- [ ] An event's position is the position of the corresponding entry in the Hosted Pi's own session log. Positions therefore survive a host restart without a separate counter, a reset rule, or a persisted sequence store, and history and live events are addressed in the same space.
- [ ] Attaching states the position the Console last applied, or learns the current boundary on a first attach, reads history from that position, and then consumes live events only from that boundary.
- [ ] The desk keeps no per-session replay buffer for control, and there is no resync record. The silent-gap failure has no way to occur because the boundary is explicit rather than inferred.
- [ ] The Console applies events in position order and de-duplicates by position.
- [ ] Attach is idempotent and replacing: the newest attach is the driver and the previous Console stops being it. A recorded identity that no longer exists after a desk restart is reconciled by an explicit rule rather than guessed.
- [ ] The Hosted Pi survives the Console disconnecting, stays attachable by its identity, and is unaffected by a Desk Link Service restart.
- [ ] The console surface owns its own input, never intercepts global terminal input, and adds no footer status.
- [ ] The held control connection exists only while the Console is attached, and it is what Control Attribution's lifetime follows.
- [ ] Test seam redefined before slicing: a host adapter exposing a session factory, an event subscription, and an abort, faked in tests with the shape the SDK actually provides. The existing one-shot adapter cannot reach streaming, steering, or a mid-turn cancel.
- [ ] Scenarios pinned: live events carry the session log's own ordering; attaching continues from a boundary instead of replaying a window; a first attach begins at the current boundary; a Hosted Pi survives its Console disconnecting; one Console drives a Hosted Pi at a time; a desk service restart does not end live sessions; the console surface owns its own input; a bounded control request cannot flood the desk.