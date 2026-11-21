from .budget import MAX_PAGE_SIZE
from .errors import PublicError
from .filters import apply_filters
from .index import TABLES

def _fields(args, required, allowed):
    if not isinstance(args, dict) or not required <= args.keys() or not args.keys() <= allowed:
        raise PublicError('BAD_ARGS')

def _table(table):
    if not isinstance(table, str) or table not in TABLES:
        raise PublicError('BAD_ARGS')

def _id(value):
    if not isinstance(value, str) or not value or len(value) > 256:
        raise PublicError('BAD_ARGS')

def execute(env, tool, args):
    if tool == 'list_records':
        _fields(args, {'table'}, {'table', 'cursor', 'limit', 'filters'})
        table = args['table']; _table(table)
        limit = args.get('limit', MAX_PAGE_SIZE)
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE:
            raise PublicError('BAD_ARGS')
        filters = args.get('filters', {})
        rows = apply_filters(table, env.data[table], filters)
        cursor = args.get('cursor')
        if cursor is not None:
            last = env.cursors.read(cursor, table, filters)
            rows = [r for r in rows if r[TABLES[table]] > last]
        page = rows[:limit]
        next_cursor = env.cursors.issue(table, filters, page[-1][TABLES[table]]) if len(rows) > limit else None
        return {'rows': page, 'next_cursor': next_cursor}
    if tool == 'get_record':
        _fields(args, {'table', 'id'}, {'table', 'id'})
        table = args['table']; _table(table); _id(args['id'])
        for row in env.data[table]:
            if row[TABLES[table]] == args['id']:
                return {'record': row}
        raise PublicError('NOT_FOUND')
    if tool == 'get_document':
        _fields(args, {'doc_id'}, {'doc_id'}); _id(args['doc_id'])
        for row in env.data['invoices']:
            if row['doc_id'] == args['doc_id']:
                return {'document': row, 'links': [link for link in env.data.get('document_links', []) if isinstance(link, dict) and link.get('doc_id') == args['doc_id']]}
        raise PublicError('NOT_FOUND')
    raise PublicError('UNKNOWN_TOOL')
