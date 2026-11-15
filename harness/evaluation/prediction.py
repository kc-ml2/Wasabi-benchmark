"""Build SWE-bench predictions from controller-only baseline snapshots."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from harness.sandbox.workspace import prepare_workspace
from harness.tasks.schema import Task


@contextmanager
def prediction_collector(task: Task):
    """Cache one pristine checkout for a trial; clean it on success or exception.

    Stored in controller temporary storage, never mounted into the agent.
    Each submission works on a disposable copy, leaving the cached tree intact.
    """
    with tempfile.TemporaryDirectory(prefix='wasabi-pristine-') as directory:
        pristine = prepare_workspace(task, Path(directory) / 'baseline')

        def collect(workspace, output, *, model_name='pi-wasabi'):
            return collect_prediction(task, workspace, output, model_name=model_name,
                                      _pristine=pristine)

        yield collect


def collect_prediction(task: Task, workspace: str | Path, output: str | Path,
                       *, model_name: str = "pi-wasabi", _pristine: Path | None = None) -> dict:
    """Compare a fresh pinned baseline against the agent tree using isolated Git.

    The fresh repository and index never enter the agent workspace. Never collect
    while an agent is running. Agent files are untrusted: Git hooks and global
    configuration are disabled, and symlinks are copied without following them.
    """
    workspace = Path(workspace).resolve(strict=True)
    if not workspace.is_dir() or (workspace / '.git').exists() or (workspace / '.git').is_symlink():
        raise ValueError('Expected an agent workspace without Git metadata')
    output = Path(output).absolute()
    if output.is_relative_to(workspace):
        raise ValueError('Prediction must remain outside agent workspace')
    with tempfile.TemporaryDirectory(prefix='wasabi-baseline-') as directory:
        root = Path(directory)
        baseline = (prepare_workspace(task, root / 'baseline') if _pristine is None
                    else Path(shutil.copytree(_pristine, root / 'baseline', symlinks=True)))
        env = {**os.environ, 'HOME': str(root), 'GIT_CONFIG_NOSYSTEM': '1',
               'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_ATTR_NOSYSTEM': '1',
               'GIT_AUTHOR_NAME': 'Benchmark', 'GIT_AUTHOR_EMAIL': 'benchmark@invalid',
               'GIT_COMMITTER_NAME': 'Benchmark', 'GIT_COMMITTER_EMAIL': 'benchmark@invalid'}
        def git(*args):
            # Detached maintenance can race TemporaryDirectory cleanup.
            return subprocess.run(['git', '-c', 'core.hooksPath=/dev/null',
                                  '-c', 'gc.auto=0', '-c', 'maintenance.auto=false',
                                  '-C', str(baseline), *args],
                                  env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
        git('init', '-q')
        git('add', '-f', '--all')
        git('commit', '-qm', 'baseline')
        # Replace only the disposable baseline working tree; preserve its Git index.
        for child in baseline.iterdir():
            if child.name == '.git':
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        for child in workspace.iterdir():
            dest = baseline / child.name
            if child.is_symlink():
                dest.symlink_to(os.readlink(child))
            elif child.is_dir():
                shutil.copytree(child, dest, symlinks=True, ignore=shutil.ignore_patterns('.git'))
            elif child.is_file():
                shutil.copy2(child, dest, follow_symlinks=False)
            else:
                raise ValueError(f'Unsupported workspace entry: {child.name}')
        git('add', '-f', '--all')
        patch = git('diff', '--cached', '--binary', '--no-ext-diff', '--no-textconv', 'HEAD').decode('utf-8')
    result = {'instance_id': task.instance_id, 'model_patch': patch, 'model_name_or_path': model_name}
    output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(json.dumps(result, ensure_ascii=False) + '\n')
    return result
