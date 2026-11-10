"""Coding-time user interaction without Wasabi or clarification preprocessing.

Questions use an explicit whole-message envelope, not punctuation heuristics.
Only settled assistant text is routed to the controller-private simulator.
"""
import json
from pathlib import Path
import re

from harness.agents.rpc import RunError, rpc_session
from harness.sandbox.docker import container_command
from harness.simulator.user import LIMIT_REPLY
from harness.tasks.schema import Setting

PROTOCOL = """Work on the following issue. You may ask the reporting user for missing
information during coding. To ask, end your turn with exactly
<user_question>Your question here</user_question>
as your entire final text response, then wait for the reply. Do not use this
wrapper for your final solution. After the user declines further help, finish
using the available information without asking again.

Issue:
"""
QUESTION = re.compile(r"\A<user_question>\s*(.+?)\s*</user_question>\Z", re.DOTALL)


def run_rpc(command, task, simulator, log_path, *, timeout=300):
    """Run a fresh extension-free Pi process with bounded simulator replies.

    One final assistant question message consumes at most one reply, even when
    it contains multiple questions. A single limit notice is allowed; repeated
    questions after that fail rather than creating an unbounded prompt loop.
    """
    interactions = []
    limit_sent = False
    turn = 0
    with rpc_session(command, log_path, timeout) as rpc:
        def prompt(message):
            rpc.send({"id": f"baseline-{turn}", "type": "prompt", "message": message})

        prompt(PROTOCOL + task.agent_input(Setting.INTERACTION)["problem_statement"])
        accepted = settled = False
        final_text = ""
        while True:
            event = rpc.receive()
            kind = event.get("type")
            if kind == "response" and event.get("id") == f"baseline-{turn}":
                if not event.get("success") or event.get("data", {}).get("disposition") != "started":
                    raise RunError("Pi rejected baseline prompt or did not start coding")
                accepted = True
            elif kind == "extension_ui_request":
                raise RunError("Unexpected extension UI in baseline")
            elif kind == "message_end":
                message = event.get("message", {})
                if message.get("role") == "assistant":
                    if message.get("stopReason") in ("error", "aborted"):
                        raise RunError("Baseline assistant failed: " + str(message.get("errorMessage", "unknown")))
                    final_text = "".join(part.get("text", "") for part in message.get("content", [])
                                         if part.get("type") == "text").strip()
            elif kind == "agent_settled":
                settled = True
            if not (accepted and settled):
                continue
            match = QUESTION.fullmatch(final_text)
            if not match:
                if "<user_question>" in final_text or "</user_question>" in final_text:
                    raise RunError("Malformed baseline question envelope")
                if not final_text:
                    raise RunError("Baseline settled without a final assistant response")
                result = {"disposition": "started", "settled": True,
                          "interactions": interactions, "simulator_turns": simulator.turns,
                          "max_turns": simulator.max_turns, "final_text": final_text}
                rpc.record("result", result)
                return result
            if limit_sent:
                raise RunError("Agent asked again after the reply limit notice")
            question = match.group(1).strip()
            if not question:
                raise RunError("Empty baseline question")
            exhausted = simulator.turns >= simulator.max_turns
            answer = LIMIT_REPLY if exhausted else simulator.reply(question)
            limit_sent = exhausted
            interaction = {"question": question, "answer": answer, "limit_reached": exhausted}
            interactions.append(interaction)
            rpc.record("interaction", interaction)
            turn += 1
            accepted = settled = False
            final_text = ""
            prompt(answer)


def run_container(bundle, task, simulator, log_path, *, agent_provider, agent_model,
                  timeout=300, image="wasabi-pi:1.4.0", network=False,
                  env_names=(), models_file=None):
    """Reuse the pinned runtime image but override its Wasabi entrypoint.

    No extension, context file, session, skill or template is loaded. Only the
    public task bundle is mounted; simulator state stays in this controller.
    """
    for value in (agent_provider, agent_model):
        if not re.fullmatch(r"[A-Za-z0-9_.:/-]+", value) or value.startswith("-"):
            raise ValueError("Invalid model or provider identifier")
    bundle = Path(bundle).resolve()
    if json.loads((bundle / "agent-input.json").read_text()) != task.agent_input(Setting.INTERACTION):
        raise ValueError("Bundle input does not match selected task")
    log = Path(log_path).resolve()
    if log.is_relative_to(bundle):
        raise ValueError("Controller log must not be inside the agent bundle")
    args = ["--mode", "rpc", "--no-session", "--no-extensions", "--no-skills",
            "--no-prompt-templates", "--no-themes", "--no-context-files",
            "--provider", agent_provider, "--model", agent_model]
    if not network:
        args.append("--offline")
    command = container_command(bundle, args, image=image, network=network,
                                env_names=env_names, models_file=models_file)
    command[2:2] = ["-i", "--entrypoint", "/opt/runtime/node_modules/.bin/pi"]
    return run_rpc(command, task, simulator, log, timeout=timeout)
