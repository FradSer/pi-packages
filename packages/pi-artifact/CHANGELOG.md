# pi-artifact

## 0.1.0

### Minor Changes

- Initial release: native `/artifact` command menu wrapping the vendored Open Artifacts CLI — publish, update (with merged-manifest target picker), status drift check, and show (with version-history picker). Procedures are delivered as follow-up messages through shared pi-kit helpers (`resolvePackageDir`, `loadProcedure`); natural-language requests route via a guidance block with no skill surface. The bundled CLI defaults to coda0.com, the recommended hosted instance, while `--api`, `OPEN_ARTIFACTS_URL`, and config overrides keep it instance-neutral.
