# @fradser/pi-monitor

## 2.0.0

### Major Changes

- e55e25e: Replace raw progress-log streaming with result-contract monitoring. `monitor_start` now requires `result_pattern`, supports an optional `failure_pattern`, scans stdout and stderr without injecting progress into model context, and emits one structured terminal result with a bounded diagnostic tail. Remove the model-facing `monitor_read` output reader so agents wait for the contracted terminal notification instead of polling.

## 1.0.0

### Major Changes

- e09c395: Replace raw progress-log streaming with result-contract monitoring. `monitor_start` now requires `result_pattern`, supports an optional `failure_pattern`, scans stdout and stderr without injecting progress into model context, and emits one structured terminal result. Add `monitor_read` for bounded, on-demand diagnostics and retain recent completed monitor output for inspection.

## 0.1.1

### Patch Changes

- 1c5e807: Rename to @fradser/pi-monitor and publish for the first time.
