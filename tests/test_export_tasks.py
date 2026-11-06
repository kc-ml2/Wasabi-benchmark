"""Synthetic workbook round trips; no benchmark-private data required."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from openpyxl import Workbook
except ImportError:
    Workbook = None

from harness.tasks.schema import load_tasks, Setting
from scripts.export_tasks import main


@unittest.skipIf(Workbook is None, "Install .[data] for workbook tests")
class ExportTests(unittest.TestCase):
    def export(self, directory, records):
        source = Path(directory) / "source.xlsx"
        output = Path(directory) / "tasks.jsonl"
        workbook = Workbook()
        headers = list(records[0])
        workbook.active.append(headers)
        for record in records:
            workbook.active.append([record[key] for key in headers])
        workbook.active.append([None] * len(headers))
        workbook.save(source)
        workbook.close()
        with patch("sys.argv", ["export_tasks", "--source", str(source),
                                "--output", str(output)]):
            main()
        return output

    def record(self):
        return dict(instance_id="example-1", repo="owner/repo", base_commit="a" * 40,
                    problem_statement="Public summary: 질문", original_issue="Private issue",
                    hints_text=None, patch="Private answer", test_patch="Private test",
                    FAIL_TO_PASS='["test_example"]')

    def test_round_trip_and_public_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.export(directory, [self.record()])
            tasks = load_tasks(output)
            self.assertEqual(len(tasks), 1)
            task = tasks[0]
            self.assertEqual(task.instance_id, "example-1")
            self.assertEqual(task.repo, "owner/repo")
            self.assertEqual(task.base_commit, "a" * 40)
            self.assertEqual(task.problem_statement, "Public summary: 질문")
            raw = json.loads(output.read_text())
            self.assertEqual(raw["FAIL_TO_PASS"], '["test_example"]')
            self.assertEqual(raw["hints_text"], "")
            self.assertEqual(raw["patch"], "Private answer")
            for setting in (Setting.HIDDEN, Setting.INTERACTION):
                public = task.agent_input(setting)
                self.assertEqual(set(public), {
                    "instance_id", "repo", "base_commit", "problem_statement"})
                self.assertNotIn("Private", json.dumps(public))

    def test_duplicate_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Workbook row 3: Duplicate"):
                self.export(directory, [self.record(), self.record()])
            self.assertFalse((Path(directory) / "tasks.jsonl").exists())

    def test_missing_required_field_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            record = self.record()
            record["problem_statement"] = None
            with self.assertRaisesRegex(ValueError, "problem_statement"):
                self.export(directory, [record])
