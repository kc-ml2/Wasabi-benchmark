"""Offline checkout, CLI and Docker policy regression tests."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from harness.sandbox.docker import container_command
from harness.sandbox.workspace import prepare_workspace
from harness.tasks.schema import Task, Setting
from scripts.prepare_task import main


TASK = Task("example-1", "owner/repo", "a" * 40, "Public", "Private",
            patch="Secret answer", test_patch="Secret test")


class WorkspaceTests(unittest.TestCase):
    def test_real_local_checkout_pins_old_commit_and_strips_history(self):
        run = subprocess.run
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()

            def git(*args):
                return run(["git", "-C", str(source), *args], check=True,
                           capture_output=True, text=True).stdout.strip()

            git("init")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            (source / "code.py").write_text("old\n")
            git("add", ".")
            git("commit", "-m", "base")
            base = git("rev-parse", "HEAD")
            (source / "code.py").write_text("future answer\n")
            git("commit", "-am", "future")

            def local_fetch(command, **kwargs):
                self.assertIn('gc.auto=0', command)
                self.assertIn('maintenance.auto=false', command)
                # Exercise real Git, redirecting only the remote to a local fixture.
                if "fetch" in command:
                    command = [str(source) if arg == "https://github.com/owner/repo.git"
                               else arg for arg in command]
                return run(command, **kwargs)

            destination = Path(directory) / "checkout"
            with patch("harness.sandbox.workspace.subprocess.run", side_effect=local_fetch):
                prepare_workspace(replace(TASK, base_commit=base), destination)
            self.assertEqual((destination / "code.py").read_text(), "old\n")
            self.assertFalse((destination / ".git").exists())
            with self.assertRaises(FileExistsError):
                prepare_workspace(TASK, destination)
            self.assertEqual((destination / "code.py").read_text(), "old\n")

    def test_invalid_repo_or_commit_never_runs_git(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("harness.sandbox.workspace.subprocess.run") as run:
                for task in (replace(TASK, repo="../bad/path"),
                             replace(TASK, base_commit="main")):
                    with self.assertRaises(ValueError):
                        prepare_workspace(task, Path(directory) / "checkout")
                run.assert_not_called()

    def test_failure_cleans_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("harness.sandbox.workspace.subprocess.run", side_effect=RuntimeError):
                with self.assertRaises(RuntimeError):
                    prepare_workspace(TASK, Path(directory) / "checkout")
            self.assertEqual(list(Path(directory).iterdir()), [])


class BundleTests(unittest.TestCase):
    def invoke(self, root, instance_id="example-1"):
        tasks = root / "tasks.jsonl"
        tasks.write_text(json.dumps(TASK.__dict__) + "\n")
        with patch("sys.argv", ["prepare_task", "--tasks", str(tasks),
                                "--instance-id", instance_id,
                                "--output", str(root / "bundles")]):
            main()

    def test_cli_public_input_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def prepare(task, destination):
                destination.mkdir()
            with patch("scripts.prepare_task.prepare_workspace", side_effect=prepare) as checkout:
                self.invoke(root)
                bundle = root / "bundles/example-1"
                self.assertEqual(json.loads((bundle / "agent-input.json").read_text()),
                                 TASK.agent_input(Setting.INTERACTION))
                with self.assertRaises(FileExistsError):
                    self.invoke(root)
                self.assertEqual(checkout.call_count, 1)

    def test_unknown_id_does_not_prepare(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("scripts.prepare_task.prepare_workspace") as checkout:
                with self.assertRaises(SystemExit):
                    self.invoke(Path(directory), "unknown")
                checkout.assert_not_called()
                self.assertFalse((Path(directory) / "bundles").exists())

    def test_docker_mounts_and_rejects_private_fields_or_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            (bundle / "workspace").mkdir()
            agent_input = bundle / "agent-input.json"
            agent_input.write_text(json.dumps(TASK.agent_input(Setting.INTERACTION)))
            command = container_command(bundle, ["python", "--version"])
            for flag in ("--network=none", "--read-only", "--cap-drop=ALL",
                         "--security-opt=no-new-privileges:true", "--memory=2g"):
                self.assertIn(flag, command)
            mounts = [command[i + 1] for i, arg in enumerate(command) if arg == "--mount"]
            self.assertEqual(len(mounts), 2)
            self.assertEqual(mounts[1],
                             f"type=bind,src={agent_input},dst=/input/task.json,readonly")
            self.assertNotIn("--privileged", command)
            with patch.dict('os.environ', {'TEST_API_KEY': 'do-not-log'}):
                online = container_command(bundle, ['true'], network=True, env_names=('TEST_API_KEY',))
                self.assertNotIn('--network=none', online)
                self.assertIn('TEST_API_KEY', online)
                self.assertNotIn('do-not-log', ' '.join(online))
            with self.assertRaises(ValueError):
                container_command(bundle, ['true'], env_names=('NOT_SET_FOR_TEST_123',))
            models = bundle / 'models.json'
            models.write_text('{}')
            configured = container_command(bundle, ['true'], models_file=models)
            self.assertIn(f'type=bind,src={models},dst=/tmp/models.json,readonly', configured)
            self.assertIn('PI_CODING_AGENT_DIR=/tmp', configured)
            agent_input.write_text(json.dumps(TASK.__dict__))
            with self.assertRaises(ValueError):
                container_command(bundle, ["true"])
            agent_input.unlink()
            agent_input.symlink_to(bundle / "private.json")
            with self.assertRaises(ValueError):
                container_command(bundle, ["true"])
