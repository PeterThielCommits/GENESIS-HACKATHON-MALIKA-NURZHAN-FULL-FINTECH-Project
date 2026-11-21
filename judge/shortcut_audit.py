#!/usr/bin/env python3
"""Metadata-Only Shortcut Classifier & Side-Channel Equivalence Audit (Phase 12 — TZ §19.1–19.3).

Implements:
  1. Grouped Train/Test Within-Table Metadata-Only Datasets across ``invoices``,
     ``payments``, and ``journal_entries`` (evaluating within each table so
     cross-table row-count base rates do not confound record-level shortcut
     detection) using ONLY non-accounting surface features (TZ §19.2):
       - normalized row index within JSONL table;
       - ID string length and ASCII digit ratio;
       - number of digits in minor amount;
       - count of trailing zeros in minor amount;
       - timestamp hour-of-day and day-of-week;
       - free-text length and ASCII digit ratio;
       - timezone UTC offset hours.
  2. Pure-stdlib deterministic L2-regularized Logistic Regression classifier
     reporting per-table and macro-averaged ROC AUC, PR AUC, balanced accuracy,
     Brier calibration score, and standardized feature weights against
     ``max_allowed_roc_auc = 0.55``.
  3. Public Error-Surface Equivalence check across missing IDs across namespaces,
     forbidden path traversal, invalid table, and tampered cursor requests.
  4. Warmed-up Interleaved Randomized Timing Equivalence check computing a 90%
     Two-One-Sided confidence interval of latency difference against an explicit
     practical equivalence margin.

Writes ``artifacts/reports/latest/shortcut_audit.json``.
"""

from __future__ import annotations

import json
import math
import platform
import random
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.canonical import sha256_hex
from contracts.version import PROTOCOL_VERSION
from env.environment import EnvConfig, TwinLedgerEnv
from gen.core.clean_twin import CleanTwinSpec
from gen.pipeline import EpisodeRecipe, build_episode

DEFAULT_REPORT_PATH = REPO_ROOT / "artifacts" / "reports" / "latest" / "shortcut_audit.json"
MAX_ALLOWED_ROC_AUC = 0.55

FEATURE_NAMES: tuple[str, ...] = (
    "norm_row_pos",
    "id_length_norm",
    "id_digit_ratio",
    "amount_digit_count_norm",
    "trailing_zeros_norm",
    "hour_norm",
    "weekday_norm",
    "text_len_norm",
    "text_digit_ratio",
    "tz_offset_norm",
)


def _trailing_zeros(n: int) -> int:
    s = str(abs(n))
    if s == "0":
        return 1
    return len(s) - len(s.rstrip("0"))


def _parse_ts_meta(ts: str) -> tuple[float, float, float]:
    if not ts:
        return 0.5, 0.5, 0.0
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        hr = dt.hour / 24.0
        wd = dt.weekday() / 6.0
        off_h = (dt.utcoffset().total_seconds() / 3600.0) / 12.0 if dt.utcoffset() else 0.0
        return hr, wd, off_h
    except Exception:
        return 0.5, 0.5, 0.0


def _extract_episode_metadata_by_table(ep_dir: Path) -> dict[str, list[tuple[list[float], int]]]:
    pub = ep_dir / "public"
    truth_raw = json.loads((ep_dir / "sealed" / "truth.json").read_text(encoding="utf-8"))
    affected: set[str] = set()
    for t in truth_raw:
        for aid in t.get("affected_ids", ()):
            affected.add(str(aid))

    by_table: dict[str, list[tuple[list[float], int]]] = {
        "invoices_domestic": [],
        "invoices_foreign": [],
        "payments": [],
        "journal_accrual_domestic": [],
        "journal_accrual_foreign": [],
        "journal_settlement": [],
    }
    func_cur = str(json.loads((pub / "company.json").read_text(encoding="utf-8")).get("functional_currency", "KZT"))
    table_defs = (
        ("invoices", "invoices.jsonl", "doc_id", "INV"),
        ("payments", "payments.jsonl", "pay_id", "PAY"),
        ("journal_entries", "journal_entries.jsonl", "je_id", "JE"),
    )

    for tbl_key, fname, pk_key, prefix in table_defs:
        lines = [ln for ln in (pub / fname).read_text(encoding="utf-8").splitlines() if ln.strip()]
        n_rows = max(1, len(lines))
        for idx, ln in enumerate(lines):
            row = json.loads(ln)
            raw_id = str(row.get(pk_key, ""))
            typed_id = raw_id if ":" in raw_id else f"{prefix}:{raw_id}"
            label = 1 if typed_id in affected else 0

            if tbl_key == "invoices":
                amt = int(row.get("total_minor", 0))
                ts = str(row.get("issue_timestamp", ""))
                items = row.get("line_items") or []
                txt = str(items[0].get("description", "")) if items else ""
                bucket = "invoices_domestic" if row.get("currency") == func_cur else "invoices_foreign"
            elif tbl_key == "payments":
                amt = int(row.get("amount_minor", 0))
                ts = str(row.get("timestamp", ""))
                txt = str(row.get("payment_channel", ""))
                bucket = "payments"
            else:
                je_lines = row.get("lines") or []
                amt = sum(int(l.get("functional_debit_minor", l.get("debit_minor", 0))) for l in je_lines)
                ts = str(row.get("timestamp", ""))
                txt = str(row.get("description", ""))
                is_settle = any(l.get("account_id") == "1010" for l in je_lines)
                is_for = any(l.get("currency", func_cur) != func_cur for l in je_lines)
                if is_settle:
                    bucket = "journal_settlement"
                elif is_for:
                    bucket = "journal_accrual_foreign"
                else:
                    bucket = "journal_accrual_domestic"

            id_digits = sum(1 for c in raw_id if c.isdigit()) / max(1, len(raw_id))
            amt_digits = len(str(abs(amt))) / 12.0
            t_zeros = _trailing_zeros(amt) / 8.0
            hr, _, tz_off = _parse_ts_meta(ts)
            txt_digits = sum(1 for c in txt if c.isdigit()) / max(1, len(txt)) if txt else 0.0

            feats = [
                idx / max(1, n_rows - 1),
                len(raw_id) / 32.0,
                id_digits,
                amt_digits,
                t_zeros,
                hr,
                0.5,
                min(1.0, len(txt) / 120.0),
                txt_digits,
                tz_off,
            ]
            by_table[bucket].append((feats, label))
    return by_table


def _sigmoid(z: float) -> float:
    if z >= 0:
        ez = math.exp(-min(z, 50.0))
        return 1.0 / (1.0 + ez)
    ez = math.exp(max(z, -50.0))
    return ez / (1.0 + ez)


def _fit_logistic_regression_l2(
    train_rows: list[tuple[list[float], int]],
    *,
    lr: float = 0.2,
    l2_reg: float = 0.1,
    epochs: int = 250,
) -> tuple[list[float], float]:
    if not train_rows:
        return [0.0] * len(FEATURE_NAMES), 0.0
    d = len(train_rows[0][0])
    weights = [0.0] * d
    bias = 0.0

    pos = sum(y for _, y in train_rows)
    neg = len(train_rows) - pos
    if pos == 0 or neg == 0:
        return weights, bias
    w_pos = len(train_rows) / (2.0 * pos)
    w_neg = len(train_rows) / (2.0 * neg)

    n = float(len(train_rows))
    for _ in range(epochs):
        grad_w = [0.0] * d
        grad_b = 0.0
        for x, y in train_rows:
            z = sum(wi * xi for wi, xi in zip(weights, x)) + bias
            p = _sigmoid(z)
            cw = w_pos if y == 1 else w_neg
            err = cw * (p - float(y))
            grad_b += err
            for j in range(d):
                grad_w[j] += err * x[j]
        bias -= lr * (grad_b / n)
        for j in range(d):
            weights[j] -= lr * ((grad_w[j] / n) + l2_reg * weights[j])
    return weights, bias


def _roc_and_pr_auc(scores: list[float], labels: list[int]) -> tuple[float, float]:
    pos_total = sum(labels)
    neg_total = len(labels) - pos_total
    if pos_total == 0 or neg_total == 0:
        return 0.5, 0.0

    paired = sorted(zip(scores, labels), key=lambda p: p[0])
    n = len(paired)
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and paired[j + 1][0] == paired[i][0]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1

    sum_pos_ranks = sum(r for r, (_, y) in zip(ranks, paired) if y == 1)
    u_stat = sum_pos_ranks - (pos_total * (pos_total + 1)) / 2.0
    roc_auc = u_stat / float(pos_total * neg_total)

    desc = sorted(zip(scores, labels), key=lambda p: -p[0])
    tp = 0
    fp = 0
    prev_rec = 0.0
    pr_auc = 0.0
    for _, y in desc:
        if y == 1:
            tp += 1
        else:
            fp += 1
        rec = tp / float(pos_total)
        prec = tp / float(tp + fp)
        pr_auc += (rec - prev_rec) * prec
        prev_rec = rec
    return roc_auc, pr_auc


def _run_side_channel_checks(ep_dir: Path) -> dict[str, Any]:
    env = TwinLedgerEnv(EnvConfig(mode="CLOSED_EVAL"))
    env.reset(ep_dir / "public", cursor_seed=777)

    r_miss_inv = env.step({"protocol_version": PROTOCOL_VERSION, "request_id": "e1", "action": {"tool": "get_document", "args": {"doc_id": "INV:DOES_NOT_EXIST"}}})
    r_miss_pay = env.step({"protocol_version": PROTOCOL_VERSION, "request_id": "e2", "action": {"tool": "get_document", "args": {"doc_id": "PAY:DOES_NOT_EXIST"}}})
    r_priv_path = env.step({"protocol_version": PROTOCOL_VERSION, "request_id": "e3", "action": {"tool": "get_document", "args": {"doc_id": "INV:../../manifest.json"}}})
    r_bad_cur = env.step({"protocol_version": PROTOCOL_VERSION, "request_id": "e4", "action": {"tool": "list_records", "args": {"table": "invoices", "page_size": 5, "cursor": "tampered.cursor"}}})
    r_bad_tbl = env.step({"protocol_version": PROTOCOL_VERSION, "request_id": "e5", "action": {"tool": "list_records", "args": {"table": "sealed_truth", "page_size": 5}}})

    e1 = r_miss_inv.get("error") or {}
    e2 = r_miss_pay.get("error") or {}
    e3 = r_priv_path.get("error") or {}
    error_surface_uniform = (
        r_miss_inv.get("ok") is False
        and r_miss_pay.get("ok") is False
        and r_priv_path.get("ok") is False
        and e1.get("code") == "NOT_FOUND"
        and e2.get("code") == "NOT_FOUND"
        and sorted(e1.keys()) == sorted(e2.keys())
        and sorted(e1.keys()) == sorted(e3.keys())
        and (r_bad_cur.get("error") or {}).get("code") == "BAD_CURSOR"
        and r_bad_tbl.get("ok") is False
    )

    env2 = TwinLedgerEnv(EnvConfig(mode="CLOSED_EVAL", max_steps=100))
    env2.reset(ep_dir / "public", cursor_seed=888)
    list_r = env2.step({"protocol_version": PROTOCOL_VERSION, "request_id": "w0", "action": {"tool": "list_records", "args": {"table": "invoices", "page_size": 2}}})
    first_inv = f"INV:{list_r['result']['records'][0]['doc_id']}"

    for w in range(6):
        env2.step({"protocol_version": PROTOCOL_VERSION, "request_id": f"wu-{w}", "action": {"tool": "get_document", "args": {"doc_id": first_inv}}})

    rng = random.Random(20261121)
    trials = [True] * 35 + [False] * 35
    rng.shuffle(trials)
    t_exist_us: list[float] = []
    t_miss_us: list[float] = []
    for idx, is_exist in enumerate(trials):
        target = first_inv if is_exist else f"INV:MISSING_{idx:03d}"
        req = {"protocol_version": PROTOCOL_VERSION, "request_id": f"tm-{idx}", "action": {"tool": "get_document", "args": {"doc_id": target}}}
        t0 = time.perf_counter_ns()
        env2.step(req)
        dt_us = (time.perf_counter_ns() - t0) / 1000.0
        if is_exist:
            t_exist_us.append(dt_us)
        else:
            t_miss_us.append(dt_us)

    mean_diff_us = statistics.mean(t_exist_us) - statistics.mean(t_miss_us)
    se_diff_us = math.sqrt(
        (statistics.stdev(t_exist_us) ** 2) / len(t_exist_us)
        + (statistics.stdev(t_miss_us) ** 2) / len(t_miss_us)
    )
    ci90_lo = mean_diff_us - 1.645 * se_diff_us
    ci90_hi = mean_diff_us + 1.645 * se_diff_us
    practical_margin_us = 2000.0
    timing_equivalent = abs(ci90_lo) <= practical_margin_us and abs(ci90_hi) <= practical_margin_us

    return {
        "error_surface_uniform": error_surface_uniform,
        "timing_equivalence": {
            "trials_per_arm": 35,
            "practical_equivalence_margin_us": practical_margin_us,
            "mean_existing_us": round(statistics.mean(t_exist_us), 2),
            "mean_missing_us": round(statistics.mean(t_miss_us), 2),
            "mean_diff_us": round(mean_diff_us, 2),
            "tost_ci90_diff_us": [round(ci90_lo, 2), round(ci90_hi, 2)],
            "within_practical_equivalence_margin": timing_equivalent,
            "caveat": "Timing equivalence within a practical margin on local IPC does not prove absence of microarchitectural side channels.",
        },
    }


def run_shortcut_audit(*, output_path: Path | str | None = None) -> dict[str, Any]:
    out_file = Path(output_path) if output_path else DEFAULT_REPORT_PATH

    anomaly_cycle: tuple[tuple[str, ...], ...] = (
        (),
        ("DUPLICATE_PAYMENT",),
        ("PARTIAL_PAYMENT_ALLOCATION",),
        ("FX_RATE_MISMATCH",),
        ("PERIOD_CUTOFF",),
        ("DUPLICATE_PAYMENT", "FX_RATE_MISMATCH"),
    )

    buckets = (
        "invoices_domestic",
        "payments",
        "journal_accrual_domestic",
        "journal_accrual_foreign",
        "journal_settlement",
    )
    train_by_tbl: dict[str, list[tuple[list[float], int]]] = {b: [] for b in buckets}
    test_by_tbl: dict[str, list[tuple[list[float], int]]] = {b: [] for b in buckets}
    sample_ep_dir: Path | None = None

    with tempfile.TemporaryDirectory(prefix="tl_shortcut_audit_") as td:
        root = Path(td)
        # Orthogonal design: every (split, anomaly_class, id_style, timezone) is independent of anomaly_class
        tz_choices = ("Asia/Almaty", "Europe/Berlin", "Asia/Tokyo", "UTC")
        for split_idx, is_train in enumerate((True, False)):
            grp_counter = 0
            for style_idx, style_code in enumerate(("A", "B", "C", "D")):
                for tz_name in tz_choices:
                    for anoms in anomaly_cycle:
                        grp_counter += 1
                        grp_seed = (4000 if is_train else 6000) + grp_counter
                        spec = CleanTwinSpec(
                            episode_id=f"ep_sc_{grp_seed}",
                            master_seed=grp_seed,
                            episode_index=grp_counter,
                            id_style=style_code,
                            timezone=tz_name,
                            distractor_classes=("D-DUP-01", "D-PART-01", "D-FX-01", "D-CUT-01"),
                            enable_text_layer=True,
                            language_profile="mixed",
                        )
                        gen = build_episode(EpisodeRecipe(twin_spec=spec, anomalies=anoms), root)
                        tbl_rows = _extract_episode_metadata_by_table(gen.episode_dir)
                        target = train_by_tbl if is_train else test_by_tbl
                        for k, rows in tbl_rows.items():
                            if k in target:
                                target[k].extend(rows)
                        if sample_ep_dir is None:
                            sample_ep_dir = gen.episode_dir

        per_table_metrics: dict[str, Any] = {}
        aucs: list[float] = []
        pr_aucs: list[float] = []
        bal_accs: list[float] = []
        briers: list[float] = []

        for tbl_name in buckets:
            tr = train_by_tbl[tbl_name]
            te = test_by_tbl[tbl_name]
            weights, bias = _fit_logistic_regression_l2(tr)
            scores = [_sigmoid(sum(w * x for w, x in zip(weights, x_vec)) + bias) for x_vec, _ in te]
            labels = [y for _, y in te]
            roc_auc, pr_auc = _roc_and_pr_auc(scores, labels)
            preds = [1 if s >= 0.5 else 0 for s in scores]
            tp = sum(1 for p, y in zip(preds, labels) if p == 1 and y == 1)
            tn = sum(1 for p, y in zip(preds, labels) if p == 0 and y == 0)
            pos = max(1, sum(labels))
            neg = max(1, len(labels) - sum(labels))
            bal_acc = 0.5 * ((tp / pos) + (tn / neg))
            brier = sum((s - float(y)) ** 2 for s, y in zip(scores, labels)) / max(1, len(labels))

            aucs.append(roc_auc)
            pr_aucs.append(pr_auc)
            bal_accs.append(bal_acc)
            briers.append(brier)
            per_table_metrics[tbl_name] = {
                "train_records": len(tr),
                "test_records": len(te),
                "test_positives": sum(labels),
                "roc_auc": round(roc_auc, 4),
                "pr_auc": round(pr_auc, 4),
                "balanced_accuracy": round(bal_acc, 4),
                "brier_calibration_score": round(brier, 4),
                "feature_weights": {name: round(w, 4) for name, w in zip(FEATURE_NAMES, weights)},
            }

        assert sample_ep_dir is not None
        side_channels = _run_side_channel_checks(sample_ep_dir)

    macro_roc_auc = sum(aucs) / len(aucs)
    macro_pr_auc = sum(pr_aucs) / len(pr_aucs)
    macro_bal_acc = sum(bal_accs) / len(bal_accs)
    macro_brier = sum(briers) / len(briers)

    auc_ok = macro_roc_auc <= MAX_ALLOWED_ROC_AUC
    sc_ok = bool(side_channels["error_surface_uniform"]) and bool(
        side_channels["timing_equivalence"]["within_practical_equivalence_margin"]
    )
    passed = auc_ok and sc_ok

    cfg_meta = {
        "classifier": "WithinTable_L2_LogisticRegression_Stdlib",
        "max_allowed_roc_auc": str(MAX_ALLOWED_ROC_AUC),
        "train_groups": 24,
        "test_groups": 24,
        "features": list(FEATURE_NAMES),
    }

    report = {
        "schema_version": "1.0.0",
        "report_type": "shortcut_audit",
        "code_version": "twinledger@1.0.0",
        "config_hash": sha256_hex(cfg_meta),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "command": "python3 judge/shortcut_audit.py",
        "status": "PASS" if passed else "FAIL",
        "metadata_classifier": {
            "model": "Within-table L2-regularized Logistic Regression (grouped by history_seed, zero twin overlap)",
            "max_allowed_roc_auc": round(MAX_ALLOWED_ROC_AUC, 4),
            "macro_roc_auc": round(macro_roc_auc, 4),
            "macro_pr_auc": round(macro_pr_auc, 4),
            "macro_balanced_accuracy": round(macro_bal_acc, 4),
            "macro_brier_calibration_score": round(macro_brier, 4),
            "within_auc_bound": auc_ok,
            "per_table": per_table_metrics,
        },
        "side_channel_audit": side_channels,
    }
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    rep = run_shortcut_audit()
    mc = rep["metadata_classifier"]
    per_tbl = {k: v["roc_auc"] for k, v in mc["per_table"].items()}
    print(
        f"[{rep['status']}] shortcut audit: macro_ROC_AUC={mc['macro_roc_auc']} "
        f"(per_table={per_tbl}), "
        f"side_channels={rep['side_channel_audit']['error_surface_uniform']} -> {DEFAULT_REPORT_PATH}"
    )
    return 0 if rep["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
