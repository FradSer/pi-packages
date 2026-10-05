---
"@fradser/pi-kit": patch
---

Accept a pre-styled detail block in a lifecycle band. A `details` entry that is
a string array keeps its host escapes, receives no text color, and still wraps,
fits and bands each row, so a caller can place highlighted code inside a band.
String entries keep the existing sanitize and color behavior.

Add the field-name vocabulary `labelField` and `labelFieldVerbatim`. They read
`Label: value` on one line. `labelField` collapses whitespace like `fieldLine`,
and `labelFieldVerbatim` keeps the value's own spacing for a command, a regex
or a payload. `fieldLine` keeps the `label · value` vocabulary, so no existing
row changes.