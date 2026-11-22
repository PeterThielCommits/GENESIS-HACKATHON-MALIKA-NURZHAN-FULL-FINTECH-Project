PYTHON ?= python3
PYTEST ?= $(PYTHON) -m pytest

.PHONY: help setup lint test test-official test-property build-episodes official-eval verify-core verify replay audit-shortcuts mutation-test report docs-verify demo demo-backup release-audit replay-all evidence-write evidence-verify rc-check docker-build docker-check-container docker-check clean

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
	@echo "  make docs-verify      Re-measure every documented number against its artifact (TZ 15.5/15.6)"
	@echo "  make demo             3-minute deterministic jury walkthrough (seed=2025, no network)"
	@echo "  make demo-backup      Technical backup demo: verify + docs-verify + replay + freeze"
	@echo "  make release-audit    Phase 16: secrets, file list, size, dependencies, entrypoint (TZ 16.5/16.6)"
	@echo "  make replay-all       Replay ALL 80 published trajectories and compare every step (TZ 16.4)"
	@echo "  make evidence-write   Phase 17: write the post-release evidence freeze manifest (run AFTER the tree is final)"
	@echo "  make evidence-verify  Phase 17: verify the committed evidence freeze against the tree (TZ 17.1-17.3)"
	@echo "  make rc-check         Release candidate gate: verify + docs-verify + replay-all + release-audit + evidence-verify"
	@echo "  make docker-check     Offline Docker check (--network=none --cpus=2 --memory=4g)"
	@echo "  make clean            Remove generated temp artifacts (keeps sealed source inputs)"

setup: ## Check Python version and optional extras; nothing is downloaded
	@$(PYTHON) -c "import sys; v=sys.version_info; assert (3,11) <= v < (3,12), f'need Python 3.11, got {sys.version}'; print(f'Python OK: {sys.version.split()[0]}')"
	@$(PYTHON) -c "import importlib.util as u; print('pytest:', 'present' if u.find_spec('pytest') else 'ABSENT (optional)'); print('hypothesis:', 'present' if u.find_spec('hypothesis') else 'ABSENT (optional)'); print('jsonschema:', 'present' if u.find_spec('jsonschema') else 'ABSENT (optional)')"

lint: ## Compile check (read-only rootfs safe) + import-boundary scan (REQ-ARC-001)
	@$(PYTHON) -c 'import pathlib; roots = "judge_adapter.py core contracts adapter gen invariants verifier nlp env harness scoring seal arena metamorphic judge tools tests independent_verifier".split(); [compile(p.read_bytes(), str(p), "exec") for r in roots for p in ([pathlib.Path(r)] if pathlib.Path(r).is_file() else sorted(pathlib.Path(r).rglob("*.py")))]'
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

verify-core: lint ## Critical core + release blockers
	@$(PYTHON) judge/verify.py --core

verify: lint ## Full 12-gate verification + all 17 reports
	@$(PYTHON) judge/verify.py --full

replay: ## Trajectory determinism & fresh-process CLOSED_EVAL replay (REQ-SEAL-030, P01..P20)
	@$(PYTHON) -m harness.replay --verify-suite
	@$(PYTHON) -m unittest tests.official.test_block4_paired -v

audit-shortcuts: ## Metadata-only shortcut classifier (AUC <= 0.55) + side-channel & C20 leakage audit
	@$(PYTHON) tools/check_import_boundaries.py
	@$(PYTHON) judge/shortcut_audit.py
	@$(PYTHON) judge/canary_fuzzer.py
	@$(PYTHON) -m unittest tests.official.test_block1_contracts.TestBlock1ContractsC01ToC20.test_C20_no_leakage_across_all_records_docs_errors_and_process_isolation -v

mutation-test: ## 26-mutant matcher/reward suite + Official Block 3 (#1..20 + M01..M12)
	@$(PYTHON) judge/mutation_suite.py
	@$(PYTHON) -m unittest tests.official.test_block3_scorer -v

report: ## Synthesize report_index.json + offline self-contained report.html
	@$(PYTHON) judge/report.py

docs-verify: ## Re-measure every documented claim against its evidence artifact (TZ 15.5, 15.6)
	@$(PYTHON) tools/verify_doc_claims.py

demo: ## 3-minute deterministic jury walkthrough (master_seed=2025, offline)
	@$(PYTHON) tools/demo_walkthrough.py

demo-backup: ## Technical backup demo (TZ 15.4): gates + claims + replay + freeze, fail-closed
	@echo "== B1/4 full verification =="
	@$(MAKE) --no-print-directory verify
	@echo "== B2/4 documentation claims =="
	@$(MAKE) --no-print-directory docs-verify
	@echo "== B3/4 replay determinism =="
	@$(PYTHON) -m harness.replay --verify-suite
	@echo "== B4/4 frozen contract surface =="
	@$(PYTHON) tools/freeze_release.py --verify
	@echo "demo-backup: PASS (all four probes green)"

release-audit: ## Secrets, file list, package size, dependencies, official entrypoint (TZ 16.5/16.6)
	@$(PYTHON) tools/release_audit.py

replay-all: ## Replay every published trajectory and compare all 80 runs (TZ 16.4)
	@$(PYTHON) tools/replay_all_trajectories.py

evidence-write: ## Phase 17: archive the release surface (code+config hashes) and the gate verdicts (TZ 17.1-17.3)
	@$(PYTHON) tools/evidence_freeze.py --write

evidence-verify: ## Phase 17: verify the committed evidence freeze against the working tree (TZ 17.1-17.3)
	@$(PYTHON) tools/evidence_freeze.py --verify --require-reports

rc-check: ## Release candidate gate (TZ 16.2/16.4/16.5/16.6, 17.1-17.3): verify + docs + replay + audit + evidence
	@$(MAKE) --no-print-directory verify
	@$(MAKE) --no-print-directory docs-verify
	@$(MAKE) --no-print-directory replay-all
	@$(MAKE) --no-print-directory release-audit
	@$(MAKE) --no-print-directory evidence-verify
	@echo "rc-check: PASS (release candidate is consistent)"

docker-build: ## Build the offline verification image
	@docker build -t twinledger:eval .

docker-check-container: ## Run the offline verification container (image must exist)
	@docker run --rm --network=none --cpus=2 --memory=4g -e GITHUB_ACTIONS="$${GITHUB_ACTIONS:-}" --security-opt no-new-privileges:true --cap-drop ALL --read-only --tmpfs /tmp:rw,noexec,nosuid,mode=1777,size=256m --tmpfs /app/artifacts/reports/latest:rw,noexec,nosuid,uid=10001,gid=10001,mode=0775,size=64m --tmpfs /app/artifacts/reports/doc_claims:rw,noexec,nosuid,uid=10001,gid=10001,mode=0775,size=16m --tmpfs /app/artifacts/trajectories:rw,noexec,nosuid,uid=10001,gid=10001,mode=0775,size=64m twinledger:eval make verify

docker-check: ## Offline Docker verification: build image, then run it hardened
	@$(MAKE) --no-print-directory docker-build
	@$(MAKE) --no-print-directory docker-check-container

clean: ## Remove generated temp artifacts only (never sealed source inputs)
	rm -rf artifacts/reports/latest/*.json artifacts/reports/latest/*.txt artifacts/reports/latest/*.csv artifacts/reports/latest/*.html artifacts/reports/latest/*.md
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "clean: generated artifacts removed"
