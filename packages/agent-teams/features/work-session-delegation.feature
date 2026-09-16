Feature: Work Session identity and delivery
  Work sessions are fresh for each Assignment Attempt and use exact incarnation routes.

  Scenario: Exact session routes prevent replacement confusion
    Given a resident name has an old and replacement incarnation
    When a caller uses the old exact session handle
    Then it cannot affect the replacement incarnation

  Scenario: Fresh assignment delivery uses a new Pi session
    Given a resident receives a new Assignment Attempt
    When the runtime delivers its Work prompt
    Then the prompt runs after a fresh session reset succeeds
