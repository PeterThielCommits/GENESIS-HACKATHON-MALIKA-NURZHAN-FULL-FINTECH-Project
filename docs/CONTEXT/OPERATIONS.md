# Operations — generate, publish, verify, inspect

Runnable recipes. Everything is offline and deterministic; no environment variables or
credentials are required.

---

## 1. Health check (do this first, every session)

```bash
make test     # 273 tests, exit 0
make sweep    # 6/6 gates, exit 0, writes artifacts/phase-04/sweep-24.json
```

`make verify` runs both. If it fails, stop and fix before building anything.

## 2. Build one episode in memory

```python
from gen.config import load_generator_config
from gen.build_episodes import build_episode

episode = build_episode(
    master_seed="demo-001",
    config=load_generator_config(),
    difficulty="L2",                 # L1 | L2 | L3
    created_at="2026-11-21T00:00:00+00:00",   # pin it for reproducible ids
)

episode.episode_id        # 'EP-L2-…'
episode.mode              # 'ANOMALOUS' | 'CLEAN'
episode.public_files      # dict: 12 public files (text)
episode.manifest          # public-safe manifest
episode.truth             # SEALED — scoring only
episode.provenance        # SEALED — audit trail
episode.findings          # candidate findings (objects)
episode.reject_stats      # {'attempts': n, 'accepted': True, 'by_reason': {...}}
```

A **clean** episode: `anomaly_count=0`. An episode that cannot pass every gate within the
budget raises `RejectBudgetExhausted` with the frozen reason breakdown — it is never returned
half-valid.

## 3. Publish to disk

```python
from gen.serialize import write_episode, verify_written_episode, read_public_episode

written = write_episode(episode, "artifacts/episodes")
written.public_dir, written.sealed_dir, written.manifest_path
written.public_digest

verify_written_episode(written.root)["ok"]     # True: hashes re-derived, no stray files
read_public_episode(written.root)              # {'manifest': …, 'files': {12 files}}
```

Rules enforced by the writer:

* atomic staging + `rename` (no partial episodes);
* same seed → same bytes → idempotent rewrite;
* different package into an existing directory → `ContractError`;
* forbidden public file names (truth/provenance/sealed/reject/canary) → `ContractError`;
* canary scan over public text → hard reject on any hit.

## 4. Build a corpus

```python
from gen.build_episodes import build_episode_set
from gen.config import load_generator_config

episodes, failures = build_episode_set(
    seeds=[f"corpus-{i:03d}" for i in range(24)],
    config=load_generator_config(),
    difficulty="L2",
)
len(episodes), failures    # failures carry the reject reason breakdown
```

## 5. Run the gate sweep

```bash
python3 tools/phase4_sweep.py --seeds 24 --difficulties L1,L2 --json artifacts/phase-04/sweep-24.json
echo $?    # 0 only if all six gates pass
```

Output includes `gates`, `anomaly_types`, `subtypes`, `forbidden_violations`,
`catalogue_problems`, `deterministic`, and `elapsed_seconds`. This file is the phase evidence;
commit it.

## 6. Inspect a published episode by hand

```bash
ls artifacts/episodes/EP-L2-*/public            # exactly 12 files
cat artifacts/episodes/EP-L2-*/manifest.json    # public-safe; note commitment, no findings
cat artifacts/episodes/EP-L2-*/sealed/truth.json        # the answer (never ship to a solver)
cat artifacts/episodes/EP-L2-*/verifier_report.json     # signature decisions + diff summary
```

A useful sanity loop: `jq '.findings[].affected_ids' sealed/truth.json`, then grep those ids in
`public/` and confirm the evidence really is there. That is exactly what
`test_truth_evidence_is_reachable` automates.

## 7. Repository hygiene tasks

| Task | Command |
|---|---|
| full test suite | `make test` |
| one suite | `python3 -m unittest tests.gen.test_diff_truth` |
| refresh generated context | `python3 tools/export_context.py` |
| detect stale context | `python3 tools/export_context.py --check` |
| clean caches | `make clean-pyc` |
| check git state before commit | `git status --short` |

## 8. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `RejectBudgetExhausted` | the seed/config pair has no viable target for any configured family | use another seed; check `by_reason` first — `NO_CANDIDATE_PARAMS` means the clean book lacks candidates, `SIGNATURE_MISMATCH` means the operator over-reached |
| `ConfigError: anomaly_count exceeds configured maximum` | asked for more anomalies than `max_anomalies_per_episode` (3) | lower `anomaly_count` or raise the config value (changes `config_hash`) |
| `ContractError: episode directory already exists with a different digest` | publishing a different package into an existing episode dir | remove the directory or use a different seed |
| Tests pass locally but digests differ in CI | a float crept in, or `datetime.now()`/global RNG was used | INV-13 and canonical serialisation reject floats; check new code for wall-clock calls |
| `unsupported JSON-Schema keyword` | schema uses a keyword outside the enforced subset | add it to `contracts/jsonschema_subset.py` deliberately, or stop using it |
