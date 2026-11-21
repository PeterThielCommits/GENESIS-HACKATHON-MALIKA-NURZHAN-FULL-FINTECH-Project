from .errors import PublicError
from .index import FILTERS

def apply_filters(table, rows, filters):
    if not isinstance(filters, dict) or any(k not in FILTERS[table] for k in filters):
        raise PublicError('BAD_FILTER')
    if any(not isinstance(v, (str, int, type(None))) or isinstance(v, bool) or (isinstance(v, str) and len(v) > 256) for v in filters.values()):
        raise PublicError('BAD_FILTER')
    return [row for row in rows if all(k in row and type(row[k]) is type(v) and row[k] == v for k, v in filters.items())]
