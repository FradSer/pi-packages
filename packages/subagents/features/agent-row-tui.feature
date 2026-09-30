Feature: The `agent` tool paints a lifecycle row, not a receipt dump

  A spawn is a lifecycle event like any other background tool: one started
  band naming the child and what it is doing now, expandable to the prompt and
  the effective grant. The raw receipt lines stay model-facing; the transcript
  shows the row. Nothing is injected by a caller, so installing the package
  alone is enough to get the row.

  Rule: The package entry binds the shared row renderer

    Scenario: Registering the extension supplies its own result renderer
      Given the package extension entry loaded outside a rendered session
      When it registers the agent tool
      Then the tool carries a result renderer and an empty call line
      And a result renders without a live theme, because the expand hint is resolved per render

    Scenario: A started child renders one band naming it and its work
      Given a started child handed a two-line prompt
      When its result is rendered collapsed
      Then the row reads as an agent started for that child
      And the prompt's first line is on the row
      And no session handle appears anywhere in the row

    Scenario: Expansion reveals the grant and the rest of the prompt
      Given a started child granted read
      When its result is rendered expanded
      Then the row lists the effective grant
      And every remaining line of the prompt is present
      And the row stays inside the terminal width it was given

    Scenario: A child with no prompt says it is waiting
      Given a child started without a prompt
      When its result is rendered collapsed
      Then the row states it will take work assigned to it
      And the model-facing receipt keeps the same statement
