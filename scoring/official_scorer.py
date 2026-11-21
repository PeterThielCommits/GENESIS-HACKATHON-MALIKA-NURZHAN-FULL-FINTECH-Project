"""Official Genesis FinTech (2026-11-20) deterministic matcher and reward scorer.

Implements every normative rule of ``spec/official_fintech_checks_2026-11-20.md``:
  - Structural validation BEFORE deduplication:
      * max 30 findings per submit;
      * max 10 ``evidence_ids`` per finding (checked before dedup — M05);
      * max 1000 Unicode code points for ``explanation`` (Test 20);
      * strict JSON integer ``claimed_amount_minor`` (no bool/str/float — M09);
      * invalid structure returns ``return=-1.0`` and ``None`` for all other metrics.
  - Exact matching without prefix regexes or string coercion (supports arbitrary
    bijective ID remaps in paired checks P06..P20):
      * exact case/whitespace ID, type, and currency equality (M06);
      * exact ``affected_ids`` set equality after dedup (M01, M02);
      * ``evidence_ids`` must cover >= 1 valid evidence set AND every listed
        ``evidence_id`` must exist in accessible public IDs (M03, M04);
      * ``abs(claimed_amount_minor - expected_amount_minor) <= tolerance_minor``
        with default ``tolerance_minor = 0`` (M07, M08).
  - Maximum-cardinality bipartite matching (duplicates kept as separate left
    vertices — M12) with deterministic tie-breaking:
      * sort truth ``issue_id`` by Unicode code points;
      * select lexicographically smallest sorted sequence of
        ``(issue_id, finding_index)`` pairs (M10, M11).
  - Exact rational reward formula (Block 3 tests 1..20):
      * empty truth + empty findings -> ``P=0, R=0, F1=1``;
      * ``return = clip([-1, 1], 2 * F1 - 1 - 0.2 * inspection_steps / 100)``.

Stdlib-only; obeys ``scoring/`` import boundaries (never imports ``gen/``,
``verifier/``, ``env/``, or ``harness/``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Collection, Mapping, Sequence

OFFICIAL_MAX_FINDINGS = 30
OFFICIAL_MAX_EVIDENCE_IDS = 10
OFFICIAL_MAX_EXPLANATION_CODEPOINTS = 1000
OFFICIAL_STEP_BUDGET = 100
OFFICIAL_STEP_PENALTY_WEIGHT = Fraction(2, 10)  # 0.2


@dataclass(frozen=True)
class OfficialFinding:
    """Validated submitted finding normalized for matching (post-limit check)."""

    index: int
    type: str
    affected_ids: frozenset[str]
    claimed_amount_minor: int
    currency: str
    evidence_ids: frozenset[str]
    explanation: str


@dataclass(frozen=True)
class OfficialTruth:
    """Canonical ground-truth anomaly for official matching."""

    issue_id: str
    type: str
    affected_ids: frozenset[str]
    expected_amount_minor: int
    currency: str
    evidence_sets: tuple[frozenset[str], ...]
    tolerance_minor: int = 0


@dataclass(frozen=True)
class OfficialScoreResult:
    """Complete official scorer result with both exact Fractions and float API dict."""

    valid: bool
    tp: int | None
    fp: int | None
    fn: int | None
    precision: Fraction | None
    recall: Fraction | None
    f1: Fraction | None
    return_exact: Fraction
    pairs: tuple[tuple[str, int], ...] = ()
    error: str | None = None

    def to_score_dict(self) -> dict[str, Any]:
        """Return the exact dict schema required by ``judge_adapter.score_episode``."""
        if not self.valid:
            return {
                "tp": None,
                "fp": None,
                "fn": None,
                "precision": None,
                "recall": None,
                "f1": None,
                "return": -1.0,
            }
        assert self.precision is not None
        assert self.recall is not None
        assert self.f1 is not None
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": float(self.precision),
            "recall": float(self.recall),
            "f1": float(self.f1),
            "return": float(self.return_exact),
        }


def _invalid_result(reason: str) -> OfficialScoreResult:
    return OfficialScoreResult(
        valid=False,
        tp=None,
        fp=None,
        fn=None,
        precision=None,
        recall=None,
        f1=None,
        return_exact=Fraction(-1),
        pairs=(),
        error=reason,
    )


def validate_official_findings_payload(
    payload: Any,
) -> tuple[list[OfficialFinding] | None, str | None]:
    """Validate raw ``findings`` payload BEFORE deduplication.

    Accepts either ``{"findings": [...]}`` (canonical §05 object) or a raw list
    ``[...]``. Returns ``(parsed_findings, None)`` on success or
    ``(None, error_message)`` on any structural violation.
    """
    if isinstance(payload, Mapping):
        if "findings" not in payload:
            return None, "submit payload object must contain 'findings' list"
        raw_list = payload["findings"]
    elif isinstance(payload, list):
        raw_list = payload
    else:
        return None, f"findings payload must be a JSON object or list, got {type(payload).__name__}"

    if not isinstance(raw_list, list):
        return None, f"'findings' must be a list, got {type(raw_list).__name__}"

    if len(raw_list) > OFFICIAL_MAX_FINDINGS:
        return (
            None,
            f"findings count {len(raw_list)} exceeds structural limit {OFFICIAL_MAX_FINDINGS}",
        )

    parsed: list[OfficialFinding] = []
    for idx, item in enumerate(raw_list):
        if not isinstance(item, Mapping):
            return None, f"findings[{idx}] must be a JSON object"

        ftype = item.get("type")
        if not isinstance(ftype, str) or not ftype:
            return None, f"findings[{idx}].type must be a non-empty string"

        # affected_ids
        raw_aff = item.get("affected_ids")
        if not isinstance(raw_aff, list) or len(raw_aff) < 1:
            return None, f"findings[{idx}].affected_ids must be a non-empty list of strings"
        for k, aid in enumerate(raw_aff):
            if not isinstance(aid, str) or not aid:
                return None, f"findings[{idx}].affected_ids[{k}] must be a non-empty string"

        # evidence_ids — limit 10 checked BEFORE deduplication (M05)
        raw_ev = item.get("evidence_ids")
        if not isinstance(raw_ev, list) or len(raw_ev) < 1:
            return None, f"findings[{idx}].evidence_ids must be a non-empty list of strings"
        if len(raw_ev) > OFFICIAL_MAX_EVIDENCE_IDS:
            return (
                None,
                f"findings[{idx}].evidence_ids length {len(raw_ev)} exceeds limit {OFFICIAL_MAX_EVIDENCE_IDS}",
            )
        for k, eid in enumerate(raw_ev):
            if not isinstance(eid, str) or not eid:
                return None, f"findings[{idx}].evidence_ids[{k}] must be a non-empty string"

        # claimed_amount_minor (or claimed_amount alias) — strict int, not bool/str/float (M09)
        has_minor = "claimed_amount_minor" in item
        has_plain = "claimed_amount" in item
        if not has_minor and not has_plain:
            return None, f"findings[{idx}] missing required 'claimed_amount_minor'"
        if has_minor:
            amount = item["claimed_amount_minor"]
            if has_plain and item["claimed_amount"] != amount:
                return None, f"findings[{idx}] conflicting claimed_amount_minor and claimed_amount"
        else:
            amount = item["claimed_amount"]
        if type(amount) is not int or isinstance(amount, bool):
            return (
                None,
                f"findings[{idx}].claimed_amount_minor must be an integer, got {type(amount).__name__}",
            )

        # currency
        currency = item.get("currency")
        if not isinstance(currency, str) or not currency:
            return None, f"findings[{idx}].currency must be a non-empty string"

        # explanation — length measured in Unicode code points (Python len(str))
        explanation = item.get("explanation", "")
        if explanation is None:
            explanation = ""
        if not isinstance(explanation, str):
            return None, f"findings[{idx}].explanation must be a string"
        if len(explanation) > OFFICIAL_MAX_EXPLANATION_CODEPOINTS:
            return (
                None,
                f"findings[{idx}].explanation length {len(explanation)} exceeds "
                f"{OFFICIAL_MAX_EXPLANATION_CODEPOINTS} Unicode code points",
            )

        parsed.append(
            OfficialFinding(
                index=idx,
                type=ftype,
                affected_ids=frozenset(raw_aff),
                claimed_amount_minor=amount,
                currency=currency,
                evidence_ids=frozenset(raw_ev),
                explanation=explanation,
            )
        )

    return parsed, None


def parse_official_truths(
    raw_truths: Sequence[Mapping[str, Any]],
    *,
    default_tolerance_minor: int = 0,
) -> list[OfficialTruth]:
    """Parse sealed truth records (either TwinLedger ``truth_id`` or official ``issue_id``)."""
    out: list[OfficialTruth] = []
    for idx, row in enumerate(raw_truths):
        issue_id = str(row.get("issue_id") or row.get("truth_id") or f"T-{idx:04d}")
        ftype = str(row["type"])
        affected = frozenset(str(x) for x in row["affected_ids"])
        if "expected_amount_minor" in row:
            amt = row["expected_amount_minor"]
        else:
            amt = row["amount_minor"]
        if type(amt) is not int or isinstance(amt, bool):
            raise ValueError(f"truth[{idx}] expected integer amount_minor, got {amt!r}")
        currency = str(row["currency"])
        tol = int(row.get("tolerance_minor", default_tolerance_minor))
        if tol < 0:
            raise ValueError(f"truth[{idx}] tolerance_minor must be >= 0")

        raw_sets = row.get("evidence_sets")
        if raw_sets is None and "evidence_ids" in row:
            raw_sets = [row["evidence_ids"]]
        if not raw_sets:
            raise ValueError(f"truth[{idx}] missing evidence_sets")
        ev_sets = tuple(frozenset(str(x) for x in s) for s in raw_sets)

        out.append(
            OfficialTruth(
                issue_id=issue_id,
                type=ftype,
                affected_ids=affected,
                expected_amount_minor=amt,
                currency=currency,
                evidence_sets=ev_sets,
                tolerance_minor=tol,
            )
        )
    return out


def _edge_allowed(
    finding: OfficialFinding,
    truth: OfficialTruth,
    accessible_ids: Collection[str] | None,
) -> bool:
    """Evaluate all exact match conditions (M01..M09)."""
    if finding.type != truth.type:
        return False
    if finding.affected_ids != truth.affected_ids:
        return False
    if finding.currency != truth.currency:
        return False
    if abs(finding.claimed_amount_minor - truth.expected_amount_minor) > truth.tolerance_minor:
        return False
    # M04: every submitted evidence_id must exist / be accessible in the episode
    if accessible_ids is not None:
        for eid in finding.evidence_ids:
            if eid not in accessible_ids:
                return False
    # M03: must include at least one complete valid evidence set
    return any(req_set.issubset(finding.evidence_ids) for req_set in truth.evidence_sets)


def _max_bipartite_cardinality(
    adj: Sequence[Sequence[int]],
    active_right: Sequence[int],
    used_left: set[int],
) -> int:
    """Exact maximum matching cardinality on the induced subgraph using Kuhn's algorithm."""
    match_left: dict[int, int] = {}

    def dfs(r_idx: int, visited: set[int]) -> bool:
        for l_idx in adj[r_idx]:
            if l_idx in used_left or l_idx in visited:
                continue
            visited.add(l_idx)
            if l_idx not in match_left or dfs(match_left[l_idx], visited):
                match_left[l_idx] = r_idx
                return True
        return False

    total = 0
    for r_idx in active_right:
        if dfs(r_idx, set()):
            total += 1
    return total


def match_official_findings(
    findings: Sequence[OfficialFinding],
    truths: Sequence[OfficialTruth],
    *,
    accessible_ids: Collection[str] | None = None,
) -> tuple[tuple[str, int], ...]:
    """Maximum-cardinality bipartite matching with exact official tie-break.

    Truths are ordered by ``issue_id`` (Unicode code points). Among all
    maximum-cardinality matchings, returns the lexicographically smallest
    sorted sequence of ``(issue_id, finding_index)`` pairs (M10, M11, M12).
    """
    if not findings or not truths:
        return ()

    sorted_truths = sorted(truths, key=lambda t: t.issue_id)
    n_truths = len(sorted_truths)

    # adj[t_pos] = sorted list of finding indices (0..n_findings-1) that match sorted_truths[t_pos]
    adj: list[list[int]] = []
    for truth in sorted_truths:
        edges = [
            f.index
            for f in findings
            if _edge_allowed(f, truth, accessible_ids)
        ]
        edges.sort()
        adj.append(edges)

    all_right = list(range(n_truths))
    max_card = _max_bipartite_cardinality(adj, all_right, set())
    if max_card == 0:
        return ()

    chosen: list[tuple[str, int]] = []
    used_left: set[int] = set()
    need = max_card

    for t_pos in range(n_truths):
        if need == 0:
            break
        suffix = list(range(t_pos + 1, n_truths))
        for f_idx in adj[t_pos]:
            if f_idx in used_left:
                continue
            if need == 1:
                feasible = True
            else:
                rem = _max_bipartite_cardinality(adj, suffix, used_left | {f_idx})
                feasible = rem >= need - 1
            if feasible:
                chosen.append((sorted_truths[t_pos].issue_id, f_idx))
                used_left.add(f_idx)
                need -= 1
                break

    return tuple(chosen)


def compute_official_metrics(
    tp: int,
    fp: int,
    fn: int,
    inspection_steps: int,
    *,
    step_budget: int = OFFICIAL_STEP_BUDGET,
) -> tuple[Fraction, Fraction, Fraction, Fraction]:
    """Compute exact ``(precision, recall, f1, clipped_return)`` as ``Fraction``."""
    if tp == 0 and fp == 0 and fn == 0:
        # Block 3 Test 3: clean book + empty submission -> P=0, R=0, F1=1
        precision = Fraction(0)
        recall = Fraction(0)
        f1 = Fraction(1)
    else:
        precision = Fraction(tp, tp + fp) if (tp + fp) > 0 else Fraction(0)
        recall = Fraction(tp, tp + fn) if (tp + fn) > 0 else Fraction(0)
        denom = 2 * tp + fp + fn
        f1 = Fraction(2 * tp, denom) if denom > 0 else Fraction(0)

    steps = max(0, int(inspection_steps))
    raw_return = (
        Fraction(2) * f1
        - Fraction(1)
        - OFFICIAL_STEP_PENALTY_WEIGHT * Fraction(steps, step_budget)
    )
    clipped = max(Fraction(-1), min(Fraction(1), raw_return))
    return precision, recall, f1, clipped


def score_official_findings(
    findings_payload: Any,
    truths: Sequence[OfficialTruth],
    inspection_steps: int,
    *,
    accessible_ids: Collection[str] | None = None,
) -> OfficialScoreResult:
    """Validate, match, and score a submission against ground truth."""
    if type(inspection_steps) is not int or isinstance(inspection_steps, bool) or inspection_steps < 0:
        return _invalid_result(f"invalid inspection_steps: {inspection_steps!r}")

    parsed, err = validate_official_findings_payload(findings_payload)
    if err is not None or parsed is None:
        return _invalid_result(err or "invalid findings payload")

    pairs = match_official_findings(parsed, truths, accessible_ids=accessible_ids)
    tp = len(pairs)
    fp = len(parsed) - tp
    fn = len(truths) - tp
    precision, recall, f1, clipped_return = compute_official_metrics(
        tp, fp, fn, inspection_steps
    )
    return OfficialScoreResult(
        valid=True,
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        return_exact=clipped_return,
        pairs=pairs,
        error=None,
    )


def collect_accessible_ids_from_episode_dir(episode_dir: Path | str) -> set[str]:
    """Collect every public record/document ID reachable through public tools.

    Supports both TwinLedger ``public/`` layout and flat judge fixture layout,
    preserving arbitrary bijective-remapped IDs (P06..P20) and FX semantic keys.
    """
    root = Path(episode_dir)
    pub = root / "public" if (root / "public").is_dir() else root

    accessible: set[str] = {
        "company",
        "policy",
        "accounts",
        "opening_balances",
        "period_calendar",
    }

    def _read_rows(names: Sequence[str]) -> list[dict[str, Any]]:
        for name in names:
            p = pub / name
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8")
            if p.suffix == ".jsonl":
                rows: list[dict[str, Any]] = []
                for ln in text.splitlines():
                    ln = ln.strip()
                    if ln:
                        obj = json.loads(ln)
                        if isinstance(obj, dict):
                            rows.append(obj)
                return rows
            obj = json.loads(text)
            if isinstance(obj, list):
                return [x for x in obj if isinstance(x, dict)]
        return []

    table_files: list[tuple[tuple[str, ...], tuple[str, ...], str]] = [
        (("journal_entries.jsonl", "ledger.jsonl", "ledger.json", "journal_entries.json"), ("je_id", "row_id", "id"), "JE"),
        (("invoices.jsonl", "invoices.json"), ("doc_id", "invoice_id", "id"), "INV"),
        (("payments.jsonl", "payments.json"), ("pay_id", "payment_id", "id"), "PAY"),
        (("fx_rates.jsonl", "fx.jsonl", "fx.json", "fx_rates.json"), ("fx_id", "id"), "FX"),
        (("credit_notes.jsonl", "credit_notes.json"), ("credit_note_id", "doc_id", "id"), "CN"),
        (("bank_lines.jsonl", "bank_lines.json"), ("bank_line_id", "id"), "BANK"),
        (("counterparties.jsonl", "counterparties.json"), ("counterparty_id", "entity_id", "id"), "CP"),
        (("accounts.json", "accounts.jsonl"), ("account_id", "id"), ""),
        (("period_calendar.json", "period_calendar.jsonl"), ("period_id", "id"), ""),
    ]

    for fnames, pk_candidates, prefix in table_files:
        for row in _read_rows(fnames):
            raw_id = None
            for pk in pk_candidates:
                val = row.get(pk)
                if isinstance(val, str) and val:
                    raw_id = val
                    break
            if raw_id is not None:
                accessible.add(raw_id)
                if prefix and ":" not in raw_id:
                    accessible.add(f"{prefix}:{raw_id}")
            # Semantic FX key: effective_date:src:dst
            if prefix == "FX":
                eff = row.get("effective_date") or row.get("date")
                pair = row.get("pair")
                if isinstance(eff, str) and isinstance(pair, str) and "/" in pair:
                    src, dst = pair.split("/", 1)
                    sem = f"{eff}:{src}:{dst}"
                    accessible.add(sem)
                    accessible.add(f"FX:{sem}")

    # Optional documents/ directory if present in judge fixtures
    docs_dir = pub / "documents"
    if docs_dir.is_dir():
        for entry in docs_dir.iterdir():
            if entry.is_file() and not entry.name.startswith("."):
                accessible.add(entry.stem)
                accessible.add(entry.name)

    return accessible


def load_truths_from_episode_dir(episode_dir: Path | str) -> list[OfficialTruth]:
    """Load sealed truth findings from an episode directory (judge-side only)."""
    root = Path(episode_dir)
    candidates = [
        root / "sealed" / "truth.json",
        root / "truth.json",
    ]
    for path in candidates:
        if path.is_file():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                raw_list = raw.get("findings", raw.get("issues", raw.get("truth", [])))
            elif isinstance(raw, list):
                raw_list = raw
            else:
                raise ValueError(f"unsupported truth.json structure in {path}")
            return parse_official_truths(raw_list)
    raise FileNotFoundError(f"truth.json not found in {root}")


__all__ = [
    "OFFICIAL_MAX_EVIDENCE_IDS",
    "OFFICIAL_MAX_EXPLANATION_CODEPOINTS",
    "OFFICIAL_MAX_FINDINGS",
    "OFFICIAL_STEP_BUDGET",
    "OFFICIAL_STEP_PENALTY_WEIGHT",
    "OfficialFinding",
    "OfficialScoreResult",
    "OfficialTruth",
    "collect_accessible_ids_from_episode_dir",
    "compute_official_metrics",
    "load_truths_from_episode_dir",
    "match_official_findings",
    "parse_official_truths",
    "score_official_findings",
    "validate_official_findings_payload",
]
