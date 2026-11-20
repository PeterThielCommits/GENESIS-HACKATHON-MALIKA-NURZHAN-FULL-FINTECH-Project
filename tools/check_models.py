"""Check that the typed models are a faithful mirror of the contract schemas (task 1.4).

Three properties, each of which has failed in real projects:

1. **parity** — every schema property has exactly one dataclass field and vice versa. A model
   that quietly drops a field is worse than no model, because it looks validated.
2. **required-set parity** — the model's ``REQUIRED`` matches the schema's ``required``, so
   "optional" cannot be decided twice and differently.
3. **round-trip** — every valid fixture becomes an object and comes back byte-identical under
   canonical JSON; every invalid fixture is rejected by ``from_dict`` (validation happens at
   construction, not at some later call).

Usage:
    python -m tools.check_models [--json]
Exit codes: 0 pass, 1 mismatch, 2 configuration error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import MODELS
from models.base import ContractViolation

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"

JSON_TYPE_TO_PYTHON = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
}


def schema_type(schema: dict, prop: dict) -> str | None:
    """Resolve a property's JSON type, following a single local ``$ref`` if needed."""
    if "type" in prop:
        node = prop
    elif "$ref" in prop:
        node = resolve_ref(schema, prop["$ref"])
    else:
        return None
    declared = node.get("type")
    if isinstance(declared, list):
        declared = next((item for item in declared if item != "null"), None)
    return declared


def resolve_ref(schema: dict, ref: str) -> dict:
    file_part, _, pointer = ref.partition("#")
    target = schema if not file_part else json.loads((CONTRACTS / file_part).read_text(encoding="utf-8"))
    node: object = target
    for token in [part for part in pointer.split("/") if part]:
        node = node[int(token)] if isinstance(node, list) else node[token]  # type: ignore[index]
    return node  # type: ignore[return-value]


def check_parity() -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []
    for schema_name, model in sorted(MODELS.items()):
        path = CONTRACTS / schema_name
        if not path.is_file():
            problems.append(f"{schema_name}: schema file missing")
            continue
        schema = json.loads(path.read_text(encoding="utf-8"))
        properties = schema.get("properties", {})
        fields = model.field_names()
        missing = set(properties) - fields
        extra = fields - set(properties)
        if missing:
            problems.append(f"{model.__name__}: schema properties with no field {sorted(missing)}")
        if extra:
            problems.append(f"{model.__name__}: fields absent from the schema {sorted(extra)}")
        if set(schema.get("required", [])) != set(model.REQUIRED):
            drift = set(schema.get("required", [])) ^ set(model.REQUIRED)
            problems.append(f"{model.__name__}: required/optional drift {sorted(drift)}")

        hints = model.__dataclass_fields__  # type: ignore[attr-defined]
        for name in sorted(set(properties) & fields):
            declared = schema_type(schema, properties[name])
            if declared is None:
                continue
            expected = JSON_TYPE_TO_PYTHON.get(declared)
            if expected is None:
                continue
            annotation = str(hints[name].type)
            # `dict[str, Any]` -> `dict`, `list[str] | None` -> `list`
            base = annotation.replace("| None", "").replace("None | ", "").strip()
            base = base.split("[")[0].strip()
            allowed_names = {t.__name__ for t in expected}
            if base not in allowed_names and base != "Any":
                problems.append(
                    f"{model.__name__}.{name}: schema type {declared!r} but annotation {annotation!r}")
        notes.append(f"{model.__name__}: {len(fields)} fields mirror {schema_name}")
    return problems, notes


def check_round_trip() -> tuple[list[str], list[str]]:
    index = json.loads((CONTRACTS / "fixtures" / "index.json").read_text(encoding="utf-8"))
    problems: list[str] = []
    valid = invalid = 0
    for case in index["cases"]:
        model = MODELS.get(case["schema"])
        if model is None:
            continue
        payload = json.loads((CONTRACTS / "fixtures" / case["file"]).read_text(encoding="utf-8"))
        if case["expect"] == "valid":
            try:
                obj = model.from_dict(payload)
            except ContractViolation as exc:
                problems.append(f"{case['case_id']}: valid fixture rejected by {model.__name__} ({exc})")
                continue
            rebuilt = obj.to_dict()
            # Plain sorted-dump comparison: canonical JSON deliberately rejects floats, and
            # `confidence` is a JSON number, so the canonical form is the wrong tool here.
            if json.dumps(rebuilt, sort_keys=True) != json.dumps(payload, sort_keys=True):
                problems.append(f"{case['case_id']}: round-trip changed the payload")
            obj.validate()  # serialisation must still be valid
            valid += 1
        else:
            try:
                model.from_dict(payload)
            except ContractViolation:
                invalid += 1
            else:
                problems.append(f"{case['case_id']}: invalid fixture accepted by {model.__name__}")
    return problems, [f"{valid} valid fixtures round-trip, {invalid} invalid fixtures rejected"]


def run() -> dict:
    parity_problems, parity_notes = check_parity()
    round_problems, round_notes = check_round_trip()
    problems = parity_problems + round_problems
    return {
        "check": "models",
        "status": "PASS" if not problems else "FAIL",
        "models": len(MODELS),
        "problems": problems,
        "notes": parity_notes + round_notes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run()
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        print(f"models: CONFIG ERROR - {exc}")
        return 2
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"models: {result['status']} ({result['models']} typed models)")
        for note in result["notes"]:
            print(f"  . {note}")
        for problem in result["problems"]:
            print(f"  - {problem}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
