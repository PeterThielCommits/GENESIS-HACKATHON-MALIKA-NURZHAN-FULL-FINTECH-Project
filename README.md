# TwinLedger v3.0 — Twin Accounting Benchmark (generator side)

Synthetic, fully deterministic accounting episodes for evaluating AI agents on real
financial-discovery work. Every episode ships a **clean** twin and a **mutated** twin of the
same books, a commit-reveal sealed truth, and a public surface that contains no answer.

Built for the GENESIS Hackathon. Offline, Python 3.11 **standard library only**, no network,
no external LLM.

---

## Status

| Item | Value |
|---|---|
| Current phase | **4 — DONE** (exit gate passed) |
| Test suite | 254 tests, 0 failures, 0 skips |
| Gate sweep | 48/48 episodes published, 0 rejects, 6/6 gates |
| Anomaly families implemented | `DUPLICATE_PAYMENT`, `PARTIAL_PAYMENT_ALLOCATION` (3 subtypes each family covered) |

Details: [`docs/STATUS.md`](docs/STATUS.md), [`docs/PHASE_REPORTS/PHASE-04.md`](docs/PHASE_REPORTS/PHASE-04.md).

## Quick start

```bash
make test      # full test suite (stdlib unittest, no dependencies)
make sweep     # 24 seeds x L1/L2 gate sweep -> artifacts/phase-04/sweep-24.json
make verify    # both; the Phase 4 exit gate
```

Generate a single episode:

```python
from gen.build_episodes import build_episode
from gen.config import load_generator_config

episode = build_episode(
    master_seed="demo-001",
    config=load_generator_config(),
    difficulty="L2",
)
print(episode.episode_id, episode.mode, len(episode.findings))
print(sorted(episode.public_files))              # exactly 12 public files
print(episode.truth["findings"][0]["type"])      # sealed: scoring only
```

Publish it with a hard public/sealed split:

```python
from gen.serialize import write_episode, read_public_episode, verify_written_episode

written = write_episode(episode, "artifacts/episodes")
public_view = read_public_episode(written.root)  # needs no sealed/ directory
assert verify_written_episode(written.root)["ok"]
```

## Layout

```
contracts/   frozen JSON schemas, row models, immutable Book model, canonical serialisation
core/        money (integer minor units), time rules (zoneinfo/DST), deterministic ids
invariants/  INV-01..17 checks over the public book (no generator imports)
gen/         clean twin builder, mutation operators + registry, structural diff,
             candidate truth, distractors, rejection sampling, publish/serialize
tools/       phase4_sweep.py — the executable exit gate
tests/       unit, contracts, gen, invariants, integration, security
docs/        official TZ, phase reports, agent reports, decisions, current state
```

## Design commitments

* **Truth is earned, not declared.** A finding requires diff facts, an observed invariant
  violation matching the frozen signature, and reachable public evidence.
* **The clean twin is untouched by mutation** — asserted byte-for-byte.
* **Sealed boundary.** `public/` holds exactly 12 book files; truth, provenance, seeds,
  operator identities and canary markers never appear there.
* **Determinism.** Same seed → same bytes, across processes and Python hash seeds.
* **Honest reporting.** Every number in the docs comes from a command with an exit code.

## Documentation

* [`docs/STATUS.md`](docs/STATUS.md) — current state, one screen
* [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) — architecture and load-bearing invariants
* [`docs/DECISIONS.md`](docs/DECISIONS.md) — append-only decision log
* [`docs/CONTEXT/NEXT_AGENT.md`](docs/CONTEXT/NEXT_AGENT.md) — handover for the next agent
* [`docs/official/`](docs/official) — the master TZ and the universal phase-execution prompt
