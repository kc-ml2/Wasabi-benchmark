"""Run identical tasks at multiple reply budgets, with bounded parallelism."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import time

from harness.agents.baseline import run_container
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
    parser.add_argument('--workers', type=int, default=10)
    parser.add_argument('--budgets', type=int, nargs='+', default=[1, 2, 3])
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--provider', default='centinels')
    parser.add_argument('--model', default='gpt-5.6-luna')
    parser.add_argument('--simulator-model', default='gpt-6.1-sol')
    parser.add_argument('--base-url', default='https://centinels.ml2-alpha.com/v1')
    parser.add_argument('--api-key-env', default='CENTINELS_API_KEY')
    parser.add_argument('--models-file', type=Path, default=Path('configs/pi-models.json'))
    parser.add_argument('--image', default='wasabi-pi:1.4.0')
    parser.add_argument('--allow-network', action='store_true')
    args = parser.parse_args()
    tasks = load_tasks(args.tasks)
    if not args.allow_network:
        parser.error('Live execution requires --allow-network')
    if not 0 < args.count <= len(tasks) or args.workers <= 0 or args.timeout <= 0:
        parser.error('Invalid count, workers or timeout')
    if not args.budgets or min(args.budgets) < 0 or len(set(args.budgets)) != len(args.budgets):
        parser.error('Budgets must be unique nonnegative integers')
    complete = completion(args.base_url, args.simulator_model, args.api_key_env, timeout=120)
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False)
    selected = tasks[:args.count]
    manifest = {**vars(args), 'instance_ids': [t.instance_id for t in selected],
                'selection': 'first N in dataset order', 'evaluation': 'not performed',
                'tasks_sha256': hashlib.sha256(args.tasks.read_bytes()).hexdigest()}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, default=str, indent=2) + '\n')
    results = []

    def run_one(index, task, budget):
        started = time.monotonic()
        row = {'instance_id': task.instance_id, 'budget': budget, 'index': index, 'status': 'error'}
        root = args.output / f'budget-{budget}' / str(index)
        bundle = root / 'bundle'
        simulator = SimulatedUser(task, complete, max_turns=budget)
        try:
            bundle.mkdir(parents=True)
            prepare_workspace(task, bundle / 'workspace')
            (bundle / 'agent-input.json').write_text(json.dumps(task.agent_input(Setting.INTERACTION)))
            result = run_container(bundle, task, simulator, root / 'rpc.jsonl',
                                   agent_provider=args.provider, agent_model=args.model,
                                   timeout=args.timeout, image=args.image, network=True,
                                   env_names=(args.api_key_env,), models_file=args.models_file)
            row.update(result)
            prediction = collect_prediction(task, bundle / 'workspace', root / 'prediction.jsonl',
                                            model_name=f'baseline/{args.model}/budget-{budget}')
            row.update(status='completed', patch_bytes=len(prediction['model_patch'].encode()))
        except Exception as exc:
            row['error'] = f'{type(exc).__name__}: {exc}'
        row['simulator_turns'] = simulator.turns
        row['seconds'] = round(time.monotonic() - started, 2)
        return row

    # Each budget uses independent fresh workspaces and simulator histories.
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for budget in args.budgets:
            futures = [pool.submit(run_one, i, task, budget) for i, task in enumerate(selected)]
            for future in as_completed(futures):
                row = future.result()
                results.append(row)
                results.sort(key=lambda r: (r['budget'], r['index']))
                temporary = args.output / 'results.json.tmp'
                temporary.write_text(json.dumps(results, indent=2) + '\n')
                temporary.replace(args.output / 'results.json')
                print(json.dumps({k: v for k, v in row.items()
                                  if k not in ('interactions', 'final_text')}), flush=True)
    return 1 if any(r['status'] != 'completed' for r in results) else 0


if __name__ == '__main__':
    raise SystemExit(main())
