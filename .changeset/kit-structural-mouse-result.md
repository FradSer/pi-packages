---
"@fradser/pi-kit": patch
---

Match Pi's typed mouse handler in the structural component contract. `PiMessageComponent.handleMouse` was declared as `(event: unknown) => unknown`, which stopped satisfying the host's `Component.handleMouse` once Pi typed it as `(event: TuiMouseEvent) => TuiMouseEventResult | undefined`, so a package returning a lifecycle component from `registerTool` or `registerMessageRenderer` no longer compiled against the current host. The interface now mirrors that result as the structural `PiMouseEventResult`, keeping kit free of Pi runtime imports while a consumer's type-checker accepts the component again.