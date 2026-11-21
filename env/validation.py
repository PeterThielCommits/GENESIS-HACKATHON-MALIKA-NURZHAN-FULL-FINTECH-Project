from .budget import MAX_FINDINGS, MAX_EVIDENCE_IDS
from .errors import PublicError

TYPES = {'DUPLICATE_PAYMENT', 'PARTIAL_PAYMENT_ALLOCATION', 'FX_RATE_MISMATCH', 'PERIOD_CUTOFF'}

def findings_valid(findings):
    if not isinstance(findings, list) or len(findings) > MAX_FINDINGS:
        raise PublicError('BAD_FINDING')
    for f in findings:
        if not isinstance(f, dict) or set(f) != {'type', 'affected_ids', 'amount_minor', 'currency', 'evidence_ids'}:
            raise PublicError('BAD_FINDING')
        if not isinstance(f['type'], str) or f['type'] not in TYPES or type(f['amount_minor']) is not int:
            raise PublicError('BAD_FINDING')
        if not isinstance(f['currency'], str) or len(f['currency']) != 3 or not f['currency'].isascii() or not f['currency'].isalpha() or not f['currency'].isupper():
            raise PublicError('BAD_FINDING')
        for field in ('affected_ids', 'evidence_ids'):
            ids = f[field]
            if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_EVIDENCE_IDS or any(not isinstance(x, str) or not x or len(x) > 256 for x in ids) or len(set(ids)) != len(ids):
                raise PublicError('BAD_FINDING')
