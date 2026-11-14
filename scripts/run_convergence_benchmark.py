"""Run paired convergence trials with private SWE-bench evaluation.

Requires an existing SWE-bench environment and official dataset JSON.
Stops on the first infrastructure error. No hidden test output reaches Pi.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from harness.agents.convergence import run_container
from harness.evaluation.prediction import collect_prediction
from harness.sandbox.workspace import prepare_workspace
from harness.simulator.openai_compatible import completion
from harness.simulator.user import SimulatedUser
from harness.tasks.schema import Setting, load_tasks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tasks', type=Path, required=True)
    parser.add_argument('--evaluation-dataset', type=Path, required=True)
    parser.add_argument('--evaluation-python', type=Path, required=True)
    parser.add_argument('--models-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=10)
    parser.add_argument('--timeout', type=float, default=1800)
    parser.add_argument('--max-submissions', type=int, default=5)
    parser.add_argument('--coding-question-limit', type=int, default=3)
    parser.add_argument('--provider', default='centinels')
    parser.add_argument('--model', default='gpt-5.6-luna')
    parser.add_argument('--wasabi-model', default='openrouter/qwen/qwen3.8-flash')
    parser.add_argument('--simulator-model', default='gpt-6.1-sol')
    parser.add_argument('--base-url', default='https://centinels.ml2-alpha.com/v1')
    parser.add_argument('--image', default='wasabi-pi:1.4.0-wasabi-614a531')
    parser.add_argument('--allow-network-and-auto-approve', action='store_true')
    args = parser.parse_args()
    if not args.allow_network_and_auto_approve:
        parser.error('Explicit network and approval opt-in required')
    tasks = load_tasks(args.tasks)
    if not 0 < args.count <= len(tasks) or args.timeout <= 0 or args.max_submissions < 1 or args.coding_question_limit < 0:
        parser.error('Invalid limits')
    for key in ('CENTINELS_API_KEY', 'OPENROUTER_API_KEY'):
        if not os.environ.get(key):
            parser.error('Missing ' + key)
    official = {r['instance_id']: r for r in json.loads(args.evaluation_dataset.read_text())}
    tasks = tasks[:args.count]
    for task in tasks:
        if task.instance_id not in official or official[task.instance_id]['base_commit'] != task.base_commit:
            parser.error('Evaluation dataset mismatch: ' + task.instance_id)
    os.umask(0o077)
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    manifest = dict(vars(args), instance_ids=[t.instance_id for t in tasks],
                    protocol='convergence-v1', feedback='boolean-only',
                    selection='first N in dataset order', execution='sequential paired; alternating condition order',
                    tasks_sha256=hashlib.sha256(args.tasks.read_bytes()).hexdigest(),
                    evaluation_sha256=hashlib.sha256(args.evaluation_dataset.read_bytes()).hexdigest())
    (root / 'manifest.json').write_text(json.dumps(manifest, default=str, indent=2))
    complete = completion(args.base_url, args.simulator_model, 'CENTINELS_API_KEY')
    results = []
    for index, task in enumerate(tasks):
        for mode in (('baseline', 'wasabi') if index % 2 == 0 else ('wasabi', 'baseline')):
            directory = root / mode / str(index)
            bundle = directory / 'bundle'
            bundle.mkdir(parents=True)
            row = dict(instance_id=task.instance_id, condition=mode, status='error')
            print(json.dumps(dict(event='start', **row)), flush=True)
            try:
                prepare_workspace(task, bundle / 'workspace')
                (bundle / 'agent-input.json').write_text(json.dumps(task.agent_input(Setting.INTERACTION)))
                simulator = SimulatedUser(task, complete, max_turns=None)

                def evaluate(number, remaining):
                    began = time.monotonic()
                    work = directory / f'submission-{number}'
                    work.mkdir()
                    prediction = work / 'prediction.jsonl'
                    collected = collect_prediction(task, bundle / 'workspace', prediction,
                                                   model_name='convergence')
                    # An empty patch is still evaluated: original checkout may already pass.
                    if not collected['model_patch'].strip():
                        # SWE-bench skips empty patches. A harmless added file makes the
                        # unchanged checkout evaluable without altering existing code/tests.
                        collected['model_patch'] = ('diff --git a/.convergence-empty-patch b/.convergence-empty-patch\n'
                            'new file mode 100644\n--- /dev/null\n+++ b/.convergence-empty-patch\n@@ -0,0 +1 @@\n+empty submission\n')
                        prediction.write_text(json.dumps(collected) + '\n')
                        (work / 'empty-patch.json').write_text('{"evaluation_only_marker": true}\n')
                    dataset = work / 'dataset.json'
                    dataset.write_text(json.dumps([official[task.instance_id]]))
                    budget = remaining - (time.monotonic() - began)
                    if budget <= 0:
                        raise TimeoutError('Deadline exhausted collecting prediction')
                    command = [str(args.evaluation_python.absolute()), '-m', 'swebench.harness.run_evaluation',
                               '--dataset_name', str(dataset), '--predictions_path', str(prediction),
                               '--instance_ids', task.instance_id, '--max_workers', '1',
                               '--timeout', str(max(1, int(budget))), '--cache_level', 'instance',
                               '--clean', 'False', '--run_id', 'submission', '--report_dir', str(work)]
                    with (work / 'evaluation.log').open('w') as log:
                        subprocess.run(command, cwd=work, stdout=log, stderr=subprocess.STDOUT,
                                       check=True, timeout=budget)
                    reports = list(work.glob('logs/run_evaluation/*/*/*/report.json'))
                    if len(reports) != 1:
                        raise RuntimeError('Missing or ambiguous evaluation report; inspect private logs')
                    report = json.loads(reports[0].read_text()).get(task.instance_id, {})
                    if type(report.get('resolved')) is not bool or not report.get('patch_successfully_applied'):
                        raise RuntimeError('Invalid report or patch application failure; inspect private logs')
                    print(json.dumps(dict(event='evaluation', condition=mode, instance_id=task.instance_id,
                                          submission=number, passed=report['resolved'])), flush=True)
                    return report['resolved']

                row.update(run_container(bundle, task, simulator, directory / 'rpc.jsonl',
                           evaluate=evaluate, agent_provider=args.provider, agent_model=args.model,
                           wasabi_model=args.wasabi_model if mode == 'wasabi' else None,
                           approve=True, timeout=args.timeout, max_submissions=args.max_submissions,
                           coding_question_limit=args.coding_question_limit, image=args.image,
                           network=True, env_names=('CENTINELS_API_KEY', 'OPENROUTER_API_KEY'),
                           models_file=args.models_file))
            except Exception as exc:
                row['error'] = f'{type(exc).__name__}: {exc}'
                results.append(row)
                (root / 'results.json').write_text(json.dumps(results, indent=2))
                (root / 'blocked.json').write_text(json.dumps(row, indent=2))
                raise
            results.append(row)
            (root / 'results.json').write_text(json.dumps(results, indent=2))
            print(json.dumps(dict(event='complete', condition=mode, instance_id=task.instance_id,
                                  status=row['status'], submissions=len(row['submissions']))), flush=True)


if __name__ == '__main__':
    main()
