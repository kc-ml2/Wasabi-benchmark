"""Rebuild the local convergence snapshot and figures (requires matplotlib).

Run from the repository root. Inputs are local, untracked experiment artifacts.
Latest selected runs replace earlier runs, not best-of-retry selection.
"""
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path('.sandbox')
OUT = Path('docs/experiments/figures/convergence')
SOURCES = [
    'convergence-500-gpt6luna-budget10-20261114-090653',
    'convergence-500-diagnostic-retry-20261114-091647',
    'convergence-remaining490-20261114-092057',
    'convergence-500-retry32-20261115-021432',
    'convergence-500-retry32-rg-20261115-030256',
    'convergence-empty108-rg-20261115-041738',
    'convergence-rg-404-reconciled.json',
    'convergence-timeout-retry-20261115-045937',
    'convergence-errors28-workers2-20261115-053251',
    'convergence-sphinx7985-retry-20261115-082726',
]


def main():
    merged = {}
    for source in SOURCES:
        path = ROOT / source
        if path.suffix != '.json':
            path /= 'results.json'
        for row in json.loads(path.read_text()):
            merged[row['instance_id'], row['condition']] = {**row, 'source': str(path)}
    assert len(merged) == 1000
    records = []
    for (instance, mode), row in sorted(merged.items()):
        known = 'feedback_count' in row and 'coding_interactions' in row
        records.append(dict(
            instance_id=instance, condition=mode, status=row['status'],
            requests=1 + row['feedback_count'] + len(row['coding_interactions']) if known else None,
            submissions=len(row['submissions']) if 'submissions' in row else None,
            source=row['source'],
        ))
    paired = []
    lookup = {(r['instance_id'], r['condition']): r for r in records}
    for instance, mode in lookup:
        if mode != 'baseline':
            continue
        b, w = (lookup[instance, c] for c in ('baseline', 'wasabi'))
        if all(r['status'] == 'resolved' and r['requests'] is not None for r in (b, w)):
            paired.append(b['requests'] - w['requests'])
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / 'task-results.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    summary = {'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'sources_in_precedence_order': SOURCES}
    colors = {'baseline': '#4477AA', 'wasabi': '#EE7733'}
    plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.5))
    maximum = max(r['requests'] for r in records if r['status'] == 'resolved' and r['requests'] is not None)
    budgets = list(range(maximum + 1))
    for mode in colors:
        rows = [r for r in records if r['condition'] == mode]
        assert len(rows) == 500
        solved = [r for r in rows if r['status'] == 'resolved']
        known = [r for r in solved if r['requests'] is not None]
        missing = len(solved) - len(known)
        counts = [sum(r['requests'] <= k for r in known) for k in budgets]
        lower = [n / 5 for n in counts]
        upper = [(n + missing) / 5 if k else 0 for k, n in zip(budgets, counts)]
        axes[0].step(budgets, lower, where='post', color=colors[mode], linewidth=2.5,
                     label=f'{mode.title()}: {len(solved)}/500 resolved')
        axes[0].fill_between(budgets, lower, upper, step='post', color=colors[mode], alpha=.2)
        summary[mode] = dict(status_counts=dict(Counter(r['status'] for r in rows)),
                             resolved_request_count_known=len(known), resolved_request_count_unknown=missing,
                             mean_requests_resolved=sum(r['requests'] for r in known)/len(known),
                             cumulative_resolved_known=dict(zip(budgets, counts)))
    axes[0].set(title='Resolution by coding-agent request budget', xlabel='Requests to coding agent (including initial request)',
                ylabel='Resolved tasks / all 500 tasks (%)', xlim=(0, maximum + .3), ylim=(0, 85))
    axes[0].set_xticks(budgets)
    axes[0].legend(loc='lower right')
    axes[0].grid(axis='y', alpha=.2)
    dist = Counter(paired)
    xs = list(range(min(dist), max(dist) + 1))
    bars = axes[1].bar(xs, [dist[x] for x in xs], color=[colors['baseline'] if x < 0 else colors['wasabi'] if x > 0 else '#AAAAAA' for x in xs])
    axes[1].bar_label(bars, padding=3)
    axes[1].set(title=f'Request difference on jointly resolved tasks (n={len(paired)})',
                xlabel='Baseline requests − Wasabi requests\nNegative: baseline fewer  |  Positive: Wasabi fewer',
                ylabel='Number of tasks', xticks=xs)
    axes[1].set_ylim(0, max(dist.values()) * 1.16)
    axes[1].grid(axis='y', alpha=.2)
    summary['paired'] = dict(n=len(paired), difference_distribution=dict(sorted(dist.items())))
    fig.suptitle('Convergence: resolution and coding-agent request efficiency', fontsize=16, fontweight='bold')
    fig.text(.02, .025,
             'Requests = initial request + coding-question responses + failure feedback; Wasabi clarification excluded.\n'
             'Retry-adjusted snapshot, not total retry cost. Shaded bands bound resolved tasks with unknown request counts.',
             fontsize=9, color='#555555')
    fig.tight_layout(rect=(0, .12, 1, .93))
    for suffix in ('png', 'svg', 'pdf'):
        fig.savefig(OUT / f'convergence-summary.{suffix}', dpi=180)
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
