# AES-37: baseline evaluation

## Setup

- Agent: Centinels `gpt-5.6-luna`, with Wasabi disabled.
- User simulator: Centinels `gpt-6.1-sol`.
- Runtime image: `wasabi-pi:1.4.0`, overriding the Wasabi entrypoint.
- Selection: first 10 tasks in dataset order (IDs below).
- Dataset JSONL SHA-256: `c2a66a2d75b03724204c2ec69d77a697eaede254fb6f7f9c00db7a131060ea76`.
- Simulator reply caps: 1, 2, 3. Each task/budget pair uses a fresh workspace and
  simulator history. Budgets run sequentially, with 10 workers per budget.
- RPC timeout: 600 seconds; simulator HTTP timeout: 120 seconds.
- Evaluation: SWE-bench Verified test split, 10 workers, 1800-second per-instance
  test timeout, instance-image caching.

A separate live smoke test verified Luna asking a question, Sol answering once,
and Luna resuming to create a file containing the requested greeting.

## Results

All 30 agent runs completed and produced predictions. All 30 evaluations
completed, with zero evaluator errors, incomplete instances or empty patches.

| Reply cap | Resolved | Unresolved | Resolve rate |
|---|---:|---:|---:|
| 1 | 5 | 5 | 50% |
| 2 | 6 | 4 | 60% |
| 3 | 3 | 7 | 30% |
| Total | 14 | 16 | 46.7% |

| Instance ID | Cap 1 | Cap 2 | Cap 3 |
|---|---|---|---|
| astropy__astropy-12907 | Resolved | Resolved | Resolved |
| astropy__astropy-13033 | Unresolved | Unresolved | Unresolved |
| astropy__astropy-13236 | Unresolved | Unresolved | Unresolved |
| astropy__astropy-13398 | Unresolved | Unresolved | Unresolved |
| astropy__astropy-13453 | Unresolved | Resolved | Unresolved |
| astropy__astropy-13579 | Resolved | Resolved | Resolved |
| astropy__astropy-13977 | Unresolved | Unresolved | Unresolved |
| astropy__astropy-14096 | Resolved | Resolved | Unresolved |
| astropy__astropy-14182 | Resolved | Resolved | Unresolved |
| astropy__astropy-14309 | Resolved | Resolved | Resolved |

**All 30 runs used zero simulator replies.** The agent did not request user
input, so the configured caps never affected execution. These results should
be interpreted as three independent no-user-interaction runs on the same 10
tasks, not evidence of a reply-budget effect. A run can contain multiple model
calls and tool executions despite having no user follow-up. The 30 results are
not 30 distinct tasks, and this small Astropy-only sample is not representative
of the full benchmark.

## Reproduction and artifacts

With the dataset, pinned runtime image and `CENTINELS_API_KEY` available,
set `BENCHMARK_BASE_URL` to your API endpoint and update the placeholder
`baseUrl` in your local models configuration before running:

```bash
python3 -m scripts.run_baseline_benchmark \
  --output runs/aes37-baseline-first10 --allow-network \
  --base-url "$BENCHMARK_BASE_URL"
```

Use a new output directory when repeating the experiment. To evaluate, combine
`budget-N/{0..9}/prediction.jsonl` into one predictions JSONL per budget, without
combining different budgets (their instance IDs repeat). For each budget, run
from a separate private evaluation directory:

```bash
/path/to/swebench-venv/bin/python -m swebench.harness.run_evaluation \
  --dataset_name SWE-bench/SWE-bench_Verified --split test \
  --predictions_path /absolute/path/to/budget-N/evaluation/predictions.jsonl \
  --max_workers 10 --timeout 1800 --cache_level instance \
  --run_id aes37-baseline-budget-N --report_dir .
```

Replace `N` with 1, 2 or 3; use fresh run IDs for repeat evaluations. See the
[evaluation guide](../../harness/evaluation/README.md) for environment setup.
The recorded evaluation also explicitly selected the 10 IDs in the table.
Model outputs may vary on rerun; Docker tags and the public evaluation dataset
are not immutable content hashes.

Local evidence is retained under `runs/aes37-baseline-first10/`:

- `manifest.json`: original execution configuration and dataset fingerprint.
  Its `evaluation: not performed` field describes launch-time state, not the
  subsequently completed evaluations.
- `results.json`: agent execution results, including actual reply counts.
- `evaluation-results.json`: consolidated per-instance evaluation reports.
- `budget-N/evaluation/`: submitted predictions, exact command, exit status,
  aggregate report, and per-instance test logs/reports.

Private conversations, task workspaces, predictions and raw evaluation logs
remain Git-ignored. Only this aggregate result summary is committed.
