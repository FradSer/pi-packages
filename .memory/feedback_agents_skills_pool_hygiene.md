---
name: agents-skills-pool-hygiene
description: ~/.agents/skills is a cross-host pool; host-exclusive skills must be removed, while local-repository symlinks remain managed by their owners
type: feedback
---

## Why

pi discovers skills from ~/.agents/skills globally, so host-exclusive entries add prompt cost and can mis-trigger on unavailable machinery. The pool should contain only skills that work across supported hosts.

## How to apply

Remove host-exclusive skills from the shared pool and remove matching lock entries when they are lock-managed. Do not remove user-managed symlinks to local development repositories. Keep ceremony skills explicitly invoked when their behavior changes branches, merges, or tags; natural-language workflow skills may remain model-invocable when that is their design.

Changes take effect in new pi sessions only; running sessions retain startup-resolved skill paths.