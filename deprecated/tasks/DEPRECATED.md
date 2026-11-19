# Deprecated: @fradser/pi-tasks

Status: archived on 2026-11-16.

This plugin is no longer suitable for current SOTA models. It has been removed
from the user's Pi configuration, from the active `packages/*` workspace, and
from the release allowlist. No further features or fixes are planned here; the
source is kept only for history and migration reference.

## Compatibility

`@fradser/pi-agent-teams@1.0.0` on npm still declares
`@fradser/pi-tasks@0.2.0` as a runtime dependency and loads its extension. That
published version cannot be removed under npm's unpublish policy because a
public package depends on it. The supported registry action is `npm deprecate
@fradser/pi-tasks "no longer suitable for current SOTA models"`, which warns
installers without breaking existing builds.

Source consumers that still need the task domain must treat this directory as
frozen. New work should not install or configure this plugin.
