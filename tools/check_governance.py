"""Governance and documentation consistency checks (Phase 0 gate).

These checks are the executable form of the Phase 0 exit criteria:

* every ``A-001..A-016`` has an explicit status and an existing isolation point;
* every open question exists, is owned and has a closure condition;
* every decision is dated, owned and cross-referenced;
* the rubric map never claims official status and every cited REQ exists;
* the archived specification is byte-identical to its recorded hash;
* no document presents a provisional formula, weight or score as official;
* generated/sealed data cannot be committed by accident.

Usage:
    python -m tools.check_governance [--json]
Exit codes: 0 all governance checks pass, 1 failure, 4 release blocker (leak or false
official claim present), 2 configuration error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
CONTRACT_DIR = ROOT / "contracts"
MAKEFILE = ROOT / "Makefile"

STATUS_VOCAB = {"UNRESOLVED", "CONFIRMED", "MODIFIED"}
QUESTION_VOCAB = {"OPEN", "ANSWERED", "WITHDRAWN", "PROVISIONAL_VERBAL"}
CHECK_STATUS_VOCAB = {"PASS", "FAIL", "SKIPPED", "BLOCKED", "NOT_IMPLEMENTED"}
BLOCKS = {"contract_isolation", "data_truth", "reward_robustness", "reproducibility", "engineering"}

REQUIRED_DOCS = [
    "README.md", "AGENTS.md",
    "docs/PROJECT_CONTEXT.md", "docs/CURRENT_STATE.md", "docs/STATUS.md", "docs/DECISIONS.md",
    "docs/QUESTIONS.md", "docs/RUBRIC_TRACEABILITY.md", "docs/RISK_REGISTER.md",
    "docs/INDEPENDENCE.md", "docs/DATA_DICTIONARY.md", "docs/DESIGN.md", "docs/THREAT_MODEL.md",
    "docs/LIMITATIONS.md", "docs/CHANGELOG.md", "docs/GIT_AND_DATA_POLICY.md", "docs/OWNERSHIP.md",
    "docs/ASSUMPTIONS.json", "docs/REQUIREMENTS.json",
    "docs/CONTEXT/NEXT_AGENT.md", "docs/CONTEXT/ARCHITECTURE_SNAPSHOT.md",
    "docs/official/README.md", "docs/official/MANIFEST.json", "docs/official/CONTRACT_SUMMARY.md",
    "docs/official/CONTRACT_SIGNOFF.md", "docs/official/SOURCE_SEARCH_LOG.md",
    "contracts/CONTRACT.md", "judge/rubric_map.json",
    # Phase 1 additions: process, freeze and submission records must not disappear silently.
    "docs/PHASE0_CHECKLIST.md", "docs/BRANCH_PROTECTION.md",
    "docs/official/SUBMISSION_DEADLINE.md", "docs/PHASE_REPORTS/PHASE-01.md",
    "contracts/GOLDEN.json", "configs/submission/submission.json",
    ".github/workflows/verify.yml", ".github/pull_request_template.md", ".github/CODEOWNERS",
]

# A forbidden claim is only a violation when the same line does not negate it.
FORBIDDEN_CLAIMS = [
    (re.compile(r"\b100\s*/\s*100\b"), "claims a perfect official score"),
    (re.compile(r"\bofficial\s+score\b", re.IGNORECASE), "mentions an official score"),
    (re.compile(r"\bofficial\s+rubric\s+(is|=|was)\s+(known|published|available)\b", re.IGNORECASE),
     "claims the official rubric is known"),
    (re.compile(r"\bguarantee(?:d|s)?\s+(?:victory|winning|a\s+win)\b", re.IGNORECASE), "claims a guaranteed win"),
]
# A line is only a violation when nothing on it frames the phrase as forbidden, blocked,
# false or provisional. This is a guard against accidental claims, not a proof-reader: the
# review checklist still requires a human to read a changed sentence.
NEGATIONS = re.compile(
    r"(never|no\b|not\b|nothing|non-|cannot|can't|forbidden|forbid|prohibit|prevent|blocks?\b|"
    r"scan|scanning|false|falsely|provisional|unconfirmed|do not|don't|without|"
    r"internal|may not|запрещ|нельзя|\bне\b|не является|предварительн|внутренн)",
    re.IGNORECASE,
)
LEAK_PATTERNS = [
    (re.compile(r"\"(?:salt|master_seed|seed)\"\s*:\s*\"[0-9a-fA-F]{16,}\""), "literal salt/seed value committed"),
    (re.compile(r"master_seed\s*=\s*['\"][0-9a-fA-F]{8,}['\"]"), "literal master seed committed"),
]
# Explicit, reviewable exemption for detector self-tests. A line carrying this marker is a
# sample string used to prove the detector still detects; it is never documentation or a claim.
DETECTOR_SAMPLE_MARKER = "claim-detector-sample"
SCAN_SUFFIXES = {".md", ".json", ".txt", ".py", ".yml", ".yaml"}
SCAN_SKIP = (
    "docs/official/master_tz/", "artifacts/", ".git/", "__pycache__/",
    # The scanner necessarily contains the phrases it looks for; scanning itself would be
    # circular and would train reviewers to ignore the check.
    "tools/check_governance.py", "tools/verify.py",
)


class Check:
    def __init__(self, check_id: str, rubric_ids: list[str], title: str) -> None:
        self.check_id = check_id
        self.rubric_ids = rubric_ids
        self.title = title
        self.status = "PASS"
        self.reason = ""
        self.details: list[str] = []
        self.blocker = False

    def fail(self, reason: str, *, blocker: bool = False) -> None:
        self.status = "FAIL"
        self.reason = reason if not self.reason else f"{self.reason}; {reason}"
        self.blocker = self.blocker or blocker

    def note(self, detail: str) -> None:
        self.details.append(detail)

    def as_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "rubric_ids": self.rubric_ids,
            "title": self.title,
            "status": self.status,
            "blocker": self.blocker,
            "reason": self.reason,
            "details": self.details,
        }


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def make_targets() -> set[str]:
    if not MAKEFILE.is_file():
        return set()
    targets = set()
    for line in MAKEFILE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+):(?!=)", line)
        if match:
            targets.add(match.group(1))
    return targets


def command_resolves(command: str) -> bool:
    """A check command resolves if its make target or python module exists."""
    targets = make_targets()
    for token in command.split():
        if token in targets:
            return True
    for match in re.finditer(r"python(?:\d(?:\.\d+)?)? -m ([\w.]+)([^&|;]*)", command):
        module, rest = match.group(1), match.group(2).strip()
        if module == "unittest":
            # `python -m unittest tests.a.b` / `... discover -s tests`
            if rest.startswith("discover"):
                return (ROOT / "tests").is_dir()
            target = next((token for token in rest.split() if not token.startswith("-")), "")
            if not target:
                return False
            path = ROOT / (target.replace(".", "/") + ".py")
            return path.is_file() or (ROOT / target.replace(".", "/")).is_dir()
        path = ROOT / (module.replace(".", "/") + ".py")
        if path.is_file() or (ROOT / module.replace(".", "/")).is_dir():
            return True
    return False


# --------------------------------------------------------------------------- checks
def check_docs_present() -> Check:
    check = Check("GOV-DOCS-01", ["EN-DOCS-01"], "Required Phase 0 documents exist")
    missing = [name for name in REQUIRED_DOCS if not (ROOT / name).is_file()]
    for name in missing:
        check.fail(f"missing {name}")
    check.note(f"{len(REQUIRED_DOCS) - len(missing)}/{len(REQUIRED_DOCS)} required documents present")
    return check


def check_assumptions() -> Check:
    check = Check("GOV-ASSUMPTIONS-01", ["EN-GOV-01"], "Assumption register is complete and isolated")
    path = DOCS / "ASSUMPTIONS.json"
    if not path.is_file():
        check.fail("docs/ASSUMPTIONS.json missing")
        return check
    registry = read_json(path)
    assumptions = registry.get("assumptions", [])
    ids = [item.get("id") for item in assumptions]
    expected = [f"A-{n:03d}" for n in range(1, 17)]
    for wanted in expected:
        if wanted not in ids:
            check.fail(f"{wanted} is not registered")
    for duplicate in {i for i in ids if ids.count(i) > 1}:
        check.fail(f"{duplicate} is registered more than once")
    questions_text = (DOCS / "QUESTIONS.md").read_text(encoding="utf-8") if (DOCS / "QUESTIONS.md").is_file() else ""
    decisions_text = (DOCS / "DECISIONS.md").read_text(encoding="utf-8") if (DOCS / "DECISIONS.md").is_file() else ""
    for item in assumptions:
        aid = item.get("id", "?")
        if item.get("status") not in STATUS_VOCAB:
            check.fail(f"{aid} has invalid status {item.get('status')!r}")
        if item.get("status") == "CONFIRMED" and not item.get("official_source"):
            check.fail(f"{aid} claims CONFIRMED without an official source")
        points = item.get("isolation_points", [])
        if not points:
            check.fail(f"{aid} has no isolation point")
        for point in points:
            if not (ROOT / point).exists():
                check.fail(f"{aid} isolation point does not exist: {point}")
        question = item.get("question_id", "")
        if not re.fullmatch(r"Q-[0-9]{3}", question or ""):
            check.fail(f"{aid} has no valid question id")
        elif f"## {question} " not in questions_text:
            check.fail(f"{aid} points to {question} which is not in docs/QUESTIONS.md")
        for decision in item.get("decision_ids", []):
            if f"## {decision} " not in decisions_text:
                check.fail(f"{aid} points to {decision} which is not in docs/DECISIONS.md")
        test_ref = item.get("verification_test", "")
        test_file = test_ref.split("::")[0]
        if not (ROOT / test_file).is_file():
            check.fail(f"{aid} verification test does not exist: {test_ref}")
        for field_name in ("close_condition", "impact_if_wrong", "owner", "spec_ref", "title_en", "provisional_value"):
            if not item.get(field_name):
                check.fail(f"{aid} is missing {field_name}")
    check.note(f"registered {len(assumptions)} assumptions, all with isolation points and owners")
    return check


def check_questions() -> Check:
    check = Check("GOV-QUESTIONS-01", ["EN-GOV-01"], "Open questions are owned, numbered and traceable")
    path = DOCS / "QUESTIONS.md"
    if not path.is_file():
        check.fail("docs/QUESTIONS.md missing")
        return check
    text = path.read_text(encoding="utf-8")
    blocks = re.findall(r"^## ((?:Q-[0-9]{3})|OPEN-0)\s+—\s+(.+)$", text, re.MULTILINE)
    ids = [block[0] for block in blocks]
    for number in range(1, 15):
        qid = f"Q-{number:03d}"
        if qid not in ids:
            check.fail(f"{qid} is missing from docs/QUESTIONS.md")
    if len(ids) != len(set(ids)):
        check.fail("duplicate question ids")
    for qid in ids:
        section = extract_section(text, qid)
        status = re.search(r"\*\*Status:\*\*\s*([A-Z_]+)", section)
        if not status or status.group(1) not in QUESTION_VOCAB:
            check.fail(f"{qid} has no valid status")
        for field_name in ("Asked to", "Date asked", "Owner", "Close condition", "Impact if unanswered", "Current mitigation"):
            if f"**{field_name}:**" not in section:
                check.fail(f"{qid} is missing the {field_name} field")
        if status and status.group(1) == "ANSWERED" and "**Answer source:**" not in section:
            check.fail(f"{qid} is ANSWERED without a quoted source")
    check.note(f"{len(ids)} question sections validated")
    return check


def extract_section(text: str, anchor: str) -> str:
    pattern = re.compile(rf"^## {re.escape(anchor)}\b.*?(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    return match.group(0) if match else ""


def check_decisions() -> Check:
    check = Check("GOV-DECISIONS-01", ["EN-GOV-01"], "Decisions are dated, owned and consistent with the assumption register")
    path = DOCS / "DECISIONS.md"
    if not path.is_file():
        check.fail("docs/DECISIONS.md missing")
        return check
    text = path.read_text(encoding="utf-8")
    blocks = re.findall(r"^## (D-[0-9]{4})\s+—\s+(.+)$", text, re.MULTILINE)
    if len(blocks) < 20:
        check.fail(f"only {len(blocks)} decisions recorded; Phase 0 requires the full decision set")
    seen: set[str] = set()
    for decision_id, _title in blocks:
        if decision_id in seen:
            check.fail(f"{decision_id} is duplicated")
        seen.add(decision_id)
        section = extract_section(text, decision_id)
        for field_name in ("Status", "Date", "Owner", "Refs", "Context", "Decision", "Alternatives", "Consequences"):
            if field_name == "Context":
                present = "**Context:**" in section
            else:
                present = f"**{field_name}:**" in section
            if not present:
                check.fail(f"{decision_id} is missing {field_name}")
        if len(section) < 400:
            check.fail(f"{decision_id} is too thin to be a decision record ({len(section)} chars)")

    registry = read_json(DOCS / "ASSUMPTIONS.json") if (DOCS / "ASSUMPTIONS.json").is_file() else {"assumptions": []}
    table_rows = dict(re.findall(r"^\|\s*(A-[0-9]{3})\s*\|.*?\|\s*([A-Z_]+)\s*\|", text, re.MULTILINE))
    for item in registry["assumptions"]:
        aid = item["id"]
        if aid not in table_rows:
            check.fail(f"assumption status table is missing {aid}")
        elif table_rows[aid] != item["status"]:
            check.fail(f"{aid} status differs between DECISIONS.md ({table_rows[aid]}) and ASSUMPTIONS.json ({item['status']})")
        for decision in item.get("decision_ids", []):
            if decision not in seen:
                check.fail(f"{aid} references unknown decision {decision}")
    check.note(f"{len(blocks)} decisions, {len(table_rows)} assumption rows cross-checked")
    return check


def check_requirements_registry() -> Check:
    check = Check("GOV-REQUIREMENTS-01", ["EN-GOV-01"], "Requirement registry matches the archived specification")
    path = DOCS / "REQUIREMENTS.json"
    if not path.is_file():
        check.fail("docs/REQUIREMENTS.json missing")
        return check
    registry = read_json(path)
    from tools import extract_requirements  # local import keeps the module import graph small

    expected = extract_requirements.render(extract_requirements.extract())
    if path.read_text(encoding="utf-8") != expected:
        check.fail("registry is stale; run python -m tools.extract_requirements")
    ids = [item["id"] for item in registry["requirements"]]
    if len(ids) != registry["total_requirements"]:
        check.fail("registry total_requirements does not match the item count")
    for area in ("PROD", "ENV", "SCORE", "VER", "GEN", "ERR", "SEAL", "JUDGE"):
        if not any(i.startswith(f"REQ-{area}-") for i in ids):
            check.fail(f"no requirements extracted for area {area}")
    check.note(f"{len(ids)} requirements from {registry['source_sha256'][:12]}…")
    return check


def check_rubric_map() -> Check:
    check = Check("GOV-RUBRIC-01", ["EN-GOV-01", "EN-VERIFY-01"], "Rubric map is provisional, traceable and never claims official checks")
    path = ROOT / "judge" / "rubric_map.json"
    if not path.is_file():
        check.fail("judge/rubric_map.json missing")
        return check
    rubric = read_json(path)
    if rubric.get("official_rubric_available") is not False:
        check.fail("official_rubric_available must be false until an official rubric is archived", blocker=True)
    if rubric.get("provisional") is not True:
        check.fail("rubric map must be declared provisional")
    reqs = {item["id"] for item in read_json(DOCS / "REQUIREMENTS.json")["requirements"]}
    ids = [c["check_id"] for c in rubric["internal_checks"]]
    if len(ids) != len(set(ids)):
        check.fail("duplicate internal check ids")
    from tools import gen_traceability

    try:
        current = DOCS.joinpath("RUBRIC_TRACEABILITY.md").read_text(encoding="utf-8")
    except OSError:
        current = ""
    if current != gen_traceability.build():
        check.fail("docs/RUBRIC_TRACEABILITY.md is stale "
                   "(run `python3 -m tools.gen_traceability --write`)")
    else:
        check.note("RUBRIC_TRACEABILITY.md is generated and current")
    for item in rubric["internal_checks"]:
        cid = item["check_id"]
        if item.get("official") is not False:
            check.fail(f"{cid} claims official status", blocker=True)
        if item.get("block") not in BLOCKS:
            check.fail(f"{cid} has unknown block {item.get('block')!r}")
        if not re.fullmatch(r"[A-Z]{2,8}-[A-Z0-9]{1,16}-[0-9]{2}", cid):
            check.fail(f"{cid} does not match the rubric check id pattern")
        if item.get("declared_state") not in {"IMPLEMENTED", "PLANNED"}:
            check.fail(f"{cid} has invalid declared_state")
        if not item.get("req_ids"):
            check.fail(f"{cid} cites no requirement")
        for req_id in item.get("req_ids", []):
            if req_id not in reqs:
                check.fail(f"{cid} cites unknown requirement {req_id}")
        if not item.get("artifact"):
            check.fail(f"{cid} has no artifact path")
        command = item.get("command", "")
        if item.get("declared_state") == "IMPLEMENTED" and not command_resolves(command):
            check.fail(f"{cid} command does not resolve: {command}")
    blocks = {item["block"] for item in rubric["blocks"]}
    if blocks != BLOCKS:
        check.fail("rubric blocks do not match the block vocabulary")
    if sum(b["provisional_points"] for b in rubric["blocks"]) != 100:
        check.fail("provisional block points do not sum to 100")
    implemented = sum(1 for c in rubric["internal_checks"] if c["declared_state"] == "IMPLEMENTED")
    check.note(f"{len(ids)} internal checks ({implemented} implemented, {len(ids) - implemented} planned)")
    return check


def check_archive() -> Check:
    check = Check("GOV-ARCHIVE-01", ["EN-ARCHIVE-01"], "Archived source documents are byte-identical to their recorded hashes")
    manifest_path = DOCS / "official" / "MANIFEST.json"
    if not manifest_path.is_file():
        check.fail("docs/official/MANIFEST.json missing")
        return check
    manifest = read_json(manifest_path)
    import hashlib

    for entry in manifest.get("documents", []):
        target = ROOT / entry["path"]
        if not target.is_file():
            check.fail(f"archived document missing: {entry['path']}")
            continue
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != entry["sha256"]:
            check.fail(f"{entry['path']} hash mismatch (recorded {entry['sha256'][:12]}…, actual {digest[:12]}…)",
                       blocker=True)
        if entry.get("classification") not in {"DERIVED_INTERNAL", "OFFICIAL_ORGANIZER"}:
            check.fail(f"{entry['path']} has invalid classification")
    check.note(f"{len(manifest.get('documents', []))} archived documents verified")
    return check


def check_no_official_claims() -> Check:
    check = Check("GOV-CLAIMS-01", ["EN-DOCS-01"], "No provisional item is presented as official and no secret is committed")
    violations: list[str] = []
    leaks: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        relative = rel(path)
        if any(relative.startswith(prefix) for prefix in SCAN_SKIP):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:  # pragma: no cover - binary file
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if DETECTOR_SAMPLE_MARKER in line:
                continue
            for pattern, description in FORBIDDEN_CLAIMS:
                if pattern.search(line) and not NEGATIONS.search(line):
                    violations.append(f"{relative}:{number}: {description} -> {line.strip()[:120]}")
            for pattern, description in LEAK_PATTERNS:
                if pattern.search(line):
                    leaks.append(f"{relative}:{number}: {description}")
    for violation in violations:
        check.fail(violation, blocker=True)
    for leak in leaks:
        check.fail(leak, blocker=True)
    check.note(f"scanned source and docs for official-status claims and committed secrets")
    return check


def check_readme_commands() -> Check:
    check = Check("GOV-README-01", ["EN-DOCS-01"], "Documented commands exist in the Makefile")
    targets = make_targets()
    if not targets:
        check.fail("Makefile has no targets")
        return check
    required_targets = {"help", "setup", "lint", "test", "verify", "verify-core", "clean"}
    for target in sorted(required_targets - targets):
        check.fail(f"required make target missing: {target}")
    for name in ("README.md", "docs/CURRENT_STATE.md", "docs/PROJECT_CONTEXT.md"):
        path = ROOT / name
        if not path.is_file():
            continue
        for match in re.finditer(r"`?make ([A-Za-z0-9_.-]+)", path.read_text(encoding="utf-8")):
            target = match.group(1)
            if target not in targets:
                check.fail(f"{name} documents 'make {target}' but the target does not exist")
    check.note(f"{len(targets)} make targets available")
    return check


def check_git_data_policy() -> Check:
    check = Check("GOV-GIT-01", ["EN-DATA-01"], "Sealed, hidden and generated data cannot be committed")
    ignore = ROOT / ".gitignore"
    policy = DOCS / "GIT_AND_DATA_POLICY.md"
    if not ignore.is_file():
        check.fail(".gitignore missing")
        return check
    if not policy.is_file():
        check.fail("docs/GIT_AND_DATA_POLICY.md missing")
    text = ignore.read_text(encoding="utf-8")
    for pattern in ("episodes/", "sealed/", "artifacts/", "*.salt", "__pycache__/"):
        if pattern not in text:
            check.fail(f".gitignore does not cover {pattern}")
    if policy.is_file():
        body = policy.read_text(encoding="utf-8")
        for token in ("sealed", "hidden", "salt", "TEST_FIXTURE"):
            if token not in body:
                check.fail(f"data policy does not discuss {token}")
    check.note(".gitignore and the written policy agree")
    return check


def check_phase_reports() -> Check:
    check = Check("GOV-PHASE-REPORT-01", ["EN-REPORT-01"], "Each phase has a human and machine readable report")
    reports = sorted((DOCS / "PHASE_REPORTS").glob("PHASE-*.md"))
    if not reports:
        check.fail("no phase reports found")
    for report in reports:
        phase = report.stem
        data = report.with_suffix(".json")
        if not data.is_file():
            check.fail(f"{phase} has no machine readable .json companion")
            continue
        try:
            payload = read_json(data)
        except json.JSONDecodeError as exc:
            check.fail(f"{phase}.json is invalid JSON: {exc}")
            continue
        for key in ("phase", "status", "requirements", "verification", "artifacts", "known_limitations"):
            if key not in payload:
                check.fail(f"{phase}.json is missing {key}")
        body = report.read_text(encoding="utf-8")
        for heading in ("## Outcome", "## Objectives", "## Verification", "## Risks", "## Owner sign-off"):
            if heading not in body:
                check.fail(f"{phase}.md is missing the '{heading}' section")
    check.note(f"{len(reports)} phase report(s) validated")
    return check


def check_signoff() -> Check:
    check = Check("GOV-SIGNOFF-01", ["EN-GOV-01"], "Contract summary review has two explicit signature slots")
    path = DOCS / "official" / "CONTRACT_SIGNOFF.md"
    if not path.is_file():
        check.fail("docs/official/CONTRACT_SIGNOFF.md missing")
        return check
    text = path.read_text(encoding="utf-8")
    reviewers = re.findall(r"^### Reviewer ([12])\b", text, re.MULTILINE)
    if len(reviewers) != 2:
        check.fail(f"expected 2 reviewer slots, found {len(reviewers)}")
    for number in (1, 2):
        section = extract_section(text, f"Reviewer {number}") if f"## Reviewer {number}" in text else ""
        if not section:
            section = re.split(rf"^### Reviewer {number}\b", text, maxsplit=1, flags=re.MULTILINE)[-1]
        status = re.search(r"\*\*Status:\*\*\s*([A-Z_]+)", section)
        if not status:
            check.fail(f"Reviewer {number} has no status")
            continue
        if status.group(1) not in {"SIGNED", "PENDING"}:
            check.fail(f"Reviewer {number} has invalid status {status.group(1)!r}")
        if status.group(1) == "SIGNED":
            for field_name in ("Name", "Date", "Scope", "Evidence"):
                if f"**{field_name}:**" not in section:
                    check.fail(f"Reviewer {number} is SIGNED without {field_name}")
    pending = text.count("**Status:** PENDING")
    if pending:
        check.note(f"{pending} human signature(s) PENDING - reported as HUMAN_ACTION_REQUIRED, never as PASS")
    return check


def check_status_doc() -> Check:
    check = Check("GOV-STATUS-01", ["EN-GOV-01"], "STATUS.md reports gates with evidence and honest vocabulary")
    path = DOCS / "STATUS.md"
    if not path.is_file():
        check.fail("docs/STATUS.md missing")
        return check
    text = path.read_text(encoding="utf-8")
    for token in ("PASS_WITH_OPEN_ITEMS", "NOT RUN", "BLOCKED", "SKIPPED", "PHASE-00"):
        if token not in text:
            check.fail(f"STATUS.md does not mention {token!r}")
    if "| Gate |" not in text:
        check.fail("STATUS.md has no gate table")
    check.note("gate table present")
    return check


def check_ci_workflow() -> Check:
    """The workflow must execute the same gate a human runs (task 1.5)."""
    from tools import check_ci

    check = Check("GOV-CI-01", ["EN-CI-01"], "CI workflow runs the same gate as a local checkout")
    result = check_ci.run()
    if result["status"] != "PASS":
        for problem in result["problems"]:
            check.fail(problem)
    else:
        check.note(f"{len(result['workflows'])} workflow(s): {', '.join(result['workflows'])}")
    for note in result["notes"]:
        check.note(note)
    if not (ROOT / ".github" / "pull_request_template.md").is_file():
        check.fail("no .github/pull_request_template.md")
    else:
        check.note(".github/pull_request_template.md present")
    templates = sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml"))
    if len(templates) < 3:
        check.fail(f"expected at least 3 issue templates, found {len(templates)}")
    else:
        check.note(f"{len(templates)} issue form(s)")
    return check


def check_submission_config() -> Check:
    """Task 0.8: the deadline is either confirmed by a human or explicitly unknown."""
    check = Check("GOV-DEADLINE-01", ["EN-SUBMIT-01"],
                  "Submission deadline and timezone are recorded honestly")
    path = ROOT / "configs" / "submission" / "submission.json"
    if not path.is_file():
        check.fail("configs/submission/submission.json missing")
        return check
    try:
        config = read_json(path)
    except json.JSONDecodeError as exc:
        check.fail(f"configs/submission/submission.json is invalid JSON: {exc}")
        return check
    values = config.get("values", {})
    deadline = values.get("SUBMISSION_DEADLINE_UTC")
    confirmed_by = values.get("DEADLINE_CONFIRMED_BY")
    confirmed_at = values.get("DEADLINE_CONFIRMED_AT")
    if deadline is None:
        if confirmed_by or confirmed_at:
            check.fail("deadline is empty but DEADLINE_CONFIRMED_BY/AT is filled")
        if "OPEN-0" not in (DOCS / "QUESTIONS.md").read_text(encoding="utf-8"):
            check.fail("deadline is unknown but docs/QUESTIONS.md has no OPEN-0 entry")
        check.note("deadline UNKNOWN and recorded as OPEN-0 - never guessed")
    else:
        if not confirmed_by or not confirmed_at:
            check.fail("deadline is set without a human confirmation (who/when)")
        local = values.get("SUBMISSION_DEADLINE_LOCAL")
        offset = values.get("LOCAL_UTC_OFFSET_HOURS")
        if not local or offset is None:
            check.fail("deadline is set without a matching local time")
        else:
            check.note(f"deadline confirmed: {deadline} (local {local}, UTC{offset:+d})")
    if values.get("LOCAL_TIMEZONE") != "Asia/Almaty":
        check.fail("LOCAL_TIMEZONE is not the team timezone Asia/Almaty")
    if values.get("LOCAL_DST_OBSERVED") is not False:
        check.fail("Asia/Almaty does not observe DST; LOCAL_DST_OBSERVED must be false")
    if not (DOCS / "official" / "SUBMISSION_DEADLINE.md").is_file():
        check.fail("docs/official/SUBMISSION_DEADLINE.md missing")
    return check


def check_models_and_freeze() -> Check:
    """Typed models must mirror the schemas, and the contract set must still match its freeze."""
    from tools import check_golden, check_models

    check = Check("GOV-MODELS-01", ["EN-MODELS-01", "CT-GOLDEN-01"],
                  "Typed models mirror the schemas and the contract freeze is intact")
    models = check_models.run()
    if models["status"] != "PASS":
        for problem in models["problems"]:
            check.fail(problem)
    else:
        check.note(f"{models['models']} typed models, parity and round-trip verified")
    golden = check_golden.run()
    if golden["status"] != "PASS":
        for problem in golden["problems"]:
            check.fail(problem)
    else:
        check.note(f"{golden['files_checked']} contract files match the recorded freeze")
    return check


def run() -> list[Check]:
    checks = [
        check_docs_present(),
        check_assumptions(),
        check_questions(),
        check_decisions(),
        check_requirements_registry(),
        check_rubric_map(),
        check_archive(),
        check_no_official_claims(),
        check_readme_commands(),
        check_git_data_policy(),
        check_phase_reports(),
        check_signoff(),
        check_status_doc(),
        check_ci_workflow(),
        check_submission_config(),
        check_models_and_freeze(),
    ]
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    checks = run()
    blocker = any(c.blocker for c in checks)
    status = "PASS" if all(c.status == "PASS" for c in checks) else "FAIL"
    payload = {
        "check": "governance",
        "status": status,
        "exit_code": 4 if blocker else (0 if status == "PASS" else 1),
        "checks": [c.as_dict() for c in checks],
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"governance: {status}")
        for check in checks:
            print(f"  {check.status} {check.check_id} {check.title}")
            if check.reason:
                for item in check.reason.split("; "):
                    print(f"      - {item}")
            for detail in check.details:
                print(f"      . {detail}")
    return payload["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
