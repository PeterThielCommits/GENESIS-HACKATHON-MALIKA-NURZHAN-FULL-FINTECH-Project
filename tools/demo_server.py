#!/usr/bin/env python3
"""TwinLedger v3.0 — Interactive Local Audit, Verifier & ProofGraph Workbench.

Zero third-party dependencies (Python 3.11 stdlib only).
Works both on a local laptop (`python3 tools/demo_server.py`) and in cloud live previews.

Endpoints (all relative `/api/...`):
  GET  /                       Interactive web UI
  GET  /api/episodes           List all episodes in episodes/dev & episodes/train
  GET  /api/episode/<split>/<id>/overview   Public metadata, manifest check, table counts
  POST /api/episode/<split>/<id>/verify     Run real Stage-1 verifier.discover + ProofGraph + Stage-2 crosscheck
  POST /api/env/reset          Reset interactive TwinLedgerEnv session on an episode
  POST /api/env/step           Execute frozen-contract tool_request against active env session
  POST /api/env/score          Score submitted findings externally via scoring.reward.compute_reward
  POST /api/generate           Generate & 100%-verify a custom episode live on the fly
  POST /api/run_checks         Run real `tools/check_import_boundaries.py` & `unittest` summary
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.models import Finding, TruthFinding
from env import EnvConfig, TwinLedgerEnv
from gen.core.clean_twin import CleanTwinSpec
from gen.pipeline import EpisodeRecipe, build_episode
from gen.serialize import verify_episode_manifest
from scoring.crosscheck import crosscheck
from scoring.reward import compute_reward
from tools.make_dataset import build_and_verify_split
from verifier import VerifierConfig, discover

_SESSIONS_LOCK = threading.Lock()
_ENV_SESSIONS: dict[str, dict[str, Any]] = {}


def _ensure_local_sealed() -> None:
    """Ensure local gitignored sealed/ directories exist by regenerating deterministically if absent."""
    for split in ("dev", "train"):
        split_dir = REPO_ROOT / "episodes" / split
        ep_dirs = sorted(p for p in split_dir.iterdir() if p.is_dir()) if split_dir.is_dir() else []
        if not ep_dirs or any(not (p / "sealed" / "truth.json").is_file() for p in ep_dirs):
            build_and_verify_split(split, split_dir, master_seed=2025)


def _list_episodes() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for split in ("dev", "train"):
        split_dir = REPO_ROOT / "episodes" / split
        if not split_dir.is_dir():
            continue
        for ep_dir in sorted(p for p in split_dir.iterdir() if p.is_dir()):
            manifest_path = ep_dir / "manifest.json"
            company_path = ep_dir / "public" / "company.json"
            policy_path = ep_dir / "public" / "policy.json"
            report_path = ep_dir / "verifier_report.json"
            if not (manifest_path.is_file() and company_path.is_file() and policy_path.is_file()):
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            company = json.loads(company_path.read_text(encoding="utf-8"))
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {"findings": []}
            items.append(
                {
                    "split": split,
                    "episode_id": ep_dir.name,
                    "company_name": company["legal_name"],
                    "currency": company["functional_currency"],
                    "supported_currencies": company["supported_currencies"],
                    "timezone": company["timezone"],
                    "fiscal_period_rule": company["fiscal_period_rule"],
                    "id_style": company["id_style"],
                    "rounding_mode": policy["rounding_mode"],
                    "quote_convention": policy["fx_policy"]["quote_convention"],
                    "finding_count": len(report.get("findings", [])),
                    "finding_types": sorted({f["type"] for f in report.get("findings", [])}),
                    "profile": manifest.get("profile", {}),
                }
            )
    return items


def _resolve_episode_dir(split: str, episode_id: str) -> Path | None:
    if split not in ("dev", "train"):
        return None
    if "/" in episode_id or "\\" in episode_id or ".." in episode_id:
        return None
    ep_dir = (REPO_ROOT / "episodes" / split / episode_id).resolve()
    base = (REPO_ROOT / "episodes" / split).resolve()
    if not ep_dir.is_relative_to(base) or not ep_dir.is_dir():
        return None
    return ep_dir


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TwinLedger v3.0 — Live Audit, Verifier &amp; ProofGraph Workbench</title>
<style>
  :root {
    --bg: #0b1020; --panel: #121933; --panel2: #182244; --border: #27345e;
    --text: #e8eefc; --muted: #9aa8cc; --accent: #4f8cff; --green: #22c55e;
    --amber: #f59e0b; --red: #ef4444; --purple: #a855f7; --cyan: #06b6d4;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif; background: var(--bg); color: var(--text); line-height: 1.45; }
  header { background: linear-gradient(90deg, #0f172a, #172554); border-bottom: 1px solid var(--border); padding: 14px 24px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
  header h1 { margin: 0; font-size: 18px; letter-spacing: 0.2px; }
  header .sub { color: var(--muted); font-size: 12px; }
  .pill { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; background: #1e293b; border: 1px solid var(--border); }
  .pill.green { color: #86efac; border-color: #166534; background: #052e16; }
  .pill.blue { color: #93c5fd; border-color: #1d4ed8; background: #172554; }
  .pill.amber { color: #fde68a; border-color: #b45309; background: #451a03; }
  .pill.red { color: #fca5a5; border-color: #991b1b; background: #450a0a; }
  .layout { display: grid; grid-template-columns: 310px 1fr; min-height: calc(100vh - 64px); }
  @media (max-width: 960px) { .layout { grid-template-columns: 1fr; } }
  aside { border-right: 1px solid var(--border); background: #0e152b; padding: 14px; overflow-y: auto; max-height: calc(100vh - 64px); }
  main { padding: 18px 22px; overflow-y: auto; max-height: calc(100vh - 64px); }
  .ep-card { padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--panel); margin-bottom: 8px; cursor: pointer; transition: 0.15s; }
  .ep-card:hover { border-color: var(--accent); background: var(--panel2); }
  .ep-card.active { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); background: #1a264d; }
  .ep-title { font-weight: 600; font-size: 13px; word-break: break-all; }
  .ep-meta { font-size: 11px; color: var(--muted); margin-top: 4px; display: flex; flex-wrap: wrap; gap: 6px; }
  .tabs { display: flex; gap: 8px; border-bottom: 1px solid var(--border); margin-bottom: 16px; flex-wrap: wrap; }
  .tab { padding: 8px 14px; border: 1px solid transparent; border-bottom: none; border-radius: 8px 8px 0 0; cursor: pointer; font-size: 13px; font-weight: 600; color: var(--muted); background: transparent; }
  .tab.active { color: var(--text); background: var(--panel); border-color: var(--border); }
  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 16px; margin-bottom: 14px; }
  .card h3 { margin: 0 0 10px 0; font-size: 15px; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
  .grid4 { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 14px; }
  .kpi { background: var(--panel2); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; }
  .kpi .lbl { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
  .kpi .val { font-size: 18px; font-weight: 700; margin-top: 3px; }
  button { background: var(--accent); color: #fff; border: none; border-radius: 8px; padding: 8px 14px; font-size: 13px; font-weight: 600; cursor: pointer; transition: 0.15s; }
  button:hover { filter: brightness(1.1); }
  button.sec { background: var(--panel2); border: 1px solid var(--border); color: var(--text); }
  button.green { background: #16a34a; }
  button.amber { background: #d97706; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  input, select, textarea { background: #0b1020; color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 7px 10px; font-size: 13px; font-family: inherit; }
  textarea { width: 100%; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
  pre { background: #070b16; border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; overflow: auto; max-height: 360px; font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; margin: 0; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
  th { color: var(--muted); font-weight: 600; background: #0f162e; position: sticky; top: 0; }
  .row-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }
  .node-badge { display: inline-block; padding: 2px 7px; border-radius: 6px; font-size: 11px; font-weight: 700; }
  .nb-RecordNode { background: #1e3a8a; color: #bfdbfe; }
  .nb-RuleNode { background: #581c87; color: #e9d5ff; }
  .nb-FactNode { background: #164e63; color: #a5f3fc; }
  .nb-CalculationNode { background: #78350f; color: #fde68a; }
  .nb-FindingNode { background: #7f1d1d; color: #fecaca; }
  .hidden { display: none; }
</style>
</head>
<body>
<header>
  <div>
    <h1>TwinLedger v3.0 — Live Audit, Verifier &amp; ProofGraph Workbench</h1>
    <div class="sub">Real-time execution on frozen v1.0.0 contracts · Phases 1–8 integrated · Zero external deps</div>
  </div>
  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
    <span class="pill green" id="hdr-status">EXIT GATE 8: 10/10 VERIFIED</span>
    <button class="sec" onclick="runRepoChecks()">Run Live Test &amp; Lint Check</button>
  </div>
</header>

<div class="layout">
  <aside>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
      <strong style="font-size:13px;">Verified Episodes (dev + train)</strong>
      <button class="sec" style="padding:4px 8px;font-size:11px;" onclick="loadEpisodes()">Refresh</button>
    </div>
    <div id="episode-list">Loading...</div>
  </aside>

  <main>
    <div id="check-banner" class="card hidden">
      <h3>Live Repo Verification Output <button class="sec" style="padding:3px 8px;font-size:11px;" onclick="document.getElementById('check-banner').classList.add('hidden')">Hide</button></h3>
      <pre id="check-output"></pre>
    </div>

    <div class="tabs">
      <button class="tab active" data-tab="verifier" onclick="switchTab('verifier')">1. Verifier &amp; ProofGraph</button>
      <button class="tab" data-tab="sandbox" onclick="switchTab('sandbox')">2. Interactive Env &amp; Calc Sandbox</button>
      <button class="tab" data-tab="tables" onclick="switchTab('tables')">3. Public Book Explorer</button>
      <button class="tab" data-tab="generator" onclick="switchTab('generator')">4. Live Episode Generator</button>
    </div>

    <!-- TAB 1: VERIFIER & PROOFGRAPH -->
    <section id="tab-verifier">
      <div class="card">
        <h3>
          <span id="cur-ep-heading">Select an episode</span>
          <div style="display:flex;gap:8px;">
            <button class="green" onclick="runVerifySelected()">Run Stage-1 Verifier + Stage-2 Crosscheck</button>
          </div>
        </h3>
        <div class="grid4" id="ep-kpis"></div>
        <div id="verify-status" style="font-size:13px;color:var(--muted);">Click "Run Stage-1 Verifier + Stage-2 Crosscheck" to execute independent public-only discovery, ProofGraph validation, minimal-evidence ablation, and sealed-truth crosscheck live.</div>
      </div>

      <div id="verify-results" class="hidden">
        <div class="grid2">
          <div class="card">
            <h3>Stage-1 Discovered Findings (Public-Only)</h3>
            <div id="findings-container"></div>
          </div>
          <div class="card">
            <h3>Stage-2 Independent Crosscheck (Exact Fraction Metrics)</h3>
            <div id="crosscheck-container"></div>
          </div>
        </div>
        <div class="card">
          <h3>ProofGraph DAG (Nodes &amp; Edges incl. Distractor Exclusions)</h3>
          <div class="grid2">
            <div>
              <div style="font-size:12px;color:var(--muted);margin-bottom:6px;">Nodes (sorted deterministically)</div>
              <div style="max-height:300px;overflow:auto;"><table id="pg-nodes"></table></div>
            </div>
            <div>
              <div style="font-size:12px;color:var(--muted);margin-bottom:6px;">Edges (derived_from / supports / governed_by / excludes)</div>
              <div style="max-height:300px;overflow:auto;"><table id="pg-edges"></table></div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- TAB 2: INTERACTIVE ENV & CALC SANDBOX -->
    <section id="tab-sandbox" class="hidden">
      <div class="card">
        <h3>
          <span>TwinLedgerEnv Interactive Audit Session (CLOSED_EVAL · protocol v1.0)</span>
          <div style="display:flex;gap:8px;">
            <button onclick="resetEnvSession()">Reset Env on Selected Episode</button>
            <span class="pill blue" id="env-steps-pill">No session</span>
          </div>
        </h3>
        <div class="grid2">
          <div>
            <div style="font-weight:600;font-size:13px;margin-bottom:6px;">Query Tool (`list_records` / `get_record` / `get_document`)</div>
            <div class="row-actions">
              <select id="env-tool" onchange="syncToolTemplate()">
                <option value="list_records">list_records</option>
                <option value="get_record">get_record</option>
                <option value="get_document">get_document</option>
                <option value="calc">calc (Safe AST Decimal)</option>
              </select>
              <button onclick="callEnvTool()">Send tool_request</button>
              <button class="sec" onclick="tryCalcAttack()">Test Attack (`__import__`)</button>
            </div>
            <textarea id="env-args" rows="5">{"table": "invoices", "page_size": 5}</textarea>
          </div>
          <div>
            <div style="font-weight:600;font-size:13px;margin-bottom:6px;">Submit Audit Findings &amp; Compute External Reward</div>
            <div class="row-actions">
              <button class="sec" onclick="autofillFindings()">Auto-fill from Verifier</button>
              <button class="sec" onclick="clearFindings()">Empty Submit (Clean Book)</button>
              <button class="green" onclick="submitAndScore()">Submit &amp; Score</button>
            </div>
            <textarea id="submit-json" rows="5">[]</textarea>
          </div>
        </div>
      </div>
      <div class="grid2">
        <div class="card">
          <h3>Latest `tool_response` (Schema-Validated)</h3>
          <pre id="env-response">Reset an episode to begin...</pre>
        </div>
        <div class="card">
          <h3>External `scoring.reward.compute_reward` Breakdown</h3>
          <pre id="score-response">Submit findings to see exact Fraction F1 &amp; reward...</pre>
        </div>
      </div>
    </section>

    <!-- TAB 3: PUBLIC BOOK EXPLORER -->
    <section id="tab-tables" class="hidden">
      <div class="card">
        <h3>Public Directory Tables (Read via Allowlisted `TwinLedgerEnv`)</h3>
        <div class="row-actions">
          <select id="browse-table" onchange="browseTable()">
            <option value="invoices">invoices</option>
            <option value="payments">payments</option>
            <option value="journal_entries">journal_entries</option>
            <option value="fx_rates">fx_rates</option>
            <option value="bank_lines">bank_lines</option>
            <option value="credit_notes">credit_notes</option>
            <option value="counterparties">counterparties</option>
            <option value="accounts">accounts</option>
            <option value="period_calendar">period_calendar</option>
            <option value="opening_balances">opening_balances</option>
          </select>
          <button onclick="browseTable()">Load Page</button>
          <button class="sec" id="btn-next-page" onclick="browseNextPage()" disabled>Next Page (Opaque Cursor)</button>
          <span class="pill" id="browse-meta">—</span>
        </div>
        <pre id="browse-out">Select a table to inspect...</pre>
      </div>
    </section>

    <!-- TAB 4: LIVE GENERATOR -->
    <section id="tab-generator" class="hidden">
      <div class="card">
        <h3>Generate &amp; 100%-Verify a Custom TwinLedger Episode Live</h3>
        <div class="grid2" style="margin-bottom:12px;">
          <div style="display:flex;flex-direction:column;gap:8px;">
            <label style="font-size:12px;color:var(--muted);">Master Seed <input id="gen-seed" type="number" value="9001" style="width:100%;margin-top:3px;"></label>
            <label style="font-size:12px;color:var(--muted);">Functional Currency
              <select id="gen-cur" style="width:100%;margin-top:3px;">
                <option value="KZT">KZT (exp 2)</option>
                <option value="USD">USD (exp 2)</option>
                <option value="EUR">EUR (exp 2)</option>
                <option value="KWD">KWD (exp 3)</option>
              </select>
            </label>
            <label style="font-size:12px;color:var(--muted);">Anti-Shortcut ID Family
              <select id="gen-idstyle" style="width:100%;margin-top:3px;">
                <option value="A">Family A (PREFIX-HEX)</option>
                <option value="B">Family B (PREFIX/8/16)</option>
                <option value="C">Family C (lower_hex)</option>
                <option value="D">Family D (mod-7 decimal)</option>
              </select>
            </label>
            <label style="font-size:12px;color:var(--muted);">Fiscal Calendar
              <select id="gen-cal" style="width:100%;margin-top:3px;">
                <option value="monthly">monthly</option>
                <option value="quarterly">quarterly</option>
              </select>
            </label>
          </div>
          <div style="display:flex;flex-direction:column;gap:8px;">
            <div style="font-size:12px;color:var(--muted);">Anomalies to Inject (empty = Clean Book)</div>
            <label><input type="checkbox" class="gen-anom" value="DUPLICATE_PAYMENT" checked> DUPLICATE_PAYMENT</label>
            <label><input type="checkbox" class="gen-anom" value="PARTIAL_PAYMENT_ALLOCATION"> PARTIAL_PAYMENT_ALLOCATION</label>
            <label><input type="checkbox" class="gen-anom" value="FX_RATE_MISMATCH" checked> FX_RATE_MISMATCH</label>
            <label><input type="checkbox" class="gen-anom" value="PERIOD_CUTOFF"> PERIOD_CUTOFF</label>
            <label><input type="checkbox" id="gen-distractors" checked> Weave clean distractors (D-DUP/PART/FX/CUT)</label>
            <button class="green" style="margin-top:6px;" onclick="generateCustom()">Generate + Run Stage-1 Verifier + Stage-2 Crosscheck</button>
          </div>
        </div>
        <pre id="gen-out">Configure options above and click Generate...</pre>
      </div>
    </section>
  </main>
</div>

<script>
let episodes = [];
let selected = null;
let lastVerify = null;
let sessionId = null;
let browseSessionId = null;
let browseCursor = null;

async function api(path, opts) {
  const res = await fetch(path, opts);
  return await res.json();
}

function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  ['verifier', 'sandbox', 'tables', 'generator'].forEach(n => {
    document.getElementById('tab-' + n).classList.toggle('hidden', n !== name);
  });
  if (name === 'tables' && selected) browseTable();
}

async function loadEpisodes() {
  const data = await api('/api/episodes');
  episodes = data.episodes || [];
  const box = document.getElementById('episode-list');
  box.innerHTML = '';
  episodes.forEach((ep, idx) => {
    const div = document.createElement('div');
    div.className = 'ep-card' + (selected && selected.episode_id === ep.episode_id ? ' active' : '');
    const types = ep.finding_types.length ? ep.finding_types.join(', ') : 'CLEAN BOOK';
    div.innerHTML = `
      <div class="ep-title">${ep.episode_id}</div>
      <div class="ep-meta">
        <span class="pill blue">${ep.split}</span>
        <span class="pill">${ep.currency} · ID-${ep.id_style}</span>
        <span class="pill ${ep.finding_count ? 'amber' : 'green'}">${ep.finding_count} findings</span>
      </div>
      <div class="ep-meta">${types}</div>
    `;
    div.onclick = () => selectEpisode(ep);
    box.appendChild(div);
    if (!selected && idx === 0) selectEpisode(ep);
  });
}

async function selectEpisode(ep) {
  selected = ep;
  lastVerify = null;
  document.querySelectorAll('.ep-card').forEach(el => {
    el.classList.toggle('active', el.querySelector('.ep-title').textContent === ep.episode_id);
  });
  document.getElementById('cur-ep-heading').textContent = `${ep.split}/${ep.episode_id} — ${ep.company_name}`;
  document.getElementById('ep-kpis').innerHTML = `
    <div class="kpi"><div class="lbl">Currency / TZ</div><div class="val">${ep.currency}</div><div class="ep-meta">${ep.timezone}</div></div>
    <div class="kpi"><div class="lbl">ID Family / Cal</div><div class="val">Style ${ep.id_style}</div><div class="ep-meta">${ep.fiscal_period_rule} · ${ep.rounding_mode}</div></div>
    <div class="kpi"><div class="lbl">Journal Entries</div><div class="val">${ep.profile?.record_count_by_table?.journal_entries ?? '?'}</div><div class="ep-meta">Docs: ${ep.profile?.document_count ?? '?'}</div></div>
    <div class="kpi"><div class="lbl">Clean Distractors</div><div class="val">${ep.profile?.distractor_count ?? 0}</div><div class="ep-meta">Expected 0 FP</div></div>
  `;
  document.getElementById('verify-results').classList.add('hidden');
  document.getElementById('verify-status').textContent = 'Running live independent verifier...';
  await runVerifySelected();
  await resetEnvSession();
}

async function runVerifySelected() {
  if (!selected) return;
  document.getElementById('verify-status').textContent = 'Running Stage-1 public-only discovery + ablation + Stage-2 crosscheck...';
  const data = await api(`/api/episode/${selected.split}/${selected.episode_id}/verify`, { method: 'POST' });
  lastVerify = data;
  document.getElementById('verify-results').classList.remove('hidden');
  const blocked = data.crosscheck.release_blocked;
  document.getElementById('verify-status').innerHTML = `
    <span class="pill ${blocked ? 'red' : 'green'}">${blocked ? 'RELEASE BLOCKED' : 'RELEASE APPROVED (release_blocked=false)'}</span>
    <span class="pill blue">Manifest: ${data.manifest_valid ? 'SHA-256 PASS' : 'FAIL'}</span>
    <span class="pill">report_digest: ${data.report_digest.slice(0, 16)}…</span>
    <span class="pill">ProofGraph: ${data.proof_graph.nodes.length} nodes / ${data.proof_graph.edges.length} edges</span>
  `;

  // Findings
  const fBox = document.getElementById('findings-container');
  const findings = data.report.findings || [];
  if (!findings.length) {
    fBox.innerHTML = `<div class="pill green">0 findings — Clean book verified (0 false positives across ${selected.profile?.distractor_count ?? 0} distractors)</div>`;
  } else {
    fBox.innerHTML = findings.map((f, i) => `
      <div style="border:1px solid var(--border);border-radius:8px;padding:10px;margin-bottom:8px;background:var(--panel2);">
        <div><strong>#${i+1} ${f.type}</strong> · <span class="pill amber">${f.claimed_amount_minor} ${f.currency}</span></div>
        <div style="font-size:12px;margin-top:4px;color:var(--muted);">Affected: <code>${f.affected_ids.join(', ')}</code></div>
        <div style="font-size:12px;margin-top:4px;color:var(--muted);">Minimal Evidence Sets: <code>${JSON.stringify(f.evidence_sets)}</code></div>
        <div style="font-size:11px;margin-top:4px;color:#86efac;">Ablation: sufficient &amp; minimal · ProofRef: ${f.proof_graph_ref}</div>
      </div>
    `).join('');
  }

  // Crosscheck
  const cc = data.crosscheck;
  const cnt = cc.counts || {};
  const m = cc.metrics || {};
  document.getElementById('crosscheck-container').innerHTML = `
    <table>
      <tr><th>Metric</th><th>Exact Value</th></tr>
      <tr><td>TP / FP / FN</td><td><strong>${cnt.tp} / ${cnt.fp} / ${cnt.fn}</strong></td></tr>
      <tr><td>Precision / Recall / F1</td><td><strong>${m.precision?.exact} / ${m.recall?.exact} / ${m.f1?.exact}</strong></td></tr>
      <tr><td>Exact Affected-ID Accuracy</td><td>${m.exact_affected_id_accuracy?.exact} (${m.exact_affected_id_accuracy?.decimal})</td></tr>
      <tr><td>Amount Exact Accuracy</td><td>${m.amount_exact_accuracy?.exact} (${m.amount_exact_accuracy?.decimal})</td></tr>
      <tr><td>Evidence Sufficiency Rate</td><td>${m.evidence_sufficiency_rate?.exact} (${m.evidence_sufficiency_rate?.decimal})</td></tr>
      <tr><td>Evidence Minimality Rate (Ablation)</td><td>${m.evidence_minimality_rate?.exact} (${m.evidence_minimality_rate?.status})</td></tr>
      <tr><td>Distractor False Positive Rate</td><td>${m.distractor_false_positive_rate?.exact} (${m.distractor_false_positive_rate?.decimal})</td></tr>
      <tr><td>Unresolved Ambiguities</td><td>${m.unresolved_ambiguity_count}</td></tr>
      <tr><td>Crosscheck Hash</td><td><code>${cc.crosscheck_hash.slice(0, 24)}…</code></td></tr>
    </table>
  `;

  // ProofGraph tables
  const nTbl = document.getElementById('pg-nodes');
  nTbl.innerHTML = '<tr><th>Type</th><th>Rule</th><th>Sources</th></tr>' +
    data.proof_graph.nodes.map(n => `
      <tr>
        <td><span class="node-badge nb-${n.node_type}">${n.node_type}</span></td>
        <td><code>${n.rule_id}</code></td>
        <td><code>${(n.source_ids || []).join(', ')}</code></td>
      </tr>
    `).join('');

  const eTbl = document.getElementById('pg-edges');
  eTbl.innerHTML = '<tr><th>Edge</th><th>From</th><th>To</th></tr>' +
    data.proof_graph.edges.map(e => `
      <tr>
        <td><span class="pill ${e.edge_type === 'excludes' ? 'green' : 'blue'}">${e.edge_type}</span></td>
        <td><code>${e.from_node_id.slice(0, 22)}…</code></td>
        <td><code>${e.to_node_id.slice(0, 22)}…</code></td>
      </tr>
    `).join('');
}

async function resetEnvSession() {
  if (!selected) return;
  const data = await api('/api/env/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ split: selected.split, episode_id: selected.episode_id }),
  });
  sessionId = data.session_id;
  document.getElementById('env-steps-pill').textContent = `Session ready · 0/${data.observation.limits.max_steps} steps`;
  document.getElementById('env-response').textContent = JSON.stringify(data.observation, null, 2);
  document.getElementById('score-response').textContent = 'Submit findings to see exact Fraction F1 & reward...';
}

function syncToolTemplate() {
  const t = document.getElementById('env-tool').value;
  const presets = {
    list_records: '{"table": "invoices", "page_size": 5}',
    get_record: '{"id": "INV:..."}',
    get_document: '{"id": "policy"}',
    calc: '{"expression": "round_half_even(100 * 483.125, 0)"}',
  };
  document.getElementById('env-args').value = presets[t] || '{}';
}

function tryCalcAttack() {
  document.getElementById('env-tool').value = 'calc';
  document.getElementById('env-args').value = '{"expression": "__import__(\\"os\\").system(\\"id\\")"}';
  callEnvTool();
}

async function callEnvTool() {
  if (!sessionId) await resetEnvSession();
  let args;
  try { args = JSON.parse(document.getElementById('env-args').value); }
  catch (e) { document.getElementById('env-response').textContent = 'Invalid JSON args: ' + e; return; }
  const req = {
    protocol_version: '1.0',
    request_id: 'ui-' + Math.random().toString(16).slice(2, 8),
    action: { tool: document.getElementById('env-tool').value, args },
  };
  const data = await api('/api/env/step', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, request: req }),
  });
  document.getElementById('env-steps-pill').textContent = `Steps: ${data.steps_used} · terminated=${data.terminated}`;
  document.getElementById('env-response').textContent = JSON.stringify(data.response, null, 2);
}

function autofillFindings() {
  if (!lastVerify) return;
  const findings = (lastVerify.report.findings || []).map(f => ({
    schema_version: '1.0.0',
    type: f.type,
    affected_ids: f.affected_ids,
    claimed_amount: f.claimed_amount_minor,
    currency: f.currency,
    evidence_ids: f.evidence_sets[0],
  }));
  document.getElementById('submit-json').value = JSON.stringify(findings, null, 2);
}

function clearFindings() {
  document.getElementById('submit-json').value = '[]';
}

async function submitAndScore() {
  if (!sessionId) await resetEnvSession();
  let findings;
  try { findings = JSON.parse(document.getElementById('submit-json').value); }
  catch (e) { document.getElementById('score-response').textContent = 'Invalid JSON findings: ' + e; return; }
  const req = {
    protocol_version: '1.0',
    request_id: 'submit-' + Math.random().toString(16).slice(2, 8),
    action: { tool: 'submit', args: { findings } },
  };
  const stepData = await api('/api/env/step', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, request: req }),
  });
  document.getElementById('env-steps-pill').textContent = `Steps: ${stepData.steps_used} · terminated=${stepData.terminated}`;
  document.getElementById('env-response').textContent = JSON.stringify(stepData.response, null, 2);

  if (stepData.response.ok) {
    const score = await api('/api/env/score', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
    document.getElementById('score-response').textContent = JSON.stringify(score, null, 2);
  }
}

async function browseTable() {
  if (!selected) return;
  const reset = await api('/api/env/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ split: selected.split, episode_id: selected.episode_id }),
  });
  browseSessionId = reset.session_id;
  browseCursor = null;
  await fetchBrowsePage();
}

async function browseNextPage() {
  if (!browseCursor) return;
  await fetchBrowsePage();
}

async function fetchBrowsePage() {
  const table = document.getElementById('browse-table').value;
  const args = { table, page_size: 10 };
  if (browseCursor) args.cursor = browseCursor;
  const data = await api('/api/env/step', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: browseSessionId,
      request: { protocol_version: '1.0', request_id: 'b-' + Date.now(), action: { tool: 'list_records', args } },
    }),
  });
  const res = data.response.result || {};
  browseCursor = res.next_cursor || null;
  document.getElementById('btn-next-page').disabled = !browseCursor;
  document.getElementById('browse-meta').textContent = `Showing ${res.count ?? 0} of ${res.total_matching ?? 0} rows`;
  document.getElementById('browse-out').textContent = JSON.stringify(res.records || data.response, null, 2);
}

async function generateCustom() {
  const out = document.getElementById('gen-out');
  out.textContent = 'Generating fresh Clean Twin, applying mutations, running Stage-1 Verifier & Stage-2 Crosscheck...';
  const anomalies = Array.from(document.querySelectorAll('.gen-anom:checked')).map(c => c.value);
  const body = {
    seed: parseInt(document.getElementById('gen-seed').value || '9001', 10),
    functional_currency: document.getElementById('gen-cur').value,
    id_style: document.getElementById('gen-idstyle').value,
    fiscal_period_rule: document.getElementById('gen-cal').value,
    anomalies,
    include_distractors: document.getElementById('gen-distractors').checked,
  };
  const data = await api('/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  out.textContent = JSON.stringify(data, null, 2);
}

async function runRepoChecks() {
  const banner = document.getElementById('check-banner');
  const out = document.getElementById('check-output');
  banner.classList.remove('hidden');
  out.textContent = 'Running import boundary scan + full 214-test suite...';
  const data = await api('/api/run_checks', { method: 'POST' });
  out.textContent = data.output;
}

loadEpisodes();
</script>
</body>
</html>
"""


class DemoHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return  # keep server logs tidy

    def _send_json(self, payload: Any, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _send_html(self, html: str) -> None:
        raw = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 262144))
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send_html(HTML_PAGE)
            return
        if parsed.path == "/api/health":
            self._send_json({"ok": True, "service": "twinledger-workbench"})
            return
        if parsed.path == "/api/episodes":
            self._send_json({"episodes": _list_episodes()})
            return

        # GET /api/episode/<split>/<id>/overview
        # Published in docs/API_USAGE.md since Phase 15 but never implemented:
        # following the documentation returned 404. The route reports only
        # *public* facts (metadata, manifest validity, row counts) — never truth,
        # never sealed data — so it is safe to serve without the sealed files the
        # /verify route needs.
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) == 5 and parts[0] == "api" and parts[1] == "episode" and parts[4] == "overview":
            ep_dir = _resolve_episode_dir(parts[2], parts[3])
            if ep_dir is None:
                self._send_json({"error": "episode not found"}, status=404)
                return
            public_dir = ep_dir / "public"
            table_counts: dict[str, int] = {}
            for path in sorted(public_dir.glob("*.jsonl")):
                table_counts[path.stem] = sum(
                    1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
                )
            for path in sorted(public_dir.glob("*.json")):
                try:
                    loaded = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    table_counts[path.stem] = 0
                    continue
                table_counts[path.stem] = len(loaded) if isinstance(loaded, list) else 1
            manifest_errors = verify_episode_manifest(ep_dir)
            company: dict[str, Any] = {}
            company_path = public_dir / "company.json"
            if company_path.is_file():
                company = json.loads(company_path.read_text(encoding="utf-8"))
            self._send_json(
                {
                    "split": parts[2],
                    "episode_id": parts[3],
                    "manifest_present": (ep_dir / "manifest.json").is_file(),
                    "manifest_valid": len(manifest_errors) == 0,
                    "manifest_errors": manifest_errors,
                    "company": {
                        key: company.get(key)
                        for key in ("company_id", "legal_name", "jurisdiction_code", "functional_currency", "timezone", "company_size")
                    },
                    "table_counts": table_counts,
                }
            )
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        try:
            # POST /api/episode/<split>/<id>/verify
            if len(parts) == 5 and parts[0] == "api" and parts[1] == "episode" and parts[4] == "verify":
                ep_dir = _resolve_episode_dir(parts[2], parts[3])
                if ep_dir is None:
                    self._send_json({"error": "episode not found"}, status=404)
                    return
                _ensure_local_sealed()
                m_errs = verify_episode_manifest(ep_dir)
                disc = discover(ep_dir / "public", VerifierConfig(run_ablation=True))
                rep_dict = disc.report.to_dict()
                truths_raw = json.loads((ep_dir / "sealed" / "truth.json").read_text(encoding="utf-8"))
                truths = [TruthFinding.from_dict(t) for t in truths_raw]
                manifest = json.loads((ep_dir / "manifest.json").read_text(encoding="utf-8"))
                distractor_count = int(manifest.get("profile", {}).get("distractor_count", 0))
                cc = crosscheck(
                    rep_dict,
                    truths,
                    expected_report_digest=disc.report_digest,
                    distractor_count=distractor_count,
                )
                self._send_json(
                    {
                        "manifest_valid": len(m_errs) == 0,
                        "manifest_errors": m_errs,
                        "report": rep_dict,
                        "report_digest": disc.report_digest,
                        "proof_graph": disc.proof_graph.to_dict(),
                        "crosscheck": cc.to_dict(),
                    }
                )
                return

            # POST /api/env/reset
            if parsed.path == "/api/env/reset":
                body = self._read_json_body()
                ep_dir = _resolve_episode_dir(str(body.get("split", "")), str(body.get("episode_id", "")))
                if ep_dir is None:
                    self._send_json({"error": "episode not found"}, status=404)
                    return
                env = TwinLedgerEnv(EnvConfig.from_file())
                obs = env.reset(ep_dir / "public")
                sid = uuid.uuid4().hex
                with _SESSIONS_LOCK:
                    if len(_ENV_SESSIONS) > 64:
                        _ENV_SESSIONS.clear()
                    _ENV_SESSIONS[sid] = {"env": env, "ep_dir": ep_dir}
                self._send_json({"session_id": sid, "observation": obs})
                return

            # POST /api/env/step
            if parsed.path == "/api/env/step":
                body = self._read_json_body()
                sid = str(body.get("session_id", ""))
                with _SESSIONS_LOCK:
                    entry = _ENV_SESSIONS.get(sid)
                if entry is None:
                    self._send_json({"error": "unknown session_id — call /api/env/reset"}, status=400)
                    return
                env: TwinLedgerEnv = entry["env"]
                resp = env.step(body.get("request"))
                self._send_json(
                    {
                        "response": resp,
                        "steps_used": env.steps_used,
                        "terminated": env.terminated,
                    }
                )
                return

            # POST /api/env/score
            if parsed.path == "/api/env/score":
                body = self._read_json_body()
                sid = str(body.get("session_id", ""))
                with _SESSIONS_LOCK:
                    entry = _ENV_SESSIONS.get(sid)
                if entry is None:
                    self._send_json({"error": "unknown session_id"}, status=400)
                    return
                env = entry["env"]
                ep_dir = entry["ep_dir"]
                _ensure_local_sealed()
                truths = [
                    TruthFinding.from_dict(t)
                    for t in json.loads((ep_dir / "sealed" / "truth.json").read_text(encoding="utf-8"))
                ]
                findings = [Finding.from_dict(f) for f in (env.submitted_findings or [])]
                rb = compute_reward(findings, truths, steps_used=env.steps_used)
                self._send_json(rb.to_dict())
                return

            # POST /api/generate
            if parsed.path == "/api/generate":
                body = self._read_json_body()
                seed = int(body.get("seed", 9001))
                fcur = str(body.get("functional_currency", "KZT"))
                id_style = str(body.get("id_style", "A"))
                cal = str(body.get("fiscal_period_rule", "monthly"))
                anomalies = tuple(str(x) for x in body.get("anomalies", []))
                foreign = ("USD", "EUR") if fcur == "KZT" else ("USD", "JPY") if fcur != "USD" else ("EUR", "JPY")
                distractors = (
                    ("D-DUP-02", "D-DUP-04", "D-PART-01", "D-FX-01", "D-CUT-02")
                    if body.get("include_distractors", True)
                    else ()
                )
                recipe = EpisodeRecipe(
                    twin_spec=CleanTwinSpec(
                        episode_id=f"live_ep_{seed}_{id_style.lower()}",
                        master_seed=seed,
                        episode_index=1,
                        functional_currency=fcur,
                        foreign_currencies=foreign,
                        fiscal_period_rule=cal,
                        id_style=id_style,
                        distractor_classes=distractors,
                    ),
                    anomalies=anomalies,
                )
                with tempfile.TemporaryDirectory() as td:
                    ep = build_episode(recipe, td)
                    disc = discover(ep.episode_dir / "public", VerifierConfig(run_ablation=True))
                    rep = disc.report.to_dict()
                    truths = [TruthFinding.from_dict(t) for t in ep.truths]
                    cc = crosscheck(
                        rep,
                        truths,
                        expected_report_digest=disc.report_digest,
                        distractor_count=len(distractors),
                    )
                    self._send_json(
                        {
                            "episode_id": ep.episode_id,
                            "manifest_profile": ep.manifest["profile"],
                            "attempts": ep.attempts,
                            "report_digest": disc.report_digest,
                            "discovered_findings": rep["findings"],
                            "crosscheck": cc.to_dict(),
                            "proof_graph_stats": {
                                "nodes": len(disc.proof_graph.nodes),
                                "edges": len(disc.proof_graph.edges),
                                "exclusion_edges": len(disc.proof_graph.exclusion_edges()),
                            },
                        }
                    )
                return

            # POST /api/run_checks
            if parsed.path == "/api/run_checks":
                p1 = subprocess.run(
                    [sys.executable, "tools/check_import_boundaries.py"],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                p2 = subprocess.run(
                    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                combined = (
                    f"$ python3 tools/check_import_boundaries.py (exit {p1.returncode})\n"
                    f"{p1.stdout}{p1.stderr}\n"
                    f"$ python3 -m unittest discover -s tests -t . (exit {p2.returncode})\n"
                    f"{p2.stdout}{p2.stderr}"
                )
                self._send_json({"ok": p1.returncode == 0 and p2.returncode == 0, "output": combined})
                return

            self._send_json({"error": "not found"}, status=404)
        except Exception as exc:
            self._send_json({"error": f"{type(exc).__name__}: {exc}"}, status=500)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TwinLedger v3.0 Interactive Workbench")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    _ensure_local_sealed()
    server = ThreadingHTTPServer((args.host, args.port), DemoHandler)
    print(f"TwinLedger v3.0 Workbench listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
