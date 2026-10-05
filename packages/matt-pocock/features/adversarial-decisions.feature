Feature: Matt Pocock decision and native-dialog boundaries
  Scenario: Native dialog cancellation and abort reap their subprocess
    Given a supported macOS environment with a disposable osascript executable
    When selection is aborted before spawn or after the process starts
    Then the result is cancelled and no native child remains running

  Scenario: Native dialog rejects malformed answers and invalid options
    Given a native adapter receives malformed JXA output or invalid button configuration
    When it parses the response
    Then it raises a controlled validation error without accepting an answer

  Scenario: Native dialog guards environment and configuration failures
    Given the package config is missing, malformed, or disabled by CI or SSH
    When the native adapter is considered
    Then Pi UI remains the safe fallback and no native process is started

  Scenario: Literal options do not invoke the custom-answer path
    Given a decision offers the literal label "Type custom answer..."
    When the user selects that offered option
    Then it is returned as a normal selection and no input dialog is opened

  Scenario: Recommendations match offered labels with surrounding whitespace
    Given an offered option contains surrounding whitespace
    When the same label is supplied as the recommendation
    Then the recommendation is accepted without changing the offered answer
