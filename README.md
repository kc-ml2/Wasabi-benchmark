# Wasabi benchmark

An independent **Pi + Wasabi evaluation harness**, separate from OpenHands and
inspired by InteractiveSWEAgents' data, experimental settings, and user simulator.
This is an initial port: Pi/Wasabi RPC execution and a single-task SWE-bench
evaluation have been smoke-tested; automated batch evaluation remains unfinished.
Wasabi is pinned as a Git submodule in `external/wasabi`.

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
live models and a controller-side simulator for one task.
Workbook regression tests skip without `openpyxl`. After installing `.[data]`,
run `python -m unittest discover -s tests -v` to include them.
See [workspace preparation](harness/sandbox/README.md) for task selection, Docker
commands, data boundaries and the verified smoke-test result.

## Experimental settings

| Setting | Issue provided to the agent | User simulator |
|---|---|---|
| `full` | `original_issue` | Disabled |
| `hidden` | `problem_statement` | Disabled |
| `interaction` | `problem_statement` | Answers using the original issue, hints, and file information |

These names make the upstream base/hidden/interact distinction explicit. The
current runner uses the `interaction` input and connects the simulator to Wasabi's
initial clarification dialogs. It does not enforce all three settings at runtime
or connect coding-time agent questions. Initial clarification can involve multiple
question-and-answer turns, but it finishes before coding begins. A future
multi-step interaction mode could pause coding when the agent asks a question,
route it to the user simulator, and resume the agent with the answer; this is not
implemented or validated. The two interaction stages should remain separately
configurable and logged. Wasabi prompt clarification and Crunch code-change
approval are separate interactions.

The upstream FakeUser condition `turns > 3` permits four replies. This port uses
`>=` to enforce the intended maximum of three. Models and API keys are not
hardcoded.

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

- The workbook was converted and loaded (500 tasks). One real task,
  `astropy__astropy-12907`, was run end to end: Wasabi asked two questions,
  the simulator answered, the final prompt was automatically approved, and Pi
  edited the checkout. SWE-bench reported `resolved: true` (2 FAIL_TO_PASS and
  13 PASS_TO_PASS tests passed). This is a single smoke test, not a batch result.
- The experiment's treatment of initial Wasabi clarification versus coding-time
  questions is **not yet decided**. Coding-time questions are not connected.
- There is no unified reproducible command for configuration, execution and
  evaluation, and automated multi-task batch evaluation is not implemented.
  `configs/models.example.json` illustrates configuration but is not read by the
  runner. See the linked sandbox and evaluation docs for current manual steps.
- Network access and API-key forwarding are opt-in. When enabled, agent
  processes can access forwarded credentials and make outbound connections;
  use restricted, revocable credentials and treat the container as defense in
  depth rather than a complete security boundary. Logs can contain private data.

See `reference/interactive_swe_agents/README.md` for source attribution and
licensing. The original repository is neither modified nor moved during porting.
