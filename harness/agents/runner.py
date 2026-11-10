"""Controller-side Wasabi runner; shared transport lives in rpc.py."""
import json
from pathlib import Path

from harness.agents.rpc import RunError, rpc_session
from harness.agents.wasabi_ui import WasabiDialog
from harness.simulator.user import SimulatedUser
from harness.sandbox.docker import container_command
from harness.tasks.schema import Task, Setting


def run_container(bundle: str | Path, task: Task, simulator: SimulatedUser,
                  log_path: str | Path, *, approve: bool = False,
                  timeout: float = 300, image: str = "wasabi-pi:1.4.0",
                  agent_provider: str, agent_model: str, wasabi_model: str,
                  network: bool = False, env_names: tuple[str, ...] = (),
                  models_file: str | Path | None = None) -> dict:
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
                   wasabi_model=wasabi_model)


def run_rpc(command: list[str], task: Task, simulator: SimulatedUser, log_path: str | Path,
            *, approve: bool = False, timeout: float = 300,
            wasabi_model: str | None = None) -> dict:
    """Run Wasabi clarification over RPC, failing closed on unfamiliar dialogs."""
    adapter = WasabiDialog(simulator, approve=approve)
    with rpc_session(command, log_path, timeout) as rpc:
        prompt = task.agent_input(Setting.INTERACTION)["problem_statement"]
        if wasabi_model:
            rpc.send({"id": "setup", "type": "prompt", "message": "/wasabi-model " + wasabi_model})
        else:
            rpc.send({"id": "task", "type": "prompt", "message": prompt})
        accepted = None
        configured = False
        settled = False
        while not (accepted is not None and (accepted == "handled" or settled)):
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
            elif event.get("type") == "response" and event.get("id") == "task":
                if not event.get("success"):
                    raise RunError("Pi rejected task prompt: " + str(event.get("error", "unknown")))
                accepted = event.get("data", {}).get("disposition")
                if accepted not in ("started", "handled"):
                    raise RunError("Unexpected prompt disposition: " + str(accepted))
            elif event.get("type") == "agent_settled":
                settled = True
        result = {"disposition": accepted, "settled": settled, "interactions": adapter.log}
        rpc.record("result", result)
        return result
