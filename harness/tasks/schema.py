"""Controller-only task records. Never mount these records into agent workspaces."""
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path


class Setting(str, Enum):
    FULL = "full"
    HIDDEN = "hidden"
    INTERACTION = "interaction"


@dataclass(frozen=True)
class Task:
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    original_issue: str
    hints_text: str = ""
    files: str = ""
    patch: str = ""
    test_patch: str = ""

    @classmethod
    def from_dict(cls, record: dict) -> "Task":
        required = ("instance_id", "repo", "base_commit", "problem_statement", "original_issue")
        for key in required:
            if not isinstance(record.get(key), str) or not record[key].strip():
                raise ValueError(f"Missing or invalid task field: {key}")
        values = {key: record.get(key, "") for key in cls.__dataclass_fields__}
        for key, value in values.items():
            if not isinstance(value, str):
                raise ValueError(f"Expected text for {key}")
        return cls(**values)

    def agent_input(self, setting: Setting) -> dict[str, str]:
        """Explicit allowlist; only FULL intentionally exposes the original issue."""
        setting = Setting(setting)
        issue = self.original_issue if setting == Setting.FULL else self.problem_statement
        return {"instance_id": self.instance_id, "repo": self.repo,
                "base_commit": self.base_commit, "problem_statement": issue}


def load_tasks(path: str | Path) -> list[Task]:
    tasks = []
    seen = set()
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                task = Task.from_dict(json.loads(line))
                if task.instance_id in seen:
                    raise ValueError(f"Duplicate task: {task.instance_id}")
            except (ValueError, TypeError) as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error
            seen.add(task.instance_id)
            tasks.append(task)
    return tasks
