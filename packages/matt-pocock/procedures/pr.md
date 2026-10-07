# Pull Request Body

Use this procedure when writing a pull request body. Keep the prose brief and use the user's domain language from `GLOSSARY.md`.

The body is a file, not a chat message. Write it to the path the task names, and do not end the turn until that file exists.

Use the smallest view that makes the change clear: a diagram, diff sketch, shallow file tree, pseudocode call tree, or Mermaid sequence. Then show evidence as a before/after pair and name the merge risk.

```markdown
## Summary

<diagram, diff-sketch, or tree>

## Evidence

- **Before:** <screenshot/output/failing test run>
  **After:** <screenshot/output/passing test run>

## Merge Danger

**Door:** <one-way or two-way>

<optional: description>

**Blast Radius:** <one-word description>

<optional: potential ramifications of merge>
```

For logic or an algorithm, use pseudocode. For runtime control flow, use a call tree. For UI structure, show the component tree and the state or module boundaries that matter. For a broad refactor, use a shallow file tree. Use a diff when the point is the exact shape of the change. Keep the final body focused on the concrete problem, resulting behavior, evidence, and merge risk.
