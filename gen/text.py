"""Deterministic multilingual text layer (contract 8.5; REQ-NLP-001..005).

Rules:
  - texts are synthetic and generated from local templates/dictionaries
    with namespaced RNG (no remote LLM, no network);
  - one fixed version of each template table per codebase (REQ-NLP-001);
  - Unicode NFC normalization for all produced strings;
  - free text is allowed only where the public schema permits it (invoice
    line descriptions, payment reference_text, bank line reference_text,
    counterparty name variants) and is never the sole proof of an anomaly;
  - text is a supplemental source only (contract 17.3);
"""
from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING

from gen.rng import NamespacedRNG

if TYPE_CHECKING:  # pragma: no cover
    from gen.company import CompanyProfile

LANGUAGES = ("ru", "kk", "en")


def normalize_nfc(text: str) -> str:
    """Unicode NFC normalization (REQ-NLP-005)."""
    return unicodedata.normalize("NFC", text)


# ---------------------------------------------------------------------------
# English templates
# ---------------------------------------------------------------------------
EN_INVOICE_LINE_TEMPLATES = [
    "Invoice {doc_id} — {item_desc} for service {start} to {end}",
    "Invoice {doc_id} for {item_desc} (period {start} to {end})",
    "Service invoice {doc_id}: {item_desc} from {cp} in {ccy}",
]
EN_PAYMENT_REFERENCE_TEMPLATES = [
    "Payment to {cp}: invoice {doc_id}",
    "Settlement of invoice {doc_id}",
    "Payment for {doc_id}",
]
EN_BANK_LINE_REFERENCE_TEMPLATES = [
    "Bank receipt {bank_line_id} linked to {payment_id}",
    "Received funds from {cp} — payment {payment_id}",
    "EFT receipt {bank_line_id}",
]
EN_INVOICE_DESCRIPTION_TEMPLATES = [
    "{doc_id} — {cp} service invoice for period {start}..{end}",
    "Invoice {doc_id} covering {amount} {ccy} for {cp}",
    "Services rendered by {cp} — invoice {doc_id}",
]


# ---------------------------------------------------------------------------
# Russian templates
# ---------------------------------------------------------------------------
RU_INVOICE_LINE_TEMPLATES = [
    "Счёт {doc_id} — {item_desc} за услугу с {start} по {end}",
    "Счёт {doc_id} за {item_desc} (период {start}..{end})",
    "Счёт на оплату {doc_id}: {item_desc} от {cp} в {ccy}",
]
RU_PAYMENT_REFERENCE_TEMPLATES = [
    "Оплата по {cp}: счёт {doc_id}",
    "Оплата счёта {doc_id}",
    "Платёж по счёту {doc_id}",
]
RU_BANK_LINE_REFERENCE_TEMPLATES = [
    "Банковский документ {bank_line_id} по оплате {payment_id}",
    "Поступление от {cp} — оплата {payment_id}",
    "Объективный выписка {bank_line_id}",
]
RU_INVOICE_DESCRIPTION_TEMPLATES = [
    "{doc_id} — счёт от {cp} за период с {start} по {end}",
    "Счёт {doc_id} на сумму {amount} {ccy} от {cp}",
    "Услуги {cp} — счёт {doc_id}",
]


# ---------------------------------------------------------------------------
# Kazakh templates
# ---------------------------------------------------------------------------
KK_INVOICE_LINE_TEMPLATES = [
    "{doc_id} — {item_desc} үшін {start} жағдайынан {end}",
    "{doc_id} үшін {item_desc} (тізбек {start}..{end})",
    "{cp} қызметінен тілгені {doc_id}: {item_desc} {ccy}",
]
KK_PAYMENT_REFERENCE_TEMPLATES = [
    "{cp}: тілгені {doc_id}",
    "{doc_id} тілгені",
    "Есепке толтыру {doc_id}",
]
KK_BANK_LINE_REFERENCE_TEMPLATES = [
    "Банк жазбасы {bank_line_id} оплатаға {payment_id}",
    "{cp}-дан есепке толтыру {payment_id}",
    "EFT жазбасы {bank_line_id}",
]
KK_INVOICE_DESCRIPTION_TEMPLATES = [
    "{doc_id} — {cp} үшін {start} күнінен {end}",
    "Счёт {doc_id} {cp} үшін {amount} {ccy}",
    "{cp} қызметінен счёт {doc_id}",
]


# ---------------------------------------------------------------------------
# Item descriptors (deterministic short phrases per language)
# ---------------------------------------------------------------------------
EN_ITEM_DESCRIPTORS = [
    "consulting services",
    "hosting and infrastructure",
    "maintenance work",
    "logistics support",
    "software development",
]
RU_ITEM_DESCRIPTORS = [
    "консультационные услуги",
    "обслуживание хостинга",
    "поддержка и сопровождение",
    "логистические услуги",
    "разработка программного обеспечения",
]
KK_ITEM_DESCRIPTORS = [
    "консультациялық қызметтер",
    "қозмет пен жеткізу",
    "әзірлеу және қолдау",
    "логистикағақ",
    "жасанды интеллект жазбастары",
]


def _template_set(lang: str):
    return {
        "en": (EN_INVOICE_LINE_TEMPLATES, EN_PAYMENT_REFERENCE_TEMPLATES,
               EN_BANK_LINE_REFERENCE_TEMPLATES, EN_INVOICE_DESCRIPTION_TEMPLATES,
               EN_ITEM_DESCRIPTORS),
        "ru": (RU_INVOICE_LINE_TEMPLATES, RU_PAYMENT_REFERENCE_TEMPLATES,
               RU_BANK_LINE_REFERENCE_TEMPLATES, RU_INVOICE_DESCRIPTION_TEMPLATES,
               RU_ITEM_DESCRIPTORS),
        "kk": (KK_INVOICE_LINE_TEMPLATES, KK_PAYMENT_REFERENCE_TEMPLATES,
               KK_BANK_LINE_REFERENCE_TEMPLATES, KK_INVOICE_DESCRIPTION_TEMPLATES,
               KK_ITEM_DESCRIPTORS),
    }[lang]


def invoice_line_description(
    rng: NamespacedRNG, lang: str, doc_id: str, cp_name: str,
    item_desc: str, currency: str, start: str, end: str | None,
) -> str:
    invoice_t, _, _, _, _ = _template_set(lang)
    template = rng.choice(invoice_t)
    end = end or start
    return normalize_nfc(template.format(
        doc_id=doc_id, item_desc=item_desc, cp=cp_name, ccy=currency,
        start=start, end=end,
    ))


def payment_reference_text(
    rng: NamespacedRNG, lang: str, payment_id: str, cp_name: str, doc_id: str,
) -> str:
    _, payment_t, _, _, _ = _template_set(lang)
    return normalize_nfc(rng.choice(payment_t).format(
        payment_id=payment_id, cp=cp_name, doc_id=doc_id,
    ))


def bank_line_reference_text(
    rng: NamespacedRNG, lang: str, bank_line_id: str, payment_id: str,
    cp_name: str,
) -> str:
    _, _, bank_t, _, _ = _template_set(lang)
    return normalize_nfc(rng.choice(bank_t).format(
        bank_line_id=bank_line_id, payment_id=payment_id, cp=cp_name,
    ))


def invoice_description_text(
    rng: NamespacedRNG, lang: str, doc_id: str, cp_name: str,
    amount: str, currency: str, start: str, end: str,
) -> str:
    _, _, _, desc_t, _ = _template_set(lang)
    return normalize_nfc(rng.choice(desc_t).format(
        doc_id=doc_id, cp=cp_name, amount=amount, ccy=currency, start=start, end=end,
    ))


def pick_language(rng: NamespacedRNG, profile: "CompanyProfile") -> str:
    """Pick a language per the company text_profile probabilities."""
    probs = profile.text_profile.get("probs", {"ru": 0.6, "kk": 0.2, "en": 0.2})
    for _ in range(50):
        lang = rng.choice(list(probs.keys()))
        if lang in LANGUAGES:
            return lang
    return rng.choice(LANGUAGES)
