# DEPENDENCY_AUDIT — TwinLedger v3.0

Measured at commit `0afdbd8`.

## D-1 Runtime dependency surface

```
$ make release-audit   ->  [PASS] DEPS
109 runtime modules parsed, 0 undeclared external import(s)
```

The runtime is **stdlib-only**. There is no `requirements.txt`, no
`pyproject.toml` dependency list, and no install step — which is why the
submission works offline in the jury container with no network.

| Item | Value |
|---|---|
| Runtime modules parsed | 109 |
| Third-party runtime imports | **0** |
| Python version used | 3.11.2 (recorded in `performance_report.json`) |
| Platform recorded | `Linux-6.1.158+-x86_64-with-glibc2.36` |

Stdlib modules relied on for correctness-critical behaviour:
`fractions` (exact reward arithmetic), `decimal` (rounding only),
`hashlib`/`hmac` (cursor signing, commitments), `zoneinfo` (period boundaries),
`json`, `base64`, `subprocess` (sandbox launcher), `ast` (calculator safety).

## D-2 Optional / test-only dependencies

| Dependency | Status |
|---|---|
| `hypothesis` | optional; property tests skip cleanly when absent (1 of 18 skips) |
| Docker CLI | required only for `make docker-check`; **absent in this sandbox** |
| Git | required only by some tooling (not by the runtime or `make verify`) |

No optional dependency gates a correctness claim: the authoritative suites
(`make verify`, `make test`, `make test-official`, `make replay-all`,
`make release-audit`) run with stdlib only.

## D-3 Supply-chain risk

Because there are zero third-party runtime packages, the usual supply-chain
attack surface (typosquatting, transitive dependency compromise, lockfile
drift) does not apply to the runtime. The residual risk is instead:

1. **Python version drift.** Behaviour depends on `fractions`, `decimal` and
   `zoneinfo` semantics. Mitigated by exact-rational arithmetic (no float
   comparisons in scoring) and by recording the interpreter version in
   artifacts.
2. **Timezone database version.** `zoneinfo` uses the system tzdata; a tzdata
   change could move a period boundary. Not measured here — listed as a
   residual risk.
3. **Build-time tools** (Docker base image) are pinned in the `Dockerfile`;
   the image build is unverified in this sandbox (no docker).

## D-4 Frozen contracts and pinning

`configs/release_freeze.json` pins 30 files with SHA-256:

```
$ python3 tools/freeze_release.py --verify
[PASS] freeze_release --verify: 30 frozen files intact (aggregate_sha256=0747baf087b9509a...)
```

Every generated artifact carries `config_hash` (for the scoring config) so a
result can be tied to the exact configuration that produced it.

## D-5 Dependency defects found

**None.** No undeclared import, no missing dependency, no version conflict.
The only dependency-related finding is that docker-based verification could
not be executed in this environment (recorded as UNVERIFIED in
`REPRODUCIBILITY_AUDIT.md`, not as PASS).
