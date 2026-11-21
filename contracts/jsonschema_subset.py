"""Minimal, strict JSON-Schema (2020-12 subset) validator — stdlib only.

Supported keywords: ``$ref`` (local ``#/$defs/...``), ``$defs``, ``type``,
``required``, ``properties``, ``additionalProperties``, ``items``, ``enum``,
``const``, ``minimum``, ``maximum``, ``exclusiveMinimum``, ``exclusiveMaximum``,
``minLength``, ``maxLength``, ``pattern``, ``minItems``, ``maxItems``,
``uniqueItems``, ``allOf``, ``anyOf``, ``oneOf``, ``not``.

Any *unsupported* keyword raises ``ContractError`` instead of being silently
ignored, so a schema can never look stricter than it actually is (this is the
honest alternative to shipping a permissive third-party validator).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Final

from contracts.errors import ContractError

_IGNORED_ANNOTATIONS: Final[frozenset[str]] = frozenset(
    {"$schema", "$id", "title", "description", "examples", "default", "format",
     "x-twinledger-note", "deprecated", "$comment"}
)

_TYPE_CHECKS = {
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "string": lambda value: isinstance(value, str),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
    "null": lambda value: value is None,
}


class SchemaValidator:
    """Validate JSON-like Python values against a schema document."""

    def __init__(
        self,
        schema: dict[str, Any],
        *,
        name: str = "<inline>",
        document: dict[str, Any] | None = None,
    ) -> None:
        if not isinstance(schema, dict):
            raise ContractError("schema must be an object", schema=name)
        self.schema = schema
        self.name = name
        # ``document`` is the schema whose ``$defs`` local $refs resolve against.
        self.document = document if document is not None else schema

    @classmethod
    def from_file(cls, path: str | Path) -> "SchemaValidator":
        schema_path = Path(path)
        try:
            with schema_path.open("r", encoding="utf-8") as handle:
                return cls(json.load(handle), name=schema_path.name)
        except FileNotFoundError as exc:
            raise ContractError("schema file not found", path=str(schema_path)) from exc
        except json.JSONDecodeError as exc:
            raise ContractError("schema file is not valid JSON", path=str(schema_path)) from exc

    def validate(self, value: Any) -> None:
        """Raise ``ContractError`` on the first violation."""
        self._validate(value, self.schema, "$")

    def is_valid(self, value: Any) -> bool:
        try:
            self.validate(value)
        except ContractError:
            return False
        return True

    # ----------------------------------------------------------------- private
    def _resolve(self, ref: str) -> dict[str, Any]:
        if not ref.startswith("#/"):
            raise ContractError("only local $ref is supported", ref=ref, schema=self.name)
        node: Any = self.document
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(node, dict) or part not in node:
                raise ContractError("unresolvable $ref", ref=ref, schema=self.name)
            node = node[part]
        if not isinstance(node, dict):
            raise ContractError("$ref must point to an object", ref=ref)
        return node

    def _validate(self, value: Any, schema: dict[str, Any], path: str) -> None:
        if not isinstance(schema, dict):
            raise ContractError("subschema must be an object", path=path)
        for keyword in schema:
            if (
                keyword in _IGNORED_ANNOTATIONS
                or keyword == "type"
                or keyword
                in {
                    "$ref", "$defs", "required", "properties", "additionalProperties",
                    "items", "enum", "const", "minimum", "maximum", "exclusiveMinimum",
                    "exclusiveMaximum", "minLength", "maxLength", "pattern", "minItems",
                    "maxItems", "uniqueItems", "allOf", "anyOf", "oneOf", "not",
                }
            ):
                continue
            raise ContractError(
                "unsupported JSON-Schema keyword", keyword=keyword, schema=self.name, path=path
            )

        if "$ref" in schema:
            self._validate(value, self._resolve(schema["$ref"]), path)

        if "type" in schema:
            expected = schema["type"]
            options = expected if isinstance(expected, list) else [expected]
            for option in options:
                if option not in _TYPE_CHECKS:
                    raise ContractError("unknown schema type", type=option, path=path)
            if not any(_TYPE_CHECKS[option](value) for option in options):
                raise ContractError(
                    "type mismatch", path=path, expected=options, got=type(value).__name__
                )

        if "const" in schema and value != schema["const"]:
            raise ContractError("const mismatch", path=path, expected=schema["const"])
        if "enum" in schema and value not in schema["enum"]:
            raise ContractError("value not in enum", path=path, allowed=schema["enum"])

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            self._validate_numeric(value, schema, path)
        if isinstance(value, str):
            self._validate_string(value, schema, path)
        if isinstance(value, list):
            self._validate_array(value, schema, path)
        if isinstance(value, dict):
            self._validate_object(value, schema, path)

        for sub in schema.get("allOf", []):
            self._validate(value, sub, path)
        if "anyOf" in schema and not any(self._matches(value, sub, path) for sub in schema["anyOf"]):
            raise ContractError("value matches no anyOf branch", path=path)
        if "oneOf" in schema:
            matches = sum(1 for sub in schema["oneOf"] if self._matches(value, sub, path))
            if matches != 1:
                raise ContractError("value must match exactly one oneOf branch", path=path, matches=matches)
        if "not" in schema and self._matches(value, schema["not"], path):
            raise ContractError("value violates 'not' constraint", path=path)

    def _matches(self, value: Any, schema: dict[str, Any], path: str) -> bool:
        try:
            self._validate(value, schema, path)
        except ContractError:
            return False
        return True

    def _validate_numeric(self, value: int | float, schema: dict[str, Any], path: str) -> None:
        if "minimum" in schema and value < schema["minimum"]:
            raise ContractError("below minimum", path=path, minimum=schema["minimum"])
        if "maximum" in schema and value > schema["maximum"]:
            raise ContractError("above maximum", path=path, maximum=schema["maximum"])
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise ContractError("not above exclusiveMinimum", path=path)
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            raise ContractError("not below exclusiveMaximum", path=path)

    def _validate_string(self, value: str, schema: dict[str, Any], path: str) -> None:
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ContractError("string too short", path=path, minLength=schema["minLength"])
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ContractError("string too long", path=path, maxLength=schema["maxLength"])
        if "pattern" in schema and not re.search(schema["pattern"], value):
            raise ContractError("pattern mismatch", path=path, pattern=schema["pattern"])

    def _validate_array(self, value: list[Any], schema: dict[str, Any], path: str) -> None:
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise ContractError("too few items", path=path, minItems=schema["minItems"])
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ContractError("too many items", path=path, maxItems=schema["maxItems"])
        if schema.get("uniqueItems"):
            seen: set[str] = set()
            for item in value:
                token = json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
                if token in seen:
                    raise ContractError("array items are not unique", path=path)
                seen.add(token)
        if "items" in schema:
            for index, item in enumerate(value):
                self._validate(item, schema["items"], f"{path}[{index}]")

    def _validate_object(self, value: dict[str, Any], schema: dict[str, Any], path: str) -> None:
        for key in schema.get("required", []):
            if key not in value:
                raise ContractError("missing required property", path=path, property=key)
        properties: dict[str, Any] = schema.get("properties", {})
        for key, item in value.items():
            if key in properties:
                self._validate(item, properties[key], f"{path}.{key}")
                continue
            additional = schema.get("additionalProperties", True)
            if additional is False:
                raise ContractError("unexpected property", path=path, property=key)
            if isinstance(additional, dict):
                self._validate(item, additional, f"{path}.{key}")


def load_validator(contracts_dir: str | Path, schema_name: str) -> SchemaValidator:
    return SchemaValidator.from_file(Path(contracts_dir) / schema_name)
