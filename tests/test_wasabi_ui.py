import unittest
from harness.agents.wasabi_ui import WasabiDialog
from harness.simulator.user import SimulatedUser
from harness.tasks.schema import Task


class WasabiUITests(unittest.TestCase):
    def setUp(self):
        task = Task('id', 'org/repo', 'a' * 40, 'public', 'private issue')
        self.messages = []
        self.simulator = SimulatedUser(task, lambda messages: self.answer(messages))
        self.adapter = WasabiDialog(self.simulator, approve=True)

    def answer(self, messages):
        self.messages = messages
        return 'Use the documented behavior.'

    def dialog(self, method, title, options=()):
        return self.adapter.respond({'type': 'extension_ui_request', 'id': '1',
                                     'method': method, 'title': title, 'options': options})

    def test_question_answer_and_approval(self):
        opts = ['1. Which behavior?', 'Finish clarification and review prompt', 'Cancel request']
        self.assertEqual(self.dialog('select', 'Wasabi · Clarification\nDetails', opts)['value'], opts[0])
        self.assertEqual(self.dialog('select', 'Wasabi · Which behavior?\nCurrent answer: Not answered',
                                     ['Write an answer'])['value'], 'Write an answer')
        self.assertEqual(self.dialog('editor', 'Wasabi · Which behavior? (close to return to controls)')['value'],
                         'Use the documented behavior.')
        self.assertIn('private issue', self.messages[0]['content'])
        self.assertEqual(self.dialog('select', 'Wasabi · Clarification\nDetails', opts)['value'], opts[1])
        self.assertEqual(self.dialog('select', 'Wasabi · Review final prompt\nDraft',
                                     ['Approve and send', 'Cancel request'])['value'], 'Approve and send')
        self.assertEqual([item['event'] for item in self.adapter.log], ['clarification', 'approval'])

    def test_unknown_and_review_without_approval_fail_closed(self):
        adapter = WasabiDialog(self.simulator)
        request = {'type': 'extension_ui_request', 'id': '2', 'method': 'select',
                   'title': 'unknown', 'options': ['Allow']}
        self.assertTrue(adapter.respond(request)['cancelled'])
        request.update(title='Wasabi · Review final prompt\nDraft', options=['Approve and send', 'Cancel request'])
        self.assertEqual(adapter.respond(request)['value'], 'Cancel request')

    def test_recovery_preserves_original_and_requires_approval(self):
        request = {'type': 'extension_ui_request', 'id': 'recovery', 'method': 'editor',
                   'title': 'Wasabi · Review response and edit prompt\nUnvalidated text',
                   'prefill': 'Original request'}
        self.assertEqual(self.adapter.respond(request)['value'], 'Original request')
        self.assertTrue(WasabiDialog(self.simulator).respond(request)['cancelled'])
        self.assertEqual(self.dialog('select', 'Wasabi · Review final prompt (manual recovery)\nOriginal request',
                                     ['Approve and send', 'Cancel request'])['value'], 'Approve and send')
        self.assertEqual([item['event'] for item in self.adapter.log], ['recovery', 'recovery_approval'])
        request.pop('prefill')
        self.assertTrue(self.adapter.respond(request)['cancelled'])
        self.assertEqual(self.simulator.turns, 0)

    def test_wait_dialog_is_not_cancelled(self):
        self.assertIsNone(self.dialog('select', 'Wasabi · Checking request (Esc to stop waiting)',
                                      ['Stop waiting']))

    def test_turn_limit_finishes_without_more_questions(self):
        self.simulator.max_turns = 0
        response = self.dialog('select', 'Wasabi · Clarification\nDetails',
                               ['1. Question?', 'Finish clarification and review prompt'])
        self.assertEqual(response['value'], 'Finish clarification and review prompt')
