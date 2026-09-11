# @fradser/pi-impeccable

## 0.1.0

### Minor Changes

- 3a6cdda: Start `/impeccable` capability runs as an abstract pi-kit lifecycle message (`[impeccable] started · <capability>`) instead of dumping the full procedure text as a visible user message; the procedure still enters context through the custom message. Live mode boots immediately without interviewing the user for a target or dev-server status.
- fff0b27: Port the upstream live variant mode (skill-v4.1.2): browser element picking, three generated HTML+CSS variants hot-swapped over dev-server HMR, and the full live helper runtime (boot, poll, wrap, accept, carbonize, journal recovery) with provenance for all 64 added sources. `/impeccable` now routes any freeform request as design guidance naming the shipped capabilities instead of rejecting unknown first words, and the live picker offers only shipped actions.

### Patch Changes

- 9cabb0d: Bump every package by one patch version.
- Updated dependencies [9cabb0d]
- Updated dependencies [919504f]
- Updated dependencies [28bdae2]
  - @fradser/pi-kit@0.5.0
