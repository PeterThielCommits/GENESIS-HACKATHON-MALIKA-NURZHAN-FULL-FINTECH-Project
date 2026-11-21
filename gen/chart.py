"""Chart of accounts generation (contract 8.3; REQ-DATA-001..005)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gen.rng import NamespacedRNG

#: Special account ids referenced by the journal/invariants (contract 12).
AP_ACCOUNT_ID = "1100"      # Liability: payables to suppliers.
CASH_ACCOUNT_ID = "1020"    # Asset: cash in bank.
REVENUE_SALES_ID = "4010"   # Revenue account for sales.
REVENUE_SERVICE_ID = "4020" # Revenue account for services.
TAX_ACCOUNT_ID = "4030"     # Revenue account: sales tax.
PURCHASES_ACCOUNT_ID = "4040"  # Expense account: purchases.

#: Fictional account dictionaries with ru/kk/en name variants (Section 8.1).
_ACCOUNTS = [
    {
        "account_id": AP_ACCOUNT_ID,
        "name": "Suppliers Payables",
        "name_variants": {"ru": "Поставщики", "kk": "Жеткізушілер", "en": "Suppliers Payables"},
        "account_type": "liability",
        "balance_side": "credit",
        "currency": "KZT",
    },
    {
        "account_id": CASH_ACCOUNT_ID,
        "name": "Cash in Bank",
        "name_variants": {"ru": "Денежные средства в банке", "kk": "Тегізбадағы ақша", "en": "Cash in Bank"},
        "account_type": "asset",
        "balance_side": "debit",
        "currency": "KZT",
    },
    {
        "account_id": "1200",
        "name": "Inventory",
        "name_variants": {"ru": "Запасы", "kk": "Толық нәрселер", "en": "Inventory"},
        "account_type": "asset",
        "balance_side": "debit",
        "currency": "KZT",
    },
    {
        "account_id": "1300",
        "name": "Equipment",
        "name_variants": {"ru": "Оборудование", "kk": "Тегізба", "en": "Equipment"},
        "account_type": "asset",
        "balance_side": "debit",
        "currency": "KZT",
    },
    {
        "account_id": "4000",
        "name": "Equity - Capital",
        "name_variants": {"ru": "Акционерный капитал", "kk": "Құрылым қоймасы", "en": "Equity - Capital"},
        "account_type": "equity",
        "balance_side": "credit",
        "currency": "KZT",
    },
    {
        "account_id": REVENUE_SALES_ID,
        "name": "Sales Revenue",
        "name_variants": {"ru": "Доходы от продажи", "kk": "Сатып алу жасақының мазақтау", "en": "Sales Revenue"},
        "account_type": "revenue",
        "balance_side": "credit",
        "currency": "KZT",
    },
    {
        "account_id": REVENUE_SERVICE_ID,
        "name": "Service Revenue",
        "name_variants": {"ru": "Услуги", "kk": "Қызмет пен жеткізу", "en": "Service Revenue"},
        "account_type": "revenue",
        "balance_side": "credit",
        "currency": "KZT",
    },
    {
        "account_id": TAX_ACCOUNT_ID,
        "name": "Sales Tax Liability",
        "name_variants": {"ru": "Налог на продажу", "kk": "Сатып алу жасақы", "en": "Sales Tax Liability"},
        "account_type": "liability",
        "balance_side": "credit",
        "currency": "KZT",
    },
    {
        "account_id": PURCHASES_ACCOUNT_ID,
        "name": "Purchases Expense",
        "name_variants": {"ru": "Покупки (расходы)", "kk": "Үсінділерді есепке толтыру", "en": "Purchases Expense"},
        "account_type": "expense",
        "balance_side": "debit",
        "currency": "KZT",
    },
    {
        "account_id": "5000",
        "name": "Salaries Expense",
        "name_variants": {"ru": "Зарплата", "kk": "Алдыңғы есепке толтыру", "en": "Salaries Expense"},
        "account_type": "expense",
        "balance_side": "debit",
        "currency": "KZT",
    },
    {
        "account_id": "5010",
        "name": "Operating Expenses",
        "name_variants": {"ru": "Операционные расходы", "kk": "Операцияғақ", "en": "Operating Expenses"},
        "account_type": "expense",
        "balance_side": "debit",
        "currency": "KZT",
    },
]


@dataclass
class Account:
    account_id: str
    name: str
    name_variants: dict[str, str]
    account_type: str
    balance_side: str
    currency: str

    def to_public(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "name": self.name,
            "name_variants": dict(self.name_variants),
            "account_type": self.account_type,
            "balance_side": self.balance_side,
            "currency": self.currency,
        }


def generate_chart(rng: NamespacedRNG) -> list[Account]:
    """Generate the chart of accounts for the company."""
    accounts = [Account(
        account_id=a["account_id"],
        name=a["name"],
        name_variants=dict(a["name_variants"]),
        account_type=a["account_type"],
        balance_side=a["balance_side"],
        currency=a["currency"],
    ) for a in _ACCOUNTS]
    return sorted(accounts, key=lambda a: a.account_id)


def account_by_id(accounts: list[Account], account_id: str) -> Account:
    for acc in accounts:
        if acc.account_id == account_id:
            return acc
    raise ValueError(f"account not found: {account_id}")


def functional_accounts(accounts: list[Account]) -> list[Account]:
    return [a for a in accounts if a.currency == "KZT"]
