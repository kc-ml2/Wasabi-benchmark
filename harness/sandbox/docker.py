"""Restricted Docker command construction; no daemon access at import time."""
import json
import os
from pathlib import Path


AGENT_FIELDS = {"instance_id", "repo", "base_commit", "problem_statement"}


def container_command(bundle: str | Path, command: list[str], *,
                      image: str = "wasabi-sandbox:local",
                      network: bool = False, env_names: tuple[str, ...] = (),
                      models_file: str | Path | None = None) -> list[str]:
    """Mount only a prepared checkout and an allowlisted input, offline by default.

    Docker is a defense-in-depth boundary, not a guarantee against kernel exploits.
    The caller must use a trusted image and a dedicated disposable bundle.
    """
    bundle = Path(bundle).resolve()
    workspace = bundle / "workspace"
    agent_input = bundle / "agent-input.json"
    if workspace.is_symlink() or not workspace.is_dir():
        raise ValueError("Expected a real workspace directory")
    if agent_input.is_symlink() or not agent_input.is_file():
        raise ValueError("Expected a real agent input file")
    payload = json.loads(agent_input.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != AGENT_FIELDS:
        raise ValueError("Agent input must contain only the four public fields")
    if not all(isinstance(value, str) and value.strip() for value in payload.values()):
        raise ValueError("Agent input fields must be non-empty text")
    if (workspace / ".git").exists():
        raise ValueError("Workspace must not expose Git metadata")
    if any("," in str(path) for path in (workspace, agent_input)):
        raise ValueError("Docker mount paths cannot contain commas")
    if not command or not image or image.startswith("-"):
        raise ValueError("Expected an image and a command")
    import re
    if any(not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) or not os.environ.get(name)
           for name in env_names):
        raise ValueError("Each requested environment variable must be set and have a valid name")
    environment = [item for name in env_names for item in ("--env", name)]
    model_mount = []
    if models_file is not None:
        model_path = Path(models_file).absolute()
        if model_path.is_symlink() or not model_path.is_file() or ',' in str(model_path):
            raise ValueError("Expected a regular models.json file")
        model_mount = ["--env", "PI_CODING_AGENT_DIR=/tmp", "--mount",
                       f"type=bind,src={model_path},dst=/tmp/models.json,readonly"]
    return [
        "docker", "run", "--rm", *( [] if network else ["--network=none"] ), "--read-only",
        *environment, *model_mount,
        "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
        "--pids-limit=256", "--memory=2g", "--cpus=2",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m,mode=1777",
        "--env", "HOME=/tmp", "--workdir", "/workspace",
        "--mount", f"type=bind,src={workspace},dst=/workspace",
        "--mount", f"type=bind,src={agent_input},dst=/input/task.json,readonly",
        image, *command,
    ]
