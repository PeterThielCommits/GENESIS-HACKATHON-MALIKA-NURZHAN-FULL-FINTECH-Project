"""Clean twin assembly (Phase 3 pipeline G1..G8).

``build_clean_book`` is deterministic on ``(master_seed, config, difficulty)``:
identical inputs produce byte-identical public files (REQ-PROD-001).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from contracts.errors import ConfigError
from core.ids import IdFactory, style_for_config
from core.time_rules import PeriodCalendar, load_zone
from gen.config import GeneratorConfig
from gen.core.company import CompanyContext, build_company_context
from gen.core.fx import FxTimeline, generate_fx_timeline
from gen.core.history import HistoryBuilder, HistoryBundle
from gen.core.reference import bank_name
from gen.core.rng import RngService
from gen.core.text import TextFactory
from gen.twins import Book, build_book
from invariants.checks_clean import check_all
from invariants.model import Violation

GENERATOR_VERSION = "1.0.0"


@dataclass(frozen=True)
class CleanBuild:
    """Result of clean-twin generation, including a private provenance skeleton."""

    book: Book
    context: CompanyContext
    fx: FxTimeline
    history: HistoryBundle
    calendar: PeriodCalendar
    rng: RngService
    config: GeneratorConfig
    master_seed_digest: str
    difficulty: str
    violations: tuple[Violation, ...]

    @property
    def clean(self) -> bool:
        return not self.violations


def build_clean_book(
    *,
    master_seed: str,
    config: GeneratorConfig,
    difficulty: str = "L1",
) -> CleanBuild:
    """Generate the clean twin for one seed/config/profile."""
    if not isinstance(master_seed, str) or not master_seed:
        raise ConfigError("master_seed must be a non-empty string")
    config.validate()
    profile = config.profile(difficulty)

    rng = RngService(master_seed=master_seed)
    history_cfg = config.raw["history"]
    start_year = int(history_cfg["start_year"])
    start_month = int(history_cfg["start_month"])
    months = int(history_cfg["months"])

    context = build_company_context(rng, config)
    calendar = PeriodCalendar(
        timezone_name=context.company["timezone"],
        period_rule=context.company["fiscal_calendar"]["period_rule"],
        fiscal_year_start_month=context.company["fiscal_calendar"]["fiscal_year_start_month"],
        fiscal_year_start_day=context.company["fiscal_calendar"]["fiscal_year_start_day"],
        cutoff_day_offset=context.company["fiscal_calendar"]["cutoff_day_offset"],
        ambiguity_policy=context.company["fiscal_calendar"]["ambiguity_policy"],
    )

    first_day = date(start_year, start_month, 1)
    last_day = _end_of_range(first_day, months)
    fx_cfg = config.raw["fx"]
    fx = generate_fx_timeline(
        rng,
        pairs=list(fx_cfg["pairs"]),
        base_rate_scaled=dict(fx_cfg["base_rate_scaled"]),
        noise_amplitude_scaled=dict(fx_cfg["noise_amplitude_scaled"]),
        mean_reversion_numerator=int(fx_cfg["mean_reversion_numerator"]),
        mean_reversion_denominator=int(fx_cfg["mean_reversion_denominator"]),
        scale=int(fx_cfg["rate_scale"]),
        sources=list(fx_cfg["sources"]),
        weekend_publication=bool(fx_cfg["weekend_publication"]),
        first_day=first_day - timedelta(days=14),
        last_day=last_day + timedelta(days=45),
    )

    id_style = style_for_config(context.company["id_style"])
    ids = IdFactory(style=id_style, rng=rng.stream("ids/records"), year=start_year)
    text = TextFactory(rng, context.company["text_profile"])

    builder = HistoryBuilder(
        rng=rng,
        config=config,
        context=context,
        fx=fx,
        ids=ids,
        calendar=calendar,
        text=text,
        difficulty=difficulty,
    )
    bundle = builder.build()

    company = dict(context.company)
    company["bank"] = {
        "bank_name": bank_name(rng.stream("chart")),
        "bank_account_marker": context.bank_account_marker,
        "synthetic": True,
    }

    book = build_book(
        company=company,
        policy=context.policy,
        accounts=context.accounts,
        counterparties=context.counterparties,
        journal_entries=bundle.journal_entries,
        invoices=bundle.invoices,
        credit_notes=bundle.credit_notes,
        payments=bundle.payments,
        bank_lines=bundle.bank_lines,
        fx_rates=_fx_rows(fx),
        opening_balances=bundle.opening_balances,
        period_calendar=bundle.period_calendar,
    )

    violations = tuple(check_all(book))
    return CleanBuild(
        book=book,
        context=context,
        fx=fx,
        history=bundle,
        calendar=calendar,
        rng=rng,
        config=config,
        master_seed_digest=_digest_seed(master_seed),
        difficulty=difficulty,
        violations=violations,
    )


def _fx_rows(fx: FxTimeline):
    from contracts.models import FxRate

    rows = []
    from datetime import datetime, time, timezone

    for point in fx.points:
        publication = datetime.combine(point.effective_date, time(12, 0, 0), tzinfo=timezone.utc)
        rows.append(
            FxRate(
                pair=point.pair,
                effective_date=point.effective_date.isoformat(),
                rate_decimal=point.rate_decimal,
                source_code=point.source_code,
                publication_timestamp=publication.isoformat(timespec="seconds"),
            )
        )
    return rows


def _digest_seed(master_seed: str) -> str:
    import hashlib

    return hashlib.sha256(master_seed.encode("utf-8")).hexdigest()


def _end_of_range(first_day: date, months: int) -> date:
    total = (first_day.year * 12 + (first_day.month - 1)) + max(1, months)
    year, month = total // 12, total % 12 + 1
    if month == 12:
        return date(year, 12, 31)
    return date(year, month, 1) - timedelta(days=1)
