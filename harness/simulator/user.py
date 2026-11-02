"""Adapted from InteractiveSWEAgents FakeUser; see reference/ attribution.

No API client is created at import time. The controller injects a completion
function, keeping credentials and private issue context outside the agent.
"""
from collections.abc import Callable
from harness.tasks.schema import Task

Completion = Callable[[list[dict[str, str]]], str]
LIMIT_REPLY = "Please continue working on the task. Do NOT ask for more help."


class SimulatedUser:
    def __init__(self, task: Task, complete: Completion, max_turns: int = 3):
        if max_turns < 0:
            raise ValueError("max_turns must be nonnegative")
        self.complete = complete
        self.max_turns = max_turns
        self.turns = 0
        self.history = [{"role": "system", "content": (
            "You are a GitHub user reporting an issue. Respond concisely to a coder "
            "who has only a summarized issue. Answer using the information below; "
            "stay in character. If unrelated or unsure, say: I don't have that information.\n\n"
            f"Issue: {task.original_issue}\nHints: {task.hints_text}\nFiles: {task.files}"
        )}]

    def reply(self, question: str) -> str:
        if not question.strip():
            raise ValueError("question must not be empty")
        if self.turns >= self.max_turns:
            return LIMIT_REPLY
        messages = [dict(message) for message in self.history]
        messages.append({"role": "user", "content": question})
        answer = self.complete(messages)
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Simulator returned an empty or invalid answer")
        self.history.extend([{"role": "user", "content": question},
                             {"role": "assistant", "content": answer}])
        self.turns += 1
        return answer
