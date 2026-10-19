---
"pi-continual-learning": patch
---

Judge documentation-style text placeholders identically in the Memory guard and
the Jev preflight, so a tracked source sample no longer refuses a whole review.
Both detectors now match plain, quoted and delimited credential assignments
through one pattern set and one placeholder rule, and a credential-named
structured member or object key is strict in both. A credential-named assignment
has no URL exemption: a webhook, a token-bearing link or a connection string
under such a key is refused, and so is a delimited value containing `,`, `;`,
`?`, `'` or an escape. The documented placeholder rule, which covers code, env
and expression references, is the only exemption. The plain pattern's
credential-key class accepts optional surrounding quotes, which widens detection
only, and the preflight no longer reads `?` or `&&` inside a password as a code
expression. No placeholder entry was added and no secret value class was
loosened. The packed validator mirrors both patterns and the shared corpus pins
them.
