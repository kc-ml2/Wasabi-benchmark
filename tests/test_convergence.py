import json
from pathlib import Path
import sys
import tempfile
import unittest

from harness.agents.convergence import FAILURE_FEEDBACK, run_rpc
from harness.agents.rpc import RunError
from harness.simulator.user import SimulatedUser
from test_runner import TASK


SCRIPT = r'''
import json, sys
for text in TEXTS:
    p = json.loads(sys.stdin.readline())
    print(json.dumps(dict(type='response', id=p['id'], success=True,
                         data=dict(disposition='started'))), flush=True)
    print(json.dumps(dict(type='message_end', message=dict(role='assistant',
          content=[dict(type='text', text=text)]))), flush=True)
    print(json.dumps(dict(type='agent_settled')), flush=True)
'''


class ConvergenceTests(unittest.TestCase):
    def run_case(self, texts, evaluate, **kwargs):
        simulator = SimulatedUser(TASK, lambda _: 'Requirement answer.', max_turns=None)
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'rpc.jsonl'
            result = run_rpc([sys.executable, '-u', '-c', 'TEXTS=' + repr(texts) + '\n' + SCRIPT],
                             TASK, simulator, log, evaluate=evaluate, timeout=5, **kwargs)
            records = [json.loads(line) for line in log.read_text().splitlines()]
        return result, records

    def test_failure_question_success(self):
        calls = []
        def evaluate(number, remaining):
            self.assertGreater(remaining, 0)
            calls.append(number)
            return number == 2
        result, records = self.run_case(
            ['Done.', '<user_question>Which behavior?</user_question>', 'Revised.'], evaluate)
        self.assertEqual(calls, [1, 2])
        self.assertEqual(result['status'], 'resolved')
        self.assertEqual(result['coding_simulator_replies'], 1)
        self.assertEqual(result['feedback_count'], 1)
        sent = [r['record']['message'] for r in records if r['direction'] == 'send']
        self.assertEqual(sent[1:], [FAILURE_FEEDBACK, 'Requirement answer.'])

    def test_summary_only_logging_and_submission_counts(self):
        result, records = self.run_case(
            ['<user_question>Which?</user_question>', 'Done.', 'Revised.'],
            lambda number, _: number == 2, detailed_logging=False)
        self.assertEqual(records, [])
        self.assertEqual([s['coding_replies'] for s in result['submissions']], [1, 0])
        self.assertEqual(result['submissions'][-1]['cumulative_coding_replies'], 1)
        self.assertNotIn('question', result['coding_interactions'][0])
        self.assertEqual(result['interactions'], [])

    def test_submission_limit(self):
        result, _ = self.run_case(['Done.', 'Revised.'], lambda *_: False, max_submissions=2)
        self.assertEqual(result['status'], 'submission_limit')
        self.assertEqual(len(result['submissions']), 2)

    def test_first_success_stops(self):
        result, _ = self.run_case(['Done.'], lambda *_: True)
        self.assertEqual(result['feedback_count'], 0)

    def test_non_boolean_evaluation_rejected(self):
        with self.assertRaises(RunError):
            self.run_case(['Done.'], lambda *_: {'passed': False, 'private_log': 'secret'})

    def test_evaluation_error_not_treated_as_failure(self):
        def evaluate(*_):
            raise RuntimeError('Evaluation infrastructure failed')
        with self.assertRaises(RuntimeError):
            self.run_case(['Done.'], evaluate)

    def test_question_limit(self):
        with self.assertRaises(RunError):
            self.run_case(['<user_question>A?</user_question>'] * 2,
                          lambda *_: True, coding_question_limit=0)
