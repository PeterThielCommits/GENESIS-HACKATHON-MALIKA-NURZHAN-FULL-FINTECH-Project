"""Minimal stdlib JSON-Schema (draft-07 subset) validator.

Core must validate contracts offline without the optional ``jsonschema``
package (REQ-PROD-010, TZ 22.2). This validator supports the subset used
by TwinLedger contracts:

  type (incl. type lists), const, enum, required, properties,
  additionalProperties (bool), patternProperties, items, minItems,
  maxItems, minLength, maxLength, minimum, maximum, pattern.

Unknown keywords are ignored. Returns a list of human-readable errors;
empty list means valid. Never raises on invalid *data* (only on malformed
*schema*).
"""

from __future__ import annotations

import re
from typing import Any


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _check_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, (int, float)) and not isinstance(value, bool))
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return False


def validate(instance: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Validate ``instance`` against ``schema``. Returns error list."""
    errors: list[str] = []

    if not isinstance(schema, dict):
        return [f"{path}: malformed schema (not an object)"]

    # const / enum
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum {schema['enum']!r}")

    # type
    if "type" in schema:
        expected = schema["type"]
        expected_list = expected if isinstance(expected, list) else [expected]
        if not any(_check_type(instance, t) for t in expected_list):
            errors.append(
                f"{path}: expected type {expected!r}, got {_type_name(instance)}"
            )
            return errors  # further checks would be meaningless

    # numeric bounds
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance!r} < minimum {schema['minimum']!r}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: {instance!r} > maximum {schema['maximum']!r}")

    # string constraints
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: string shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: string longer than maxLength {schema['maxLength']}")
        if "pattern" in schema:
            try:
                if not re.search(schema["pattern"], instance):
                    errors.append(f"{path}: {instance!r} does not match pattern {schema['pattern']!r}")
            except re.error:
                errors.append(f"{path}: invalid pattern in schema {schema['pattern']!r}")

    # array constraints
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: array shorter than minItems {schema['minItems']}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: array longer than maxItems {schema['maxItems']}")
        if "items" in schema and isinstance(schema["items"], dict):
            for i, item in enumerate(instance):
                errors.extend(validate(item, schema["items"], f"{path}[{i}]"))

    # object constraints
    if isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path}: missing required property {req!r}")
        props = schema.get("properties", {})
        pattern_props = schema.get("patternProperties", {})
        additional = schema.get("additionalProperties", True)
        for key, value in instance.items():
            matched = False
            if key in props:
                matched = True
                errors.extend(validate(value, props[key], f"{path}.{key}"))
            for pat, subschema in pattern_props.items():
                try:
                    if re.search(pat, key):
                        matched = True
                        errors.extend(validate(value, subschema, f"{path}.{key}"))
                except re.error:
                    errors.append(f"{path}: invalid patternProperties pattern {pat!r}")
            if not matched and additional is False:
                errors.append(f"{path}: additional property {key!r} not allowed")

    return errors


def is_valid(instance: Any, schema: dict[str, Any]) -> bool:
    return not validate(instance, schema)
