import json
from pathlib import Path
import sys
import tempfile
import unittest

from harness.agents.runner import run_rpc, RunError
from harness.simulator.user import SimulatedUser
from harness.tasks.schema import Task

TASK = Task('id', 'owner/repo', 'a' * 40, 'public problem', 'PRIVATE ISSUE', patch='SECRET PATCH')

FAKE_PI = r'''
import json, sys
read = lambda: json.loads(sys.stdin.buffer.readline())
def send(value):
    print(json.dumps(value), flush=True)
prompt = read()
assert prompt['message'] == 'public problem'
def dialog(method, title, options=[]):
    send({'type':'extension_ui_request','id':'dlg','method':method,'title':title,'options':options})
    return read()
assert dialog('select', 'Wasabi · Clarification\ndetails', ['1. Which?', 'Finish clarification and review prompt'])['value'] == '1. Which?'
assert dialog('select', 'Wasabi · Which?\nCurrent answer: Not answered', ['Write an answer'])['value'] == 'Write an answer'
assert dialog('editor', 'Wasabi · Which? (close to return to controls)')['value'] == 'simulated answer'
assert dialog('select', 'Wasabi · Clarification\ndetails', ['1. Which?', 'Finish clarification and review prompt'])['value'] == 'Finish clarification and review prompt'
assert dialog('select', 'Wasabi · Review final prompt\ndraft', ['Approve and send', 'Cancel request'])['value'] == 'Approve and send'
send({'type':'response','id':'task','success':True,'data':{'disposition':'started'}})
send({'type':'agent_settled'})
'''

class RunnerTests(unittest.TestCase):
    def test_dialog_roundtrip_and_private_log(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'log.jsonl'
            observed = []
            def complete(messages):
                observed.extend(messages)
                return 'simulated answer'
            result = run_rpc([sys.executable, '-u', '-c', FAKE_PI], TASK,
                             SimulatedUser(TASK, complete), path, approve=True, timeout=5)
            self.assertTrue(result['settled'])
            self.assertEqual(result['disposition'], 'started')
            self.assertIn('PRIVATE ISSUE', observed[0]['content'])
            records = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertNotIn('PRIVATE ISSUE', path.read_text())
            self.assertNotIn('SECRET PATCH', path.read_text())
            self.assertTrue(any(x['record'].get('value') == 'simulated answer'
                                for x in records if isinstance(x['record'], dict)))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                run_rpc([], TASK, SimulatedUser(TASK, complete), path)

    def test_unexpected_exit_and_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            for script, name in [('pass', 'exit'), ('import time; time.sleep(30)', 'timeout')]:
                with self.assertRaises(RunError):
                    run_rpc([sys.executable, '-c', script], TASK,
                            SimulatedUser(TASK, lambda _: 'answer'),
                            Path(directory) / name, timeout=0.2)
