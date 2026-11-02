import json
from pathlib import Path
import tempfile
import unittest
from harness.tasks.schema import Task, Setting, load_tasks

RECORD = dict(instance_id="example-1", repo="owner/repo", base_commit="abc",
              problem_statement="Summary", original_issue="Private issue",
              patch="Secret patch", test_patch="Secret tests", hints_text="Private hint")


class TaskTests(unittest.TestCase):
    def test_hidden_and_interaction_do_not_leak(self):
        task = Task.from_dict(RECORD)
        for setting in (Setting.HIDDEN, Setting.INTERACTION):
            public = task.agent_input(setting)
            self.assertEqual(set(public), {"instance_id", "repo", "base_commit", "problem_statement"})
            self.assertEqual(public["problem_statement"], "Summary")
            self.assertNotIn("Private", json.dumps(public))
        self.assertEqual(task.agent_input(Setting.FULL)["problem_statement"], "Private issue")

    def test_load_and_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.jsonl"
            path.write_text(json.dumps(RECORD) + "\n", encoding="utf-8")
            self.assertEqual(len(load_tasks(path)), 1)
            path.write_text((json.dumps(RECORD) + "\n") * 2, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                load_tasks(path)

    def test_required_field(self):
        with self.assertRaises(ValueError):
            Task.from_dict({**RECORD, "base_commit": ""})


if __name__ == "__main__":
    unittest.main()
