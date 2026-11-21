"""Explicit public table names and sort keys. No index is loaded from disk."""
TABLES = {
    'counterparties': 'counterparty_id', 'journal_entries': 'je_id',
    'invoices': 'doc_id', 'credit_notes': 'credit_note_id',
    'payments': 'pay_id', 'bank_lines': 'bank_line_id',
    'fx_rates': 'fx_rate_id', 'accounts': 'account_id',
}
# Filters are exact equality on these public scalar fields only.
FILTERS = {
    'counterparties': {'counterparty_id'},
    'journal_entries': {'je_id', 'posting_period', 'source_document_id'},
    'invoices': {'doc_id', 'counterparty_id', 'currency', 'status'},
    'credit_notes': {'credit_note_id', 'invoice_id', 'counterparty_id', 'currency'},
    'payments': {'pay_id', 'counterparty_id', 'currency'},
    'bank_lines': {'bank_line_id', 'currency', 'direction', 'matched_payment_id'},
    'fx_rates': {'fx_rate_id', 'pair', 'effective_date'},
    'accounts': {'account_id'},
}


def record_key(table, row):
    """Stable external key; FX may use the Phase 4 pair/date composite."""
    if not isinstance(row, dict):
        raise ValueError('invalid public row')
    if table == 'fx_rates' and 'fx_rate_id' not in row:
        pair, day = row.get('pair'), row.get('effective_date')
        if (not isinstance(pair, str) or not isinstance(day, str) or
                not pair or not day or '@' in pair or '@' in day):
            raise ValueError('invalid FX key')
        return pair + '@' + day
    return row.get(TABLES[table])
