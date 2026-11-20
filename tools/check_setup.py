"""Environment check for `make setup` (master spec 23.2): nothing is downloaded.

Verifies the Python version and reports which optional extras are importable. Absent
extras only ever turn optional checks into SKIPPED (REQ-JUDGE-003); they never fail the
mandatory suite and never change a PASS into a FAIL.
"""

from __future__ import annotations

import importlib.util
import json
import sys

REQUIRED = (3, 11)
OPTIONAL = ["pytest", "hypothesis", "jsonschema", "gymnasium", "numpy", "sklearn"]


def main() -> int:
    version = sys.version_info
    python_ok = (version.major, version.minor) == REQUIRED
    extras = {name: importlib.util.find_spec(name) is not None for name in OPTIONAL}
    payload = {
        "check": "setup",
        "status": "PASS" if python_ok else "FAIL",
        "python": sys.version.split()[0],
        "python_required": ".".join(str(part) for part in REQUIRED),
        "optional_extras": extras,
        "network_used": False,
    }
    print(json.dumps(payload, indent=2))
    if not python_ok:
        print(f"setup: FAIL - Python {payload['python_required']}.x is required", file=sys.stderr)
        return 3
    print("setup: OK (no network access, nothing installed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
