"""Deterministic multilingual description generation (Phase 3.5, 17.2).

Descriptions are a supplementary signal only (P-007): they never create facts and
never encode anomaly hints. Each document type draws from its own namespace, so
adding text to one document cannot shift ids, amounts or ordering elsewhere
(REQ-GEN-004).
"""

from __future__ import annotations

from typing import Final

from gen.core.reference import SERVICE_CATALOG
from gen.core.rng import RngService

_QUALIFIERS: Final[dict[str, tuple[str, ...]]] = {
    "en": ("under contract", "per agreed schedule", "as invoiced", "per addendum"),
    "ru": ("по договору", "по согласованному графику", "по счёту", "по допсоглашению"),
    "kk": ("шарт бойынша", "келісілген кесте бойынша", "шот бойынша", "қосымша келісім бойынша"),
}

_PAYMENT_TEMPLATES: Final[dict[str, tuple[str, ...]]] = {
    "en": ("Payment for {doc}", "Settlement of {doc}", "Transfer against {doc}"),
    "ru": ("Оплата по {doc}", "Расчёт по {doc}", "Перевод в счёт {doc}"),
    "kk": ("{doc} бойынша төлем", "{doc} бойынша есеп айырысу", "{doc} есебіне аударым"),
}

_CREDIT_TEMPLATES: Final[dict[str, tuple[str, ...]]] = {
    "en": ("Credit adjustment for {doc}", "Billing correction for {doc}"),
    "ru": ("Корректировка по {doc}", "Исправление выставления по {doc}"),
    "kk": ("{doc} бойынша түзету", "{doc} бойынша шотты түзету"),
}


class TextFactory:
    """Advisory text factory bound to one RNG service and one profile."""

    def __init__(self, rng: RngService, profile: str) -> None:
        if profile not in ("ru_kk_en", "en_primary", "ru_primary"):
            raise ValueError(f"unsupported text profile: {profile}")
        self._rng = rng
        self._profile = profile

    def service_description(self, language: str, index: int) -> str:
        if language not in ("en", "ru", "kk"):
            raise ValueError(f"unsupported language: {language}")
        stream = self._rng.stream(f"text/{language}/invoice")
        service = SERVICE_CATALOG[stream.randint(0, len(SERVICE_CATALOG) - 1)]
        qualifier = _QUALIFIERS[language][stream.randint(0, len(_QUALIFIERS[language]) - 1)]
        return f"{service[language]} — {qualifier}"

    def payment_reference(self, language: str, document_label: str) -> str:
        stream = self._rng.stream(f"text/{language}/payment")
        template = _PAYMENT_TEMPLATES[language][stream.randint(0, len(_PAYMENT_TEMPLATES[language]) - 1)]
        return template.format(doc=document_label)

    def credit_note_reason(self, language: str, document_label: str) -> str:
        stream = self._rng.stream(f"text/{language}/credit_note")
        template = _CREDIT_TEMPLATES[language][
            stream.randint(0, len(_CREDIT_TEMPLATES[language]) - 1)
        ]
        return template.format(doc=document_label)

    def journal_description(self, kind: str, document_label: str) -> str:
        """Primary-language journal narrative (English label keeps the ledger readable)."""
        templates = {
            "invoice": "Revenue recognition for {doc}",
            "payment": "Customer settlement for {doc}",
            "credit_note": "Credit adjustment for {doc}",
            "fx": "FX revaluation on settlement of {doc}",
        }
        if kind not in templates:
            raise ValueError(f"unsupported journal description kind: {kind}")
        return templates[kind].format(doc=document_label)

    def bank_reference(self, payment_label: str, counterparty_label: str) -> str:
        stream = self._rng.stream("text/en/bank")
        token = f"{stream.random.getrandbits(20):05X}"
        return f"INV-REF {payment_label} {counterparty_label} {token}"
