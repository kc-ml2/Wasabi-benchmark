"""Run a deterministic interaction sample; keep all artifacts controller-private."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import time

from harness.agents.runner import run_container
from harness.evaluation.prediction import collect_prediction
from harness.sandbox.workspace import prepare_workspace
from harness.simulator.openai_compatible import completion
from harness.simulator.user import SimulatedUser
from harness.tasks.schema import Setting, load_tasks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tasks', type=Path, default=Path('data/tasks.jsonl'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=10)
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--provider', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--api-key-env', required=True)
    parser.add_argument('--models-file', type=Path, required=True)
    parser.add_argument('--wasabi-model', help='provider/model; defaults to agent model')
    parser.add_argument('--simulator-model', help='Defaults to agent model')
    parser.add_argument('--container-api-key-env', action='append',
                        help='Repeat for each credential forwarded to containers')
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--image', default='wasabi-pi:1.4.0')
    parser.add_argument('--simulator-reply-limit', type=int, default=3,
                        help='Maximum simulator replies per task (default: 3)')
    parser.add_argument('--unlimited-simulator-replies', action='store_true',
                        help='No reply count cap; the per-task timeout still applies')
    parser.add_argument('--coding-question-limit', type=int, default=0,
                        help='Coding-time user replies, separate from Wasabi (0: legacy mode; try 3)')
    parser.add_argument('--allow-network-and-auto-approve', action='store_true')
    args = parser.parse_args()
    tasks = load_tasks(args.tasks)
    if not 0 < args.count <= len(tasks) or args.timeout <= 0:
        parser.error('count must fit the dataset and timeout must be positive')
    if not args.allow_network_and_auto_approve:
        parser.error('live execution requires explicit network and approval opt-in')
    if args.workers < 1:
        parser.error('workers must be positive')
    if args.simulator_reply_limit < 0:
        parser.error('simulator reply limit must be nonnegative')
    if args.coding_question_limit < 0:
        parser.error('coding question limit must be nonnegative')
    if args.coding_question_limit > 0 or args.unlimited_simulator_replies:
        args.simulator_reply_limit = None
    args.wasabi_model = args.wasabi_model or f'{args.provider}/{args.model}'
    args.simulator_model = args.simulator_model or args.model
    args.container_api_key_env = args.container_api_key_env or [args.api_key_env]
    for name in args.container_api_key_env:
        if not os.environ.get(name):
            parser.error(f'Missing container credential: {name}')
    complete = completion(args.base_url, args.simulator_model, args.api_key_env)
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False)
    selected = tasks[:args.count]
    manifest = {**vars(args), 'instance_ids': [task.instance_id for task in selected],
                'selection': 'first N in dataset order', 'evaluation': 'not performed',
                'interaction_protocol': 'wasabi-return-v1' if args.coding_question_limit else 'wasabi-initial-only',
                'question_parser_version': 'single-envelope-v2' if args.coding_question_limit else None}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, default=str, indent=2) + '\n')
    results = []
    def run_one(index, task):
        started = time.monotonic()
        row = {'instance_id': task.instance_id, 'status': 'error'}
        # Numeric bundle names avoid treating dataset identifiers as filesystem paths.
        bundle = args.output / 'bundles' / str(index)
        bundle.mkdir(parents=True)
        try:
            prepare_workspace(task, bundle / 'workspace')
            (bundle / 'agent-input.json').write_text(json.dumps(task.agent_input(Setting.INTERACTION)))
            simulator = SimulatedUser(task, complete,
                                      max_turns=args.simulator_reply_limit)
            result = run_container(
                bundle, task, simulator, args.output / f'{index}.rpc.jsonl',
                approve=True, timeout=args.timeout, image=args.image, agent_provider=args.provider,
                agent_model=args.model, wasabi_model=args.wasabi_model,
                network=True, env_names=tuple(args.container_api_key_env), models_file=args.models_file,
                coding_question_limit=args.coding_question_limit)
            row.update(result)
            row['simulator_turns'] = simulator.turns
            prediction = collect_prediction(task, bundle / 'workspace',
                                            args.output / f'{index}.prediction.jsonl',
                                            model_name=f'{args.provider}/{args.model}')
            row['patch_bytes'] = len(prediction['model_patch'].encode())
            row['status'] = 'completed' if result['settled'] else 'handled_without_coding'
        except Exception as exc:
            row['error'] = f'{type(exc).__name__}: {exc}'
        row['seconds'] = round(time.monotonic() - started, 2)
        return row

    order = {task.instance_id: index for index, task in enumerate(selected)}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_one, index, task) for index, task in enumerate(selected)]
        for future in as_completed(futures):
            row = future.result()
            results.append(row)
            results.sort(key=lambda item: order[item['instance_id']])
            (args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
            print(json.dumps({k: v for k, v in row.items() if k != 'interactions'}), flush=True)


if __name__ == '__main__':
    main()
