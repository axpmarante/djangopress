#!/usr/bin/env python
"""
Compare two benchmark reports side by side.

Usage:
    python scripts/benchmark_compare.py benchmarks/bench_A.json benchmarks/bench_B.json
    python scripts/benchmark_compare.py --latest 2    # compare the 2 most recent
"""

import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCHMARKS_DIR = os.path.join(PROJECT_ROOT, 'benchmarks')


def fmt_duration(seconds):
    if seconds is None:
        return '-'
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.1f}s"


def delta_str(old, new):
    """Return a delta string like '+12.3s (+15%)' or '-5.2s (-8%)'."""
    if old is None or new is None or old == 0:
        return ''
    diff = new - old
    pct = (diff / old) * 100
    sign = '+' if diff >= 0 else ''
    return f"{sign}{diff:.1f}s ({sign}{pct:.0f}%)"


def load_report(path):
    with open(path) as f:
        return json.load(f)


def compare(report_a, report_b):
    meta_a = report_a['meta']
    meta_b = report_b['meta']
    sum_a = report_a['summary']
    sum_b = report_b['summary']

    print(f"\n{'='*80}")
    print(f"  BENCHMARK COMPARISON")
    print(f"{'='*80}")

    # Meta
    print(f"\n  {'':30} {'Baseline':>18} {'Current':>18}")
    print(f"  {'-'*66}")
    print(f"  {'Date':<30} {meta_a['date'][:19]:>18} {meta_b['date'][:19]:>18}")
    print(f"  {'Model':<30} {meta_a['model']:>18} {meta_b['model']:>18}")
    print(f"  {'Skip images':<30} {str(meta_a.get('skip_images', '?')):>18} {str(meta_b.get('skip_images', '?')):>18}")

    # Step comparison
    all_steps = list(dict.fromkeys(
        list(report_a.get('steps', {}).keys()) + list(report_b.get('steps', {}).keys())
    ))

    print(f"\n  Pipeline Steps:")
    print(f"  {'Step':<25} {'Baseline':>10} {'Current':>10} {'Delta':>18}")
    print(f"  {'-'*63}")
    for step in all_steps:
        a = report_a.get('steps', {}).get(step)
        b = report_b.get('steps', {}).get(step)
        label = step.replace('_', ' ').title()
        d = delta_str(a, b)
        print(f"  {label:<25} {fmt_duration(a):>10} {fmt_duration(b):>10} {d:>18}")

    ta = meta_a.get('total_time_s', 0)
    tb = meta_b.get('total_time_s', 0)
    print(f"  {'-'*63}")
    print(f"  {'TOTAL':<25} {fmt_duration(ta):>10} {fmt_duration(tb):>10} {delta_str(ta, tb):>18}")

    # Page comparison
    pages_a = report_a.get('pages', {})
    pages_b = report_b.get('pages', {})
    all_pages = list(dict.fromkeys(list(pages_a.keys()) + list(pages_b.keys())))

    if all_pages:
        print(f"\n  Per-Page Times:")
        print(f"  {'Page':<25} {'Baseline':>10} {'Current':>10} {'Delta':>18}")
        print(f"  {'-'*63}")
        for page in all_pages:
            a = pages_a.get(page, {}).get('elapsed_s')
            b = pages_b.get(page, {}).get('elapsed_s')
            print(f"  {page:<25} {fmt_duration(a):>10} {fmt_duration(b):>10} {delta_str(a, b):>18}")

    # Summary metrics
    metrics = [
        ('Total LLM time', 'total_llm_time_s'),
        ('Avg per LLM call', 'avg_llm_call_s'),
        ('Avg per page', 'avg_page_time_s'),
        ('Text gen avg', 'text_llm_avg_s'),
        ('Image gen avg', 'image_gen_avg_s'),
        ('Overhead (non-LLM)', 'overhead_time_s'),
    ]

    print(f"\n  Key Metrics:")
    print(f"  {'Metric':<25} {'Baseline':>10} {'Current':>10} {'Delta':>18}")
    print(f"  {'-'*63}")
    for label, key in metrics:
        a = sum_a.get(key)
        b = sum_b.get(key)
        if a is None and b is None:
            continue
        print(f"  {label:<25} {fmt_duration(a):>10} {fmt_duration(b):>10} {delta_str(a, b):>18}")

    count_metrics = [
        ('Total LLM calls', 'total_llm_calls'),
        ('Pages created', 'pages_created'),
        ('Fallbacks', 'fallback_count'),
        ('Failed calls', 'failed_count'),
    ]
    print()
    for label, key in count_metrics:
        a = sum_a.get(key, 0)
        b = sum_b.get(key, 0)
        diff = b - a
        sign = '+' if diff > 0 else ''
        delta = f"{sign}{diff}" if diff != 0 else ''
        print(f"  {label:<25} {a:>10} {b:>10} {delta:>18}")

    # Speed change headline
    if ta and tb:
        change_pct = ((tb - ta) / ta) * 100
        if change_pct < 0:
            print(f"\n  >>> {abs(change_pct):.0f}% FASTER <<<")
        elif change_pct > 0:
            print(f"\n  >>> {change_pct:.0f}% SLOWER <<<")
        else:
            print(f"\n  >>> NO CHANGE <<<")

    print(f"\n{'='*80}\n")


def get_latest_reports(n=2):
    """Get the N most recent benchmark files."""
    if not os.path.isdir(BENCHMARKS_DIR):
        print(f"No benchmarks/ directory found.")
        sys.exit(1)

    files = sorted(
        [f for f in os.listdir(BENCHMARKS_DIR) if f.endswith('.json')],
        reverse=True
    )
    if len(files) < n:
        print(f"Need at least {n} reports to compare, found {len(files)}.")
        sys.exit(1)

    return [os.path.join(BENCHMARKS_DIR, f) for f in files[:n]]


def main():
    parser = argparse.ArgumentParser(description='Compare two benchmark reports')
    parser.add_argument('reports', nargs='*', help='Two JSON report files to compare')
    parser.add_argument('--latest', type=int, default=0,
                        help='Compare the N most recent reports (default: use positional args)')

    args = parser.parse_args()

    if args.latest:
        paths = get_latest_reports(args.latest)
        # oldest first (baseline), newest second (current)
        paths.reverse()
    elif len(args.reports) == 2:
        paths = args.reports
    else:
        # Default: compare 2 most recent
        paths = get_latest_reports(2)
        paths.reverse()

    for p in paths:
        if not os.path.exists(p):
            print(f"Error: {p} not found")
            sys.exit(1)

    report_a = load_report(paths[0])
    report_b = load_report(paths[1])

    print(f"  Baseline: {os.path.basename(paths[0])}")
    print(f"  Current:  {os.path.basename(paths[1])}")

    compare(report_a, report_b)


if __name__ == '__main__':
    main()
