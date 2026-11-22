# PERFORMANCE_AFTER — post-remediation state (`0afdbd8`)

Measured with the same harness (`python3 judge/performance_and_deps.py`) on
the same host type, from `make verify` → RC-012.

| Metric | Value | Target |
|---|---:|---|
| `env_step_p50_ms` | 0.0515 | — |
| `env_step_p95_ms` | 0.0845 | — |
| `env_step_p99_ms` | 0.1253 | < 5.0 |
| `peak_rss_mb` | 22.43 | < 300.0 |
| `max_episode_disk_mb` | 0.0812 | < 50.0 |
| status | PASS | |

## Functional result after the fix

Deep pagination of fixture L (214-row ledger, limit 50):

```
AFTER(0afdbd8): pages=5 rows=214 err=None time=0.0042s
```

All 214 rows reachable across 5 pages, no duplicates, no error — the official
C05 requirement.

## Verification timings on the audit host

| Run | Wall clock |
|---|---:|
| `make verify` (12 gates, in the git working tree) | 72.4 s |
| `make verify` (clean `git archive`, empty artifacts, no `git` on PATH) | 65.8 s |
| `make verify-core` (6 gates) | 57.9 s |
| `make rc-check` (verify + docs + replay-all + release-audit) | 77.9 s |
