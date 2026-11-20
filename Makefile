# TwinLedger - one entry point for developers and the jury.
# Required targets (master spec 23.2) and their current implementation status.
# A target that is not implemented yet says so and exits 5; it never pretends to pass.

PY ?= python3
PY_MIN := 3.11

.DEFAULT_GOAL := help
.PHONY: help setup lint test test-property build-episodes verify-core verify replay \
        audit-shortcuts mutation-test report docker-check clean phase0 models golden ci probe traceability

help: ## Show available commands and what they do
	@echo "TwinLedger - available commands"
	@echo ""
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-16s %s\n", $$1, $$2}'
	@echo ""
	@echo "Exit codes (master spec 23.3): 0 pass, 1 required check failed, 2 config/contract error,"
	@echo "3 resource/environment error, 4 release blocker, 5 suite incomplete / not implemented."

setup: ## Check Python version and optional extras (downloads nothing)
	@$(PY) -m tools.check_setup

lint: ## Style-adjacent checks: compile, boundaries, contracts, registry, models, freeze, CI
	@$(PY) -m compileall -q tools adapter models tests > /dev/null
	@$(PY) -m tools.check_import_boundaries
	@$(PY) -m tools.extract_requirements --check
	@$(PY) -m tools.validate_contracts
	@$(PY) -m tools.check_models
	@$(PY) -m tools.check_golden
	@$(PY) -m tools.check_ci
	@$(PY) -m tools.gen_traceability --check
	@echo "lint: OK"

models: ## Typed models must mirror the contract schemas exactly (parity + round-trip)
	@$(PY) -m tools.check_models

golden: ## Contract freeze: verify that no contract byte changed since GOLDEN.json
	@$(PY) -m tools.check_golden

ci: ## Lint the CI workflow: gate commands, pinned actions, artifact upload
	@$(PY) -m tools.check_ci

probe: ## Look for official starter code and smoke-test it if it exists (skips honestly)
	@$(PY) -m tools.probe_starter

traceability: ## Regenerate docs/RUBRIC_TRACEABILITY.md from the registries
	@$(PY) -m tools.gen_traceability --write

test: ## Unit, contract and Phase 0 tests (unittest, stdlib only)
	@$(PY) -m unittest discover -s tests -t . -p 'test_*.py'

test-property: ## Property-based tests (Hypothesis if present, stdlib loops otherwise)
	@echo "test-property: not implemented yet (PHASE-13). This is NOT a pass."; exit 5

build-episodes: ## Generate train/dev/heldout episodes from locked configs
	@echo "build-episodes: not implemented yet (PHASE-03/04). This is NOT a pass."; exit 5

verify-core: ## Phase gate checks: contracts, governance, boundaries, mandatory tests
	@$(PY) -m tools.verify --profile core

verify: ## Full verification suite with rubric mapping and artifacts (default profile)
	@$(PY) -m tools.verify

replay: ## Reproduce a trajectory and compare hashes
	@echo "replay: not implemented yet (PHASE-08). This is NOT a pass."; exit 5

audit-shortcuts: ## Metadata-only leakage / shortcut audit
	@echo "audit-shortcuts: not implemented yet (PHASE-12). This is NOT a pass."; exit 5

mutation-test: ## Run scorer mutants against the reward suite
	@echo "mutation-test: not implemented yet (PHASE-13). This is NOT a pass."; exit 5

report: ## Build the aggregated JSON report (HTML report is optional later)
	@echo "report: not implemented yet (PHASE-14); verify already writes artifacts/reports/latest/."; exit 5

docker-check: ## Offline Docker build and smoke run
	@echo "docker-check: not implemented yet (PHASE-16). This is NOT a pass."; exit 5

phase0: ## Run the Phase 0 gate and print its open items
	@$(PY) -m tools.verify --profile core --phase-report

clean: ## Remove generated temporary artifacts only (never sealed source inputs)
	@rm -rf artifacts .pytest_cache .ruff_cache .mypy_cache
	@find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "clean: removed artifacts/ and caches; episodes/ and docs/ untouched"
