Feature: A lifecycle row paints one band, not a receipt dump

  A child is a lifecycle event like any other background tool: one started
  band naming the child and what it is doing now, expandable to the prompt and
  the effective grant. The structured details stay model-facing; the transcript
  shows the row. Nothing is injected by a caller, so installing the package
  alone is enough to get the row.

  Rule: Disk identity provenance stays out of the collapsed row

    A disk definition supplies its role, Memory and private history; no invocation
    flag declares them. The model reads scope/source in the structured details and a
    person reads that source in expanded detail, never instead of the prompt.

    Scenario: A disk identity source does not lead the row
      Given a saved definition supplying its own private session
      When a child starts from it with a prompt
      Then the collapsed row leads with the prompt
      And the record the session came from appears only when expanded

  Rule: A standalone child's activity uses the shared above-editor widget

    Scenario: Startup is visible before readiness resolves
      Given the standalone extension in a TUI session
      When a child is reserved and its native readiness is still pending
      Then pi-kit's passive widget shows its name and Starting activity above the editor
      And it uses pi-kit's spinner cadence and width fitting

    Scenario: Streaming activity refreshes without polling
      Given a child starting in a TUI session
      When its RPC stream reports thinking, text or an active tool
      Then the widget shows the latest activity through the same shared row
      And control characters are sanitized and narrow or wide rows fit their width

    Scenario: Package module roots share roster observation
      Given one extension entry observes the roster from its own module root
      When another module root registers or streams a child
      Then the observer refreshes without polling
      And unsubscribe prevents later callbacks
      And stale incarnation frames trigger no updates

    Scenario: Settlement keeps a resident visible while confirmed closure clears activity
      Given one or more active standalone children
      When a child settles and another confirms stopping
      Then the settled child remains visible as Idle and ready for input with a static pending marker
      And the stopped child row disappears while other active rows remain
      And shutdown unsubscribes roster updates and clears the widget

    Scenario: The widget is terminal-only and has one owner
      Given a print or RPC session, or a coordinator-owned child
      When its roster changes
      Then the standalone entry mounts no widget for that child
      And a standalone child started alongside a coordinator still gets its own row

  Rule: The package entry binds the shared row renderer

    Scenario: Registering the extension supplies its own result renderer
      Given the package extension entry loaded outside a rendered session
      When it registers the intent tools
      Then the tools carry a result renderer and an empty call line
      And a result renders without a live theme, because the expand hint is resolved per render

    Scenario: A started child renders one band naming it and its work
      Given a started child handed a two-line prompt
      When its result is rendered collapsed
      Then the row reads as an agent started for that child
      And the prompt's first line is on the row
      And no session handle appears anywhere in the row

    Scenario: The effective model is displayed once in expanded startup details
      Given a prompted child whose structured detail names its effective model
      When its startup row renders collapsed
      Then the model detail is not copied into the activity summary
      When the row renders expanded
      Then one model line shows the effective model
      And the original model detail and structured model field remain unchanged
      And the same rule applies to a coordinator-hosted startup

    Scenario: Expansion reveals the grant and the rest of the prompt
      Given a started child granted read
      When its result is rendered expanded
      Then the row lists the effective grant
      And every remaining line of the prompt is present
      And the row stays inside the terminal width it was given

    Scenario: A start requires a prompt
      Given a startup request without a prompt
      When the request is validated
      Then it is refused before reservation or process effects
      And no row promises that the child will take later work

  Rule: Input-control receipts expand and collapse through the same native tool row

    Scenario: A long single-line steer is fully available on expansion
      Given a working exact child accepts a steer longer than the collapsed headline
      When its steered row renders collapsed
      Then it shows one width-fitted preview and the configured expansion hint
      When the row renders expanded
      Then the bounded authored steering text is displayed once including its first-line tail
      And the exact session, observed state and next actor are expanded metadata
      And collapsing again restores the same compact preview
      And no receipt or structured data is modified by rendering

    Scenario: Short control input still has useful expandable provenance
      Given a next or steer receipt with a short authored input and exact session metadata
      When its row is toggled
      Then expanded mode reveals the exact session and state without repeating the input
      And collapsed mode keeps handles and configuration out of the row

    Scenario: Multiline input is one body rather than a repeated headline
      Given a start, next or steer receipt with multiline input
      When its row renders expanded
      Then its first line and subsequent authored paragraphs each appear once
      And terminal width governs wrapping without a fixed character preview cap

  Rule: The row says what the child is for instead of repeating its name

    Scenario: An applied role description reaches the row
      Given a started child with an inline role description
      When its result is rendered expanded
      Then the role line carries that description
      And the role line does not repeat the child's name, which the subject already carries

    Scenario: A coordination-only grant is disclosed however it was asked for
      Given a started child granted no file or shell tool
      When the caller named no grant at all
      Then the row warns that file and shell work is unavailable
      When the caller explicitly granted an empty tool set
      Then the row warns all the same, because the child is equally unable to read
