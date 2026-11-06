# Wasabi benchmark

An independent **Pi + Wasabi evaluation harness**, separate from OpenHands and
inspired by InteractiveSWEAgents' data, experimental settings, and user simulator.
This is an initial port: **Pi execution, Docker isolation, patch evaluation, and
live model calls are not implemented yet.** Set `WASABI_SOURCE` to the local
Wasabi checkout (for example, `export WASABI_SOURCE="$HOME/Wasabi-was"`).

## Language

Use English as the primary language for code, comments, docstrings, and Markdown.
Preserve original benchmark data and quoted source material when appropriate.

## Structure

- `harness/tasks/`: task validation, JSONL loading, and agent-visible field selection
- `harness/simulator/`: user simulator with an injected completion function (three replies by default)
- `harness/agents/`, `sandbox/`, `evaluation/`: planned implementation areas
- `scripts/export_tasks.py`: source workbook to JSONL conversion
- `configs/`: example experimental settings
- `data/source/`: copied source data and provenance
- `reference/interactive_swe_agents/`: non-executable reference snapshots and license
- `tests/`: unit tests without API calls
- `runs/`: future conversations, interactions, patches, and evaluation results (Git-ignored)

## Getting started

```bash
export WASABI_SOURCE="$HOME/Wasabi-was"  # Set this to your checkout
python3 -m unittest discover -s tests -v
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[data]'
python -m scripts.export_tasks
```

The source workbook was copied locally and is excluded from Git. On another
machine, see `data/source/README.md` for its provenance. Conversion requires
`openpyxl`; task loading and simulator unit tests need no external packages.

## Experimental settings

| Setting | Issue provided to the agent | User simulator |
|---|---|---|
| `full` | `original_issue` | Disabled |
| `hidden` | `problem_statement` | Disabled |
| `interaction` | `problem_statement` | Answers using the original issue, hints, and file information |

These names make the upstream base/hidden/interact distinction explicit. Only
input field selection is implemented so far; runtime interaction enforcement is
not implemented. Wasabi prompt clarification and Crunch code-change approval
will be treated as separate experimental dimensions.

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

## Next steps

1. Verify Pi/Wasabi loading and the RPC interaction contract.
2. Prepare a Docker workspace and code checkout for one task.
3. Connect Wasabi model selection, clarification, and final approval responses,
   with separate interaction logging.
4. Collect the final diff and evaluate tests in isolation.
5. Run one real task as a smoke test before adding batch execution.

See `reference/interactive_swe_agents/README.md` for source attribution and
licensing. The original repository is neither modified nor moved during porting.
