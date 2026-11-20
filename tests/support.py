"""Shared helpers for the TwinLedger test suite (stdlib unittest only)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # allow `python -m unittest discover -s tests -t .`
    sys.path.insert(0, str(ROOT))

DOCS = ROOT / "docs"
CONTRACTS = ROOT / "contracts"
CONFIGS = ROOT / "configs"


def load_json(path: str | Path) -> dict:
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / target
    return json.loads(target.read_text(encoding="utf-8"))


def read_text(path: str | Path) -> str:
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / target
    return target.read_text(encoding="utf-8")


def assumptions() -> dict[str, dict]:
    return {item["id"]: item for item in load_json(DOCS / "ASSUMPTIONS.json")["assumptions"]}


def requirements() -> dict[str, dict]:
    return {item["id"]: item for item in load_json(DOCS / "REQUIREMENTS.json")["requirements"]}


def markdown_sections(text: str, heading_level: int = 2) -> dict[str, str]:
    """Split markdown into {anchor: body} for `#`*heading_level headings."""
    prefix = "#" * heading_level + " "
    pattern = re.compile(rf"^{re.escape(prefix)}(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        title = match.group(1).strip()
        anchor = title.split(" — ")[0].split(" – ")[0].strip()
        sections[anchor] = text[start:end]
    return sections
