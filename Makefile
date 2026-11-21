# TwinLedger v3.0 — developer entry points.
#
# The project is offline and standard-library only: no pip install, no network.
# Every target below is deterministic for a given seed and config hash.

PYTHON ?= python3
SEEDS ?= 24
DIFFICULTIES ?= L1,L2
ARTIFACTS ?= artifacts/phase-04

.PHONY: help test test-unit test-contracts test-gen test-invariants test-integration test-security sweep verify clean-pyc

help:
	@echo "make test         run the full stdlib test suite (no skips expected)"
	@echo "make sweep        run the Phase 4 gate sweep ($(SEEDS) seeds x $(DIFFICULTIES))"
	@echo "make verify       run tests + sweep, i.e. the Phase 4 exit gate"
	@echo "make clean-pyc    remove __pycache__ directories"

test:
	$(PYTHON) -m unittest discover -s tests -t .

test-unit:
	$(PYTHON) -m unittest tests.unit.test_money tests.unit.test_time_rules tests.unit.test_ids

test-contracts:
	$(PYTHON) -m unittest tests.contracts.test_schemas

test-gen:
	$(PYTHON) -m unittest tests.gen.test_clean_twin tests.gen.test_operators \
		tests.gen.test_diff_truth tests.gen.test_reject_and_episodes tests.gen.test_registry

test-invariants:
	$(PYTHON) -m unittest tests.invariants.test_invariants

test-integration:
	$(PYTHON) -m unittest tests.integration.test_serialize

test-security:
	$(PYTHON) -m unittest tests.security.test_sealed_boundary

sweep:
	mkdir -p $(ARTIFACTS)
	$(PYTHON) tools/phase4_sweep.py --seeds $(SEEDS) --difficulties $(DIFFICULTIES) \
		--json $(ARTIFACTS)/sweep-$(SEEDS).json

verify: test sweep
	@echo "Phase 4 gate: tests and sweep both completed with exit code 0"

clean-pyc:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
