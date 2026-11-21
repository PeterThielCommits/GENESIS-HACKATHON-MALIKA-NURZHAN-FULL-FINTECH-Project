import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from env import Environment

PUBLIC = Path(__file__).resolve().parents[1] / 'fixtures/example/public'
CONFIG = {'mode': 'CLOSED_EVAL', 'max_steps': 10, 'cursor_key': b'x' * 32}

def action(tool, **args):
    return {'tool': tool, 'args': args}

def result(value):
    return value['observation']['result']

class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.env = Environment()
        self.initial = self.env.reset(PUBLIC, CONFIG)

    def test_valid_actions_and_readonly_responses(self):
        self.assertEqual(self.initial['mode'], 'CLOSED_EVAL')
        row = result(self.env.step(action('get_record', table='invoices', id='I-1')))['record']
        row['total_minor'] = 0
        self.assertEqual(result(self.env.step(action('get_document', doc_id='I-1')))['document']['total_minor'], 1000)
        self.assertEqual(len(result(self.env.step(action('list_records', table='payments')))['rows']), 1)
        finding = {'type':'DUPLICATE_PAYMENT', 'affected_ids':['P-1'], 'amount_minor':500, 'currency':'USD', 'evidence_ids':['I-1']}
        value = self.env.step(action('submit', findings=[finding]))
        self.assertTrue(value['terminated']); self.assertEqual(value['reward'], 0)
        self.assertEqual(value['observation']['steps_remaining'], 7)

    def test_pagination_filters_and_determinism(self):
        one = result(self.env.step(action('list_records', table='invoices', limit=1, filters={'status':'open'})))
        self.assertEqual(one['rows'][0]['doc_id'], 'I-1')
        cursor = one['next_cursor']
        two = result(self.env.step(action('list_records', table='invoices', limit=1, filters={'status':'open'}, cursor=cursor)))
        self.assertEqual(two['rows'][0]['doc_id'], 'I-2'); self.assertIsNone(two['next_cursor'])
        other = Environment(); other.reset(PUBLIC, CONFIG)
        self.assertEqual(cursor, result(other.step(action('list_records', table='invoices', limit=1, filters={'status':'open'})))['next_cursor'])
        self.assertNotIn('I-1', cursor)

    def test_invalid_and_foreign_cursors(self):
        c = result(self.env.step(action('list_records', table='invoices', limit=1)))['next_cursor']
        for a in [action('list_records', table='invoices', cursor='bad'), action('list_records', table='payments', cursor=c), action('list_records', table='invoices', cursor=c, filters={'status':'open'}), action('list_records', table='invoices', cursor=c[:-1]+'!')]:
            self.assertEqual(result(self.env.step(a))['error']['code'], 'BAD_CURSOR')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'public'; shutil.copytree(PUBLIC, p)
            (p/'invoices.jsonl').write_text((p/'invoices.jsonl').read_text() + '{"doc_id":"I-3"}\n')
            other = Environment(); other.reset(p, CONFIG)
            self.assertEqual(result(other.step(action('list_records',table='invoices',cursor=c)))['error']['code'], 'BAD_CURSOR')

    def test_bad_actions_charge_and_fixed_errors(self):
        cases = [(None,'BAD_ARGS'), ({'tool':'unknown','args':{}},'UNKNOWN_TOOL'), (action('get_record',table='sealed',id='x'),'BAD_ARGS'), (action('list_records',table='invoices',limit=51),'BAD_ARGS'), (action('list_records',table='invoices',filters={'seed':1}),'BAD_FILTER'), (action('get_document',doc_id='absent'),'NOT_FOUND'), (action('submit', findings=[{}]),'BAD_FINDING'), ({'tool':'submit','args':{},'extra':True},'BAD_ARGS')]
        for i,(a,code) in enumerate(cases,1):
            r = self.env.step(a); self.assertEqual(result(r), {'error':{'code':code}}); self.assertEqual(r['observation']['steps_remaining'],10-i)
        self.assertEqual(result(self.env.step(action('get_document',doc_id='nonexistent'))), {'error':{'code':'NOT_FOUND'}})

    def test_budget_truncation_and_duplicate_submit(self):
        e = Environment(); e.reset(PUBLIC, {**CONFIG,'max_steps':1})
        r=e.step(action('unknown')); self.assertTrue(r['truncated']); self.assertFalse(r['terminated'])
        self.assertEqual(result(e.step(action('submit',findings=[])))['error']['code'], 'TERMINATED')
        r=self.env.step(action('submit',findings=[])); self.assertTrue(r['terminated'])
        self.assertEqual(result(self.env.step(action('submit',findings=[])))['error']['code'], 'ALREADY_SUBMITTED')
        self.assertEqual(result(self.env.step(action('get_document',doc_id='I-1')))['error']['code'], 'TERMINATED')

    def test_closed_no_private_info(self):
        out=[self.initial,self.env.step(action('get_document',doc_id='I-1')),self.env.step(action('submit',findings=[]))]
        text=json.dumps(out).lower()
        for name in ['truth','seed','provenance','tp','fp','fn']:
            self.assertNotIn('"'+name+'"',text)
        for r in out[1:]:
            self.assertEqual(r['reward'], 0); self.assertEqual(r['info'], {})

    def test_invalid_config_and_reset_failed_closed(self):
        for cfg in [{**CONFIG,'mode':'OPEN_DEV'}, {**CONFIG,'max_steps':True}, {**CONFIG,'cursor_key':b'x'}, {**CONFIG,'extra':0}]:
            with self.assertRaises(ValueError): self.env.reset(PUBLIC,cfg)
            with self.assertRaises(RuntimeError): self.env.step(action('submit',findings=[]))

    def test_public_only_loader_rejects_sealed_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); public=root/'public'; shutil.copytree(PUBLIC,public)
            sealed=root/'sealed'; sealed.mkdir(); (sealed/'truth.json').write_text('{"secret":"private"}')
            e=Environment()
            with self.assertRaises(ValueError): e.reset(sealed,CONFIG)
            (public/'policy.json').unlink(); (public/'policy.json').symlink_to(sealed/'truth.json')
            with self.assertRaises(OSError): e.reset(public,CONFIG)
            (public/'policy.json').unlink(); (public/'policy.json').write_text('{"master_seed": 123}')
            with self.assertRaises(ValueError): e.reset(public,CONFIG)

    def test_loader_never_opens_non_public_files(self):
        from unittest.mock import patch
        opened = []
        real_open = os.open
        def tracking(path, *args, **kwargs):
            opened.append(str(path))
            return real_open(path, *args, **kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); public = root / 'public'; shutil.copytree(PUBLIC, public)
            sealed = root / 'sealed'; sealed.mkdir(); (sealed / 'truth.json').write_text('{"secret":"private"}')
            (public / 'unlisted.json').write_text('{"secret":"private"}')
            with patch('env.state.os.open', side_effect=tracking):
                self.env.reset(public, CONFIG)
            self.assertNotIn('truth.json', opened)
            self.assertNotIn('unlisted.json', opened)

    def test_no_forbidden_module_imports(self):
        import ast
        for path in (Path(__file__).resolve().parents[2] / 'env').glob('*.py'):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [x.name.split('.')[0] for x in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [(node.module or '').split('.')[0]]
                else:
                    continue
                self.assertFalse(set(names) & {'gen', 'verifier', 'scoring', 'seal'}, (path, names))

    def test_file_validation_and_request_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'public'; shutil.copytree(PUBLIC,p)
            (p/'policy.json').write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError): self.env.reset(p, CONFIG)
        self.env.reset(PUBLIC,CONFIG)
        self.assertEqual(result(self.env.step(action('get_document',doc_id='x'*20000)))['error']['code'],'LIMIT')

    def test_finding_validation_edges(self):
        f={'type':'DUPLICATE_PAYMENT','affected_ids':['P-1'],'amount_minor':10,'currency':'USD','evidence_ids':['I-1']}
        for change in [{'amount_minor':1.0},{'amount_minor':True},{'currency':'12A'},{'evidence_ids':['x','x']},{'type':'unknown'},{'affected_ids':[]}]:
            with self.subTest(change=change):
                r=self.env.step(action('submit',findings=[{**f,**change}]))
                self.assertEqual(result(r)['error']['code'],'BAD_FINDING')
        self.assertTrue(self.env.step(action('submit',findings=[]))['terminated'])

if __name__ == '__main__': unittest.main()
