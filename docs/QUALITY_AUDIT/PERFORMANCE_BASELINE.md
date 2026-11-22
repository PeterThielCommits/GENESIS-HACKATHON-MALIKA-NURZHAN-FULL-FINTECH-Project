# PERFORMANCE_BASELINE — pre-fix state (`3a3988e`)

Measured from a pristine `git archive 3a3988e` extraction in `/tmp/base398`,
using the repository's own harness (`python3 judge/performance_and_deps.py`).
This is the honest pre-remediation baseline for the comparison in
`PERFORMANCE_COMPARISON.md`.

| Metric | Value | Target |
|---|---:|---|
| `env_step_p50_ms` | 0.0493 | — |
| `env_step_p95_ms` | 0.0863 | — |
| `env_step_p99_ms` | 0.1427 | < 5.0 |
| `env_step_samples` | 180 | — |
| `max_episode_disk_mb` | 0.0812 | < 50.0 |
| `peak_rss_mb` | 23.46 | < 300.0 |
| status | PASS | PASS |

Platform: `Linux-6.1.158+-x86_64-with-glibc2.36`, Python `3.11.2`,
`config_hash = 0bbdc0c8cfda6621ae4983e2dcb666e8de2cb61252dd3ea43bf378b6e8a8b3d1`.

Caveat (as recorded by the harness): Measured on the host recorded in 'platform'; judge hardware timings may vary slightly.

## Functional baseline measured on the same extraction

Deep pagination of the official fixture **L** (214-row ledger, limit 50):

```
BASELINE(3a3988e): pages=3 rows=150 err={'code': 'BAD_CURSOR',
                    'message': 'cursor signature verification failed'} time=0.003s
```

That is the defect captured as BUG-TL-0002: the walk stops after 150 of 214
rows. The reward formula on the same extraction failed 10 of 11 published
vectors (BUG-TL-0001).
