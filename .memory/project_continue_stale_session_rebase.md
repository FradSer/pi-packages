---
name: continue-stale-session-rebase
description: /continue reloads only genuinely unseen persisted entries while preserving a user-selected session-tree leaf
type: project
---

## Why

A session file may contain entries written by another process or an abandoned branch. Reloading whenever the physical disk tip differs from the selected leaf resets deliberate tree navigation and resumes the wrong branch.

## How to apply

Read the last valid persisted entry id with readDiskTipEntryId. Reload only when getEntry(diskTipEntryId) is undefined, which proves the active session has not loaded the appended history. If the tip is already known, preserve the selected leaf and let the next append create a continuation branch there. Route idle keyword input through /continue and use the direct marker while streaming. Classify continuation from the active getBranch path only.