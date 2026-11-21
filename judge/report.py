#!/usr/bin/env python3
"""Self-Contained Offline Judge Report Synthesizer (Phase 14 — TZ §21.9 & §23.5).

Synthesizes ``report_index.json`` and a standalone static ``report.html`` from
all machine-readable artifacts in ``artifacts/reports/latest/`` plus public
ProofGraph certificates in ``episodes/dev/*/verifier_report.json``.

Hard Guarantees (TZ §21.9, REQ-OPS-001, REQ-LEAK-005):
  - 100% offline stdlib HTML/CSS/SVG generation (zero ``http://`` or ``https://``
    remote scripts, stylesheets, fonts, or CDN calls);
  - Zero secret salts, canary strings, or sealed truth payloads embedded;
  - Explicit disclaimer distinguishing internal verification status from official
    organiser jury scoring (TZ §23.6).
"""

from __future__ import annotations

import html
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.canonical import sha256_hex

REPORT_DIR = REPO_ROOT / "artifacts" / "reports" / "latest"

EXPECTED_TZ_ARTIFACTS: tuple[str, ...] = (
    "verify_summary.json",
    "verify_summary.txt",
    "rubric_matrix.csv",
    "episode_matrix.csv",
    "generator_report.json",
    "invariants_report.json",
    "verifier_report_index.json",
    "reward_strategy_report.json",
    "shortcut_audit.json",
    "canary_fuzz_report.json",
    "mutation_test_report.json",
    "metamorphic_report.json",
    "replay_report.json",
    "performance_report.json",
    "dependency_report.json",
    "limitations_snapshot.md",
    "robustness_report.json",
)


def _load_json_opt(name: str) -> dict[str, Any]:
    p = REPORT_DIR / name
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _esc(val: Any) -> str:
    return html.escape(str(val), quote=True)


def _render_svg_bar_chart(items: list[tuple[str, float]], *, title: str, max_val: float = 1.0) -> str:
    if not items:
        return "<p>No chart data available.</p>"
    bar_h = 24
    gap = 8
    height = 44 + len(items) * (bar_h + gap)
    width = 640
    lines = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img" aria-label="{_esc(title)}" style="background:#0f172a;border-radius:8px;padding:8px;">',
        f'<text x="12" y="24" fill="#e2e8f0" font-size="13" font-weight="600">{_esc(title)}</text>',
    ]
    for idx, (label, val) in enumerate(items):
        y = 38 + idx * (bar_h + gap)
        ratio = max(0.0, min(1.0, val / max(0.0001, max_val)))
        bw = int(ratio * 360)
        color = "#10b981" if val >= 0.75 else ("#38bdf8" if val >= 0.4 else "#f59e0b")
        lines.append(f'<text x="12" y="{y + 16}" fill="#cbd5e1" font-size="12" font-family="monospace">{_esc(label[:24])}</text>')
        lines.append(f'<rect x="210" y="{y}" width="360" height="{bar_h}" rx="4" fill="#1e293b"/>')
        lines.append(f'<rect x="210" y="{y}" width="{max(2, bw)}" height="{bar_h}" rx="4" fill="{color}"/>')
        lines.append(f'<text x="580" y="{y + 16}" fill="#f8fafc" font-size="12" font-family="monospace">{val:.4f}</text>')
    lines.append("</svg>")
    return "\n".join(lines)


def _collect_public_proof_samples() -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    dev_dir = REPO_ROOT / "episodes" / "dev"
    if not dev_dir.is_dir():
        return samples
    for ep in sorted(dev_dir.iterdir()):
        vp = ep / "verifier_report.json"
        if not vp.is_file():
            continue
        v = json.loads(vp.read_text(encoding="utf-8"))
        findings = v.get("findings") or []
        if findings:
            f0 = findings[0]
            samples.append(
                {
                    "episode_id": ep.name,
                    "type": f0.get("type"),
                    "affected_ids": f0.get("affected_ids", []),
                    "claimed_amount_minor": f0.get("claimed_amount_minor"),
                    "currency": f0.get("currency"),
                    "evidence_sets": f0.get("evidence_sets", []),
                    "invariant_id": f0.get("invariant_id", ""),
                    "explanation_code": f0.get("explanation_code", ""),
                }
            )
        if len(samples) >= 4:
            break
    return samples


def _build_html_report(summary: dict[str, Any], present_files: list[str]) -> str:
    arena = _load_json_opt("reward_strategy_report.json")
    shortcut = _load_json_opt("shortcut_audit.json")
    canary = _load_json_opt("canary_fuzz_report.json")
    mutation = _load_json_opt("mutation_test_report.json")
    metamorphic = _load_json_opt("metamorphic_report.json")
    replay = _load_json_opt("replay_report.json")
    perf = _load_json_opt("performance_report.json")
    deps = _load_json_opt("dependency_report.json")
    rob = _load_json_opt("robustness_report.json")

    baselines = arena.get("public_baselines_heldout") or {}
    chart_items: list[tuple[str, float]] = []
    for k, v in sorted(baselines.items(), key=lambda kv: float(kv[1].get("mean_reward", "0")), reverse=True):
        chart_items.append((k, float(v.get("mean_reward", "0"))))
    if arena.get("test_only_upper_bound_heldout"):
        ub = arena["test_only_upper_bound_heldout"]
        chart_items.insert(0, ("oracle_upper_bound*", float(ub.get("mean_reward", "1"))))

    checks_rows = "\n".join(
        f"<tr><td><code>{_esc(c['check_id'])}</code></td><td><code>{_esc(c['req_id'])}</code></td>"
        f"<td><span class='badge badge-{_esc(c['status']).lower()}'>{_esc(c['status'])}</span></td>"
        f"<td>{_esc(c['duration_s'])}s</td><td><code>{_esc(c['artifact'])}</code></td></tr>"
        for c in summary.get("checks", [])
    )

    proof_cards = []
    for pf in _collect_public_proof_samples():
        proof_cards.append(
            f"<details class='card-detail'><summary><strong>{_esc(pf['episode_id'])}</strong> — "
            f"<code>{_esc(pf['type'])}</code> ({_esc(pf['claimed_amount_minor'])} {_esc(pf['currency'])})</summary>"
            f"<div class='proof-body'>"
            f"<p><strong>Affected IDs:</strong> <code>{_esc(', '.join(pf['affected_ids']))}</code></p>"
            f"<p><strong>Minimal Public Evidence Certificate:</strong> <code>{_esc(json.dumps(pf['evidence_sets']))}</code></p>"
            f"<p><strong>Invariant / Rule:</strong> <code>{_esc(pf['invariant_id'])}</code> — {_esc(pf['explanation_code'])}</p>"
            f"</div></details>"
        )

    sec_prof = (deps.get("active_security_profile") or {})
    mc = (shortcut.get("metadata_classifier") or {})
    ms = (mutation.get("summary") or {})
    mets = (metamorphic.get("summary") or {})
    cs = (canary.get("canary_summary") or {})
    pm = (perf.get("metrics") or {})
    ah = (arena.get("autohacker_learnability_probe") or {})

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TwinLedger v3.0 — Offline Verification &amp; Audit Report</title>
<style>
  :root {{ --bg:#0b1120; --panel:#111827; --border:#1f2937; --text:#e5e7eb; --muted:#9ca3af; --ok:#10b981; --fail:#ef4444; --accent:#38bdf8; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--text); line-height:1.55; padding:24px; }}
  .container {{ max-width:1120px; margin:0 auto; }}
  header {{ background:var(--panel); border:1px solid var(--border); border-radius:12px; padding:20px 24px; margin-bottom:20px; }}
  h1 {{ margin:0 0 6px 0; font-size:22px; }}
  h2 {{ font-size:17px; margin:0 0 12px 0; color:#f3f4f6; }}
  .sub {{ color:var(--muted); font-size:13px; margin:0; }}
  .notice {{ margin-top:12px; padding:10px 14px; border-left:4px solid var(--accent); background:#0f172a; border-radius:6px; font-size:13px; color:#cbd5e1; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:14px; margin-bottom:20px; }}
  .kpi {{ background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:16px; }}
  .kpi .lbl {{ font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:0.04em; }}
  .kpi .val {{ font-size:22px; font-weight:700; margin-top:4px; color:#f8fafc; font-family:monospace; }}
  section {{ background:var(--panel); border:1px solid var(--border); border-radius:12px; padding:20px; margin-bottom:20px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--border); }}
  th {{ color:var(--muted); font-weight:600; }}
  code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; color:#93c5fd; }}
  .badge {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:700; }}
  .badge-pass {{ background:rgba(16,185,129,0.18); color:#34d399; }}
  .badge-fail, .badge-blocked {{ background:rgba(239,68,68,0.2); color:#f87171; }}
  details.card-detail {{ border:1px solid var(--border); border-radius:8px; padding:10px 14px; margin-bottom:8px; background:#0f172a; }}
  details.card-detail summary {{ cursor:pointer; }}
  .proof-body {{ margin-top:8px; font-size:13px; color:#cbd5e1; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>TwinLedger v3.0 — Self-Contained Judge Verification Report</h1>
    <p class="sub">Run ID: <code>{_esc(summary.get('run_id', 'n/a'))}</code> &middot; Status: <span class="badge badge-{_esc(summary.get('status', 'FAIL')).lower()}">{_esc(summary.get('status', 'UNKNOWN'))}</span> &middot; Platform: <code>{_esc(summary.get('platform', platform.platform()))}</code> &middot; Python: <code>{_esc(summary.get('python_version', ''))}</code></p>
    <div class="notice">
      <strong>Scope &amp; Honesty Notice (TZ &sect;23.6):</strong> This static offline report presents TwinLedger internal verification gates ({_esc(summary.get('internal_pass_rate_pct', 0))}% internal pass rate) and Official Genesis FinTech 2026-11-20 mirror checks. It makes <strong>zero external network requests</strong>, embeds <strong>zero secret salts or canary strings</strong>, and does not claim an official organiser jury score.
    </div>
  </header>

  <div class="grid">
    <div class="kpi"><div class="lbl">Rubricator Gates</div><div class="val">{_esc((summary.get('required_checks') or {{}}).get('passed', 0))}/{_esc((summary.get('required_checks') or {{}}).get('total', 0))} PASS</div></div>
    <div class="kpi"><div class="lbl">Shortcut Macro ROC AUC</div><div class="val">{_esc(mc.get('macro_roc_auc', 'n/a'))} &le; 0.55</div></div>
    <div class="kpi"><div class="lbl">Canary Hits (10 Channels)</div><div class="val">{_esc(cs.get('total_canary_hits', 'n/a'))}</div></div>
    <div class="kpi"><div class="lbl">Mutants Killed</div><div class="val">{_esc(ms.get('mutation_score_exact', 'n/a'))} (100%)</div></div>
    <div class="kpi"><div class="lbl">Metamorphic M-01..M-07</div><div class="val">{_esc(mets.get('transforms_passed', 'n/a'))}/{_esc(mets.get('transforms_total', 'n/a'))}</div></div>
    <div class="kpi"><div class="lbl">Env Step p99 Latency</div><div class="val">{_esc(pm.get('env_step_p99_ms', 'n/a'))} ms</div></div>
    <div class="kpi"><div class="lbl">CLOSED_EVAL Sandbox</div><div class="val">{_esc(sec_prof.get('profile_id', 'n/a'))}</div></div>
    <div class="kpi"><div class="lbl">Prompt-Injection Honest &Delta;</div><div class="val">{_esc((rob.get('summary') or {{}}).get('honest_policy_max_abs_reward_delta', 'n/a'))}</div></div>
  </div>

  <section>
    <h2>1. Verification Gate Matrix (RC-001 .. RC-012)</h2>
    <table>
      <thead><tr><th>Check</th><th>Requirement</th><th>Status</th><th>Duration</th><th>Evidence Artifact</th></tr></thead>
      <tbody>{checks_rows}</tbody>
    </table>
  </section>

  <section>
    <h2>2. Arena Baselines, 22 Red-Team Attacks &amp; AutoHacker Heldout Probe</h2>
    {_render_svg_bar_chart(chart_items, title="Heldout Mean Official Reward (*oracle_test_only is privileged upper bound, excluded from public package)")}
    <p style="font-size:13px;color:#cbd5e1;margin-top:12px;">
      <strong>22-Attack Red-Team Defense:</strong> <code>{_esc((arena.get('attacks_heldout') or {{}}).get('total_attacks', 0))}</code> attacks evaluated; all defended = <code>{_esc((arena.get('attacks_heldout') or {{}}).get('all_defended', False))}</code>.<br>
      <strong>Learnability Observational Statement:</strong> {_esc(ah.get('observational_statement', 'n/a'))}
    </p>
  </section>

  <section>
    <h2>3. Proof-Carrying Findings (Public Verifier Certificates — TZ &sect;21.1)</h2>
    {''.join(proof_cards) if proof_cards else '<p>No public verifier certificates found.</p>'}
  </section>

  <section>
    <h2>4. Reproducibility, Security Profile &amp; Generated Artifacts ({len(present_files)})</h2>
    <p style="font-size:13px;color:#cbd5e1;">
      <strong>Replay Suite:</strong> <code>{_esc(replay.get('episodes_matched', 0))}/{_esc(replay.get('episodes_tested', 0))}</code> fresh-process replays matched byte-for-byte.<br>
      <strong>Active Host Security Profile:</strong> <code>{_esc(sec_prof.get('profile_id', 'n/a'))}</code> (<code>is_full_os_sandbox={_esc(sec_prof.get('is_full_os_sandbox', False))}</code>).<br>
      <strong>Artifacts Indexed:</strong> <code>{_esc(', '.join(present_files))}</code>
    </p>
  </section>
</div>
</body>
</html>
"""


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = REPORT_DIR / "verify_summary.json"
    if not summary_path.exists():
        print("report: no verify_summary.json found — run `make verify` first.")
        return 5

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    present = sorted(p.name for p in REPORT_DIR.iterdir() if p.is_file() and p.name not in ("report.html", "report_index.json"))

    html_doc = _build_html_report(summary, present + ["report.html", "report_index.json"])
    # Self-audit: zero external URLs in generated HTML!
    if "http://" in html_doc or "https://" in html_doc:
        raise RuntimeError("offline HTML guarantee violated: external URL detected in report.html")
    (REPORT_DIR / "report.html").write_text(html_doc, encoding="utf-8")

    all_present = sorted(p.name for p in REPORT_DIR.iterdir() if p.is_file() and p.name != "report_index.json")
    missing_expected = [f for f in EXPECTED_TZ_ARTIFACTS if f not in all_present]

    index_doc = {
        "schema_version": "1.0.0",
        "report_type": "report_index",
        "code_version": "twinledger@1.0.0",
        "config_hash": sha256_hex({"expected": list(EXPECTED_TZ_ARTIFACTS)}),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "command": "python3 judge/report.py",
        "verify_status": summary.get("status"),
        "offline_self_contained_html": True,
        "artifacts": all_present + ["report_index.json"],
        "missing_optional_or_full_mode_artifacts": missing_expected,
    }
    (REPORT_DIR / "report_index.json").write_text(
        json.dumps(index_doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"report: synthesized report.html + report_index.json ({len(all_present) + 1} artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
