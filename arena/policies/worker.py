"""Isolated subprocess JSONL worker for public baseline policies.

Runs as a separate OS process (``python3 -m arena.policies.worker --policy ...``)
communicating strictly via stdin/stdout JSONL. Interacts exclusively with
public observations and the five canonical actions (satisfies C20 isolation).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from arena.policies.base import BasePolicy
from arena.policies.mass_flagging import MassFlaggingPolicy
from arena.policies.random_policy import RandomExplorationPolicy
from arena.policies.simple_reconciliation import SimpleReconciliationPolicy


def make_public_policy(name: str, seed: int = 0) -> BasePolicy:
    key = name.strip().lower()
    if key == "random":
        return RandomExplorationPolicy(seed=seed)
    if key in ("simple", "simple_reconciliation"):
        return SimpleReconciliationPolicy(seed=seed)
    if key in ("mass_flagging", "mass-flagging"):
        return MassFlaggingPolicy(seed=seed)
    raise ValueError(f"unknown public policy: {name!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TwinLedger isolated policy worker")
    parser.add_argument("--policy", required=True, choices=["random", "simple", "simple_reconciliation", "mass_flagging"])
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    policy = make_public_policy(args.policy, seed=args.seed)

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        msg: dict[str, Any] = json.loads(line)
        mtype = msg.get("type")
        if mtype == "quit":
            break
        if mtype == "reset":
            policy.reset(msg["observation"])
            action = policy.act(msg["observation"])
        elif mtype == "step":
            action = policy.act(msg["observation"])
        else:
            raise ValueError(f"unsupported worker message type: {mtype!r}")
        sys.stdout.write(json.dumps({"action": action}, separators=(",", ":"), ensure_ascii=False) + "\n")
        sys.stdout.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
