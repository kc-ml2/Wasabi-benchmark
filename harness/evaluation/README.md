# SWE-bench evaluation

After the agent has stopped, collect a prediction using a fresh controller-only
baseline fetched at the task's base commit. The agent workspace has no `.git`;
its files are copied into a disposable baseline and a Git-compatible patch is
created without changing the workspace. Do not run collection concurrently with
an agent. Predictions and evaluation artifacts are controller-private.

```python
from harness.tasks.schema import load_tasks
from harness.evaluation.prediction import collect_prediction

task = next(t for t in load_tasks('data/tasks.jsonl')
            if t.instance_id == 'astropy__astropy-12907')
collect_prediction(task, '.sandbox/astropy__astropy-12907/workspace',
                   'runs/swebench/predictions.jsonl')
```

The output is exclusive (existing files are not overwritten), and contains the
SWE-bench `instance_id`, `model_patch`, and `model_name_or_path` fields. Test
changes are collected as part of the agent patch, as in InteractiveSWEAgents.
SWE-bench resets the files touched by its own test patch before applying that
patch; other agent-modified files are not automatically filtered.

Install the evaluation harness in a separate ignored environment. This smoke
run used `swebench==4.1.0` and the public Verified test split:

```bash
python3 -m venv .sandbox/swebench-venv
.sandbox/swebench-venv/bin/pip install 'swebench==4.1.0'
mkdir -p runs/swebench/eval
# Run from this directory so Docker/test logs remain controller-private.
cd runs/swebench/eval
../../../.sandbox/swebench-venv/bin/python -m swebench.harness.run_evaluation \
  --dataset_name SWE-bench/SWE-bench_Verified --split test \
  --instance_ids astropy__astropy-12907 --predictions_path ../predictions.jsonl \
  --max_workers 1 --timeout 1800 --cache_level instance \
  --run_id astropy12907 --report_dir .
```

The harness downloads the dataset and task image, applies the prediction and
hidden tests in a separate evaluation container, and records reports and logs
under the current directory. It requires Docker and network access. Use a fresh
run ID and output path for each run. Never mount these artifacts into the agent.
The evaluation can execute untrusted agent code; Docker access and image trust
are security-sensitive. This is not a fully automated batch pipeline.
