Feature: Release publishing without local provenance assumptions
  The repository release script publishes its explicit package allowlist in
  dependency order and must remain runnable both in GitHub Actions and locally.

  Scenario: Local publishing does not force CI-only provenance
    Given the release script runs outside GitHub Actions
    When it publishes an unpublished package
    Then it does not pass --provenance to npm publish
    And npm authentication errors remain visible to the caller

  Scenario: CI publishing enables npm provenance
    Given the release script runs in GitHub Actions
    When it publishes an unpublished package
    Then it passes --provenance to npm publish

  Scenario: Publishing verifies packed packages contain no unresolved workspace protocols
    Given an unpublished package is ready for publication
    When the release script prepares to publish the package
    Then it verifies the packed tarball manifest contains no workspace protocol dependencies
    And publication halts if an unresolved workspace protocol is detected

  Scenario: Publishing queries the exact target version
    Given a package has a newer version already published
    When the release script checks the local package version
    Then it queries npm for the local version explicitly
    And it publishes only when that exact version is absent

  Scenario: Registry failures stop release evaluation
    Given npm returns a network or authentication error
    When the release script checks a package version
    Then it terminates with the registry error
    And it does not attempt to publish that package

  Scenario: Importing the release module has no side effects
    Given a test imports the release module
    When the module is evaluated
    Then it does not query npm
    And it does not invoke npm publish

  Scenario: Pack validation can run without registry access
    Given the release script is invoked in validation mode
    When it validates the workspace package set
    Then it verifies every package in kit-first order
    And it does not query npm or publish

  Scenario: The release workflow publishes versions after version commits
    Given Changesets has already committed package versions and removed its changesets
    When the release workflow finds no changesets to publish
    Then it runs the explicit package release script
    And the release script publishes versions missing from npm

  Scenario: The main workflow retries versioned package publication
    Given package versions on main are newer than npm
    When the Changesets action has no pending changesets
    Then a main-branch publish step still runs the explicit package release script
    And already published versions are skipped safely

  Scenario: A version that wins the publish race is skipped safely
    Given the release script found a package version absent from npm
    When npm rejects the publish because that version already exists or is staged
    Then the release script captures both publish streams
    And it recognizes the conflict whatever stream carries it
    And it reports the version as already published
    And it continues with the remaining packages
    And it does not fail the release for that conflict

  Scenario: A publish failure that is not a version conflict still stops the release
    Given the release script is publishing an unpublished package
    When npm rejects the publish for any reason other than an existing version
    Then the release script re-emits the captured error output
    And it propagates the error with the registry's own words
    And it does not publish the remaining packages

  Scenario: The main workflow does not publish the version PR working tree
    Given the Changesets action found pending changesets and created or updated a version PR
    When the action leaves the working tree with bumped package versions
    Then the main-branch retry step is skipped
    And publication waits for the version PR merge
    And the retry checks the Changesets action's camelCase `hasChangesets` output

  Scenario: Release actions use Node 24-compatible action versions
    Given the release workflow runs on GitHub-hosted runners
    When GitHub loads the release workflow actions
    Then checkout uses actions/checkout@v5
    And Node setup uses actions/setup-node@v5
    And Bun setup uses oven-sh/setup-bun@v2
    And the npm CLI is upgraded because trusted publishing and provenance need npm 11.5.1

  Scenario: Version bumps refresh the lockfile that packing reads
    Given Changesets has bumped a workspace package version
    When the release workflow versions packages
    Then it runs `bun install` in the same step
    So packed consumers pin the version the version PR declares

  Scenario: A package npm has never published waits for a manual first release
    Given the release script found a package version absent from npm
    And npm holds no record of that package at all
    When the release script plans the publish run
    Then it does not call npm publish for that package
    And it publishes the remaining packages in kit-first order
    And it names the package as needing a manual first release
    And the publish run does not fail for that package

  Scenario: A failed version step reports the tree it ran in
    Given the Changesets version step exits with a failure
    When the release workflow runs its version step
    Then the step reports the checked-out tree and the Changesets output
    And the reason is readable without workflow log access

  Scenario: A failed publish run is readable from the run annotations
    Given the release script fails inside GitHub Actions
    When the run terminates with an error
    Then it reports the failure as a workflow error command
    And the message keeps the registry output that caused it
