# TwinLedger — Decision Log (append-only)

Format: `D-<phase>-<nn>` + date + status. Never rewrite history; add a
new entry to supersede.

## D-00-01 (2026-11-20) — Official organiser contract status: UNKNOWN

The attached Master TZ v3.0.0 is preserved verbatim at
`docs/reference/TwinLedger_v3_Master_TZ_AI_Agents.txt` (SHA-256
`a46cdb63bb4b41aabb95a842406f5a4fff91e218ead1e4f97b22b60d1c748e36`).
No separate organizer-issued TZ, rubric, sample I/O or starter code was
present in the repository at Phase 0/1 start (repo contained only
`README.md` + initial commit `c961a00`). All Master TZ assumptions
A-001…A-016 about the competition are therefore **UNRESOLVED** and
isolated in `adapter/` + `configs/`. Owner: A0. Closure condition:
organizer contract published → copy to `docs/official/`, record
hash/date/source, update this log + `docs/QUESTIONS.md`.

## D-01-01 (2026-11-20) — Contract freeze v1.0.0 for MVP (Phase 1)

Schemas in `contracts/` frozen at `1.0.0` (`contracts/version.json`).
Further changes require an approved CR (`docs/CR/`). Owner: A0.
Rationale: TZ Phase 1 exit gate.

## D-01-02 (2026-11-20) — Flat package layout (no `twinledger/` prefix)

Top-level packages `gen/`, `verifier/`, `env/`, … per Master TZ 6, so
import-boundary rules map 1:1 to directories. Owner: A0.

## D-01-03 (2026-11-20) — Stdlib-only core; optional extras isolated

Core uses Python 3.11 stdlib only (`requirements-core.txt` empty).
`pytest`/`hypothesis`/`jsonschema` are dev-only; `gymnasium`/`numpy`/
`scikit-learn`/`matplotlib` are extras. Owner: A0. (TZ 22.1–22.2)

## D-01-04 (2026-11-20) — Sealed data git policy (provisional)

`episodes/*/sealed/` and `episodes/hidden/` are git-ignored by default
(`.gitignore`). Public episode fixtures may be committed. Revisit in
Phase 0 once organiser submission rules are known. Owner: A0.

## D-01-05 (2026-11-20) — Provisional reward/budget in configs, not code

`configs/scoring/default.json` (ETA=0.05, max_steps=100) and
`configs/environment/default.json` (CLOSED_EVAL, 100 steps, page 50)
hold provisional values (A-004/A-005). Code must read them; no hidden
defaults. Owner: A0.

## D-01-06 (2026-11-20) — Rubric map is provisional

`judge/rubric_map.json` has `provisional: true`. Internal test counts
must never be presented as official organiser checks (TZ 23.4/23.6).
Owner: A0/D.

## Assumptions register (A-001…A-016)

All UNRESOLVED pending D-00-01 closure. Isolated in `adapter/` +
`configs/`; not baked into core logic. See `docs/QUESTIONS.md` Q-001…Q-014.

## D-02-01 — local primitive conventions (provisional)
FX rate input is positive fixed-point text in target/source direction. Conversion
accepts signed int64 inputs/outputs and records one final rounding operation.
Monthly and quarterly periods use month-aligned fiscal calendars; quarters are
labelled by fiscal start year. Reject gaps; reject folds unless explicitly resolved.
A date without time is a company business date, not a machine-local instant.
Aging labels and open/partial/paid statuses are MVP group semantics, not organizer rules.
