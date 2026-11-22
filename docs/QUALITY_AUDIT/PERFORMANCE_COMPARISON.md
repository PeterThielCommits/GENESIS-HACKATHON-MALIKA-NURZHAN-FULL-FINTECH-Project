# PERFORMANCE_COMPARISON — `3a3988e` vs `0afdbd8`

Both sides measured with the repository's own harness
(`judge/performance_and_deps.py`, 180 step samples, same host class). Baseline
taken from a pristine `git archive 3a3988e`.

## Environment step latency and memory

| Metric | Baseline `3a3988e` | After `0afdbd8` | Delta |
|---|---:|---:|---|
| `env_step_p50_ms` | 0.0493 ms | 0.0515 ms | +0.0022 (+4.5%) |
| `env_step_p95_ms` | 0.0863 ms | 0.0845 ms | -0.0018 (-2.1%) |
| `env_step_p99_ms` | 0.1427 ms | 0.1253 ms | -0.0174 (-12.2%) |
| `peak_rss_mb` | 23.46 MB | 22.43 MB | -1.0300 (-4.4%) |
| `max_episode_disk_mb` | 0.0812 MB | 0.0812 MB | +0.0000 (+0.0%) |

All three targets still hold with large margin (`p99 < 5 ms`, `RSS < 300 MB`,
`disk < 50 MB`). The p99 delta (-0.0174 ms)
is ~0.02 ms — far below the 5 ms target and within run-to-run noise for a
2-vCPU host. The cursor layout change adds a fixed-width slice and one
`base64.b64encode` call on decode; it does not add a pass over the payload.

## Correctness delta (the part that matters)

| Metric | Baseline | After |
|---|---|---|
| Official reward vectors reproduced | **1 / 11** | **11 / 11** |
| L-fixture ledger rows reachable (214 total) | **150**, then `BAD_CURSOR` | **214 / 214**, 5 pages |
| Cursor offsets usable (0–999) | **935 / 1000** | **1000 / 1000** |
| Trailing-garbage token rejected | **no** | **yes** |
| Mutation mutants killed | 26/26 (3 disarmed, false negative) | 26/26 (3 re-armed on the live path) |
| Full test suite | 490 | 502 |
| `make verify` | 12/12 PASS | 12/12 PASS |
| Trajectory replay | 80/80 | 80/80 |
| Published baselines (oracle / simple / random / mass) | 1.0000/+0.9920 · 1.0000/+0.9853 · 0.2500/−0.5060 · 0.0000/−1.0000 | **identical** |

## Honest reading

Performance is unchanged (the fixes are correctness fixes, not optimisations).
What changed is that the environment now satisfies official C05 on the shipped
L fixture and that internal reward arithmetic matches the published formula.
No performance claim is made about the jury's hardware: the caveat recorded in
both reports stands — timings may vary on different machines.
