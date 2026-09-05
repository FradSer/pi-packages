# Interface writing

## Voice and scope

Read nearby copy, terminology, localization patterns and any voice guide before editing. Keep one product voice, with tone changing by stakes: warm onboarding/success/empty states, neutral routine settings, calm unplayful errors/destructive confirmations, and explicit seriousness for security or data loss. A deliberate brand voice is not a defect unless it creates ambiguity, inconsistency, translation risk or inappropriate tone.

Be brief without deleting information users need. Prefer plain words a tired reader understands; avoid idioms and jokes that will not translate. Address the reader as you in instructions. Avoid ambiguous we in failures unless an established voice remains clear about responsibility. Keep perspective consistent and unnecessary possessives out of labels.

## Actions and destinations

Button text starts with the verb and names the consequence: Save draft, Send message, Delete project. Consequential confirmations should be answerable from the action labels, not bare Yes/No or OK. Pair Delete project with Cancel, and retain the product's undo/confirmation boundary instead of solving safety with copy alone.

Use one flow vocabulary: Get started to enter, Continue or Next consistently to advance, Done to finish. Use the same term for an action in its menu, button and result message. A setting describes its ON state, such as Send read receipts, not a double negative. Link directly to a referenced setting instead of narrating a fragile navigation path.

Links name their destination and make sense in a link list: Read the billing docs, not Click here. Distinguish repeated Learn more links with their subject. Match device verbs only when necessary: tap for touch, click for a pointer, select when both are possible. [Accessible names](accessibility.md#semantics-and-names) remain governed by the visible label and semantics, not a separate copy-only naming rule.

## Errors and recovery

An error explains how to recover, near what failed. State the actionable requirement or next step, without blame, oops, exclamation marks or playful deflection. Unable to save. Check your connection and try again is useful only when retry really is an available recovery. If no recovery is known, say what is preserved and what can happen next rather than inventing a cause.

Give format guidance before the mistake where it helps. Phrase requirements positively, but do not turn sample rules into arbitrary restrictions: names are not universally letters-only, and a password minimum must come from the real policy. If one error keeps recurring, consider improving the interaction rather than repeatedly rewording the message. Validation timing, disabled submission, inline association and announcements belong to [forms](accessibility.md#forms-and-disabled-states).

## Empty states and hints

An empty state orients: what belongs here, how it becomes populated, and one clear next action. No projects yet can explain what projects organize and offer Create a project. Search/filter emptiness names the query and offers a real exit such as Clear filters. Do not store persistent instructions only in an empty state that disappears after the first item.

A placeholder illustrates an expected format; it is never the control's label. Use an example appropriate to locale and actual accepted data, not a fictitious universal date format. [Labels and input behavior](accessibility.md#forms-and-disabled-states) own the durable association. Keep ordinary labels concise without truncating away distinctions between actions.

## Localization and presentation

Use complete localized message templates with proper plural handling, never sentence fragments concatenated around variables. Word order and inflection change by locale. Avoid unnecessary gender and culture-bound idioms. Pick one capitalization policy per element type; sentence case is a calm default, but consistency with the existing product governs. Store natural text and leave purely visual capitalization and punctuation mechanics to [typography](typography.md#wrapping-and-truncation).

Reserve room for actual translated strings through [layout](layout.md#disclosure-and-adaptation), not an assumed expansion percentage. Copy specificity is useful only while it stays true: names, counts and recovery destinations should follow actual product state.

## Verification

Check every label against the action it invokes, every link against its destination, every error against a real recovery and every repeated term against neighboring copy. Source review can establish many copy findings; render when truncation, contextual ambiguity or localization fit determines the result. Report evidence and requested edits, not a new voice imposed on an isolated flow. For a combined review, use [evidence discipline](principles.md#evidence-and-verification) and do not issue a second competing verdict.
