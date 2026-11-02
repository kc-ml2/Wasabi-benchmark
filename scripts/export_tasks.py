"""Convert the reference workbook into controller-private JSONL.

Usage: python -m scripts.export_tasks [--source ...] [--output ...]
Requires the optional openpyxl dependency.
"""
import argparse
import json
from pathlib import Path
from harness.tasks.schema import Task


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/source/full_summaries_verified.xlsx"))
    parser.add_argument("--output", type=Path, default=Path("data/tasks.jsonl"))
    args = parser.parse_args()
    try:
        from openpyxl import load_workbook
    except ImportError:
        parser.error("Install conversion dependencies: pip install -e '.[data]'")
    workbook = load_workbook(args.source, read_only=True, data_only=True)
    try:
        rows = iter(workbook.active.iter_rows(values_only=True))
        headers = next(rows)
        records = []
        seen = set()
        for number, row in enumerate(rows, 2):
            if not any(value is not None for value in row):
                continue
            record = {key: "" if value is None else str(value)
                      for key, value in zip(headers, row) if key}
            try:
                task = Task.from_dict(record)
                if task.instance_id in seen:
                    raise ValueError(f"Duplicate task: {task.instance_id}")
            except ValueError as error:
                raise ValueError(f"Workbook row {number}: {error}") from error
            seen.add(task.instance_id)
            # Retain metadata (e.g. test lists, environment commit) for evaluation.
            records.append(record)
    finally:
        workbook.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Exported {len(records)} tasks to {args.output}")


if __name__ == "__main__":
    main()
