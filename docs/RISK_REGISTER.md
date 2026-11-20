# RISK REGISTER

Sources: master specification §27 (R-01…R-24), its §0.3 P0 list, and Phase 0 findings.
Owner column names the accountable zone; status is the *current* truth, not an intention.

Statuses: `OPEN` (real risk, mitigation in progress), `MITIGATED` (control exists and is
tested), `ACCEPTED` (residual risk documented), `WATCH` (no action until a trigger fires).

| ID | Risk | Impact | Mitigation | Control / evidence | Owner | Status |
|----|------|--------|-----------|--------------------|-------|--------|
| P0-1 | Truth leaks to policy through observation, info, error, log or metadata | benchmark invalid | info allowlist in closed mode; sealed truth never mounted; canary scan in Phase 12 | `configs/environment/mode.json`, `docs/THREAT_MODEL.md`, REQ-SEAL-001..005 | B (env) | OPEN |
| P0-2 | Policy reaches scorer memory or sealed files | benchmark invalid | separate process after env close; no sealed path in policy cwd; deny-by-default env vars | D-0012, Phase 8 security tests | B (env) | OPEN |
| P0-3 | Real financial/personal data enters the corpus | legal/ethical defect, disqualification risk | synthetic universe only; jurisdiction codes XA–XZ; schema-enforced patterns; no scraping | `contracts/company.schema.json`, D-0013, `tests/contracts/` | A (gen) | MITIGATED |
| P0-4 | Core reset/step does not work | nothing else matters | Phase 5 gate; contract tests per tool and per error | Phase 5 tasks | B (env) | OPEN |
| P0-5 | Reward contract non-deterministic or wrong | scores meaningless | matcher is the single TP/FP/FN source; exact arithmetic; brute-force reference for ≤7×7 | REQ-SCORE-001..005, Phase 9 | B (eval) | OPEN |
| R-01 | Official rubric differs from our assumptions | wasted effort, mis-scored | adapter/config isolation; rubric map stays internal; CR process | `docs/ASSUMPTIONS.json`, `judge/rubric_map.json` | A0 | OPEN |
| R-02 | Truth is diff-correct but semantically wrong | false ground truth | independent verifier + invariant signatures + hand-authored vectors | Phase 4/6 | C (ver) | OPEN |
| R-03 | Verifier repeats generator's bug | false confidence | separate owner/algorithm/import tree; common-mode report | `docs/INDEPENDENCE.md` | C (ver) | OPEN |
| R-04 | Evidence IDs unreachable via tools | findings impossible to prove | reachability test per evidence ID; ablation test | REQ-VER-010..014 | C (ver) | OPEN |
| R-05 | Matcher ambiguity with overlapping findings | unfair reward | ambiguity rejection; exact affected IDs; deterministic tie-break | REQ-ERR-021, `configs/scoring/match.json` | B (eval) | OPEN |
| R-06 | Inserted record recognisable by metadata | shortcut solution | metadata-only classifier + realistic insertion distribution | REQ-DATA-002, Phase 12 | C (red team) | OPEN |
| R-07 | Text similarity creates false links | wrong findings rewarded | text is supplemental only; structured proof required | REQ-NLP-002 | C (ver) | WATCH |
| R-08 | Prompt injection in documents steers the policy | invalid results | separate robustness track, neutral twin comparison | REQ-NLP-004, Phase 11 | C (red team) | WATCH |
| R-09 | Isolation claimed stronger than implemented | credibility loss with jury | capability table + LIMITATIONS; only claim what is enabled | D-0012, `docs/THREAT_MODEL.md` | D (docs) | MITIGATED |
| R-10 | Commit-reveal mistaken for proof of truth | wrong conclusion | explicit separation in docs and receipts | REQ-SEAL-023 | B (eval) | MITIGATED |
| R-11 | Wall-clock time breaks determinism | replay impossible | truncation only from step budget; watchdog is a run error | `configs/environment/limits.json` | B (env) | MITIGATED |
| R-12 | Timing test with p>0.05 mistaken for equivalence | false isolation claim | predeclared equivalence margin; report as inconclusive | Phase 12 | C (red team) | OPEN |
| R-13 | Legit strategy improvement called an exploit | wrong messaging | separate strategy optimisation from leakage testing | §18.4 | C (red team) | WATCH |
| R-14 | Clean/mutated twins split across train/dev | contaminated evaluation | split by base-history group | `configs/generator/default.json` | A (gen) | OPEN |
| R-15 | Optional extras unavailable offline | suite cannot run | stdlib fallbacks for every critical property; extras only add checks | D-0003, `make setup` | D (QA) | MITIGATED |
| R-16 | Over-engineering consumes time | nothing finished | strict A/B/C cut rule; Phase 0 built only gate infrastructure | §25 | A0 | WATCH |
| R-17 | Shared money helper imports a common-mode bug | verifier and generator wrong together | tiny, hand-vector-tested helper; rate selection implemented twice | §12.4 | A0 | OPEN |
| R-18 | Currency exponent / FX direction confusion | wrong amounts | explicit pair convention + JPY/KWD boundary tests | D-0004 | A (gen) | OPEN |
| R-19 | Timezone transform changes period semantics | invalid metamorphic test | only semantically equivalent instants allowed | §20.3 | D (QA) | OPEN |
| R-20 | Reward examples conflict with the official formula | wrong tests | organizer spec wins; single controlled CR updates examples + tests | Q-005 | A0 | OPEN |
| R-21 | Judge machine resources exceeded | disqualification | measured targets on a recorded host; stdlib only; no heavy data | §22.5 | D (QA) | OPEN |
| R-22 | Held-out data leaks into dev artifacts | invalid benchmark | no held-out artifacts in reports; separate permissions | REQ-GH-007, D-0008 | D (docs) | MITIGATED |
| R-23 | Tests pass only in the developer workspace | unverifiable claim | clean-clone + offline run in Phase 16; no absolute paths | Phase 16 | D (QA) | OPEN |
| R-24 | False claim of 100/100 or guaranteed victory | credibility loss | automated claim scan in `make verify` | `tools/check_governance.py` GOV-CLAIMS-01 | D (docs) | MITIGATED |
| P0-6 | Phase 0 documentation drifts from the actual repository | misleading context for the next agent | governance checks compare docs, configs, assumptions, questions, rubric map and Makefile | `tools/check_governance.py` | A0 | MITIGATED |

## Phase 0 assessment

No architectural blocker remains unresolved: the critical risk (unknown official contract)
has a documented safe solution (adapter/config isolation plus an explicit UNBOUND profile).
Two items cannot be closed by an AI agent and stay open by design:

* a human second signature on the contract summary (`CONTRACT_SIGNOFF.md` Reviewer 2),
* the submission deadline (`OPEN-0`), which is not published in any accessible source.
