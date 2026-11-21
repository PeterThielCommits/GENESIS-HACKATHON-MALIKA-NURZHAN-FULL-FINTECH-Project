#!/usr/bin/env python3
"""Public-safe episode inspector CLI (reads only manifest.json and public/)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gen.serialize import verify_episode_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect a TwinLedger public episode")
    parser.add_argument("episode", help="Episode directory")
    args = parser.parse_args(argv)

    ep_dir = Path(args.episode)
    errs = verify_episode_manifest(ep_dir)
    manifest = json.loads((ep_dir / "manifest.json").read_text(encoding="utf-8"))
    company = json.loads((ep_dir / "public" / "company.json").read_text(encoding="utf-8"))
    policy = json.loads((ep_dir / "public" / "policy.json").read_text(encoding="utf-8"))
    out = {
        "episode_id": manifest["episode_id"],
        "manifest_valid": len(errs) == 0,
        "manifest_errors": errs,
        "company_currency": company["functional_currency"],
        "company_timezone": company["timezone"],
        "fiscal_period_rule": company["fiscal_period_rule"],
        "id_style": company["id_style"],
        "rounding_mode": policy["rounding_mode"],
        "fx_policy": policy["fx_policy"],
        "cutoff_policy": policy["cutoff_policy"],
        "profile": manifest.get("profile", {}),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if not errs else 1


if __name__ == "__main__":
    raise SystemExit(main())
