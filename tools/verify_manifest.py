#!/usr/bin/env python3
"""Manifest verifier stub (Phase 3+). Checks public file hashes (REQ-DATA-021)."""
import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify episode manifest hashes (Phase 3+)")
    parser.add_argument("episode", help="episode directory")
    parser.parse_args()
    print("verify_manifest: not yet implemented (Phase 3).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
