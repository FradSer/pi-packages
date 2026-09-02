# pi-keyboard

## 0.1.6

### Patch Changes

- fab8160: Unify package TUI notifications, lifecycle rows, panels, and widgets through shared pi-kit rendering abstractions.
- Updated dependencies [ec7d764]
- Updated dependencies [b28ef2d]
- Updated dependencies [fab8160]
  - @fradser/pi-kit@0.4.2

## 0.1.5

### Patch Changes

- Standardize runtime package entry points on package-root `index.ts` modules. The monitor status is also rendered through Pi's native footer so it appears below the directory and usage lines.

## 0.1.4

### Patch Changes

- f4fccb1: Republish all published package versions through GitHub CI to align with current release flow and regenerate their release metadata after version comparison.

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
