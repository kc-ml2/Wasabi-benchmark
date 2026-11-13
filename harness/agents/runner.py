"""Controller-side Wasabi runner; shared transport lives in rpc.py."""
import json
from pathlib import Path

from harness.agents.rpc import RunError, rpc_session
from harness.agents.baseline import PROTOCOL, QUESTION_PARSER_VERSION, extract_question
from harness.simulator.user import LIMIT_REPLY
from harness.agents.wasabi_ui import WasabiDialog
from harness.simulator.user import SimulatedUser
from harness.sandbox.docker import container_command
from harness.tasks.schema import Task, Setting


def run_container(bundle: str | Path, task: Task, simulator: SimulatedUser,
                  log_path: str | Path, *, approve: bool = False,
                  timeout: float = 300, image: str = "wasabi-pi:1.4.0",
                  agent_provider: str, agent_model: str, wasabi_model: str,
                  network: bool = False, env_names: tuple[str, ...] = (),
                  models_file: str | Path | None = None,
                  coding_question_limit: int = 0) -> dict:
    """Run Pi with explicit models; network and credential forwarding are opt-in."""
    import re
    for value in (agent_provider, agent_model, wasabi_model):
        if not re.fullmatch(r"[A-Za-z0-9_.:/-]+", value) or value.startswith("-"):
            raise ValueError("Invalid model or provider identifier")
    if "/" not in wasabi_model:
        raise ValueError("Wasabi model must be provider/model")
    bundle = Path(bundle).resolve()
    if json.loads((bundle / "agent-input.json").read_text(encoding="utf-8")) != task.agent_input(Setting.INTERACTION):
        raise ValueError("Bundle input does not match selected task")
    log = Path(log_path).resolve()
    if log.is_relative_to(bundle):
        raise ValueError("Controller log must not be inside the agent bundle")
    args = ["--provider", agent_provider, "--model", agent_model]
    if not network:
        args.append("--offline")
    command = container_command(bundle, args, image=image, network=network,
                                env_names=env_names, models_file=models_file)
    command.insert(2, "-i")
    return run_rpc(command, task, simulator, log, approve=approve, timeout=timeout,
                   wasabi_model=wasabi_model, coding_question_limit=coding_question_limit)


def run_rpc(command: list[str], task: Task, simulator: SimulatedUser, log_path: str | Path,
            *, approve: bool = False, timeout: float = 300,
            wasabi_model: str | None = None, coding_question_limit: int = 0) -> dict:
    """Run Wasabi clarification over RPC, failing closed on unfamiliar dialogs."""
    if coding_question_limit < 0:
        raise ValueError('coding_question_limit must be nonnegative')
    if coding_question_limit and simulator.max_turns is not None:
        raise ValueError('Coding questions require unlimited Wasabi simulator replies')
    adapter = WasabiDialog(simulator, approve=approve)
    dialog_log = []
    coding_interactions = []
    coding_replies = 0
    limit_sent = False
    turn = 0
    prompt_id = 'task'
    final_text = ''
    with rpc_session(command, log_path, timeout) as rpc:
        prompt = task.agent_input(Setting.INTERACTION)["problem_statement"]
        if coding_question_limit:
            prompt = PROTOCOL + prompt
        if wasabi_model:
            rpc.send({"id": "setup", "type": "prompt", "message": "/wasabi-model " + wasabi_model})
        else:
            rpc.send({"id": "task", "type": "prompt", "message": prompt})
        accepted = None
        configured = False
        settled = False
        while True:
            event = rpc.receive()
            if event.get("type") == "extension_ui_request":
                if (event.get("method") == "notify" and
                        event.get("message") == "Wasabi model: " + str(wasabi_model)):
                    configured = True
                response = adapter.respond(event)
                if response is not None:
                    rpc.send(response)
            elif event.get("type") == "response" and event.get("id") == "setup":
                if not event.get("success") or not configured:
                    raise RunError("Wasabi model selection failed or was not confirmed")
                rpc.send({"id": "task", "type": "prompt", "message": prompt})
            elif event.get("type") == "response" and event.get("id") == prompt_id:
                if not event.get("success"):
                    raise RunError("Pi rejected task prompt: " + str(event.get("error", "unknown")))
                accepted = event.get("data", {}).get("disposition")
                if accepted not in ("started", "handled"):
                    raise RunError("Unexpected prompt disposition: " + str(accepted))
            elif event.get('type') == 'message_end':
                message = event.get('message', {})
                if message.get('role') == 'assistant':
                    if message.get('stopReason') in ('error', 'aborted'):
                        raise RunError('Wasabi coding assistant failed: ' + str(message.get('errorMessage', 'unknown')))
                    final_text = ''.join(p.get('text', '') for p in message.get('content', [])
                                         if p.get('type') == 'text').strip()
            elif event.get("type") == "agent_settled":
                settled = True
            if accepted is None or (accepted != 'handled' and not settled):
                continue
            if accepted == 'handled' or not coding_question_limit:
                break
            if not final_text:
                raise RunError('Wasabi coding assistant settled without final text')
            parsed = extract_question(final_text)
            if parsed is None:
                break
            if limit_sent:
                raise RunError('Agent asked again after the reply limit notice')
            question, prefix, suffix = parsed
            rpc.record('question_parse', dict(parser_version=QUESTION_PARSER_VERSION,
                       raw_text=final_text, question=question, ignored_prefix=prefix, ignored_suffix=suffix))
            exhausted = coding_replies >= coding_question_limit
            answer = LIMIT_REPLY if exhausted else simulator.reply(question)
            if not exhausted:
                coding_replies += 1
            limit_sent = exhausted
            interaction = dict(question=question, answer=answer, limit_reached=exhausted)
            coding_interactions.append(interaction)
            rpc.record('coding_interaction', interaction)
            # Every user reply is a fresh regular prompt, through the Wasabi extension.
            # Reset dialog selection state, but keep the simulator's shared history.
            dialog_log.extend(adapter.log)
            adapter = WasabiDialog(simulator, approve=approve)
            turn += 1
            prompt_id = f'task-{turn}'
            accepted = None
            settled = False
            final_text = ''
            rpc.send({'id': prompt_id, 'type': 'prompt', 'message': answer})
        dialog_log.extend(adapter.log)
        result = {"disposition": accepted, "settled": settled, "interactions": dialog_log,
                  'coding_interactions': coding_interactions, 'coding_simulator_replies': coding_replies,
                  'wasabi_simulator_replies': simulator.turns - coding_replies,
                  'coding_question_limit': coding_question_limit,
                  'question_parser_version': QUESTION_PARSER_VERSION if coding_question_limit else None}
        rpc.record("result", result)
        return result
