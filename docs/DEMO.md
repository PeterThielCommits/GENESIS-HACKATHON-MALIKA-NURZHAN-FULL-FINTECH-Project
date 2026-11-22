# Demo Guide — 3-Minute Jury Demo + Technical Backup Demo (Task 15.4)

Two separate artefacts, for two different audiences:

| | Primary demo | Technical backup demo |
|---|---|---|
| Command | `python3 tools/demo_walkthrough.py` | `make demo-backup` |
| Audience | judges, product reviewers | engineers, QA, sceptical reviewers |
| Runtime | ~10 s (scripted 3-minute narration) | ~2–4 min |
| Proves | the product story end-to-end | reproducibility, isolation and evidence integrity |
| Network | none | none |

Both are deterministic and offline. Neither requires `pip install`.

---

## 1. Primary demo — `tools/demo_walkthrough.py` (3 minutes)

`master_seed=2025`, six segments, printed with a `[mm:ss–mm:ss]` timing guide you
can read aloud while the terminal scrolls.

This table is not free text: `tools/demo_walkthrough.py::SEGMENTS` is the single
source for both the printed headers and the rows below, and
`tools/verify_doc_claims.py::C-DEMO` fails the build if they disagree.

| Segment | Time | What the audience sees |
|---|---|---|
| 1. Architecture & Contract Overview | 0:00–0:25 | the layering, the frozen contracts, and the AST-enforced zone boundaries |
| 2. Counterfactual Twins (Clean Distractor Twin vs Mutated Twin) | 0:25–0:55 | a synthetic company built deterministically from the seed; the clean book is *correct by construction*, then exactly one accounting lie is injected; the diff shows *what changed*, the invariants show *why it is wrong* |
| 3. Independent Public-Only Verifier & ProofGraph | 0:55–1:25 | a Stage-1 verifier that never imports the generator finds the finding and emits a minimal public ProofGraph certificate |
| 4. CLOSED_EVAL 3-Process Isolation, Commit-Reveal & Fresh Replay | 1:25–1:55 | 3-process isolation, commit-reveal, Merkle receipt and a fresh-process replay matching byte-for-byte |
| 5. Reward Stress Test (Official Formula, Internal Step Penalty) | 1:55–2:30 | honest policy vs `flag_all` / `duplicate_spam` / `silent` — the official formula resists each shortcut |
| 6. Honest Limitations & Scope | 2:30–3:00 | what is *not* claimed (internal verification is not a jury score, Linux-only kernel sandbox, bounded side-channel checks) |

```bash
python3 tools/demo_walkthrough.py
```

Expected final lines:

```text
[2:30–3:00] 6. Honest Limitations & Scope
  - Internal verification pass rate is NOT an official organiser jury score.
  ...
```

Segment 4 prints `Security profile: linux-kernel-ns-seccomp-v1 (full_os_sandbox=True)`
on a capable Linux host and honestly degrades to
`posix-subprocess-isolated-v1 (is_full_os_sandbox=False)` elsewhere — with the
unavailable controls listed. **If you see `full_os_sandbox=False`, say so**; the
claim is conditional by design (`docs/LIMITATIONS.md` L2).

If live generation fails on a locked-down machine, fall back to the checked-in
fixtures — no claim in the demo depends on the fallback path.

---

## 2. Technical backup demo — `make demo-backup`

Answers the four questions a technical reviewer actually asks, in order, with
greppable evidence at each step.

```bash
make demo-backup     # ~2–4 min, no network, exits non-zero on any failure
```

| Step | Reviewer question | Command executed | Evidence produced |
|---|---|---|---|
| B1 | "Is the whole suite green, right now?" | `make verify` | `artifacts/reports/latest/verify_summary.json` (12/12 PASS) |
| B2 | "Are the claims in the docs real?" | `python3 tools/verify_doc_claims.py` | `artifacts/reports/doc_claims/doc_claims_report.json` (22 measured facts) |
| B3 | "Is evaluation actually re-derivable?" | `python3 -m harness.replay --verify-suite` | `artifacts/reports/latest/replay_report.json` (5/5 byte-identical) |
| B4 | "Is the frozen contract surface unchanged?" | `python3 tools/freeze_release.py --verify` | 30 files, aggregate `0747baf0…` |

### Deeper manual probes (copy/paste, no scripts)

```bash
# (a) Prove the environment cannot leak truth: 10 channels, 9 encodings, 0 hits
python3 judge/canary_fuzzer.py && python3 -c \
  "import json;print(json.load(open('artifacts/reports/latest/canary_fuzz_report.json'))['canary_summary'])"

# (b) Prove the tool vocabulary is what the contract says
python3 -c "import json;s=json.load(open('contracts/tool_request.schema.json'));\
print(s['properties']['action']['properties']['tool']['enum'])"

# (c) Prove a policy sees zero truth fields in CLOSED_EVAL
python3 -c "import judge_adapter;e=judge_adapter.make_env();\
o,i=e.reset(seed=2026,config={'mode':'closed','episode_dir':'episodes/dev/ep_dev_001_clean_distractors','team_config':{}});\
print(sorted(o.keys()), 'reward=', e.step({'name':'calculator','args':{'expression':'1+1'}})[1])"

# (d) Prove the report is offline
make report && grep -c "http" artifacts/reports/latest/report.html   # expect 0

# (e) Prove the reward resists shortcut policies on a freshly built twin
#     (checked-in episodes/dev/* carry no sealed/truth.json by design — D-01-04 —
#     so scoring needs an episode built in a temp dir, exactly as the demo does)
python3 - <<'PY'
import tempfile
from pathlib import Path
from gen.pipeline import default_dataset_recipes
from scoring.reward import compute_reward
from tools.make_dataset import build_and_verify_split

with tempfile.TemporaryDirectory() as td:
    build_and_verify_split("dev", Path(td) / "eps", recipes=default_dataset_recipes("dev", master_seed=2025)[:2])
    ep = Path(td) / "eps" / "ep_dev_002_duplicate"
    print("built:", ep.name, "| sealed truth present:", (ep / "sealed" / "truth.json").is_file())
PY
```

### What to do if something fails during the demo

| Symptom | Honest response |
|---|---|
| `make verify` fails on a gate | Do **not** narrate around it. Read `verify_summary.json` → `checks[].reason`, report the exit code (0–5) and the failing gate. The exit-code contract is in `docs/PHASE_REPORTS/PHASE-14.md` §3.2. |
| `full_os_sandbox=False` | Expected on macOS/Windows/restricted kernels; see L2. |
| `hypothesis` extra missing | 1 test skips as *optional*; recorded in `verify_summary.json → optional_checks`, never hidden. |
| `make official-eval` slow | It is 4 policies × 20 episodes; `artifacts/trajectories/trajectories.jsonl` is already checked in. |
| Docker unavailable | `make docker-check` is optional for the demo; the offline guarantee is separately proven in (d). |

---

## 3. Evidence-to-claim map

Every statement made in either demo resolves to one of these files:

| Claim | File |
|---|---|
| 12/12 gates PASS, exit code 0 | `artifacts/reports/latest/verify_summary.json` |
| 601 tests, 55 official mirror tests | `unittest` discovery over `tests/` and `tests/official/` (`python3 tools/verify_doc_claims.py --list`); `verify_summary.json` also records the counts that *one* run observed |
| 5/5 byte-identical replays | `artifacts/reports/latest/replay_report.json` |
| 26/26 mutants killed | `artifacts/reports/latest/mutation_test_report.json` |
| 7/7 metamorphic transforms | `artifacts/reports/latest/metamorphic_report.json` |
| 0 canary hits (10 channels, 9 encodings) | `artifacts/reports/latest/canary_fuzz_report.json` |
| AUC 0.5389 ≤ 0.55 | `artifacts/reports/latest/shortcut_audit.json` |
| p99 / RSS / disk **budgets** and verdict | `artifacts/reports/latest/performance_report.json` |
| stdlib-only core | `artifacts/reports/latest/dependency_report.json` |
| Baseline F1 / return / steps | `artifacts/trajectories/trajectories.jsonl` |
| Docs match the above | `artifacts/reports/doc_claims/doc_claims_report.json` |
| Offline HTML | `artifacts/reports/latest/report.html` (0 `http`) |

`python3 tools/verify_doc_claims.py` re-checks this whole table automatically: if a
number here and a number in the artifacts disagree, the demo-backup step fails.
