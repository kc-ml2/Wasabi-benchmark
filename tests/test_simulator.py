import unittest
from harness.tasks.schema import Task
from harness.simulator.user import SimulatedUser, LIMIT_REPLY

RECORD = dict(instance_id="example-1", repo="owner/repo", base_commit="abc",
              problem_statement="Summary", original_issue="Private issue",
              patch="Secret patch", test_patch="Secret tests", hints_text="Private hint")


class SimulatorTests(unittest.TestCase):
    def test_exact_turn_limit(self):
        calls = []
        def complete(messages):
            calls.append(messages)
            return "Answer"
        user = SimulatedUser(Task.from_dict(RECORD), complete)
        for _ in range(3):
            self.assertEqual(user.reply("Question?"), "Answer")
        self.assertEqual(user.reply("Another?"), LIMIT_REPLY)
        self.assertEqual(len(calls), 3)
        self.assertIn("Private issue", calls[0][0]["content"])
        self.assertNotIn("Secret patch", calls[0][0]["content"])
        self.assertEqual(len(user.history), 7)

    def test_failure_does_not_consume_turn(self):
        user = SimulatedUser(Task.from_dict(RECORD), lambda _: "")
        with self.assertRaises(ValueError):
            user.reply("Question?")
        self.assertEqual(user.turns, 0)
        self.assertEqual(len(user.history), 1)


if __name__ == "__main__":
    unittest.main()
