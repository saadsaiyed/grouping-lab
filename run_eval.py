#!/usr/bin/env python3
"""Run every strategy over the synthetic corpus and render a markdown report."""
from __future__ import annotations

import sys

from corpus import TEMPLATES, generate
from grouping import evaluate

STRATEGIES = ["raw", "shallow", "fingerprint", "fingerprint+nn"]


def main(n_per_group: int = 25) -> None:
    events = generate(n_per_group=n_per_group)
    rows = [evaluate(events, s) for s in STRATEGIES]

    hdr = f"{'strategy':<16}{'issues':>8}{'dupes':>8}{'overmerge':>11}{'bad events':>12}{'purity':>9}"
    print(f"{len(events)} events from {len(TEMPLATES)} true root causes\n")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['strategy']:<16}{r['issues']:>8}{r['duplicate_issues']:>8}"
              f"{r['overmerged_issues']:>11}{r['wrong_events']:>12}{r['purity']:>9.3f}")

    base = rows[2]
    nn = rows[3]
    print(f"\nfingerprint alone: {base['duplicate_issues']} duplicate issues, "
          f"{base['overmerged_issues']} overmerges")
    print(f"with cosine fallback: {nn['duplicate_issues']} duplicate issues, "
          f"{nn['overmerged_issues']} overmerges")

    sweep = [(t, evaluate(events, "fingerprint+nn", t)) for t in
             (0.55, 0.65, 0.72, 0.80, 0.85, 0.90, 0.95)]
    print("\nthreshold sweep (fingerprint + cosine fallback)")
    for t, r in sweep:
        print(f"  {t:.2f}  issues={r['issues']:>2}  dupes={r['duplicate_issues']}  "
              f"overmerge={r['overmerged_issues']}  bad_events={r['wrong_events']}")

    with open("report.md", "w") as fh:
        fh.write("# Grouping experiment results\n\n")
        fh.write(f"{len(events)} synthetic events, {len(TEMPLATES)} true root causes, "
                 f"{n_per_group} events each.\n\n")
        fh.write("| strategy | issues created | duplicate issues | overmerged issues | events in wrong cluster | purity |\n")
        fh.write("|---|---|---|---|---|---|\n")
        for r in rows:
            fh.write(f"| `{r['strategy']}` | {r['issues']} | {r['duplicate_issues']} | "
                     f"{r['overmerged_issues']} | {r['wrong_events']} | {r['purity']:.3f} |\n")
        fh.write("\n## Threshold sweep\n\n")
        fh.write("| cosine threshold | issues | duplicate issues | overmerged issues | events in wrong cluster |\n")
        fh.write("|---|---|---|---|---|\n")
        for t, r in sweep:
            fh.write(f"| {t:.2f} | {r['issues']} | {r['duplicate_issues']} | "
                     f"{r['overmerged_issues']} | {r['wrong_events']} |\n")
    print("\nwrote report.md")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 25)
