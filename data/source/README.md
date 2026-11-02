# Source data

Copied from `~/InteractiveSWEAgents/evaluation/benchmarks/swe_bench/data/`.
Source commit: `00421fe393380d916b9a17b9874949a5c41528cc`.
See `../../reference/interactive_swe_agents/` for code attribution and licensing.
Verify any separate data redistribution terms before public distribution.

- `full_summaries_verified.xlsx`: local copy; excluded from Git
- `instance_ids.txt`, `subset_ids.txt`, `mappings.json`: upstream auxiliary files

The workbook contains these columns: repo, instance_id, base_commit, patch,
test_patch, original_issue, hints_text, created_at, version, FAIL_TO_PASS,
PASS_TO_PASS, environment_setup_commit, problem_statement, and files.

The source data and converted JSONL are controller-only. Do not copy them into
the agent workspace. In a new environment, copy the source workbook into this
directory, then convert it with:

```bash
python -m scripts.export_tasks
```
