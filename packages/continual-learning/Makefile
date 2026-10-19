# Verification gates for pi-continual-learning.
#
# Run from this directory. `make check` is the local completion gate; `make test`
# is the full package suite and takes about 13 minutes.
#
# This checkout is shared with other sessions. A failure in a file you did not
# touch is often a mid-run edit by another owner: re-run that single file with
# `make test-one FILE=packages/continual-learning/tests/test_x.py` before treating
# it as a regression.
#
# Nothing here makes a paid call. `make dossiers` is a read-only offline probe.

REPO := ../..
PKG := packages/continual-learning
PRIVACY_TESTS := \
	$(PKG)/tests/test_jev_learning.py \
	$(PKG)/tests/test_jev_memory_pair.py \
	$(PKG)/tests/test_learning_controls.py \
	$(PKG)/tests/test_validate_consolidate.py

.PHONY: help test test-one test-privacy typecheck pack dossiers check

help:
	@echo "make test          full package suite (about 13 min)"
	@echo "make test-privacy  the four guard/consolidation files (about 1 min)"
	@echo "make test-one      FILE=packages/continual-learning/tests/test_x.py"
	@echo "make typecheck     pnpm typecheck over the extension project"
	@echo "make pack          pnpm pack --dry-run for this package"
	@echo "make dossiers      re-measure the privacy guard over retained dossiers (0 calls)"
	@echo "make check         typecheck + pack + full suite"

test:
	cd $(REPO) && python3 -m pytest $(PKG)/tests/ -q

test-one:
	@test -n "$(FILE)" || (echo "usage: make test-one FILE=packages/continual-learning/tests/test_x.py" && exit 2)
	cd $(REPO) && python3 -m pytest $(FILE) -q

test-privacy:
	cd $(REPO) && python3 -m pytest $(PRIVACY_TESTS) -q

typecheck:
	cd $(REPO) && pnpm typecheck

pack:
	cd $(REPO) && pnpm --dir $(PKG) pack --dry-run

dossiers:
	cd $(REPO) && bun $(PKG)/tests/preflight_dossier_probe.ts

check: typecheck pack test