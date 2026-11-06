# Task workspace preparation

From the repository root, with `.[data]` installed and the workbook present:

```bash
python -m scripts.export_tasks
python -m unittest discover -s tests -v
docker build -t wasabi-sandbox:local harness/sandbox
python -m scripts.prepare_task --instance-id astropy__astropy-12907 \
  --run python --version
```

Preparation fetches the specified GitHub commit, verifies HEAD, and removes Git
metadata. It creates `.sandbox/<instance_id>/workspace/` and `agent-input.json`.
Existing bundles are never overwritten; use a fresh `--output` directory for a
new run. Git and network access are needed for preparation. Docker is needed
only with `--run`; building the image also requires network access.

The container mounts only the writable checkout at `/workspace` and the read-only
input at `/input/task.json`. Input fields are `instance_id`, `repo`, `base_commit`,
and `problem_statement` (the interaction setting). The controller keeps the
workbook, JSONL, original issue, hints, reference patch and test patch. Neither
the agent nor simulator should receive reference patches or evaluation tests.

Execution is offline, non-root on a non-root host account, with a read-only root
filesystem, dropped capabilities, no privilege escalation, and CPU/memory/PID
limits. No home directory, credentials or Docker socket is mounted. Use a
trusted image and dedicated bundles only; this is defense in depth, not a
security guarantee. Do not use a root host account. The checkout is disposable;
Docker writes can change host workspace files.

## Verified smoke test

- Real workbook: 500 records converted and loaded.
- Selected task: `astropy__astropy-12907`, `astropy/astropy`, commit
  `d16bfe05a744909de4b27f5875fe0d4ed41ce607` fetched and verified.
- Container: checkout writable, public input read-only, no Git metadata or Docker
  socket exposed in the checked locations.
- Offline regression suite: synthetic workbook conversion, public-field selection,
  local Git commit pinning, failure cleanup, overwrite protection and mount policy.
  Workbook tests skip without `openpyxl`; install `.[data]` to run all tests.

The separate Pi image can be built with:

```bash
docker build -f harness/sandbox/Dockerfile.pi -t wasabi-pi:1.4.0 .
```

`harness.agents.runner.run_container` connects Pi RPC to a `SimulatedUser`
with an injected completion function. Pass `agent_provider` and `agent_model`
for Pi's `--provider`/`--model`, and `wasabi_model` as `provider/model` for
Wasabi's `/wasabi-model` command. Selection must be confirmed before the task
is sent. `configs/models.example.json` is illustrative; it is not read yet.

The default is offline. Pass `network=True` to enable Docker's normal network,
and `env_names=("OPENAI_API_KEY",)` (for example) to pass only named, already
set host environment variables. Keys are not placed in command arguments, but
are visible to container processes, the Docker daemon and privileged host users.
With network enabled, agent code can make unrestricted outbound connections and
could disclose credentials or files. Use a limited, revocable key in a trusted
experiment; this is not a strong boundary against a malicious agent. The host
simulator completion function needs its own provider and credentials.

Private RPC logs are created outside the bundle (new files, mode 0600). Automatic
final approval must be explicitly enabled; unknown dialogs are cancelled. Unit
tests use a fake RPC process. Real model interaction, a completion client and
agent coding-time questions are not yet validated or implemented. RPC logs can
contain private answers; do not share or mount them. These images are not yet
Astropy test evaluation environments.
