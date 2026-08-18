# pi-keyboard

## 0.1.3

### Patch Changes

- 57d7017: Clean up orphaned unread glow records left by sessions that exited unexpectedly.
  
  - Add `pruneOrphanedGlowStates()`: a session-start sweep that removes `settled`/`hasUnread`
    glow records whose owning process is no longer alive (crash, SIGKILL, terminal closed
    without a clean `session_shutdown`), so leftover unread records no longer pile up and
    keep the keyboard green.
  - Deliberately no time-based auto-return to idle: a genuinely live unread session still
    keeps its green light.
  - `getRegistryDir()` honors `PI_DIRECTORY_SESSIONS_DIR` as a test seam.
