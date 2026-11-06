import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from harness.simulator.openai_compatible import completion


class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class CompletionTests(unittest.TestCase):
    @patch.dict(os.environ, {'TEST_SIM_KEY': 'secret'})
    def test_completion_and_request(self):
        payload = {'choices': [{'message': {'content': 'answer'}}]}
        with patch('urllib.request.urlopen', return_value=Response(json.dumps(payload).encode())) as call:
            answer = completion('https://example.test/v1', 'gpt', 'TEST_SIM_KEY')([{'role': 'user', 'content': 'hi'}])
            self.assertEqual(answer, 'answer')
            req = call.call_args.args[0]
            self.assertEqual(req.full_url, 'https://example.test/v1/chat/completions')
            self.assertEqual(json.loads(req.data)['model'], 'gpt')
            self.assertEqual(req.get_header('Authorization'), 'Bearer secret')

    @patch.dict(os.environ, {'TEST_SIM_KEY': 'secret'})
    def test_error_does_not_include_server_body(self):
        with patch('urllib.request.urlopen', side_effect=HTTPError('url', 401, 'error', {}, None)):
            with self.assertRaisesRegex(RuntimeError, 'HTTP 401'):
                completion('https://example.test/v1', 'gpt', 'TEST_SIM_KEY')([])
