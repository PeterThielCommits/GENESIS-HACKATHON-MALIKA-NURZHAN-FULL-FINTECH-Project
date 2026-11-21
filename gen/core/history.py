"""Clean history construction: invoices, payments, credit notes, bank lines, JEs.

Phase 3.4/3.6. Every row is built so that the *entire* invariant suite passes for
the clean twin. Design decisions that keep the clean twin provably balanced:

* Recognition JE: receivable D / revenue C in functional currency, recognition
  date = ``service_start`` (policy ``recognition_rule``).
* Payment JE: bank D / receivable C at the actual settlement date, using the
  policy rate for the payment date (an FX difference is booked to the equity-like
  FX gain/loss account) — the receivable is therefore relieved at the *original*
  functional amount, which is what keeps INV-03 exact and INV-08 recomputable.
* Credit note JE: revenue D / receivable C at the recognition date.
* FX conversions always go through ``core.money.convert_minor`` (integer minor
  units, Decimal rates, explicit rounding trace).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Sequence

from contracts.errors import ConfigError
from contracts.models import (
    Allocation,
    BankLine,
    CreditNote,
    Invoice,
    InvoiceLine,
    JournalEntry,
    JournalLine,
    Payment,
)
from core.ids import IdFactory
from core.money import convert_minor
from core.time_rules import (
    PeriodCalendar,
    format_timestamp,
    load_zone,
    parse_timestamp,
    resolve_local_wall_time,
)
from gen.config import GeneratorConfig
from gen.core.company import CompanyContext
from gen.core.fx import FxTimeline
from gen.core.rng import RngService
from gen.core.text import TextFactory

BUSINESS_START_HOUR = 9
BUSINESS_END_HOUR = 17
UNALLOCATED_BANK_TOKEN = "UNAPPLIED CASH"


@dataclass
class HistoryBundle:
    journal_entries: list[JournalEntry]
    invoices: list[Invoice]
    credit_notes: list[CreditNote]
    payments: list[Payment]
    bank_lines: list[BankLine]
    opening_balances: dict[str, Any]
    period_calendar: dict[str, Any]


@dataclass(frozen=True)
class DocumentPlan:
    """A business document before its journal entry is produced."""

    invoice: Invoice
    recognition_day: date


class HistoryBuilder:
    """Builds the clean twin history for a fixed seed/config."""

    def __init__(
        self,
        *,
        rng: RngService,
        config: GeneratorConfig,
        context: CompanyContext,
        fx: FxTimeline,
        ids: IdFactory,
        calendar: PeriodCalendar,
        text: TextFactory,
        difficulty: str,
    ) -> None:
        self.rng = rng
        self.config = config
        self.context = context
        self.fx = fx
        self.ids = ids
        self.calendar = calendar
        self.text = text
        self.difficulty = difficulty
        self.zone = load_zone(context.company["timezone"])
        self.functional = str(context.company["functional_currency"])
        self.history_stream = rng.stream("history/ordering")
        self._subscriptions: list[str] = []
        self._totals_seen: dict[tuple[str, int], str] = {}

    # ------------------------------------------------------------------ public
    def build(self) -> HistoryBundle:
        history_cfg = self.config.raw["history"]
        volumes = self.config.raw["volumes"]
        profile = self.config.profile(self.difficulty)
        invoices_per_month = int(profile["invoices_per_month"])

        start_year = int(history_cfg["start_year"])
        start_month = int(history_cfg["start_month"])
        months = int(history_cfg["months"])

        journal_entries: list[JournalEntry] = []
        invoices: list[Invoice] = []
        credit_notes: list[CreditNote] = []
        payments: list[Payment] = []
        bank_lines: list[BankLine] = []

        customers = [cp for cp in self.context.counterparties if cp.category in ("CUSTOMER", "BOTH")]
        if not customers:  # pragma: no cover - config guarantees at least one customer
            raise ConfigError("no customer counterparty available")

        for month_offset in range(months):
            year, month = _add_months(start_year, start_month, month_offset)
            month_stream = self.rng.stream(f"history/{year}-{month:02d}/invoices")
            month_docs = int(invoices_per_month)
            # A subscription series is sticky: once a recurring relationship exists,
            # the next month bills the *same* customer for the next period. That is
            # also the natural distractor for a duplicated charge (D-DUP-03).
            recurring = bool(self._subscriptions) and month_stream.ratio_hit(7000)
            if not recurring and len(invoices) > 0 and month_stream.ratio_hit(
                int(volumes["recurring_invoice_ratio_bps"])
            ):
                recurring = True
            for index in range(month_docs):
                day = month_stream.randint(1, 24)
                if recurring and self._subscriptions:
                    customer_id = self._subscriptions[0]
                    customer = next(
                        cp for cp in customers if cp.counterparty_id == customer_id
                    )
                else:
                    customer = customers[month_stream.randint(0, len(customers) - 1)]
                plan = self._plan_invoice(
                    year=year,
                    month=month,
                    day=day,
                    customer_id=customer.counterparty_id,
                    recurring=recurring and index == 0,
                    stream=month_stream,
                )
                if recurring:
                    if customer.counterparty_id not in self._subscriptions:
                        self._subscriptions.append(customer.counterparty_id)
                    self._subscriptions = self._subscriptions[:1]
                invoices.append(plan.invoice)
                journal_entries.append(self._recognition_entry(plan))

                credit = self._maybe_credit_note(plan, month_stream)
                credited_minor = 0
                if credit is not None:
                    credit_notes.append(credit[0])
                    journal_entries.append(credit[1])
                    credited_minor = credit[0].amount_minor

                for payment, je, bank in self._month_payments(plan, month_stream, credited_minor):
                    payments.append(payment)
                    if je is not None:
                        journal_entries.append(je)
                    if bank is not None:
                        bank_lines.append(bank)

        # A small amount of unapplied cash keeps BANK_MATCH honest (UNMATCHED).
        bank_lines.extend(self._unapplied_cash_lines(bank_lines, start_year, start_month, months))

        # Customer advances: cash received before invoicing, booked to the advance
        # account. This is the policy-sanctioned look-alike of a mis-allocated
        # partial payment (distractor D-PART-02).
        advance_entries, advance_lines = self._advance_receipts(
            customers, start_year, start_month, months
        )
        journal_entries.extend(advance_entries)
        bank_lines.extend(advance_lines)

        invoices = list(
            _apply_statuses(invoices, payments, credit_notes)
        )

        debit_total = sum(entry.functional_debit_total for entry in journal_entries)
        credit_total = sum(entry.functional_credit_total for entry in journal_entries)
        if debit_total != credit_total:  # pragma: no cover - structural safety net
            raise ConfigError(
                "clean history is not balanced",
                functional_debit=debit_total,
                functional_credit=credit_total,
            )

        opening_balances = {
            "as_of": _first_day(start_year, start_month).isoformat(),
            "currency": self.functional,
            "accounts": [
                {"account_id": account.account_id, "balance_minor": 0}
                for account in sorted(self.context.accounts, key=lambda item: item.code)
            ],
        }
        period_calendar = {
            **self.calendar.describe(),
            "periods": sorted({
                self.calendar.posting_period(_invoice_moment(invoice))
                for invoice in invoices
            }),
        }
        return HistoryBundle(
            journal_entries=journal_entries,
            invoices=invoices,
            credit_notes=credit_notes,
            payments=payments,
            bank_lines=bank_lines,
            opening_balances=opening_balances,
            period_calendar=period_calendar,
        )

    # --------------------------------------------------------------- documents
    def _plan_invoice(
        self,
        *,
        year: int,
        month: int,
        day: int,
        customer_id: str,
        recurring: bool,
        stream,
    ) -> DocumentPlan:
        volumes = self.config.raw["volumes"]
        amounts = self.config.raw["amounts"]
        issue_day = date(year, month, min(day, _days_in_month(year, month)))
        issue_moment = resolve_local_wall_time(
            issue_day,
            time(stream.randint(BUSINESS_START_HOUR, BUSINESS_END_HOUR), stream.randint(0, 59), 0),
            self.zone,
            self.calendar.ambiguity_policy,
        )
        terms = stream.choice((14, 30, 45, 60))
        due_day = issue_day + timedelta(days=int(terms))
        due_moment = resolve_local_wall_time(due_day, time(12, 0, 0), self.zone,
                                            self.calendar.ambiguity_policy)

        foreign = stream.ratio_hit(int(volumes["foreign_currency_ratio_bps"]))
        supported = [
            code for code in self.context.company["supported_currencies"] if code != self.functional
        ]
        currency = str(stream.choice(supported)) if foreign and supported else self.functional

        line_count = stream.randint(1, int(volumes["lines_per_invoice_max"]))
        language = str(stream.choice(("en", "ru", "kk")))
        total_minor = 0
        line_items: list[InvoiceLine] = []
        round_to = int(amounts["round_price_to_minor"])
        min_total = int(amounts["min_invoice_minor"])
        max_total = int(amounts["max_invoice_minor"])
        for _ in range(line_count):
            raw_amount = stream.randint(min_total // line_count, max_total // line_count)
            amount_minor = max(round_to, raw_amount // round_to * round_to)
            line_items.append(
                InvoiceLine(
                    line_id=self.ids.new("line_items"),
                    description=self.text.service_description(language, 0),
                    quantity_decimal=Decimal(stream.randint(1, 12)),
                    unit_price_minor=amount_minor,
                    amount_minor=amount_minor,
                    service_reference=None,
                )
            )
            total_minor += amount_minor

        tax_bps = int(stream.choice(self.config.raw["amounts"]["tax_rate_bps_pool"]))
        tax_minor = total_minor * tax_bps // 10000
        total_minor_with_tax = total_minor + tax_minor

        # A natural coincidence: the same document total recurs for a *different*
        # counterparty. Naive amount matching flags it; the correct answer is "two
        # unrelated invoices" (distractor D-DUP-02).
        if stream.ratio_hit(int(self.config.raw["volumes"]["identical_amount_coincidence_bps"])):
            for (seen_currency, seen_total), seen_customer in sorted(self._totals_seen.items()):
                if seen_currency != currency or seen_customer == customer_id:
                    continue
                if tax_minor:
                    continue  # taxed documents keep the auditable tax split intact
                delta = seen_total - total_minor_with_tax
                last = line_items[-1]
                adjusted = last.amount_minor + delta
                if adjusted <= 0:
                    continue
                line_items[-1] = InvoiceLine(
                    line_id=last.line_id,
                    description=last.description,
                    quantity_decimal=last.quantity_decimal,
                    unit_price_minor=adjusted,
                    amount_minor=adjusted,
                    service_reference=last.service_reference,
                )
                total_minor_with_tax = seen_total
                break
        self._totals_seen.setdefault((currency, total_minor_with_tax), customer_id)

        service_start = issue_moment
        service_end: datetime | None = (
            None
            if recurring
            else resolve_local_wall_time(
                issue_day + timedelta(days=stream.randint(1, 20)),
                time(18, 0, 0),
                self.zone,
                self.calendar.ambiguity_policy,
            )
        )
        doc_id = self.ids.new("invoices")
        invoice = Invoice(
            doc_id=doc_id,
            counterparty_id=customer_id,
            issue_timestamp=format_timestamp(issue_moment),
            service_start=format_timestamp(service_start),
            service_end=None if service_end is None else format_timestamp(service_end),
            due_timestamp=format_timestamp(due_moment),
            currency=currency,
            total_minor=total_minor_with_tax,
            tax_minor=tax_minor,
            line_items=tuple(line_items),
            status="OPEN",
        )
        # The policy rate basis is the *company-local* document date, which is what
        # the verifier recomputes; never the UTC date of the timestamp.
        return DocumentPlan(
            invoice=invoice,
            recognition_day=self.calendar.effective_date(issue_moment),
        )

    def _recognition_entry(self, plan: DocumentPlan) -> JournalEntry:
        invoice = plan.invoice
        moment = _invoice_moment(invoice)
        rate = self._rate(invoice.currency, plan.recognition_day)
        functional_total = self._to_functional(invoice.total_minor, invoice.currency, rate)
        lines = [
            self._line(
                account_id=str(self.context.policy["receivable_account_id"]),
                currency=invoice.currency,
                debit=invoice.total_minor,
                rate=rate,
                counterparty_id=invoice.counterparty_id,
                analytic_tag=invoice.doc_id,
            ),
            self._line(
                account_id=str(self.context.policy["revenue_account_id"]),
                currency=invoice.currency,
                credit=invoice.total_minor,
                rate=rate,
                counterparty_id=invoice.counterparty_id,
                analytic_tag=invoice.doc_id,
            ),
        ]
        if sum(line.functional_debit_minor for line in lines) != functional_total:
            raise ConfigError("recognition functional amount mismatch")  # pragma: no cover
        return JournalEntry(
            je_id=self.ids.new("journal_entries", month=moment.month),
            timestamp=format_timestamp(moment),
            posting_period=self.calendar.posting_period(moment),
            source_document_id=invoice.doc_id,
            description=self.text.journal_description("invoice", invoice.doc_id),
            lines=tuple(lines),
        )

    def _month_payments(self, plan, stream, credited_minor: int):  # noqa: ANN001, ANN201
        """A partial payment followed by the settlement of the remainder.

        Realistic settlement cycles matter for Phase 4: an invoice carrying two
        settlements is what makes a "close the document with the gross amount"
        allocation mistake observable from public data.
        """
        first = self._maybe_payment(plan, stream, credited_minor)
        if first[0] is None:
            return [first]
        payment = first[0]
        outstanding = plan.invoice.total_minor - credited_minor - payment.allocated_minor
        if outstanding <= 0:
            return [first]
        # Most partial payments are settled later by a second transfer; the rest
        # leave a legitimately open balance (realistic AR).
        if not stream.ratio_hit(int(self.config.raw["volumes"]["remainder_settlement_ratio_bps"])):
            return [first]
        second = self._settle_remainder(plan, stream, payment, outstanding)
        return [first, second]

    def _settle_remainder(self, plan, stream, previous, outstanding: int):  # noqa: ANN001, ANN201
        invoice = plan.invoice
        previous_moment = parse_timestamp(previous.timestamp)
        pay_moment = previous_moment + timedelta(days=stream.randint(3, 25))
        pay_moment = pay_moment.replace(
            hour=stream.randint(BUSINESS_START_HOUR, BUSINESS_END_HOUR),
            minute=stream.randint(0, 59),
            second=0,
        )
        pay_id = self.ids.new("payments")
        rate = self._rate(invoice.currency, plan.recognition_day)
        allocation = Allocation(
            allocation_id=self.ids.new("allocations"),
            document_id=invoice.doc_id,
            amount_minor=outstanding,
            allocation_timestamp=format_timestamp(pay_moment),
        )
        bank_line = BankLine(
            bank_line_id=self.ids.new("bank_lines"),
            timestamp=format_timestamp(pay_moment),
            amount_minor=outstanding,
            currency=invoice.currency,
            direction="IN",
            reference_text=self.text.bank_reference(pay_id, invoice.counterparty_id),
            matched_payment_id=pay_id,
            bank_account_id=self.context.account_id_for_role("bank"),
            status="MATCHED",
        )
        payment = Payment(
            pay_id=pay_id,
            timestamp=format_timestamp(pay_moment),
            counterparty_id=invoice.counterparty_id,
            currency=invoice.currency,
            amount_minor=outstanding,
            functional_amount_minor=self._to_functional(outstanding, invoice.currency, rate),
            fx_rate_decimal=rate,
            allocations=(allocation,),
            bank_reference=bank_line.bank_line_id,
            payment_channel=str(stream.choice(("WIRE", "ACH"))),
        )
        entry = self._payment_entry(payment, invoice, pay_moment, rate)
        return payment, entry, bank_line

    def _maybe_credit_note(self, plan: DocumentPlan, stream) -> tuple[CreditNote, JournalEntry] | None:
        volumes = self.config.raw["volumes"]
        if not stream.ratio_hit(int(volumes["credit_note_ratio_bps"])):
            return None
        invoice = plan.invoice
        cap_bps = int(self.context.policy["credit_note_cap_bps"])
        max_amount = invoice.total_minor * cap_bps // 10000
        if max_amount < 100:
            return None
        amount = max(100, stream.randint(100, max_amount) // 100 * 100)
        moment = _invoice_moment(invoice) + timedelta(days=stream.randint(1, 5))
        moment = moment.replace(
            hour=stream.randint(BUSINESS_START_HOUR, BUSINESS_END_HOUR),
            minute=stream.randint(0, 59),
        )
        note = CreditNote(
            credit_note_id=self.ids.new("credit_notes"),
            invoice_id=invoice.doc_id,
            counterparty_id=invoice.counterparty_id,
            timestamp=format_timestamp(moment),
            amount_minor=amount,
            currency=invoice.currency,
            reason_code=str(stream.choice(
                ("PRICE_ADJUSTMENT", "SERVICE_SHORTFALL", "GOODWILL", "BILLING_CORRECTION")
            )),
        )
        # Policy basis is the document date, so a late credit note still books the
        # document-date rate and the receivable is relieved consistently.
        rate = self._rate(invoice.currency, plan.recognition_day)
        lines = [
            self._line(
                account_id=str(self.context.policy["revenue_account_id"]),
                currency=invoice.currency,
                debit=amount,
                rate=rate,
                counterparty_id=invoice.counterparty_id,
                analytic_tag=invoice.doc_id,
            ),
            self._line(
                account_id=str(self.context.policy["receivable_account_id"]),
                currency=invoice.currency,
                credit=amount,
                rate=rate,
                counterparty_id=invoice.counterparty_id,
                analytic_tag=invoice.doc_id,
            ),
        ]
        entry = JournalEntry(
            je_id=self.ids.new("journal_entries", month=moment.month),
            timestamp=format_timestamp(moment),
            posting_period=self.calendar.posting_period(moment),
            # A credit note is its own accounting event: it must reference the credit
            # note so the posting period is judged against the adjustment date, not
            # retro-actively against the original invoice's recognition period.
            source_document_id=note.credit_note_id,
            description=self.text.journal_description("credit_note", note.credit_note_id),
            lines=tuple(lines),
        )
        return note, entry

    def _maybe_payment(
        self, plan: DocumentPlan, stream, credited_minor: int
    ) -> tuple[Payment | None, JournalEntry | None, BankLine | None]:
        """Clean payment: settles the net obligation, or a part of it.

        The policy applies the *document-date* rate for the whole settlement cycle
        (``fx_rate_date_basis=document_date``), so a clean payment books exactly the
        same rate as the recognition entry and no artificial FX difference arises.
        """
        volumes = self.config.raw["volumes"]
        invoice = plan.invoice
        issue_day = plan.recognition_day
        delay = stream.randint(0, int(volumes["payment_delay_days_max"]))
        pay_day = issue_day + timedelta(days=delay)
        pay_moment = resolve_local_wall_time(
            pay_day,
            time(stream.randint(BUSINESS_START_HOUR, BUSINESS_END_HOUR), stream.randint(0, 59), 0),
            self.zone,
            self.calendar.ambiguity_policy,
        )

        net_minor = invoice.total_minor - credited_minor
        if net_minor <= 0:
            return None, None, None
        partial = stream.ratio_hit(int(volumes["partial_payment_ratio_bps"]))
        amount_minor = (
            net_minor
            if not partial
            else max(100, net_minor * stream.randint(3000, 7000) // 10000)
        )
        pay_id = self.ids.new("payments")
        rate = self._rate(invoice.currency, plan.recognition_day)
        allocation = Allocation(
            allocation_id=self.ids.new("allocations"),
            document_id=invoice.doc_id,
            amount_minor=amount_minor,
            allocation_timestamp=format_timestamp(pay_moment),
        )
        bank_line = BankLine(
            bank_line_id=self.ids.new("bank_lines"),
            timestamp=format_timestamp(pay_moment),
            amount_minor=amount_minor,
            currency=invoice.currency,
            direction="IN",
            reference_text=self.text.bank_reference(pay_id, invoice.counterparty_id),
            matched_payment_id=pay_id,
            bank_account_id=self.context.account_id_for_role("bank"),
            status="MATCHED",
        )
        payment = Payment(
            pay_id=pay_id,
            timestamp=format_timestamp(pay_moment),
            counterparty_id=invoice.counterparty_id,
            currency=invoice.currency,
            amount_minor=amount_minor,
            functional_amount_minor=self._to_functional(amount_minor, invoice.currency, rate),
            fx_rate_decimal=rate,
            allocations=(allocation,),
            bank_reference=bank_line.bank_line_id,
            payment_channel=str(stream.choice(("WIRE", "ACH", "CARD"))),
        )
        entry = self._payment_entry(payment, invoice, pay_moment, rate)
        return payment, entry, bank_line

    def _payment_entry(
        self, payment: Payment, invoice: Invoice, moment: datetime, rate: Decimal
    ) -> JournalEntry:
        """Bank D / receivable C at the policy (document-date) rate: exact relief."""
        receivable = str(self.context.policy["receivable_account_id"])
        bank = str(self.context.policy["bank_account_id"])
        lines = [
            self._line(
                account_id=bank,
                currency=invoice.currency,
                debit=payment.amount_minor,
                rate=rate,
                counterparty_id=invoice.counterparty_id,
                analytic_tag=payment.pay_id,
            ),
            self._line(
                account_id=receivable,
                currency=invoice.currency,
                credit=payment.amount_minor,
                rate=rate,
                counterparty_id=invoice.counterparty_id,
                analytic_tag=invoice.doc_id,
            ),
        ]
        return JournalEntry(
            je_id=self.ids.new("journal_entries", month=moment.month),
            timestamp=format_timestamp(moment),
            posting_period=self.calendar.posting_period(moment),
            source_document_id=invoice.doc_id,
            description=self.text.journal_description("payment", payment.pay_id),
            lines=tuple(lines),
        )

    def _advance_receipts(self, customers, start_year: int, start_month: int, months: int):  # noqa: ANN001, ANN201
        """Prepayments received before invoicing, parked on the advance account."""
        volumes = self.config.raw["volumes"]
        stream = self.rng.stream("history/advances")
        if not stream.ratio_hit(int(volumes["advance_receipt_ratio_bps"])):
            return [], []
        entries: list[JournalEntry] = []
        lines: list[BankLine] = []
        count = stream.randint(1, 2)
        for _ in range(count):
            year, month = _add_months(start_year, start_month, stream.randint(0, months - 1))
            day = date(year, month, stream.randint(2, min(26, _days_in_month(year, month))))
            moment = resolve_local_wall_time(
                day, time(stream.randint(BUSINESS_START_HOUR, BUSINESS_END_HOUR), 0, 0),
                self.zone, self.calendar.ambiguity_policy,
            )
            customer = customers[stream.randint(0, len(customers) - 1)]
            amount = stream.randint(500_000, 9_000_000)
            bank_line = BankLine(
                bank_line_id=self.ids.new("bank_lines"),
                timestamp=format_timestamp(moment),
                amount_minor=amount,
                currency=self.functional,
                direction="IN",
                reference_text=f"PREPAYMENT {customer.counterparty_id} {stream.random.getrandbits(20):05X}",
                matched_payment_id=None,
                bank_account_id=self.context.account_id_for_role("bank"),
                status="EXPLAINED_NON_PAYMENT",
            )
            entry = JournalEntry(
                je_id=self.ids.new("journal_entries", month=moment.month),
                timestamp=format_timestamp(moment),
                posting_period=self.calendar.posting_period(moment),
                source_document_id=None,
                description=f"Customer advance received from {customer.counterparty_id}",
                lines=(
                    self._line(
                        account_id=str(self.context.policy["bank_account_id"]),
                        currency=self.functional,
                        rate=Decimal(1),
                        counterparty_id=customer.counterparty_id,
                        analytic_tag=bank_line.bank_line_id,
                        debit=amount,
                    ),
                    self._line(
                        account_id=str(self.context.policy["advance_account_id"]),
                        currency=self.functional,
                        rate=Decimal(1),
                        counterparty_id=customer.counterparty_id,
                        analytic_tag=bank_line.bank_line_id,
                        credit=amount,
                    ),
                ),
            )
            entries.append(entry)
            lines.append(bank_line)
        return entries, lines

    def _unapplied_cash_lines(
        self, existing: Sequence[BankLine], start_year: int, start_month: int, months: int
    ) -> list[BankLine]:
        """A few honest UNMATCHED bank credits (deposits not yet allocated)."""
        volumes = self.config.raw["volumes"]
        stream = self.rng.stream("history/unapplied_cash")
        if not stream.ratio_hit(int(volumes["unapplied_cash_ratio_bps"])):
            return []
        count = stream.randint(1, 2)
        lines: list[BankLine] = []
        used_refs = {line.reference_text for line in existing}
        for _ in range(count):
            year, month = _add_months(start_year, start_month, stream.randint(0, months - 1))
            day = date(year, month, stream.randint(2, min(26, _days_in_month(year, month))))
            moment = resolve_local_wall_time(
                day, time(stream.randint(BUSINESS_START_HOUR, BUSINESS_END_HOUR), 0, 0),
                self.zone, self.calendar.ambiguity_policy,
            )
            for _attempt in range(20):
                reference = f"RECEIPT {UNALLOCATED_BANK_TOKEN} {stream.random.getrandbits(20):05X}"
                if reference not in used_refs:
                    used_refs.add(reference)
                    break
            else:  # pragma: no cover - defensive
                raise ConfigError("bank reference space exhausted")
            lines.append(
                BankLine(
                    bank_line_id=self.ids.new("bank_lines"),
                    timestamp=format_timestamp(moment),
                    amount_minor=stream.randint(50_000, 900_000),
                    currency=self.functional,
                    direction="IN",
                    reference_text=reference,
                    matched_payment_id=None,
                    bank_account_id=self.context.account_id_for_role("bank"),
                    status="UNMATCHED",
                )
            )
        return lines

    # ----------------------------------------------------------------- helpers
    def _rate(self, currency: str, day: date) -> Decimal:
        if currency == self.functional:
            return Decimal(1)
        pair = f"{currency}/{self.functional}"
        point = self.fx.rate_on(pair, day, fallback=self.context.policy["fx_fallback_rule"])
        return point.rate_decimal

    def _to_functional(self, amount_minor: int, currency: str, rate: Decimal) -> int:
        if currency == self.functional:
            return amount_minor
        return convert_minor(
            amount_minor, currency, self.functional, rate,
            mode=self.context.policy["rounding_mode"],
        ).amount_minor

    def _line(
        self,
        *,
        account_id: str,
        currency: str,
        rate: Decimal,
        counterparty_id: str | None,
        analytic_tag: str | None,
        debit: int = 0,
        credit: int = 0,
        functional_only: bool = False,
    ) -> JournalLine:
        functional_debit = self._to_functional(debit, currency, rate) if debit else 0
        functional_credit = self._to_functional(credit, currency, rate) if credit else 0
        if functional_only:
            # A pure functional-currency adjustment line, expressed in the
            # functional currency with rate 1 so INV-08 recomputes exactly.
            return JournalLine(
                line_id=self.ids.new("journal_entry_lines"),
                account_id=account_id,
                debit_minor=debit,
                credit_minor=credit,
                currency=self.functional,
                fx_rate_decimal=Decimal(1),
                functional_debit_minor=debit,
                functional_credit_minor=credit,
                counterparty_id=counterparty_id,
                analytic_tag=analytic_tag,
            )
        return JournalLine(
            line_id=self.ids.new("journal_entry_lines"),
            account_id=account_id,
            debit_minor=debit,
            credit_minor=credit,
            currency=currency,
            fx_rate_decimal=rate,
            functional_debit_minor=functional_debit,
            functional_credit_minor=functional_credit,
            counterparty_id=counterparty_id,
            analytic_tag=analytic_tag,
        )


def _apply_statuses(
    invoices: Sequence[Invoice],
    payments: Sequence[Payment],
    credit_notes: Sequence[CreditNote],
) -> list[Invoice]:
    """Derive stored document statuses through the shared helper (INV-17)."""
    from gen.core.journal import credited_totals, allocated_totals, derive_status

    credited = credited_totals(credit_notes)
    allocated = allocated_totals(payments)
    return [
        Invoice(
            doc_id=invoice.doc_id,
            counterparty_id=invoice.counterparty_id,
            issue_timestamp=invoice.issue_timestamp,
            service_start=invoice.service_start,
            service_end=invoice.service_end,
            due_timestamp=invoice.due_timestamp,
            currency=invoice.currency,
            total_minor=invoice.total_minor,
            tax_minor=invoice.tax_minor,
            line_items=invoice.line_items,
            status=derive_status(
                invoice, credited.get(invoice.doc_id, 0), allocated.get(invoice.doc_id, 0)
            ),
        )
        for invoice in invoices
    ]


def _add_months(year: int, month: int, offset: int) -> tuple[int, int]:
    total = (year * 12 + (month - 1)) + offset
    return total // 12, total % 12 + 1


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


def _first_day(year: int, month: int) -> date:
    return date(year, month, 1)


def _invoice_moment(invoice: Invoice) -> datetime:
    from core.time_rules import parse_timestamp

    return parse_timestamp(invoice.issue_timestamp)
