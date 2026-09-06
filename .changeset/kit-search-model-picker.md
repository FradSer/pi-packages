---
"@fradser/pi-kit": minor
---

Add `searchModelFromPicker`, an interactive type-to-filter model picker built on `ctx.ui.custom`. Packages can pass the full registry model list (e.g. `ctx.modelRegistry.getAll()`) instead of only scoped or available models; the picker offers live search, keyboard navigation, a current-model marker, and empty-list warning fallback.

`pi-recap`, `pi-vision`, and `pi-continual-learning` model menus now use the searchable picker and enumerate all registered models instead of limiting selection to scoped models.
