---
"pi-continual-learning": patch
---

Give an otherwise complete Memory selector decision one bounded correction when its only defect is an out-of-range or duplicate frozen index. A real run in `~/Developer/FradSer/open-deskos` returned `[44,50,20,26,27,52]` against a 52-entry frozen index (valid `0..51`); the bare `selectedIndices contains an invalid or duplicate frozen position` diagnostic rejected the whole run with no retry. The parent now names the exact bad position and range in the rejection, passes that reason to the existing one-attempt structural correction, and fully revalidates the fresh decision before writing a dossier. All other structural, identity, privacy and range gates stay fail-closed, and a second invalid position still fails the run.
