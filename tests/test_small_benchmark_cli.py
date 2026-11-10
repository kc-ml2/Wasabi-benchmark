"""CLI validation for the Wasabi simulator reply budget."""
import sys
import unittest
from unittest.mock import patch

from scripts.run_small_benchmark import main


class ReplyLimitTests(unittest.TestCase):
    def test_negative_reply_limit_rejected_before_execution(self):
        argv = ['runner', '--output', 'unused', '--count', '1',
                '--provider', 'test', '--model', 'test', '--base-url', 'https://example.com',
                '--api-key-env', 'TEST_KEY', '--models-file', 'unused.json',
                '--allow-network-and-auto-approve', '--simulator-reply-limit', '-1']
        with patch.object(sys, 'argv', argv), \
                patch('scripts.run_small_benchmark.load_tasks', return_value=[object()]), \
                patch('sys.stderr'), \
                self.assertRaises(SystemExit) as raised:
            main()
        self.assertEqual(raised.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
