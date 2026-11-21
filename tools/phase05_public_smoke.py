"""Smoke-test a supplied public-only episode; never reads its parent or sealed data."""
import argparse
import json
from env import Environment
from env.index import TABLES, record_key


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('public_dir')
    args = parser.parse_args()
    env = Environment()
    initial = env.reset(args.public_dir, {'mode': 'CLOSED_EVAL', 'max_steps': 100, 'cursor_key': b'public-smoke-test-key-not-secret!!'})
    assert initial['mode'] == 'CLOSED_EVAL'
    checked = []
    for table in TABLES:
        step = env.step({'tool': 'list_records', 'args': {'table': table, 'limit': 2}})
        assert step['reward'] == 0 and step['info'] == {} and 'error' not in step['observation']['result']
        rows = step['observation']['result']['rows']
        if rows:
            row = rows[0]
            step = env.step({'tool': 'get_record', 'args': {'table': table, 'id': record_key(table, row)}})
            assert step['observation']['result'].get('record') == row
            if table == 'invoices':
                step = env.step({'tool': 'get_document', 'args': {'doc_id': row['doc_id']}})
                assert step['observation']['result'].get('document') == row
        checked.append(table)
    step = env.step({'tool': 'submit', 'args': {'findings': []}})
    assert step['terminated'] and not step['truncated'] and step['reward'] == 0
    print(json.dumps({'status': 'PASS', 'tables': checked, 'submit': 'accepted', 'official_contract': 'unknown'}))

if __name__ == '__main__':
    main()
