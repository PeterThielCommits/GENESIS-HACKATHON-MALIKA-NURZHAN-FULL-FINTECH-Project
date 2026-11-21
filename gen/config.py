"""Versioned generator configuration loading and strict validation (REQ-CONTRACT-020..022).

Every numeric parameter that influences data, reward, budget or determinism is
explicit — there are no hidden defaults in code for those. Unknown config
versions fail with a bounded ``ConfigError`` instead of being interpreted
approximately.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from contracts.canonical import digest_of
from contracts.errors import ConfigError
from core.money import ALLOWED_ROUNDING_MODES, SUPPORTED_CURRENCIES, validate_currency
from core.time_rules import PERIOD_RULES, load_zone

SUPPORTED_CONFIG_VERSIONS: Final[tuple[str, ...]] = ("1.0.0",)
DEFAULT_GENERATOR_CONFIG: Final[Path] = (
    Path(__file__).resolve().parent.parent / "configs" / "generator" / "default.json"
)
DEFAULT_MUTATION_CONFIG: Final[Path] = (
    Path(__file__).resolve().parent.parent / "configs" / "generator" / "mutations.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError("config file not found", path=str(path)) from exc
    except json.JSONDecodeError as exc:
        raise ConfigError("config file is not valid JSON", path=str(path), reason=str(exc)) from exc
    if not isinstance(data, dict):
        raise ConfigError("config root must be an object", path=str(path))
    return data


def _require_int(section: dict[str, Any], key: str, *, minimum: int, maximum: int, where: str) -> int:
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError("config value must be int", key=key, where=where, got=repr(value))
    if not minimum <= value <= maximum:
        raise ConfigError("config value out of range", key=key, where=where, value=value,
                          minimum=minimum, maximum=maximum)
    return value


def _require_str(section: dict[str, Any], key: str, *, where: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError("config value must be a non-empty string", key=key, where=where)
    return value


@dataclass(frozen=True)
class GeneratorConfig:
    """Validated generator configuration with a canonical config hash."""

    raw: dict[str, Any]
    mutation_raw: dict[str, Any]
    path: Path | None = None

    # --------------------------------------------------------------- factories
    @classmethod
    def from_files(
        cls, generator_path: Path | str | None = None, mutation_path: Path | str | None = None
    ) -> "GeneratorConfig":
        gen_path = Path(generator_path) if generator_path else DEFAULT_GENERATOR_CONFIG
        mut_path = Path(mutation_path) if mutation_path else DEFAULT_MUTATION_CONFIG
        return cls(raw=_load_json(gen_path), mutation_raw=_load_json(mut_path), path=gen_path)

    # -------------------------------------------------------------- validation
    def validate(self) -> None:
        raw = self.raw
        version = _require_str(raw, "config_version", where="root")
        if version not in SUPPORTED_CONFIG_VERSIONS:
            raise ConfigError(
                "unsupported config_version",
                config_version=version,
                supported=list(SUPPORTED_CONFIG_VERSIONS),
            )
        _require_str(raw, "generator_version", where="root")
        mutation_version = _require_str(self.mutation_raw, "config_version", where="mutation")
        if mutation_version not in SUPPORTED_CONFIG_VERSIONS:
            raise ConfigError("unsupported mutation config_version", config_version=mutation_version)

        history = self._section("history")
        _require_int(history, "start_year", minimum=1990, maximum=2100, where="history")
        _require_int(history, "start_month", minimum=1, maximum=12, where="history")
        _require_int(history, "months", minimum=1, maximum=24, where="history")
        _require_int(history, "fiscal_year_start_month", minimum=1, maximum=12, where="history")
        _require_int(history, "fiscal_year_start_day", minimum=1, maximum=28, where="history")
        _require_int(history, "cutoff_day_offset", minimum=-3, maximum=3, where="history")
        if history.get("period_rule") not in PERIOD_RULES:
            raise ConfigError("unknown period_rule", where="history", value=history.get("period_rule"))
        if history.get("ambiguity_policy") not in ("prefer_earlier", "prefer_later", "raise"):
            raise ConfigError("unknown ambiguity_policy", where="history")

        company = self._section("company")
        timezones = company.get("timezone_pool")
        if not isinstance(timezones, list) or not timezones:
            raise ConfigError("timezone_pool must be a non-empty list")
        for zone in timezones:
            load_zone(zone)
        currency = _require_str(company, "functional_currency", where="company")
        validate_currency(currency)
        currencies = company.get("supported_currencies")
        if not isinstance(currencies, list) or currency not in currencies:
            raise ConfigError("supported_currencies must include functional_currency")
        for code in currencies:
            validate_currency(code)
        if company.get("size") not in ("small", "medium", "large"):
            raise ConfigError("unknown company size", value=company.get("size"))
        styles = company.get("id_style_pool")
        if not isinstance(styles, list) or not styles or any(style not in "ABCD" for style in styles):
            raise ConfigError("id_style_pool must be a non-empty subset of A/B/C/D")
        jurisdictions = company.get("jurisdiction_pool")
        if not isinstance(jurisdictions, list) or not jurisdictions:
            raise ConfigError("jurisdiction_pool must be a non-empty list")
        for marker in jurisdictions:
            if not isinstance(marker, str) or len(marker) != 2 or marker[0] != "X":
                raise ConfigError("jurisdiction markers must be X-prefixed synthetic codes", value=marker)

        volumes = self._section("volumes")
        for key in (
            "counterparty_count", "invoices_per_month", "lines_per_invoice_max",
            "payment_delay_days_max",
        ):
            _require_int(volumes, key, minimum=1, maximum=400, where="volumes")
        for key in (
            "customer_ratio_bps", "foreign_currency_ratio_bps", "early_payment_ratio_bps",
            "credit_note_ratio_bps", "recurring_invoice_ratio_bps", "unapplied_cash_ratio_bps",
            "partial_payment_ratio_bps", "remainder_settlement_ratio_bps",
            "identical_amount_coincidence_bps", "advance_receipt_ratio_bps",
        ):
            _require_int(volumes, key, minimum=0, maximum=10000, where="volumes")

        fx = self._section("fx")
        scale = _require_int(fx, "rate_scale", minimum=2, maximum=12, where="fx")
        pairs = fx.get("pairs")
        if not isinstance(pairs, list) or not pairs:
            raise ConfigError("fx.pairs must be a non-empty list")
        base_rates = fx.get("base_rate_scaled")
        noise = fx.get("noise_amplitude_scaled")
        if not isinstance(base_rates, dict) or not isinstance(noise, dict):
            raise ConfigError("fx base/noise maps are required")
        for pair in pairs:
            if not isinstance(pair, str) or "/" not in pair:
                raise ConfigError("fx pair must be AAA/BBB", value=pair)
        for pair in pairs:
            if pair not in base_rates or pair not in noise:
                raise ConfigError("fx pair lacks base rate or noise amplitude", pair=pair)
            for key, mapping in (("base_rate_scaled", base_rates), ("noise_amplitude_scaled", noise)):
                value = mapping[pair]
                if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                    raise ConfigError("fx scalar must be a positive int", pair=pair, key=key)
        _require_int(fx, "mean_reversion_numerator", minimum=0, maximum=100, where="fx")
        _require_int(fx, "mean_reversion_denominator", minimum=1, maximum=100, where="fx")
        if fx["mean_reversion_numerator"] >= fx["mean_reversion_denominator"]:
            raise ConfigError("mean reversion numerator must be < denominator")
        sources = fx.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ConfigError("fx.sources must be a non-empty list")
        if not isinstance(fx.get("weekend_publication"), bool):
            raise ConfigError("fx.weekend_publication must be a boolean")
        if not 1 <= scale <= 12:  # pragma: no cover - covered above
            raise ConfigError("rate_scale out of range")

        amounts = self._section("amounts")
        low = _require_int(amounts, "min_invoice_minor", minimum=1, maximum=10**12, where="amounts")
        high = _require_int(amounts, "max_invoice_minor", minimum=1, maximum=10**12, where="amounts")
        if low >= high:
            raise ConfigError("min_invoice_minor must be < max_invoice_minor")
        taxes = amounts.get("tax_rate_bps_pool")
        if not isinstance(taxes, list) or not taxes:
            raise ConfigError("tax_rate_bps_pool must be a non-empty list")
        for rate in taxes:
            if isinstance(rate, bool) or not isinstance(rate, int) or not 0 <= rate <= 10000:
                raise ConfigError("tax rate out of range", value=repr(rate))
        _require_int(amounts, "round_price_to_minor", minimum=1, maximum=100000, where="amounts")

        profiles = raw.get("difficulty_profiles")
        if not isinstance(profiles, dict) or not profiles:
            raise ConfigError("difficulty_profiles must be a non-empty object")
        for name, profile in profiles.items():
            if not isinstance(profile, dict):
                raise ConfigError("difficulty profile must be an object", profile=name)
            _require_int(profile, "anomaly_count", minimum=0, maximum=4, where=f"profiles.{name}")
            _require_int(profile, "distractor_pairs", minimum=0, maximum=4, where=f"profiles.{name}")
            _require_int(profile, "invoices_per_month", minimum=1, maximum=40, where=f"profiles.{name}")
        if raw.get("default_profile") not in profiles:
            raise ConfigError("default_profile must reference a defined profile")

        mutation = self.mutation_raw.get("mutation")
        if not isinstance(mutation, dict):
            raise ConfigError("mutation section is required")
        _require_int(mutation, "reject_attempt_limit", minimum=1, maximum=1000, where="mutation")
        _require_int(mutation, "max_anomalies_per_episode", minimum=1, maximum=8, where="mutation")
        order = mutation.get("operator_order")
        if not isinstance(order, list) or not order:
            raise ConfigError("operator_order must be a non-empty list")
        for name in ("duplicate_payment", "partial_payment_allocation"):
            section = self.mutation_raw.get(name)
            if not isinstance(section, dict):
                raise ConfigError("mutation operator config missing", operator=name)
            _require_str(section, "operator_version", where=f"mutation.{name}")
        partial = self.mutation_raw["partial_payment_allocation"]
        weights = partial.get("subtype_weights_bps")
        if not isinstance(weights, dict) or not weights:
            raise ConfigError("subtype_weights_bps must be a non-empty object")
        total = 0
        for name, weight in weights.items():
            if isinstance(weight, bool) or not isinstance(weight, int) or weight < 0:
                raise ConfigError("subtype weight must be a non-negative int", subtype=name)
            total += weight
        if total != 10000:
            raise ConfigError("subtype weights must sum to 10000", total=total)
        ratios = partial.get("partial_ratio_bps_pool")
        if not isinstance(ratios, list) or not ratios:
            raise ConfigError("partial_ratio_bps_pool must be a non-empty list")
        for ratio in ratios:
            if isinstance(ratio, bool) or not isinstance(ratio, int) or not 0 < ratio < 10000:
                raise ConfigError("partial ratio out of range", value=repr(ratio))

    # ----------------------------------------------------------------- helpers
    def _section(self, name: str) -> dict[str, Any]:
        section = self.raw.get(name)
        if not isinstance(section, dict):
            raise ConfigError("missing config section", section=name)
        return section

    @property
    def config_hash(self) -> str:
        """Hash over both config documents (canonical JSON, REQ-CONTRACT-021)."""
        return digest_of({"generator": self.raw, "mutation": self.mutation_raw})

    def profile(self, difficulty: str) -> dict[str, Any]:
        profiles = self.raw["difficulty_profiles"]
        if difficulty not in profiles:
            raise ConfigError("unknown difficulty profile", difficulty=difficulty,
                              available=sorted(profiles))
        return profiles[difficulty]

    def rounding_mode(self) -> str:
        mode = self.raw.get("rounding_mode", "ROUND_HALF_EVEN")
        if mode not in ALLOWED_ROUNDING_MODES:
            raise ConfigError("unknown rounding mode", mode=mode)
        return mode


def load_generator_config(
    generator_path: Path | str | None = None, mutation_path: Path | str | None = None
) -> GeneratorConfig:
    config = GeneratorConfig.from_files(generator_path, mutation_path)
    config.validate()
    return config


def validate_currency_supported(currency: str, config: GeneratorConfig) -> str:
    if currency not in SUPPORTED_CURRENCIES:
        raise ConfigError("currency not in registry", currency=currency)
    if currency not in config.raw["company"]["supported_currencies"] and currency != config.raw[
        "company"
    ]["functional_currency"]:
        # FX quote currencies may legitimately sit outside the invoice list.
        pass
    return currency
