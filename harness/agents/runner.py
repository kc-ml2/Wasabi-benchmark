"""Controller-side Pi RPC runner. Logs and simulator remain controller-private."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

from harness.agents.wasabi_ui import WasabiDialog
from harness.simulator.user import SimulatedUser
from harness.sandbox.docker import container_command
from harness.tasks.schema import Task, Setting


class RunError(RuntimeError):
    pass


def run_container(bundle: str | Path, task: Task, simulator: SimulatedUser,
                  log_path: str | Path, *, approve: bool = False,
                  timeout: float = 300, image: str = "wasabi-pi:1.4.0") -> dict:
    """Run the pinned image offline; model/network configuration is not enabled."""
    bundle = Path(bundle).resolve()
    if json.loads((bundle / "agent-input.json").read_text(encoding="utf-8")) != task.agent_input(Setting.INTERACTION):
        raise ValueError("Bundle input does not match selected task")
    log = Path(log_path).resolve()
    if log.is_relative_to(bundle):
        raise ValueError("Controller log must not be inside the agent bundle")
    command = container_command(bundle, ["--offline"], image=image)
    command.insert(2, "-i")
    return run_rpc(command, task, simulator, log, approve=approve, timeout=timeout)


def run_rpc(command: list[str], task: Task, simulator: SimulatedUser, log_path: str | Path,
            *, approve: bool = False, timeout: float = 300) -> dict:
    """Run one task over RPC, fail closed on unfamiliar dialogs and errors.

    Logs can contain private simulator answers and must never be agent-mounted.
    The supplied command must start a fresh Pi RPC process with stdin open.
    """
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite previous run artifacts; file contents are controller-private.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    events = queue.Queue()
    adapter = WasabiDialog(simulator, approve=approve)
    process = None
    with os.fdopen(fd, "w", encoding="utf-8") as log:
        def record(direction, message):
            log.write(json.dumps({"direction": direction, "record": message}, ensure_ascii=False) + "\n")
            log.flush()

        try:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, bufsize=0, start_new_session=True)
            def read_stdout():
                try:
                    for line in process.stdout:
                        events.put(("stdout", line))
                finally:
                    events.put(("eof", None))

            def read_stderr():
                for line in process.stderr:
                    events.put(("stderr", line))

            threading.Thread(target=read_stdout, daemon=True).start()
            threading.Thread(target=read_stderr, daemon=True).start()

            def send(message):
                record("send", message)
                process.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode())
                process.stdin.flush()

            prompt = task.agent_input(Setting.INTERACTION)["problem_statement"]
            send({"id": "task", "type": "prompt", "message": prompt})
            deadline = time.monotonic() + timeout
            accepted = None
            settled = False
            while not (accepted is not None and (accepted == "handled" or settled)):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RunError("Pi RPC timed out")
                try:
                    kind, raw = events.get(timeout=remaining)
                except queue.Empty as error:
                    raise RunError("Pi RPC timed out") from error
                if kind == "eof":
                    raise RunError("Pi exited before task completed")
                if kind == "stderr":
                    record("stderr", raw.decode("utf-8", errors="replace").rstrip("\n"))
                    continue
                try:
                    event = json.loads(raw)
                except (ValueError, UnicodeDecodeError) as error:
                    raise RunError("Invalid Pi RPC record") from error
                if not isinstance(event, dict):
                    raise RunError("Invalid Pi RPC record")
                record("receive", event)
                if event.get("type") == "extension_ui_request":
                    response = adapter.respond(event)
                    if response is not None:
                        send(response)
                elif event.get("type") == "response" and event.get("id") == "task":
                    if not event.get("success"):
                        raise RunError("Pi rejected task prompt: " + str(event.get("error", "unknown")))
                    accepted = event.get("data", {}).get("disposition")
                    if accepted not in ("started", "handled"):
                        raise RunError("Unexpected prompt disposition: " + str(accepted))
                elif event.get("type") == "agent_settled":
                    settled = True
            result = {"disposition": accepted, "settled": settled, "interactions": adapter.log}
            record("result", result)
            return result
        finally:
            if process is not None:
                if process.stdin:
                    process.stdin.close()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    import signal
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                if process.stdout:
                    process.stdout.close()
                if process.stderr:
                    process.stderr.close()
