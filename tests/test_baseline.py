import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from harness.agents.baseline import QUESTION_PARSER_VERSION, extract_question, run_rpc, run_container
from harness.agents.rpc import RunError
from harness.simulator.user import SimulatedUser
from test_runner import TASK


SCRIPT = r'''
import json, sys
read = lambda: json.loads(sys.stdin.readline())
def send(x): print(json.dumps(x), flush=True)
def respond(p, text):
    send({'type':'response','id':p['id'],'success':True,'data':{'disposition':'started'}})
    send({'type':'message_end','message':{'role':'assistant','content':[{'type':'text','text':text}]}})
    send({'type':'agent_settled'})
p = read()
assert 'public problem' in p['message']
assert 'PRIVATE ISSUE' not in p['message']
for i in range(LIMIT + 1):
    respond(p, '<user_question>Which behavior?</user_question>')
    p = read()
    assert p['message'] == ('answer' if i < LIMIT else 'Please continue working on the task. Do NOT ask for more help.')
respond(p, FINAL)
'''


class BaselineTests(unittest.TestCase):
    def test_reply_limits_and_private_logs(self):
        for limit in (0, 1, 2, 3):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as directory:
                calls = []
                def complete(messages):
                    calls.append(messages)
                    return 'answer'
                simulator = SimulatedUser(TASK, complete, max_turns=limit)
                log = Path(directory) / 'rpc.jsonl'
                script = f'LIMIT={limit}\nFINAL="Fixed the issue."\n' + SCRIPT
                result = run_rpc([sys.executable, '-u', '-c', script], TASK, simulator, log, timeout=5)
                self.assertEqual(len(calls), limit)
                self.assertEqual(result['simulator_turns'], limit)
                self.assertEqual(len(result['interactions']), limit + 1)
                self.assertTrue(result['interactions'][-1]['limit_reached'])
                self.assertEqual(log.stat().st_mode & 0o777, 0o600)
                self.assertNotIn('SECRET PATCH', log.read_text())
                self.assertNotIn('PRIVATE ISSUE', log.read_text())

    def test_repeated_question_after_limit_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            script = 'LIMIT=0\nFINAL="<user_question>Again?</user_question>"\n' + SCRIPT
            with self.assertRaisesRegex(RunError, 'after the reply limit'):
                run_rpc([sys.executable, '-u', '-c', script], TASK,
                        SimulatedUser(TASK, lambda _: self.fail('Unexpected API call'), 0),
                        Path(directory) / 'log', timeout=5)

    def test_no_question_does_not_call_simulator(self):
        with tempfile.TemporaryDirectory() as directory:
            script = 'LIMIT=-1\nFINAL="Fixed. Does this help?"\n' + SCRIPT
            result = run_rpc([sys.executable, '-u', '-c', script], TASK,
                             SimulatedUser(TASK, lambda _: self.fail('Unexpected API call')),
                             Path(directory) / 'log', timeout=5)
            self.assertEqual(result['interactions'], [])

    def test_single_envelope_with_surrounding_text(self):
        self.assertEqual(extract_question('Before <user_question> Which? </user_question> After'),
                         ('Which?', 'Before ', ' After'))
        self.assertIsNone(extract_question('Fixed. Any questions?'))

    def test_invalid_envelopes(self):
        cases = [
            '<user_question></user_question>',
            '<user_question>   </user_question>',
            '<user_question>Missing close',
            'Missing open</user_question>',
            '</user_question>reversed<user_question>',
            '<user_question>A</user_question><user_question>B</user_question>',
            '<user_question>A<user_question>B</user_question></user_question>',
            '<user_question x="1">A</user_question>',
            '<user_question>A</user_question><user_question',
        ]
        for text in cases:
            with self.subTest(text=text), self.assertRaises(RunError):
                extract_question(text)

    def test_surrounding_text_is_logged_not_forwarded(self):
        with tempfile.TemporaryDirectory() as directory:
            script = 'LIMIT=1\nFINAL="Fixed."\n' + SCRIPT.replace(
                "respond(p, '<user_question>Which behavior?</user_question>')",
                "respond(p, 'Explanation. <user_question>Which behavior?</user_question> More prose.')")
            simulator = SimulatedUser(TASK, lambda _: 'answer', max_turns=1)
            log = Path(directory) / 'rpc.jsonl'
            with patch.object(simulator, 'reply', wraps=simulator.reply) as reply:
                result = run_rpc([sys.executable, '-u', '-c', script], TASK, simulator, log, timeout=5)
                reply.assert_called_once_with('Which behavior?')
            self.assertEqual(result['simulator_turns'], 1)
            text = log.read_text()
            self.assertIn('ignored_prefix', text)
            self.assertIn('Explanation.', text)
            self.assertIn('More prose.', text)
            self.assertIn(QUESTION_PARSER_VERSION, text)

    def test_container_overrides_wasabi_entrypoint(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / 'bundle'
            (bundle / 'workspace').mkdir(parents=True)
            from harness.tasks.schema import Setting
            (bundle / 'agent-input.json').write_text(json.dumps(TASK.agent_input(Setting.INTERACTION)))
            with patch('harness.agents.baseline.run_rpc', return_value={}) as rpc:
                run_container(bundle, TASK, SimulatedUser(TASK, lambda _: 'answer'),
                              Path(directory) / 'log', agent_provider='centinels',
                              agent_model='gpt-5.6-luna')
            command = rpc.call_args.args[0]
            self.assertIn('--entrypoint', command)
            self.assertIn('--no-extensions', command)
            self.assertNotIn('/opt/wasabi', command)
            self.assertNotIn('-e', command)
