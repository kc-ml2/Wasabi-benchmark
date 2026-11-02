# Wasabi installation and Ambig-SWE evaluation plan

## Goal

Build a small evaluation harness independent of OpenHands in
`~/wasabi-benchmark/`, starting with one issue to verify end-to-end execution.

**Wasabi installation and Ambig-SWE evaluation are separate tasks.** Loading
Wasabi does not automatically connect it to the benchmark.

> This document records the earlier environment inspection and proposed plan.
> It is stored at `~/wasabi-benchmark-grayling/setup_plan.md`; the examples below
> retain the original proposed `~/wasabi-benchmark/` path. An independent harness
> skeleton, reference code, and data have now been added to
> `~/wasabi-benchmark-grayling/`, along with task-loading and simulator unit tests.
> Use the current directory for actual work and see `README.md` for the latest
> structure and commands. Wasabi installation, personal configuration changes,
> and benchmark execution have not been performed.

## 1. Current environment

State at the earlier inspection:

- Pi **1.4.0** and Node **24.21.0** are installed.
- Docker and `uv` are installed; Docker usability still needs verification.
- Wasabi source for this benchmark: `~/Wasabi-was/` (directory and README verified).
  `~/src/Wasabi/` also exists but is not the target checkout.
- `~/wasabi-benchmark/` is a Git repository containing two paper PDFs.
- The personal Pi configuration points to `../../Wasabi` (that is, `~/Wasabi`)
  and disables `extensions/wasabi/index.ts`. This differs from the intended
  `~/Wasabi-was` checkout, so specify the package path explicitly as shown below.

Explicitly selecting the benchmark's Wasabi path is safer than immediately
changing the existing personal configuration.

## 2. Verify standalone Wasabi loading

Install and check the local source dependencies:

```bash
cd ~/Wasabi-was
npm ci
npm run check
```

Explicitly load only that package:

```bash
cd ~/wasabi-benchmark

pi --offline --no-session --no-extensions \
  -e ~/Wasabi-was
```

Run this command inside Pi:

```text
/hello
```

Expected response:

```text
Hello! Wasabi is running.
```

This check does not require a model call.

### Compatibility warning

The tested baseline in the Wasabi README is Pi **0.84.4**. The installed version
is **1.4.0**; do not assume compatibility from version numbers alone. Verify
loading and the main features.

## 3. Distinguish evaluation targets

The main features in `~/Wasabi-was` are:

- **Wasabi: a dedicated model checks request ambiguity, conducts private
  clarification, and forwards the final prompt after approval.**
- Session cropping
- LiteLLM session tracking
- **Crunch: human approval and feedback before code changes**

The Ambig-SWE user simulator and automated question-answer routing require
separate implementation.

### Headless execution limitations

According to the Wasabi documentation, Crunch **does not enforce its approval
gate during headless execution without a UI.** In contrast, Wasabi prompt
clarification holds headless input when options remain unresolved or checking
fails. Running `pi --print` alone therefore does not evaluate Wasabi's
question-answer and approval features. Automated evaluation needs an RPC
client/harness that responds to dedicated model selection, clarification
questions, and final prompt approval.

### Recommended evaluation stages

| Stage | Purpose | Execution mode |
|---|---|---|
| Manual smoke test | Solve one issue with Pi + Wasabi and verify questions and feedback | TUI |
| Automated baseline | Measure performance without interaction | JSON / RPC / SDK |
| Automated interaction | Connect agent questions to the user simulator | RPC / SDK harness |
| Crunch evaluation | Measure change approval, rejection, and feedback effects | TUI or an RPC client handling approval responses |

**Issue clarification and code-change approval are different interactions.**
Keep their logs and experimental conditions separate. Wasabi clarification
questions, answers, and review history are not saved in the main session
conversation; the harness must record them separately for interaction evaluation.
Specify a non-interactive baseline explicitly, for example by disabling prompt
clarification with `/wasabi off`.

## 4. Minimal Ambig-SWE setup

Proposed directory layout:

```text
~/wasabi-benchmark/
├── README.md
├── data/
│   └── tasks.jsonl       # Tasks converted from the source workbook
├── scripts/
│   └── export_tasks.py
├── harness/              # Pi execution and user simulator integration
├── configs/              # Models, budgets, and interaction settings
└── runs/                 # Conversations, final patches, and test results
```

### Execution environment

Use Docker containers isolated from the host. Benchmark code and tests will be
executed, so avoid unnecessary exposure of personal settings, API keys, and other
working directories.

### Execution flow for one task

1. Extract the issue, `repo`, and `base_commit` from the workbook.
2. Prepare the code checkout and test environment for that commit.
3. Give the coding agent **only `problem_statement`** as the issue text.
4. Give the user simulator the original issue and hints.
5. Route simulator answers to Pi when questions arrive.
6. Save the final diff.
7. Apply the test patch and run tests in a separate evaluation stage.

### Prevent evaluation data leakage

Hide the following from the coding agent's workspace in hidden/interaction settings:

- `original_issue`
- Reference `patch`
- `test_patch`

Placing source data and reference answers where the agent can read them causes
evaluation data leakage.

## 5. Initial implementation scope

Start with the following checks rather than running all 500 tasks immediately:

1. Verify loading and compatibility of `~/Wasabi-was`.
2. Convert the workbook to JSONL.
3. Prepare an isolated environment for one task.
4. Run Pi + Wasabi manually in the TUI.
5. Verify that questions, answers, patches, and test results are saved.

Add the automated user simulator and batch runner after validating this flow.
