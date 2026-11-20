"""A small, strict JSON-Schema subset validator (stdlib only).

Why this exists
---------------
The mandatory core may not depend on third-party packages (master spec §22.1), and
``make verify`` must run offline on Python 3.11 with the standard library only. The
optional ``jsonschema`` extra may be installed for development, but contract validation
must never become a mandatory external dependency.

Supported keywords (everything the TwinLedger contracts actually use):

    $ref (local ``#/$defs/...`` and cross-file ``file.json#/$defs/...``),
    type, const, enum, required, properties, patternProperties, additionalProperties,
    propertyNames, items, minItems, maxItems, uniqueItems, minLength, maxLength,
    pattern, minimum, maximum, allOf, anyOf, oneOf, not, if/then/else

Unknown keywords are ignored (they are treated as annotations). Anything that would need
a network resolver (remote ``$ref``) is rejected, so validation stays offline and
deterministic.

This validator is intentionally *not* a general-purpose JSON-Schema implementation; the
contracts are written to stay inside the supported subset, and
``tests/contracts/test_schema_self_consistency.py`` fails the build if a schema starts
using an unsupported construct.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

__all__ = [
    "SchemaError",
    "ValidationError",
    "ContractValidator",
    "SUPPORTED_KEYWORDS",
    "ANNOTATION_KEYWORDS",
]

SUPPORTED_KEYWORDS = frozenset(
    {
        "$schema", "$id", "$defs", "$ref", "title", "description",
        "type", "const", "enum", "required", "properties", "patternProperties",
        "additionalProperties", "propertyNames", "items", "minItems", "maxItems",
        "uniqueItems", "minLength", "maxLength", "pattern", "minimum", "maximum",
        "allOf", "anyOf", "oneOf", "not", "if", "then", "else",
        # TwinLedger annotations carried on schema documents themselves:
        "schema_version", "status", "provisional_reason",
    }
)
ANNOTATION_KEYWORDS = frozenset(
    {"$schema", "$id", "title", "description", "schema_version", "status", "provisional_reason", "$defs"}
)

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: (isinstance(v, (int, float)) and not isinstance(v, bool)),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


class SchemaError(RuntimeError):
    """Raised when a schema document itself is malformed or uses unsupported features."""


@dataclass(frozen=True)
class ValidationError:
    """One deterministic validation failure."""

    path: str
    keyword: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "keyword": self.keyword, "message": self.message}

    def __str__(self) -> str:  # pragma: no cover - formatting only
        return f"{self.path}: [{self.keyword}] {self.message}"


def _json_pointer_escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


class ContractValidator:
    """Validate JSON documents against the schemas in ``root_dir``."""

    def __init__(self, root_dir: str | Path, max_ref_depth: int = 32) -> None:
        self.root_dir = Path(root_dir)
        self._cache: dict[Path, Any] = {}
        self._max_ref_depth = max_ref_depth

    # ------------------------------------------------------------------ loading
    def _load(self, path: Path) -> Any:
        path = path.resolve()
        if path not in self._cache:
            if not path.is_file():
                raise SchemaError(f"schema file not found: {path.name}")
            try:
                self._cache[path] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                raise SchemaError(f"schema {path.name} is not valid JSON: {exc}") from exc
        return self._cache[path]

    def load_schema(self, name: str) -> Any:
        """Load a schema by file name (e.g. ``finding.schema.json``)."""
        return self._load(self.root_dir / name)

    def _resolve_ref(self, ref: str, current_file: Path) -> tuple[Any, Path]:
        if ref.startswith(("http://", "https://")):
            raise SchemaError(f"remote $ref is not allowed (offline contract): {ref}")
        file_part, _, fragment = ref.partition("#")
        target_file = (current_file.parent / file_part) if file_part else current_file
        document = self._load(target_file)
        if not fragment:
            return document, target_file
        if not fragment.startswith("/"):
            raise SchemaError(f"unsupported $ref fragment (only JSON pointers): {ref}")
        node = document
        for raw_token in fragment.lstrip("/").split("/"):
            token = raw_token.replace("~1", "/").replace("~0", "~")
            if not isinstance(node, dict) or token not in node:
                raise SchemaError(f"unresolvable $ref: {ref}")
            node = node[token]
        return node, target_file

    # --------------------------------------------------------------- validation
    def validate_file(self, data_path: str | Path, schema_name: str) -> list[ValidationError]:
        raw = Path(data_path).read_text(encoding="utf-8")
        try:
            instance = json.loads(raw)
        except json.JSONDecodeError as exc:
            return [ValidationError("$", "json", f"invalid JSON: {exc}")]
        return self.validate(instance, schema_name)

    def validate(self, instance: Any, schema_name: str) -> list[ValidationError]:
        schema = self.load_schema(schema_name)
        errors: list[ValidationError] = []
        self._validate(instance, schema, "$", self.root_dir / schema_name, errors, 0)
        errors.sort(key=lambda e: (e.path, e.keyword, e.message))
        return errors

    def is_valid(self, instance: Any, schema_name: str) -> bool:
        return not self.validate(instance, schema_name)

    # ------------------------------------------------------------------ internals
    def _validate(
        self,
        instance: Any,
        schema: Any,
        path: str,
        current_file: Path,
        errors: list[ValidationError],
        ref_depth: int,
    ) -> None:
        if schema is True or schema == {}:
            return
        if schema is False:
            errors.append(ValidationError(path, "false", "no value is allowed here"))
            return
        if not isinstance(schema, dict):
            raise SchemaError(f"schema node at {path} must be an object or boolean")

        if "$ref" in schema:
            if ref_depth >= self._max_ref_depth:
                raise SchemaError(f"$ref recursion deeper than {self._max_ref_depth} at {path}")
            target, target_file = self._resolve_ref(schema["$ref"], current_file)
            self._validate(instance, target, path, target_file, errors, ref_depth + 1)

        self._check_annotations(schema, path)

        if "type" in schema:
            types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
            for type_name in types:
                if type_name not in _TYPE_CHECKS:
                    raise SchemaError(f"unknown type {type_name!r} at {path}")
            if not any(_TYPE_CHECKS[t](instance) for t in types):
                expected = "|".join(types)
                errors.append(
                    ValidationError(path, "type", f"expected {expected}, got {type(instance).__name__}")
                )
                # Type mismatch makes the remaining structural keywords meaningless.
                return

        if "const" in schema and instance != schema["const"]:
            errors.append(ValidationError(path, "const", f"must equal {schema['const']!r}"))

        if "enum" in schema and not _enum_contains(schema["enum"], instance):
            errors.append(ValidationError(path, "enum", f"must be one of {sorted(map(str, schema['enum']))}"))

        if isinstance(instance, str):
            self._validate_string(instance, schema, path, errors)
        if isinstance(instance, (int, float)) and not isinstance(instance, bool):
            self._validate_number(instance, schema, path, errors)
        if isinstance(instance, list):
            self._validate_array(instance, schema, path, current_file, errors, ref_depth)
        if isinstance(instance, dict):
            self._validate_object(instance, schema, path, current_file, errors, ref_depth)

        for keyword, subschema in (("allOf", schema.get("allOf")), ("anyOf", schema.get("anyOf")),
                                   ("oneOf", schema.get("oneOf"))):
            if subschema is None:
                continue
            if not isinstance(subschema, list) or not subschema:
                raise SchemaError(f"{keyword} must be a non-empty array at {path}")
            if keyword == "allOf":
                for sub in subschema:
                    self._validate(instance, sub, path, current_file, errors, ref_depth)
                continue
            results = []
            for sub in subschema:
                sub_errors: list[ValidationError] = []
                self._validate(instance, sub, path, current_file, sub_errors, ref_depth)
                results.append(sub_errors)
            matched = [i for i, errs in enumerate(results) if not errs]
            if keyword in ("anyOf", "oneOf") and not matched:
                errors.append(
                    ValidationError(path, keyword, "does not satisfy any allowed shape")
                )
                # Best-effort diagnostics: surface the closest branch so that bounded
                # environment errors (BAD_ARGS) can name the offending field instead of
                # reporting only "no shape matched". Purely diagnostic - never affects
                # the pass/fail verdict.
                best_index = min(range(len(results)), key=lambda i: (len(results[i]), i))
                errors.extend(results[best_index])
            if keyword == "oneOf" and len(matched) > 1:
                errors.append(
                    ValidationError(path, "oneOf", f"ambiguous: matches {len(matched)} shapes")
                )

        if "not" in schema:
            probe: list[ValidationError] = []
            self._validate(instance, schema["not"], path, current_file, probe, ref_depth)
            if not probe:
                errors.append(ValidationError(path, "not", "value matches a forbidden shape"))

        if "if" in schema:
            probe = []
            self._validate(instance, schema["if"], path, current_file, probe, ref_depth)
            branch = "then" if not probe else "else"
            if branch in schema:
                self._validate(instance, schema[branch], path, current_file, errors, ref_depth)

    @staticmethod
    def _check_annotations(schema: dict[str, Any], path: str) -> None:
        unknown = set(schema) - SUPPORTED_KEYWORDS
        if unknown:
            raise SchemaError(
                f"unsupported schema keywords at {path}: {sorted(unknown)} "
                "(extend tools/jsonschema_lite.py deliberately or rewrite the schema)"
            )

    def _validate_string(self, instance: str, schema: dict[str, Any], path: str,
                         errors: list[ValidationError]) -> None:
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(ValidationError(path, "minLength", f"shorter than {schema['minLength']}"))
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(ValidationError(path, "maxLength", f"longer than {schema['maxLength']}"))
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(ValidationError(path, "pattern", f"does not match {schema['pattern']}"))

    @staticmethod
    def _validate_number(instance: float, schema: dict[str, Any], path: str,
                         errors: list[ValidationError]) -> None:
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(ValidationError(path, "minimum", f"less than {schema['minimum']}"))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(ValidationError(path, "maximum", f"greater than {schema['maximum']}"))

    def _validate_array(self, instance: list[Any], schema: dict[str, Any], path: str,
                        current_file: Path, errors: list[ValidationError], ref_depth: int) -> None:
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(ValidationError(path, "minItems", f"fewer than {schema['minItems']} items"))
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(ValidationError(path, "maxItems", f"more than {schema['maxItems']} items"))
        if schema.get("uniqueItems"):
            seen: list[Any] = []
            for item in instance:
                if item in seen:
                    errors.append(ValidationError(path, "uniqueItems", f"duplicate item {item!r}"))
                    break
                seen.append(item)
        if "items" in schema:
            if isinstance(schema["items"], list):
                for index, (item, sub) in enumerate(zip(instance, schema["items"])):
                    self._validate(item, sub, f"{path}/{index}", current_file, errors, ref_depth)
            else:
                for index, item in enumerate(instance):
                    self._validate(item, schema["items"], f"{path}/{index}", current_file, errors, ref_depth)

    def _validate_object(self, instance: dict[str, Any], schema: dict[str, Any], path: str,
                         current_file: Path, errors: list[ValidationError], ref_depth: int) -> None:
        for required_key in schema.get("required", []):
            if required_key not in instance:
                errors.append(ValidationError(path, "required", f"missing required property {required_key!r}"))

        properties = schema.get("properties", {})
        patterns: dict[str, Any] = schema.get("patternProperties", {})
        additional = schema.get("additionalProperties", True)

        for key, value in instance.items():
            child_path = f"{path}/{_json_pointer_escape(key)}"
            matched = False
            if key in properties:
                matched = True
                self._validate(value, properties[key], child_path, current_file, errors, ref_depth)
            for pattern, subschema in patterns.items():
                if re.search(pattern, key):
                    matched = True
                    self._validate(value, subschema, child_path, current_file, errors, ref_depth)
            if not matched:
                if additional is False:
                    errors.append(
                        ValidationError(child_path, "additionalProperties", f"unknown property {key!r}")
                    )
                elif isinstance(additional, dict):
                    self._validate(value, additional, child_path, current_file, errors, ref_depth)

        if "propertyNames" in schema:
            for key in instance:
                self._validate(key, schema["propertyNames"], f"{path}/<name>", current_file, errors, ref_depth)


def _enum_contains(values: Iterable[Any], instance: Any) -> bool:
    """Strict enum membership (exact type match, so ``True`` never equals ``1``)."""
    for value in values:
        if type(value) is type(instance) and value == instance:
            return True
        if value is None and instance is None:
            return True
    return False
