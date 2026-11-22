# Verification gates for pi-continual-learning.
#
# Run from this directory. `make check` is the local completion gate.

REPO := ../..
PKG := packages/continual-learning
PRIVACY_TESTS := \
	$(PKG)/tests/test_jev_learning.py \
	$(PKG)/tests/test_learning_controls.py \
	$(PKG)/tests/test_validate_consolidate.py

.PHONY: help test test-bun test-one test-privacy typecheck pack check

help:
	@echo "make test-bun      native Bun test suite (~12s)"
	@echo "make test          Python package test suite"
	@echo "make test-privacy  the guard/consolidation privacy files"
	@echo "make test-one      FILE=packages/continual-learning/tests/test_x.py"
	@echo "make typecheck     bun run typecheck over the extension project"
	@echo "make pack          bun pm pack check for this package"
	@echo "make check         test-bun + typecheck + pack"

test-bun:
	cd $(REPO) && bun test $(PKG)/tests/

test:
	cd $(REPO) && uv run pytest $(PKG)/tests/ -q

test-one:
	@test -n "$(FILE)" || (echo "usage: make test-one FILE=packages/continual-learning/tests/test_x.py" && exit 2)
	cd $(REPO) && uv run pytest $(FILE) -q

test-privacy:
	cd $(REPO) && uv run pytest $(PRIVACY_TESTS) -q

typecheck:
	cd $(REPO) && bun run typecheck

pack:
	cd $(REPO) && bun pm pack --destination /tmp --quiet --cwd $(PKG)

check: test-bun typecheck pack
