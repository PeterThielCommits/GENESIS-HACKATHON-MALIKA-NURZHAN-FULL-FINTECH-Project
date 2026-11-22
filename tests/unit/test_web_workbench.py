"""Smoke tests for the browser entry point and its public API."""
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

from tools.demo_server import DemoHandler


class WebWorkbenchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), DemoHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_home_and_technical_view(self):
        with urlopen(self.base + '/') as response:
            html = response.read().decode('utf-8')
            self.assertIn('id="language"', html)
            self.assertIn('Қазақша', html)
            self.assertIn('Русский', html)
            self.assertIn('English', html)
            self.assertIn('/advanced', html)
        with urlopen(self.base + '/advanced') as response:
            self.assertIn('ProofGraph', response.read().decode('utf-8'))

    def test_episodes_and_unknown_episode(self):
        with urlopen(self.base + '/api/episodes') as response:
            episodes = json.load(response)['episodes']
            self.assertTrue(episodes)
            self.assertIn('episode_id', episodes[0])
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base + '/api/episode/dev/not-an-episode/overview')
        self.assertEqual(error.exception.code, 404)
