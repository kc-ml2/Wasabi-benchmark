"""Prepare a disposable task bundle; optionally run an offline container command."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

from harness.sandbox.docker import container_command
from harness.sandbox.workspace import prepare_workspace
from harness.tasks.schema import Setting, load_tasks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=Path("data/tasks.jsonl"))
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--output", type=Path, default=Path(".sandbox"))
    parser.add_argument("--image", default="wasabi-sandbox:local")
    parser.add_argument("--run", nargs=argparse.REMAINDER,
                        help="Run the remaining arguments inside Docker after preparation")
    args = parser.parse_args()
    tasks = load_tasks(args.tasks)
    matches = [task for task in tasks if task.instance_id == args.instance_id]
    if len(matches) != 1:
        parser.error("Expected exactly one matching instance_id")
    # Reject path traversal in task IDs before creating anything.
    if not args.instance_id or args.instance_id in (".", "..") or any(
        char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
        for char in args.instance_id
    ):
        parser.error("Unsafe instance_id")
    if args.run == []:
        parser.error("--run requires a command")
    bundle = args.output.absolute() / args.instance_id
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.mkdir()  # Exclusive: never overwrite a previous run.
    try:
        prepare_workspace(matches[0], bundle / "workspace")
        payload = matches[0].agent_input(Setting.INTERACTION)
        (bundle / "agent-input.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except BaseException:
        shutil.rmtree(bundle)
        raise
    print(f"Prepared {args.instance_id} at {bundle}")
    if args.run:
        subprocess.run(container_command(bundle, args.run, image=args.image), check=True)


if __name__ == "__main__":
    main()
