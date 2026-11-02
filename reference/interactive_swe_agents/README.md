# Upstream reference (not executable project code)

- Local source: `~/InteractiveSWEAgents/`
- Local checkout origin: `git@github.com:kc-ml2/InteractiveSWEAgents.git`
- Source commit: `00421fe393380d916b9a17b9874949a5c41528cc`
- Original directory: `evaluation/benchmarks/swe_bench/`
- Copied files: `base_run_infer.py`, `hidden_run_infer.py`, `interact_run_infer.py`, `prompt.py`
- License: upstream MIT license reproduced in `LICENSE`

These files are read-only reference snapshots. They retain OpenHands imports and
are not installed as packages or invoked by this project. No OpenHands runtime,
frontend, historical result logs, or credentials were copied.

`harness/simulator/user.py` adapts `FakeUser` from `interact_run_infer.py`:
completion client injection replaces the global API client and fixed model;
questions are strings rather than OpenHands actions; the turn limit is exactly
three; failed completions do not mutate history or consume a turn.

The full/hidden/interaction input split is inspired by the corresponding runners;
the OpenHands-specific instructions and orchestration were not ported.
