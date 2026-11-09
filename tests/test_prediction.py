import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from harness.evaluation.prediction import collect_prediction
from harness.tasks.schema import Task

TASK = Task('fixture', 'owner/repo', 'a'*40, 'problem', 'private')

class PredictionTests(unittest.TestCase):
    def test_patch_applies_and_includes_new_deleted_and_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / 'workspace'
            workspace.mkdir()
            (workspace / 'modified').write_text('after\n')
            (workspace / 'new').write_bytes(b'\0\1binary')
            (workspace / 'link').symlink_to('modified')
            def baseline(task, dest):
                dest.mkdir()
                (dest / 'modified').write_text('before\n')
                (dest / 'deleted').write_text('delete\n')
                return dest
            output = root / 'prediction.jsonl'
            with patch('harness.evaluation.prediction.prepare_workspace', side_effect=baseline):
                result = collect_prediction(TASK, workspace, output)
            self.assertEqual(json.loads(output.read_text()), result)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            target = root / 'target'
            baseline(TASK, target)
            subprocess.run(['git', '-C', str(target), 'init', '-q'], check=True)
            subprocess.run(['git', '-C', str(target), 'apply', '--binary', '-'],
                           input=result['model_patch'].encode(), check=True)
            self.assertEqual((target / 'modified').read_text(), 'after\n')
            self.assertEqual((target / 'new').read_bytes(), b'\0\1binary')
            self.assertFalse((target / 'deleted').exists())
            self.assertEqual(os.readlink(target / 'link'), 'modified')
            with self.assertRaises(FileExistsError):
                with patch('harness.evaluation.prediction.prepare_workspace', side_effect=baseline):
                    collect_prediction(TASK, workspace, output)
