PYTHON ?= python3
PYTEST ?= $(PYTHON) -m pytest

.PHONY: help setup lint test test-property build-episodes verify-core verify replay audit-shortcuts mutation-test report docker-check clean

help: ## Show available commands
	@echo "TwinLedger — available make targets:"
	@echo "  make setup            Check Python version and optional extras (no downloads)"
	@echo "  make lint             Style/compile check + import-boundary scan"
	@echo "  make test             Unit + contract tests (core)"
	@echo "  make test-property    Property tests (stdlib fallback if Hypothesis missing)"
	@echo "  make build-episodes   Generate train/dev episodes from locked configs (Phase 3+)"
	@echo "  make verify-core      Critical core + release blockers"
	@echo "  make verify           Full rubricator + reports (exit 0 only if all required PASS)"
	@echo "  make replay           Trajectory determinism check (Phase 9+)"
	@echo "  make audit-shortcuts  Metadata-only leakage audit (Phase 12+)"
	@echo "  make mutation-test    Scorer mutants (Phase 13+)"
	@echo "  make report           Aggregated JSON/HTML report"
	@echo "  make docker-check     Offline Docker smoke test"
	@echo "  make clean            Remove generated temp artifacts (keeps sealed source inputs)"

setup: ## Check Python version and optional extras; nothing is downloaded
	@$(PYTHON) -c "import sys; v=sys.version_info; assert (3,11) <= v < (3,12), f'need Python 3.11, got {sys.version}'; print(f'Python OK: {sys.version.split()[0]}')"
	@$(PYTHON) -c "import importlib.util as u; print('pytest:', 'present' if u.find_spec('pytest') else 'ABSENT (optional)'); print('hypothesis:', 'present' if u.find_spec('hypothesis') else 'ABSENT (optional)'); print('jsonschema:', 'present' if u.find_spec('jsonschema') else 'ABSENT (optional)')"

lint: ## Compile check + import-boundary scan (REQ-ARC-001)
	@$(PYTHON) -m compileall -q contracts adapter gen invariants verifier env harness scoring seal arena metamorphic judge tools tests
	@$(PYTHON) tools/check_import_boundaries.py

test: ## Unit + contract tests (core, stdlib unittest)
	@$(PYTHON) -m unittest discover -s tests -t . -v

test-property: ## Property tests; stdlib fallback when Hypothesis is absent
	@$(PYTHON) -m unittest tests.unit.test_property -v

build-episodes: ## Generate episodes from locked configs (Phase 3+; stub in Phase 1)
	@$(PYTHON) tools/make_dataset.py --help >/dev/null 2>&1 || true
	@echo "build-episodes: generator not yet implemented (Phase 3). No episodes written."
	@exit 0

verify-core: lint test ## Critical core + release blockers
	@$(PYTHON) judge/verify.py --core

verify: lint test test-property ## Full rubricator + reports
	@$(PYTHON) judge/verify.py --full

replay: ## Trajectory determinism (Phase 9+; stub in Phase 1)
	@echo "replay: harness not yet implemented (Phase 9). SKIPPED (not PASS)."
	@exit 0

audit-shortcuts: ## Metadata-only leakage audit (Phase 12+; stub in Phase 1)
	@echo "audit-shortcuts: not yet implemented (Phase 12). SKIPPED (not PASS)."
	@exit 0

mutation-test: ## Scorer mutants (Phase 13+; stub in Phase 1)
	@echo "mutation-test: not yet implemented (Phase 13). SKIPPED (not PASS)."
	@exit 0

report: ## Aggregated report
	@$(PYTHON) judge/report.py

docker-check: ## Offline Docker smoke test
	@docker build --network=none -t twinledger:phase1 . && docker run --rm --network=none twinledger:phase1 make verify-core

clean: ## Remove generated temp artifacts only (never sealed source inputs)
	rm -rf artifacts/reports/latest/*.json artifacts/reports/latest/*.txt artifacts/reports/latest/*.csv artifacts/reports/latest/*.html
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "clean: generated artifacts removed"
