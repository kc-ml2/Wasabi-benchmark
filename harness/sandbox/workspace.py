"""Prepare a disposable checkout without copying controller-private data."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from harness.tasks.schema import Task


def prepare_workspace(task: Task, destination: str | Path) -> Path:
    """Clone GitHub over HTTPS and pin HEAD; refuse any existing destination.

    Fetch only the requested commit, then remove Git metadata so future history,
    remotes and checkout hooks are not available to the agent.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", task.repo):
        raise ValueError("Expected a GitHub owner/repository")
    if not re.fullmatch(r"[0-9a-f]{40}", task.base_commit):
        raise ValueError("Expected a full lowercase commit SHA")
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".checkout-", dir=destination.parent))
    try:
        def git(*args: str) -> str:
            return subprocess.run(
                ["git", "-c", "core.hooksPath=/dev/null",
                 "-c", "gc.auto=0", "-c", "maintenance.auto=false",
                 "-C", str(staging), *args],
                check=True, text=True, capture_output=True, timeout=300,
            ).stdout.strip()

        git("init")
        git("fetch", "--depth=1", "--no-tags", "--",
            f"https://github.com/{task.repo}.git", task.base_commit)
        git("checkout", "--detach", "FETCH_HEAD")
        if git("rev-parse", "HEAD") != task.base_commit:
            raise ValueError("Checkout does not match base_commit")
        shutil.rmtree(staging / ".git")
        # mkdir is exclusive, unlike rename which can replace an empty directory.
        destination.mkdir()
        try:
            for child in staging.iterdir():
                child.rename(destination / child.name)
        except BaseException:
            shutil.rmtree(destination)
            raise
        return destination
    finally:
        shutil.rmtree(staging, ignore_errors=True)
