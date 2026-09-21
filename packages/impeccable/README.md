# @fradser/pi-impeccable

Native Pi design procedures with one concern-organized taste library. The agent loads canonical guidance for interface work instead of improvising it; loading guidance never executes scripts, installs packages, generates variants, or authorizes edits beyond the request.

## Install

```bash
pi install npm:@fradser/pi-impeccable
```

## Usage

```
/impeccable <capability> <target/request>   Run one capability against a target
/impeccable <request>                       Route any freeform request to the capabilities that match
```

**Tool:** `impeccable_load` — `{ capability, reference? }` loads one procedure whose reference closure stays within 64 KiB. A bundle above that limit fails instead of being truncated. Further references are disclosed as `](impeccable:<referenceId>)` links and load only when their conditions apply.

Capabilities: `polish`, `animate`, `typeset`, `colorize`, `layout`, `clarify`, `critique`, `audit`, `bolder`, `quieter`, `distill`, `delight`, `overdrive`, `harden`, `onboard`, `adapt`, `optimize`, `extract`, `shape`, `init`, `document`, `live`

References: `setup`, `principles`, `components`, `motion`, `accessibility`, `typography`, `color`, `taste-layout`, `writing`, `live-setup`

## Live variant mode

`/impeccable live` selects elements in the browser, applies one design action, and hot-swaps three generated HTML+CSS variants through the running dev server's HMR. The helper runtime boots from this package, probes the default URL before spawning a server, bounds every JSON request to 1 MiB with HTTP 413 for oversized bodies, and removes its preview markers during accept or completion.

## License

MIT for this package. The procedures and taste references are Pi adaptations of the upstream Impeccable design skill (Apache-2.0); upstream license texts, the NOTICE, and the MIT licenses of derived work ship in `licenses/`.
