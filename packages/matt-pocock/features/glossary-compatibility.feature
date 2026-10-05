Feature: Glossary reference compatibility
  Scenario: An existing workflow restores its renamed reference
    Given a persisted workflow loaded domain-modeling and CONTEXT-FORMAT
    When Pi restores its procedure context after the glossary rename
    Then CONTEXT-FORMAT resolves to GLOSSARY-FORMAT
    And the restored workflow retains the glossary instructions
