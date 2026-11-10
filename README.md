# Wasabi benchmark

An independent **Pi + Wasabi evaluation harness**, separate from OpenHands and
inspired by InteractiveSWEAgents' data, experimental settings, and user simulator.
This is an initial port with parallel task execution, patch collection, and
separate SWE-bench batch evaluation validated on a 10-task sample. Generation
and evaluation are still separate steps, not one unified command.
Wasabi is pinned as a Git submodule in `external/wasabi` at
`614a531b04d13c4345d6c5983aec0356bdb8eb2a`.

## Language

Use English as the primary language for code, comments, docstrings, and Markdown.
Preserve original benchmark data and quoted source material when appropriate.

## Structure

- `harness/tasks/`: task validation, JSONL loading, and agent-visible field selection
- `harness/simulator/`: user simulator with an injected completion function (three replies by default)
- `harness/sandbox/`: pinned task checkouts and offline Docker isolation
- `harness/agents/`: Pi RPC controller and Wasabi dialog adapter
- `harness/evaluation/`: prediction collection and SWE-bench evaluation instructions
- `scripts/export_tasks.py`: source workbook to JSONL conversion
- `scripts/run_small_benchmark.py`: parallel interaction runs and patch collection
- `configs/`: example experimental settings
- `data/source/`: copied source data and provenance
- `reference/interactive_swe_agents/`: non-executable reference snapshots and license
- `tests/`: unit tests without API calls
- `runs/`: private conversations, interactions, patches, and evaluation results (Git-ignored)

## Getting started

```bash
git submodule update --init --recursive
npm ci  # Node.js >= 22.19.0; installs benchmark Pi 1.4.0
npm --prefix external/wasabi ci  # Wasabi development dependencies
export WASABI_SOURCE="$PWD/external/wasabi"
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[data]'
python -m scripts.export_tasks
python -m unittest discover -s tests -v
```

The source workbook was copied locally and is excluded from Git. On another
machine, see `data/source/README.md` for its provenance. Conversion requires
`openpyxl`; task loading and simulator unit tests need no external packages.
Use `./node_modules/.bin/pi` for the benchmark's pinned Pi version; Wasabi's
own development dependencies include a separate Pi version and do not select the
benchmark runtime. Pi and Wasabi have been exercised in a Docker container with
live models and a controller-side simulator across 10-task runs.
Workbook regression tests skip without `openpyxl`. After installing `.[data]`,
run `python -m unittest discover -s tests -v` to include them.
See [workspace preparation](harness/sandbox/README.md) for task selection, Docker
commands, data boundaries and the verified smoke-test result.

## Required model assignments

Use the following role-specific models for benchmark runs. Do not substitute a
single model for all roles or silently fall back to another provider/model.

| Role | Provider | Model ID |
|---|---|---|
| Pi coding agent | Centinels | `gpt-5.6-luna` |
| Wasabi initial clarification | OpenRouter | `qwen/qwen3.8-flash` |
| User simulator | Centinels | `gpt-6.1-sol` |

Before launching a run, verify each role's model, provider configuration, and
credentials, and record all three assignments in the run manifest. If a required
model is unavailable, stop and ask rather than substitute. The exact Wasabi model
ID above is authoritative; do not infer a different ID from a nickname such as
“flash-next”.

The runner accepts separate agent (`--provider`, `--model`), checker
(`--wasabi-model`, as `provider/model`), and simulator (`--simulator-model`)
assignments. The simulator uses the OpenAI-compatible endpoint and credential
selected by `--base-url` and `--api-key-env`. Always supply both role overrides:
omitting them defaults those roles to the agent model.
`configs/pi-models.json` configures the custom Centinels agent provider;
Wasabi uses Pi's built-in OpenRouter provider with `OPENROUTER_API_KEY`.

**Historical exception:** the AES-38 first-10 smoke run used
`centinels/gpt-5.6-luna` for all three roles. Its results remain a pipeline smoke
test, not a run with the required model assignments above. See
the local, Git-ignored report at `.sandbox/reports/aes38-small-benchmark.md`
(not included in repository clones).

## Run the 10-task sample in parallel

After setup and task export, build a revision-specific image. Existing images do
not update automatically when the submodule changes:

```bash
docker build -f harness/sandbox/Dockerfile.pi \
  -t wasabi-pi:1.4.0-wasabi-614a531 .
```

Export `CENTINELS_API_KEY` and `OPENROUTER_API_KEY` through your secret-management
environment; never put their values in tracked files or command arguments.
Then run:

```bash
python -m scripts.run_small_benchmark \
  --output runs/first10-unlimited \
  --count 10 --workers 10 --timeout 600 \
  --image wasabi-pi:1.4.0-wasabi-614a531 \
  --provider centinels --model gpt-5.6-luna \
  --wasabi-model openrouter/qwen/qwen3.8-flash \
  --simulator-model gpt-6.1-sol \
  --base-url https://api.example.invalid/v1 \
  --api-key-env CENTINELS_API_KEY \
  --container-api-key-env CENTINELS_API_KEY \
  --container-api-key-env OPENROUTER_API_KEY \
  --models-file configs/pi-models.json \
  --unlimited-simulator-replies \
  --allow-network-and-auto-approve
```

This selects the first 10 records in dataset order, not a random sample. Use a
fresh output directory: existing directories are rejected. The image flag is
important because the runner's default remains the older `wasabi-pi:1.4.0` tag.
Omit `--unlimited-simulator-replies` to retain the default three-reply cap.
The RPC timeout remains active in unlimited mode; it is not a total deadline
for checkout preparation and patch collection.

Artifacts include `manifest.json`, `results.json`, numbered `*.rpc.jsonl` logs,
numbered `*.prediction.jsonl` files, and isolated agent bundles. Individual task
errors are recorded without stopping the other tasks; inspect `results.json`
rather than treating process exit or `completed` as proof of a correct patch.
Here, `completed` means the RPC session settled, not that tests passed.

### Checker-failure recovery

With automatic approval enabled, a checker failure opens the new Wasabi recovery
flow. The adapter returns the original prompt unchanged and explicitly approves
it, ignoring the unvalidated checker response. It records `recovery` and
`recovery_approval` separately from normal clarification. This is an automated
experiment policy, **not human or simulator approval**, and does not mean the
checker validated the prompt. Unknown dialogs still fail closed.

### Evaluate the generated patches

After generation finishes, combine the prediction files from that run into a
single JSONL file and run the separate SWE-bench harness with `--max_workers 10`.
See [evaluation instructions](harness/evaluation/README.md) for environment setup,
dataset selection, and the evaluation command. Use a fresh run ID and private
output directory. The generation manifest's `evaluation: not performed` field
is a creation-time snapshot; subsequent evaluation reports are authoritative
for test outcomes. The generation script does not launch evaluation or update
that field afterward.

## Experimental settings

| Setting | Issue provided to the agent | User simulator |
|---|---|---|
| `full` | `original_issue` | Disabled |
| `hidden` | `problem_statement` | Disabled |
| `interaction` | `problem_statement` | Answers using the original issue, hints, and file information |

These names make the upstream base/hidden/interact distinction explicit. The
current runner uses the `interaction` input and connects the simulator to Wasabi's
initial clarification dialogs. It does not enforce all three settings at runtime
or connect coding-time agent questions in the Wasabi runner. A separate
[baseline runner](harness/agents/README.md) now supports coding-time questions
without Wasabi, using an explicit question envelope and bounded simulator replies.
This path has synthetic RPC test coverage and a successful live Luna/Sol
question-answer-resume smoke test.
Initial clarification can involve multiple
question-and-answer turns, but it finishes before coding begins. A future
multi-step interaction mode could pause coding when the agent asks a question,
route it to the user simulator, and resume the agent with the answer; this is not
implemented for the Wasabi runner. The two interaction stages should remain separately
configurable and logged. Wasabi prompt clarification and Crunch code-change
approval are separate interactions.

The upstream FakeUser condition `turns > 3` permits four replies. This port uses
`>=` to enforce the default maximum of three. Unlimited mode uses
`max_turns=None` and answers remaining offered questions without a count cap;
it does not force Wasabi to generate more questions. Models are selected through
CLI arguments and credentials through environment variables.

## Data boundaries

This repository is the **evaluation controller workspace**, not the agent's code
workspace. Do not mount the entire repository, `data/`, or `reference/` into an
agent container. Pass only fields allowed by `Task.agent_input()`, and provide
the original issue and other private context separately to the simulator.
Keep the reference patch and test_patch hidden from both the agent and simulator.
Apply the evaluation test patch in a separate stage after the agent exits.

## Workflow

```text
Controller (private)                         Agent container
┌──────────────────────────────┐            ┌───────────────────────────────┐
│ Excel → JSONL → select task  │            │ Pi + Wasabi                   │
│ original issue / hints       │            │ problem_statement             │
│ reference patch / test data  │            │ checkout @ base_commit        │
│                              │            │                               │
│ simulator (model call)       │◀── RPC ───▶│ clarification → approval     │
│                              │  Q & A     │ → modify checkout             │
└──────────────┬───────────────┘            └──────────────┬────────────────┘
               │            after agent exits               │
               └── private baseline + workspace diff ◀──────┘
                                │
                                ▼
                    SWE-bench prediction JSONL
                                │
                                ▼
               Separate SWE-bench evaluation container
               hidden test patch + tests → report / logs
```

The reference patch and test data are not sent to the agent or simulator.
Simulator answers and automatic approval are recorded in private RPC logs.
The selected approval policy is automatic only when explicitly enabled; it is
not human approval. See [sandbox](harness/sandbox/README.md) for preparation and
runtime security, and [evaluation](harness/evaluation/README.md) for prediction
collection and the SWE-bench command.

## Validation and remaining work

- The workbook was converted and loaded (500 tasks). With the required model
  assignments and Wasabi `614a531`, the first-10 sample produced 10 nonempty
  patches in both capped and unlimited runs. Separate parallel SWE-bench
  evaluation resolved 5/10 in the capped run and 4/10 in the unlimited run,
  with no evaluation execution errors.
- Neither run exceeded three simulator replies (maximum two in the capped run,
  three in the unlimited run). These results do not establish an effect of
  removing the cap: model responses, recovery paths, and patches varied.
  All 10 tasks are Astropy tasks, not a representative benchmark sample.
- Local, Git-ignored reports live under `.sandbox/reports/`; the unlimited-run
  report is `aes38-unlimited-replies.md`. Raw artifacts remain under `runs/`.
  These files are not included in repository clones.
- Wasabi connects only initial clarification. The separate baseline runner
  connects coding-time questions with a configurable simulator reply cap.
  The [AES-37 baseline experiment](docs/experiments/aes37-baseline.md) completed
  30 evaluations: 5/10, 6/10 and 3/10 resolved across the three reply caps.
  All runs used zero simulator replies, so this does not measure a cap effect.
- `scripts/run_baseline_benchmark.py` runs independent task workspaces across
  reply budgets with bounded parallelism and collects predictions. SWE-bench
  evaluation remains a separate command rather than part of this runner.
- Generation and evaluation are separate commands. `configs/models.example.json`
  is illustrative and is not read by the runner. Model settings must be passed
  explicitly using the CLI arguments above.
- Dedicated Wasabi model-call audit-log retention is not yet wired into the
  benchmark runner. UI reply counts must not be reported as checker invocation
  counts.
- Network access and API-key forwarding are opt-in. When enabled, agent
  processes can access forwarded credentials and make outbound connections;
  use restricted, revocable credentials and treat the container as defense in
  depth rather than a complete security boundary. Logs can contain private data.

See `reference/interactive_swe_agents/README.md` for source attribution and
licensing. The original repository is neither modified nor moved during porting.
