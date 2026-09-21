# pi-open-deskos

## 0.2.0

### Minor Changes

- b0231e3: Report this machine's Pi sessions and their operating events to Open DeskOS over a
  package-initiated Desk Link. The package observes the session lifecycle and message
  stream in process, bounds every retained event exactly like the runtime's local
  collector (60 per session, one single line each, tool results reduced to their first
  line), reconnects with a growing capped wait, and holds one bounded snapshot across an
  outage. An unconfigured or partially configured machine stays silent, and v1 is
  report-only: it never sends a prompt, blocks a turn, or mutates a message.

### Patch Changes

- b0231e3: Remove automatic Desk Link footer status updates in every configuration and connection state. Keep reporting unchanged and expose link and configuration diagnostics through `/open-deskos` only.
- 5dda2df: Document local installation from any checkout using a quoted absolute package path,
  without relying on a personal home-directory layout. Verify both language recipes
  in a disposable checkout whose path contains spaces.
- Updated dependencies [b0231e3]
- Updated dependencies [ac83f4e]
- Updated dependencies [9cabb0d]
- Updated dependencies [919504f]
- Updated dependencies [bcb0054]
- Updated dependencies [efd5641]
- Updated dependencies [919504f]
- Updated dependencies [274cc90]
- Updated dependencies [28bdae2]
- Updated dependencies [707c4c5]
- Updated dependencies [5b4f51b]
- Updated dependencies [b0231e3]
- Updated dependencies [552a083]
- Updated dependencies [efd5641]
  - @fradser/pi-kit@0.5.0
