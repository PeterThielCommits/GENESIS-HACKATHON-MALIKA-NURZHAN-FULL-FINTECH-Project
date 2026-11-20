#!/usr/bin/env python3
"""Episode inspector stub (Phase 3+)."""
import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a TwinLedger episode (Phase 3+)")
    parser.add_argument("episode", help="episode directory")
    parser.parse_args()
    print("inspect_episode: not yet implemented (Phase 3).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
