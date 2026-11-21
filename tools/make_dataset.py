#!/usr/bin/env python3
"""Dataset builder stub (Phase 3+). See TZ 10.2 pipeline G1..G17."""
import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Build TwinLedger episodes (Phase 3+)")
    parser.add_argument("--config", default="configs/generator/default.json")
    parser.add_argument("--out", default="episodes/dev")
    parser.parse_args()
    print("make_dataset: generator not yet implemented (Phase 3). No episodes written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
