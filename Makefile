PYTHON ?= python3
PYTEST ?= $(PYTHON) -m pytest

.PHONY: help setup lint test test-official test-property build-episodes official-eval verify-core verify replay audit-shortcuts mutation-test report docker-check clean

help: ## Show available commands
	@echo "TwinLedger — available make targets:"
	@echo "  make setup            Check Python version and optional extras (no downloads)"
	@echo "  make lint             Style/compile check + import-boundary scan"
	@echo "  make test             All unit, contract, and official mirror tests"
	@echo "  make test-official    Official Genesis FinTech 2026-11-20 mirror suite (C01..C20, D01..D20, Block 3, M01..M12, P01..P20, Baselines)"
	@echo "  make test-property    Property tests (stdlib fallback if Hypothesis missing)"
	@echo "  make build-episodes   Generate train/dev episodes from locked configs"
	@echo "  make official-eval    Run D01..D20 x 4 isolated baseline policies -> artifacts/trajectories/trajectories.jsonl"
	@echo "  make verify-core      Critical core + release blockers"
	@echo "  make verify           Full verification suite (lint + all tests + property + judge kit)"
	@echo "  make report           Aggregated JSON/HTML report"
	@echo "  make docker-check     Offline Docker check (--network=none --cpus=2 --memory=4g)"
	@echo "  make clean            Remove generated temp artifacts (keeps sealed source inputs)"

setup: ## Check Python version and optional extras; nothing is downloaded
	@$(PYTHON) -c "import sys; v=sys.version_info; assert (3,11) <= v < (3,12), f'need Python 3.11, got {sys.version}'; print(f'Python OK: {sys.version.split()[0]}')"
	@$(PYTHON) -c "import importlib.util as u; print('pytest:', 'present' if u.find_spec('pytest') else 'ABSENT (optional)'); print('hypothesis:', 'present' if u.find_spec('hypothesis') else 'ABSENT (optional)'); print('jsonschema:', 'present' if u.find_spec('jsonschema') else 'ABSENT (optional)')"

lint: ## Compile check + import-boundary scan (REQ-ARC-001)
	@$(PYTHON) -m compileall -q judge_adapter.py core contracts adapter gen invariants verifier env harness scoring seal arena metamorphic judge tools tests
	@$(PYTHON) tools/check_import_boundaries.py

test: ## All unit, contract, and official mirror tests (stdlib unittest)
	@$(PYTHON) -m unittest discover -s tests -t . -v

test-official: ## Official Genesis FinTech 2026-11-20 mirror test suite (Blocks 1..5)
	@$(PYTHON) -m unittest discover -s tests/official -t . -v

test-property: ## Property tests; stdlib fallback when Hypothesis is absent
	@$(PYTHON) -m unittest tests.unit.test_property -v

build-episodes: ## Generate train/dev episodes from locked configs
	@$(PYTHON) tools/make_dataset.py --split all

official-eval: ## Run all 4 baseline policies across D01..D20 -> trajectories.jsonl + summary
	@$(PYTHON) tools/run_official_eval.py --seed 2026

verify-core: lint test ## Critical core + release blockers
	@$(PYTHON) judge/verify.py --core

verify: lint test test-property ## Full verification + reports
	@$(PYTHON) judge/verify.py --full

replay: ## Trajectory determinism & fresh-process CLOSED_EVAL replay (REQ-SEAL-030, P01..P20)
	@$(PYTHON) -m harness.replay --verify-suite
	@$(PYTHON) -m unittest tests.official.test_block4_paired -v

audit-shortcuts: ## Metadata-only leakage audit (C20 + boundary scan)
	@$(PYTHON) tools/check_import_boundaries.py
	@$(PYTHON) -m unittest tests.official.test_block1_contracts.TestBlock1ContractsC01ToC20.test_C20_no_leakage_across_all_records_docs_errors_and_process_isolation -v

mutation-test: ## Scorer boundary & mutant tests (Block 3 #1..20 + M01..M12)
	@$(PYTHON) -m unittest tests.official.test_block3_scorer -v

report: ## Aggregated report
	@$(PYTHON) judge/report.py

docker-check: ## Offline Docker verification (--network=none --cpus=2 --memory=4g)
	@docker build --network=none -t twinledger:eval . && docker run --rm --network=none --cpus=2 --memory=4g twinledger:eval make verify

clean: ## Remove generated temp artifacts only (never sealed source inputs)
	rm -rf artifacts/reports/latest/*.json artifacts/reports/latest/*.txt artifacts/reports/latest/*.csv artifacts/reports/latest/*.html
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "clean: generated artifacts removed"
