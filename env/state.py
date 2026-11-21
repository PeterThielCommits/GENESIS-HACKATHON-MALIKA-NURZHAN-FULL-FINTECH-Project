"""Load only known files from an explicitly supplied public directory.

This is an API boundary, not an OS sandbox: isolate processes and filesystem
permissions separately before exposing the environment to untrusted code.
"""
import hashlib
import json
import os
import stat
from .index import TABLES, record_key

FILES = {'company.json': 'object', 'policy.json': 'object', 'accounts.json': 'array',
         'opening_balances.json': 'object_or_array', 'period_calendar.json': 'object_or_array',
         **{name + '.jsonl': 'jsonl' for name in TABLES if name != 'accounts'}}
OPTIONAL = {'document_links.jsonl': 'jsonl', 'accounts.jsonl': 'jsonl'}
MAX_FILE_BYTES = 10 * 1024 * 1024
FORBIDDEN_KEYS = {'truth', 'provenance', 'seed', 'master_seed', 'mutation', 'operator', 'index_hints', 'truth_id', 'affected_ids', 'distractor_of', 'distinguishing_fact'}

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')

def _pairs(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError('duplicate key')
        result[k] = v
    return result

def _float(_):
    raise ValueError('JSON floats are not allowed')

def _decode(data):
    return json.loads(data, object_pairs_hook=_pairs, parse_float=_float,
                      parse_constant=_float)

def _safe(value):
    if isinstance(value, dict):
        if any(k.lower() in FORBIDDEN_KEYS for k in value):
            raise ValueError('private field in public input')
        for v in value.values():
            _safe(v)
    elif isinstance(value, list):
        for v in value:
            _safe(v)

def _open_dir(path):
    # Walk without following symlinks, including intermediate path components.
    path = os.path.abspath(os.fspath(path))
    parts = path.split(os.sep)[1:]
    if not parts or parts[-1] != 'public' or 'sealed' in parts:
        raise ValueError('expected public directory')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise

def load_public(path):
    fd = _open_dir(path)
    result = {}
    try:
        for name, kind in (FILES | OPTIONAL).items():
            try:
                f = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            except FileNotFoundError:
                if name in OPTIONAL or name == 'accounts.json':
                    continue
                raise
            try:
                info = os.fstat(f)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_FILE_BYTES:
                    raise ValueError('invalid public file')
                with os.fdopen(f, 'rb') as stream:
                    f = -1
                    data = stream.read(MAX_FILE_BYTES + 1)
                if len(data) > MAX_FILE_BYTES:
                    raise ValueError('public file too large')
            finally:
                if f != -1:
                    os.close(f)
            if kind == 'jsonl':
                value = [_decode(line) for line in data.splitlines() if line.strip()]
            else:
                value = _decode(data)
            if ((kind == 'object' and not isinstance(value, dict)) or
                (kind in ('array', 'jsonl') and not isinstance(value, list)) or
                (kind == 'object_or_array' and not isinstance(value, (dict, list)))):
                raise ValueError('invalid public shape')
            _safe(value)
            key = name.rsplit('.', 1)[0]
            if key in result:
                raise ValueError('ambiguous public files')
            result[key] = value
    finally:
        os.close(fd)
    for table in TABLES:
        if table not in result:
            raise ValueError('missing public table')
        rows = result[table]
        ids = [record_key(table, row) for row in rows]
        if any(not isinstance(x, str) or not x or len(x) > 256 for x in ids) or len(set(ids)) != len(ids):
            raise ValueError('invalid public table identifier')
        result[table] = sorted(rows, key=lambda row: record_key(table, row))
    return result, hashlib.sha256(canonical(result)).hexdigest()
