import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from harness.evaluation.prediction import collect_prediction, prediction_collector
from harness.tasks.schema import Task

TASK = Task('fixture', 'owner/repo', 'a'*40, 'problem', 'private')

class PredictionTests(unittest.TestCase):
    def test_cached_checkout_is_pristine_and_cleaned_on_error(self):
        paths = []
        def baseline(task, dest):
            dest.mkdir()
            (dest / 'file').write_text('original\n')
            paths.append(dest)
            return dest
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / 'workspace'
            workspace.mkdir()
            with patch('harness.evaluation.prediction.prepare_workspace', side_effect=baseline) as prepare:
                with self.assertRaisesRegex(RuntimeError, 'fixture'):
                    with prediction_collector(TASK) as collect:
                        for i in range(2):
                            (workspace / 'file').write_text(f'change {i}\n')
                            result = collect(workspace, root / f'{i}.jsonl')
                            self.assertIn('-original', result['model_patch'])
                            self.assertEqual((paths[0] / 'file').read_text(), 'original\n')
                        self.assertEqual(prepare.call_count, 1)
                        raise RuntimeError('fixture')
            self.assertFalse(paths[0].exists())

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
            run = subprocess.run
            def checked_git(command, **kwargs):
                self.assertIn('gc.auto=0', command)
                self.assertIn('maintenance.auto=false', command)
                return run(command, **kwargs)
            with patch('harness.evaluation.prediction.prepare_workspace', side_effect=baseline), \
                    patch('harness.evaluation.prediction.subprocess.run', side_effect=checked_git):
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
