Feature: magpie provider
  Pi reaches every model and routing group magpie serves through one provider.
  The catalog comes from magpie's own gateway rather than a hand-written list,
  so a model added, renamed or removed in magpie appears in Pi without editing
  models.json.

  Background:
    Given the pi-magpie package is installed
    And a magpie gateway answers GET /v1/models

  Scenario: The gateway catalog becomes Pi's model list
    Given magpie serves routing groups and provider models
    When the provider refreshes with network access
    Then every catalog entry becomes a Pi chat model on the magpie provider
    And its id, display name, context window, output limit and input modalities come from magpie
    And Pi's thinking levels follow the reasoning efforts magpie reports for that model

  Scenario: The catalog refreshes without editing models.json
    Given a Pi session starts
    When the last refresh is older than the refresh interval
    Then the provider asks Pi to refresh the magpie catalog over the network
    And a new magpie model is selectable in that session

  Scenario: An existing catalog survives a failed refresh
    Given the provider already serves a catalog
    When the gateway answers with an HTTP error or an empty model list
    Then the previous catalog stays selectable
    And nothing is persisted for the failed attempt

  Scenario: A persisted catalog is restored without network access
    Given Pi persisted the catalog from an earlier session
    When a later start has no network access
    Then the persisted catalog stays selectable
    And the provider contacts no gateway

  Scenario: A saved key alone never redirects requests
    Given a credential holds a key but no gateway address
    When Pi resolves authentication for a model
    Then no base URL is returned for that request
    And the address the model already carries stays in force
    And the provider does not substitute its localhost default

  Scenario: A keyless provider stays unconfigured
    Given neither a stored credential nor MAGPIE_API_KEY exists
    When the provider considers a network refresh
    Then it sends no request to the gateway
    And the provider reports no available models

  Scenario: Operators can limit the listed models
    Given MAGPIE_PI_MODELS names comma-separated globs
    When the catalog is published
    Then only model ids matching a glob are listed
    And routing groups can be listed alone with group/*

  Scenario: The gateway location comes from the environment or models.json
    Given MAGPIE_BASE_URL names a gateway origin
    When the provider refreshes
    Then requests go to that origin with a single trailing slash removed
    And every published model carries that base URL

  Scenario: models.json stays the address Pi sends requests to
    Given models.json sets the magpie provider's baseUrl
    When a model is selected
    Then the request goes to that baseUrl rather than the extension's own
    And a mismatch between the two surfaces as a request timeout, not a silent fallback

  Scenario: magpie's effective prices become Pi's cost figures
    Given the catalog request carries the price header
    When magpie answers with a price for a model
    Then Pi's input, output, cache-read and cache-write costs use those numbers
    And a model magpie cannot price keeps every cost at zero
    And a routing group over differently priced members stays at zero rather than borrowing one price

  Scenario: A local models.json price masks the live one
    Given models.json lists the model with its own cost
    When a turn completes
    Then Pi bills from that local cost, not from magpie's effective price

  Scenario: The README shows the real login screens
    Given the README documents /login magpie
    When a reader follows it
    Then every screenshot it embeds ships with the package
    And each screenshot shows a screen captured from a running Pi session

  Scenario: Streaming goes through Pi's own OpenAI chat implementation
    Given a magpie model is selected
    When a turn streams
    Then the request is sent with Pi's openai-completions implementation
    And magpie translates it to the upstream provider

  Scenario: An unreachable gateway fails as a request timeout
    Given the configured baseUrl cannot be reached
    When a turn runs
    Then Pi reports a request timeout
    And no model from another provider is substituted
