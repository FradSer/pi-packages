---
"@fradser/pi-kit": patch
"@fradser/pi-impeccable": patch
"pi-matt-pocock": patch
"@fradser/pi-utils": patch
"@fradser/pi-plan-mode": patch
"@fradser/pi-recap": patch
"pi-skill-router": patch
"@fradser/pi-vision": patch
---

Declare the pi core packages these extensions already use as `"*"` peer dependencies instead of resolving them by hoisting, per pi's package guide: `typebox` for pi-kit, impeccable, matt-pocock, and utils; `@earendil-works/pi-ai` for plan-mode, recap, and skill-router; `@earendil-works/pi-tui` for plan-mode, skill-router, and vision; and `@earendil-works/pi-coding-agent` for pi-kit, whose best-effort worker CLI probe resolves it at runtime. `import type` counts because pi packages ship TypeScript source that a consumer's type-checker must resolve. impeccable no longer bundles `typebox` in `dependencies`, since pi provides core packages. A pi-kit check now fails when a package uses a core package without declaring it as a `"*"` peer or when a core package ships as a dependency.