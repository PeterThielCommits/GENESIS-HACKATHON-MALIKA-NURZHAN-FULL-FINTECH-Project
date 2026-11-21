# Determinism

**Principle:** a seed and a config fully determine every byte of an episode — across runs,
processes, machines and Python hash seeds.

**Tests:** `test_episode_is_deterministic`, `test_same_seed_same_bytes_across_processes`
(two different `PYTHONHASHSEED` values), `test_same_seed_same_reject_behaviour`,
`test_diff_is_deterministic`, sweep gate G6.

---

## 1. Derivation chain

```
master_seed (string)
   │
   ├─ sha256("episode␟seed␟config_hash␟difficulty")[:16]  → EP-{difficulty}-{HEX}
   ├─ sha256(master_seed)                                → seed_offset → operator order
   └─ RngService(master_seed).stream("<namespace>")      → every random draw
```

Config enters through `config_hash`, computed from the canonical JSON of the generator config.
Change a volume and the hash changes — which changes the episode id and every digest. That is
intended: an episode is only reproducible together with its config hash.

## 2. RNG namespaces

`gen/core/rng.py` exposes `RngService(seed).stream(namespace)`; each stream is an independent
`random.Random` seeded from `sha256(seed ␟ namespace)`.

| Namespace | Used for |
|---|---|
| `ids/records` | id issuance for the clean history |
| `history/...` | draw of counterparties, invoices, payment behaviour |
| `fx/...` | exchange-rate walk |
| `company/...` | company profile, names, timezone |
| `mutation/<operator>/<index>/<attempt>` | candidate choice, mutation parameters |

Consequences:

* A retry uses a **different** namespace, so it explores a different target instead of
  repeating the failure.
* Two operators never share a stream, so adding one does not perturb another's draws.
* `RngStream` exposes only `random`, `choice`, `choices_weighted`, `randint`, `ratio_hit`,
  `shuffled` — no global randomness is reachable from generation code.

## 3. What is *not* deterministic (and must not be)

Nothing in episode content. The only non-derived inputs are explicitly injected:

* `created_at` — passed as a parameter (tests pin `2026-11-21T00:00:00+00:00`).
* `verifier_hook` — an optional injected cross-check, used by tests.
* `episode_id` — may be overridden; otherwise derived.

`time.time()`, `datetime.now()`, `random.random()` and `uuid4()` are absent from generation
paths.

## 4. Canonical serialisation

`contracts/canonical.py`:

* keys sorted, separators `(",", ":")`, **`ensure_ascii=False`**, LF line endings only;
* floats **rejected** (`ContractError`), `Decimal` must be materialised as `str` by the caller;
* sets are rendered in sorted canonical order;
* CR characters rejected (no platform-dependent line endings);
* dataclasses are normalised structurally.

Hash of an episode's public surface:

```
public_digest = digest_of({ name: sha256(public_files[name]) for name in PUBLIC_FILE_ORDER })
```

## 5. Commit-reveal

```
salt       = sha256("salt␟config_hash␟episode_id")
commitment = sha256(salt || truth_digest)
```

The salt is sealed; only the commitment is public. The commitment therefore cannot be compared
against a guessed truth digest without the salt — and it is asserted **not equal** to the plain
truth digest (`test_commitment_is_not_the_plain_truth_digest`).

## 6. Id families

Four styles, selected by config and therefore stable per book:

| Style | Example | Note |
|---|---|---|
| A | `INV-2025-0042`, `PAY-000123` | per-table prefix + zero-padded counter |
| B | `2025/05/J/0123`, `S-0042-25`, `P0007F3A` | compact per-table prefix |
| C | `in_9f2e3a`, `pm_77aa01` | short prefix + random token |
| D | `011395951` | two namespace digits + six counter digits + Luhn check digit |

Invariants of every style:

* **no shortcut** — no seed, anomaly type, operator index or record position is encoded;
* **global uniqueness across document tables** — `source_document_id` and allocation targets
  are cross-table pointers (D-006);
* collisions inside one namespace **raise** instead of silently re-issuing.

## 7. Verification recipe

```bash
# same seed twice -> identical digests
python3 - <<'PY'
from gen.config import load_generator_config
from gen.build_episodes import build_episode
cfg = load_generator_config()
a = build_episode(master_seed="det", config=cfg, difficulty="L2", created_at="2026-11-21T00:00:00+00:00")
b = build_episode(master_seed="det", config=cfg, difficulty="L2", created_at="2026-11-21T00:00:00+00:00")
assert a.public_files == b.public_files and a.truth == b.truth
print("deterministic:", a.manifest["public_digest"])
PY

# cross-process (hash seed independence)
PYTHONHASHSEED=0  python3 -c "..." # compare output with
PYTHONHASHSEED=99 python3 -c "..."
```

Both cases are covered by tests; if you change anything in the RNG or canonical layer, those
tests are the ones that must stay green.
