"""Shared private logging and lifecycle for a fresh Pi RPC subprocess."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import threading
import time


class RunError(RuntimeError):
    pass


class RpcSession:
    def __init__(self, process, log, timeout):
        self.process = process
        self.log = log
        self.deadline = time.monotonic() + timeout
        self.events = queue.Queue()
        for stream, kind in ((process.stdout, "stdout"), (process.stderr, "stderr")):
            threading.Thread(target=self._read, args=(stream, kind), daemon=True).start()

    def _read(self, stream, kind):
        try:
            for line in stream:
                self.events.put((kind, line))
        finally:
            if kind == "stdout":
                self.events.put(("eof", None))

    def record(self, direction, message):
        self.log.write(json.dumps({"direction": direction, "record": message}, ensure_ascii=False) + "\n")
        self.log.flush()

    def send(self, message):
        self.record("send", message)
        try:
            self.process.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode())
            self.process.stdin.flush()
        except BrokenPipeError as error:
            raise RunError("Pi exited while sending a command") from error

    def receive(self):
        while True:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise RunError("Pi RPC timed out")
            try:
                kind, raw = self.events.get(timeout=remaining)
            except queue.Empty as error:
                raise RunError("Pi RPC timed out") from error
            if kind == "eof":
                raise RunError("Pi exited before task completed")
            if kind == "stderr":
                self.record("stderr", raw.decode("utf-8", errors="replace").rstrip("\n"))
                continue
            try:
                event = json.loads(raw)
            except (ValueError, UnicodeDecodeError) as error:
                raise RunError("Invalid Pi RPC record") from error
            if not isinstance(event, dict):
                raise RunError("Invalid Pi RPC record")
            self.record("receive", event)
            return event


@contextmanager
def rpc_session(command, log_path, timeout=300):
    """Use an exclusive 0600 log; always reap the subprocess and its process group."""
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    process = None
    with os.fdopen(fd, "w", encoding="utf-8") as log:
        try:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, bufsize=0, start_new_session=True)
            yield RpcSession(process, log, timeout)
        finally:
            if process is not None:
                process.stdin.close()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                process.stdout.close()
                process.stderr.close()
