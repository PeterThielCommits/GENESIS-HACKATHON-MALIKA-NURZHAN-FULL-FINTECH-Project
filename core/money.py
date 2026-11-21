"""Money primitives: integer minor units + exact Decimal rates (REQ-MONEY-001..006).

Invariants enforced here:
  * amounts are ``int`` minor units; binary ``float`` is rejected everywhere;
  * ``Decimal`` is always constructed from ``str``;
  * conversion explicitly accounts for the exponent of *both* currencies;
  * every rounding operation is recorded (``RoundingTrace``) so tolerance can be
    derived from real operations instead of a guess (9.2);
  * overflow / invalid magnitude is raised as a bounded ``MoneyError``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import (
    Decimal,
    InvalidOperation,
    Overflow,
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    ROUND_UP,
    localcontext,
)
from pathlib import Path
from typing import Any, Final

from contracts.errors import ConfigError, MoneyError

_ROUNDING_MODES: Final[dict[str, str]] = {
    "ROUND_HALF_EVEN": ROUND_HALF_EVEN,
    "ROUND_HALF_UP": ROUND_HALF_UP,
    "ROUND_DOWN": ROUND_DOWN,
    "ROUND_UP": ROUND_UP,
    "ROUND_CEILING": ROUND_CEILING,
    "ROUND_FLOOR": ROUND_FLOOR,
}
ALLOWED_ROUNDING_MODES: Final[tuple[str, ...]] = tuple(_ROUNDING_MODES)

_DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "contracts" / "currency.json"
_EXPONENT_CACHE: dict[str, int] = {}
_MAX_ABS_MINOR: int = 9007199254740991


def _load_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or _DEFAULT_REGISTRY_PATH
    try:
        with registry_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:  # pragma: no cover - packaging safety
        raise ConfigError("currency registry not found", path=str(registry_path)) from exc
    except json.JSONDecodeError as exc:
        raise ConfigError("currency registry is not valid JSON", reason=str(exc)) from exc
    currencies = data.get("currencies")
    if not isinstance(currencies, dict) or not currencies:
        raise ConfigError("currency registry has no currencies", path=str(registry_path))
    for code, meta in currencies.items():
        if not isinstance(code, str) or len(code) != 3 or not code.isupper():
            raise ConfigError("currency code must be a 3-letter upper-case code", code=repr(code))
        if not isinstance(meta, dict) or not isinstance(meta.get("exponent"), int):
            raise ConfigError("currency entry needs integer exponent", code=code)
        if not 0 <= meta["exponent"] <= 6:
            raise ConfigError("currency exponent out of range", code=code, exponent=meta["exponent"])
    data["default_rounding_mode"] = _validated_mode(
        data.get("default_rounding_mode", "ROUND_HALF_EVEN")
    )
    limit = data.get("max_abs_minor_units", _MAX_ABS_MINOR)
    if not isinstance(limit, int) or limit <= 0:
        raise ConfigError("max_abs_minor_units must be a positive integer")
    return data


def _validated_mode(mode: str) -> str:
    if mode not in _ROUNDING_MODES:
        raise ConfigError(
            "unknown rounding mode",
            mode=mode,
            allowed=list(ALLOWED_ROUNDING_MODES),
        )
    return mode


_REGISTRY: dict[str, Any] = _load_registry()
SUPPORTED_CURRENCIES: Final[tuple[str, ...]] = tuple(sorted(_REGISTRY["currencies"]))
DEFAULT_ROUNDING_MODE: Final[str] = _REGISTRY["default_rounding_mode"]
MAX_ABS_MINOR: Final[int] = _REGISTRY["max_abs_minor_units"]


def exponent_of(currency: str) -> int:
    """Return the ISO-like exponent for a synthetic currency code."""
    if not isinstance(currency, str):
        raise MoneyError("currency must be a string", got=type(currency).__name__)
    if currency in _EXPONENT_CACHE:
        return _EXPONENT_CACHE[currency]
    meta = _REGISTRY["currencies"].get(currency)
    if meta is None:
        raise MoneyError("unsupported currency", currency=currency)
    _EXPONENT_CACHE[currency] = int(meta["exponent"])
    return _EXPONENT_CACHE[currency]


def validate_currency(currency: str) -> str:
    exponent_of(currency)
    return currency


def parse_decimal(value: str | int | Decimal, *, field: str = "value") -> Decimal:
    """Create ``Decimal`` from an exact source; ``float`` is forbidden."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise MoneyError("non-finite Decimal is forbidden", field=field)
        return value
    if isinstance(value, bool):
        raise MoneyError("bool is not a valid decimal source", field=field)
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise MoneyError("empty string is not a valid decimal source", field=field)
        try:
            parsed = Decimal(text)
        except InvalidOperation as exc:
            raise MoneyError("invalid decimal string", field=field, value=value) from exc
        if not parsed.is_finite():
            raise MoneyError("non-finite Decimal is forbidden", field=field, value=value)
        return parsed
    raise MoneyError(
        "decimal source must be str/int/Decimal (float is forbidden)",
        field=field,
        got=type(value).__name__,
    )


def parse_rate(value: str | int | Decimal, *, field: str = "rate") -> Decimal:
    """Parse an FX rate; rates must be strictly positive and exact."""
    rate = parse_decimal(value, field=field)
    if rate <= 0:
        raise MoneyError("rate must be positive", field=field, value=str(rate))
    return rate


def _check_minor(amount: int, *, field: str = "amount_minor") -> int:
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise MoneyError(
            "minor units must be int (float/str forbidden)",
            field=field,
            got=type(amount).__name__,
        )
    if abs(amount) > MAX_ABS_MINOR:
        raise MoneyError(
            "minor units exceed safe range", field=field, limit=MAX_ABS_MINOR
        )
    return amount


def _increment_for(exponent: int) -> Decimal:
    return Decimal(1).scaleb(-exponent)


@dataclass(frozen=True)
class RoundingTrace:
    """Auditable record of one rounding operation (feeds tolerance, 9.2)."""

    input_value: str
    output_value: str
    mode: str
    operations: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_value": self.input_value,
            "output_value": self.output_value,
            "mode": self.mode,
            "operations": self.operations,
        }


@dataclass(frozen=True)
class MoneyResult:
    """Integer minor units plus the rounding metadata that produced them."""

    amount_minor: int
    trace: RoundingTrace

    @property
    def rounding_operations(self) -> int:
        return self.trace.operations

    def to_dict(self) -> dict[str, Any]:
        return {"amount_minor": self.amount_minor, "trace": self.trace.to_dict()}


def to_minor(
    major: str | Decimal,
    currency: str,
    *,
    mode: str | None = None,
) -> MoneyResult:
    """Convert an exact major-unit amount into integer minor units."""
    exponent = exponent_of(currency)
    rounding_mode = _validated_mode(mode or DEFAULT_ROUNDING_MODE)
    value = parse_decimal(major, field="major")
    with localcontext() as ctx:
        ctx.prec = 40
        scaled = value.scaleb(exponent)
        quantised = scaled.quantize(Decimal(1), rounding=_ROUNDING_MODES[rounding_mode])
        operations = 0 if quantised == scaled else 1
        amount = int(quantised)
    _check_minor(amount)
    trace = RoundingTrace(
        input_value=str(value),
        output_value=str(quantised),
        mode=rounding_mode,
        operations=operations,
    )
    return MoneyResult(amount_minor=amount, trace=trace)


def from_minor(amount_minor: int, currency: str) -> Decimal:
    """Render integer minor units as an exact major-unit ``Decimal``."""
    exponent = exponent_of(currency)
    return Decimal(_check_minor(amount_minor)).scaleb(-exponent)


def convert_minor(
    amount_minor: int,
    from_currency: str,
    to_currency: str,
    rate: str | int | Decimal,
    *,
    mode: str | None = None,
    field: str = "amount_minor",
) -> MoneyResult:
    """Convert minor units across currencies honouring both exponents.

    ``rate`` is the price of one ``from_currency`` major unit expressed in
    ``to_currency`` major units.
    """
    amount = _check_minor(amount_minor, field=field)
    exp_from = exponent_of(from_currency)
    exp_to = exponent_of(to_currency)
    fx_rate = parse_rate(rate)
    rounding_mode = _validated_mode(mode or DEFAULT_ROUNDING_MODE)

    with localcontext() as ctx:
        ctx.prec = 60
        try:
            major_from = Decimal(amount).scaleb(-exp_from)
            major_to = major_from * fx_rate
            scaled = major_to.scaleb(exp_to)
            quantised = scaled.quantize(Decimal(1), rounding=_ROUNDING_MODES[rounding_mode])
        except (InvalidOperation, Overflow) as exc:  # pragma: no cover - guarded by checks
            raise MoneyError("conversion failed", reason=str(exc)) from exc
        operations = 0 if quantised == scaled else 1
        result = int(quantised)

    _check_minor(result, field=f"{field}->{to_currency}")
    trace = RoundingTrace(
        input_value=f"{amount} {from_currency} @ {fx_rate}",
        output_value=f"{result} {to_currency}",
        mode=rounding_mode,
        operations=operations,
    )
    return MoneyResult(amount_minor=result, trace=trace)


def add_minor(*amounts: int) -> int:
    """Deterministic integer sum with range checking (no floats, no rounding)."""
    total = 0
    for amount in amounts:
        total = _check_minor(total + _check_minor(amount))
    return total


def sub_minor(left: int, right: int) -> int:
    return _check_minor(_check_minor(left) - _check_minor(right))


def scale_minor(amount_minor: int, quantity: str | Decimal) -> MoneyResult:
    """Multiply a minor amount by an exact quantity, completing to whole units."""
    amount = _check_minor(amount_minor)
    qty = parse_decimal(quantity, field="quantity")
    with localcontext() as ctx:
        ctx.prec = 40
        scaled = Decimal(amount) * qty
        quantised = scaled.quantize(Decimal(1), rounding=_ROUNDING_MODES[DEFAULT_ROUNDING_MODE])
        operations = 0 if quantised == scaled else 1
        result = int(quantised)
    _check_minor(result)
    return MoneyResult(
        amount_minor=result,
        trace=RoundingTrace(
            input_value=f"{amount} * {qty}",
            output_value=str(result),
            mode=DEFAULT_ROUNDING_MODE,
            operations=operations,
        ),
    )


def allocate_minor(total_minor: int, weights: list[int]) -> list[int]:
    """Largest-remainder allocation preserving the exact total (INV-15 helper)."""
    total = _check_minor(total_minor)
    if not weights:
        raise MoneyError("allocation requires at least one weight")
    cleaned = [_check_minor(weight, field="weight") for weight in weights]
    if any(weight < 0 for weight in cleaned):
        raise MoneyError("allocation weights must be non-negative", weights=cleaned)
    weight_sum = sum(cleaned)
    if weight_sum == 0:
        raise MoneyError("allocation weights must not sum to zero")
    base = [total * weight // weight_sum for weight in cleaned]
    remainder = total - sum(base)
    # Deterministic largest-remainder assignment with stable tie-break on index.
    order = sorted(
        range(len(cleaned)),
        key=lambda index: (-(total * cleaned[index] % weight_sum), index),
    )
    for index in order[:remainder]:
        base[index] += 1
    if sum(base) != total:  # pragma: no cover - defensive
        raise MoneyError("allocation did not preserve total")
    return base
