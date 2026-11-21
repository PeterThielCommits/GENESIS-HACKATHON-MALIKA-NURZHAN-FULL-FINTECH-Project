# Honest Limitations (Scenario-Linked)

Every limitation below is tied directly to concrete verified scenarios in
TwinLedger (`D01..D20`, `C01..C20`, `L`, `P01..P20`). No claims are made
regarding LLM or RL fine-tuning improvement, as no model training comparison
was run in this repository.

1. **Synthetic Accounting Domain Scope (`D01..D20`):**
   - TwinLedger models a synthetic accrual double-entry chart of accounts
     (7 standard accounts, 5 currencies `KZT/USD/EUR/JPY/KWD`, 4 anomaly
     classes + 2 multi-anomaly interaction classes). It does **not** cover tax
     filings, payroll, multi-entity consolidation, deferred tax, inventory
     costing (FIFO/LIFO), or real statutory compliance.
2. **Table-Scan Budget Ceiling for `simple_reconciliation` (`L`, >4,950 rows):**
   - On standard episodes (`D01..D20`, ~200–300 total rows across tables) and
     fixture `L` (~700 rows), `simple_reconciliation` completes full table
     scans in `7..15` steps (`mean_steps=7.3` on `D01..D20`). However, on very
     large books exceeding `99 * 50 = 4,950` rows across scanned tables, a naive
     sequential scan cannot read every row within the 100-action budget without
     targeted filtering or prioritization.
3. **Rule-Based vs. Learned Agent Evaluation:**
   - The four baseline policies (`random`, `simple_reconciliation`,
     `mass_flagging`, `oracle`) validate environment soundness, reward shaping,
     and baseline separation (`+0.9920 >= +0.9853 >> -0.5060 > -1.0000`). We
     make **no** claim that training an RL/LLM agent on TwinLedger improves
     real-world financial auditing performance.
4. **OS Process Isolation Boundary (`C20`):**
   - Public baseline policies execute in a separate OS child process
     (`arena.policies.worker`) with a sanitized environment and stdin/stdout
     JSONL messaging, enforcing strict separation inside the evaluation harness.
     Stronger kernel-level sandboxing (seccomp/namespaces/read-only container
     mounts) is expected to be enforced by the outer Docker container runtime
     (`--network=none --cpus=2 --memory=4g`, non-root user `uid 10001`).
5. **Wall-Clock Timeout Determinism (`C18`):**
   - The 60-second wall-clock episode limit is enforced in both
     `OfficialJudgeEnv` (via injectable monotonic clock, tested deterministically
     in `test_C18`) and `harness/isolated_runner.py` (via `select` timeout +
     subprocess `kill`). Actual wall-clock latency varies by host CPU; on the
     reference 2-CPU environment, worst-case baseline episode duration across
     `D01..D20` is `0.084s`.
6. **Backward Compatibility of Legacy Internal Modules:**
   - Legacy Phase 1–6 modules (`env/environment.py`, `scoring/reward.py`,
     `scoring/matcher.py`, `configs/scoring/default.json`) remain intact to
     preserve the frozen `contracts/*.schema.json` v1.0.0 suite (214 unit
     tests). All official Genesis FinTech 2026-11-20 grading traffic runs
     through `judge_adapter.py` -> `adapter/official_env.py` +
     `scoring/official_scorer.py`.
