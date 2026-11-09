"""Fail-closed adapter for Wasabi RPC dialogs; private task stays in controller."""
import re
from harness.simulator.user import SimulatedUser


class WasabiDialog:
    """Answer each clarification once, then explicitly approve the review.

    Approval is an experimental policy, not a human approval. Unrecognized
    dialogs cancel rather than silently forwarding a request.
    """
    def __init__(self, simulator: SimulatedUser, *, approve: bool = False):
        self.simulator = simulator
        self.approve = approve
        self.answered = set()
        self.pending_question = None
        self.log = []

    def respond(self, request: dict) -> dict | None:
        if request.get("type") != "extension_ui_request":
            return None
        method = request.get("method")
        if method not in ("select", "editor", "input", "confirm"):
            return None
        response = {"type": "extension_ui_response", "id": request["id"]}
        title = request.get("title", "")
        # Wasabi uses a background select while the model is running. Responding
        # with cancellation means "stop waiting"; leave it pending instead.
        if method == "select" and (title.startswith("Wasabi · Checking request (Esc to stop waiting)")
                                   or title.startswith("Wasabi · Clarifying request (Esc to stop waiting)")):
            return None
        options = request.get("options", [])
        value = None
        if method == "select" and title.startswith("Wasabi · Clarification\n"):
            questions = [(option, re.sub(r"^\d+\. ", "", option)) for option in options
                         if re.match(r"^\d+\. ", option)]
            remaining = [(option, question) for option, question in questions
                         if question not in self.answered]
            if remaining and self.simulator.turns < self.simulator.max_turns:
                value, self.pending_question = remaining[0]
            elif "Finish clarification and review prompt" in options:
                value = "Finish clarification and review prompt"
        elif method == "select" and self.pending_question and title.startswith(
                "Wasabi · " + self.pending_question + "\nCurrent answer:"):
            if "Write an answer" in options:
                value = "Write an answer"
        elif method == "editor" and self.pending_question and title.startswith(
                "Wasabi · " + self.pending_question + " (close to return to controls)"):
            value = self.simulator.reply(self.pending_question)
            self.answered.add(self.pending_question)
            self.log.append({"event": "clarification", "question": self.pending_question,
                             "answer": value})
            self.pending_question = None
        elif method == "select" and title.startswith("Wasabi · Review final prompt\n"):
            if self.approve and "Approve and send" in options:
                value = "Approve and send"
                self.log.append({"event": "approval", "policy": "automatic", "review": title})
            elif "Cancel request" in options:
                value = "Cancel request"
        elif method == "select" and title.startswith("Wasabi · Recovery\n"):
            if "Cancel request" in options:
                value = "Cancel request"
        if value is None:
            response["cancelled"] = True
            self.log.append({"event": "cancelled_dialog", "title": title, "method": method})
        else:
            response["value"] = value
        return response
