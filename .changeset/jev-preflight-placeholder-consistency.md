---
"pi-continual-learning": patch
---

Judge documentation-style text placeholders identically in the Memory guard and
the Jev preflight, so a tracked source sample no longer refuses a whole review.
Both detectors now match plain, quoted and delimited credential assignments
through one pattern set and one placeholder rule; a credential-named structured
member or object key is strict in both. A value is exempted as a URL only when it
starts with a well-known scheme and carries no userinfo, so a secret with no
scheme, an unknown scheme, or a `scheme://user:pass@host` connection string is
refused, as is a delimited value containing `,`, `;`, `?`, `'` or an escape. The
plain pattern's credential-key class accepts optional surrounding quotes, which
widens detection only, and the preflight no longer reads `?` or `&&` inside a
password as a code expression. No placeholder entry was added and no secret value
class was loosened. The packed validator mirrors both patterns and the shared
corpus pins them.
