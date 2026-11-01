# Grouping Lab

A 250-line reproduction of the core problem in Sentry's [Issue Grouping: Smarter, Faster, Half as Wrong](https://blog.sentry.io/enhancing-issue-grouping/): how do you decide that 400 incoming error events are 7 bugs and not 400 bugs — without ever merging two different bugs into one issue?

Sentry solves it with a lexical fingerprint plus a trained model that catches what the fingerprint misses. This repo isolates the decision, generates the messy parts on purpose, and measures both failure directions instead of just one.

## Why the second direction matters

Undergrouping is annoying: the same bug shows up as many issues, alerts get noisy, triage multiplies. Overgrouping is worse. When two distinct bugs collapse into one issue, the second bug's stack trace, its release, its affected users and its fix all disappear behind the first one. Nobody files a bug about a bug that was never created.

So every strategy below is scored on both.

## What it does

1. `corpus.py` generates events from 7 known root causes, each arriving 25 times with the noise production adds: UUIDs, temp paths, ports, request ids, IPs, durations, line drift, and an SDK wrapper frame that appears in some versions and not others.
2. Two noise families are adversarial by design:
   - **wording drift** — the same bug with a reworded message (what an SDK bump produces), which lexically distinct fingerprints split apart;
   - **lookalikes** — two different bugs sharing the same outer call path, which any shallow signature collapses together.
3. `grouping.py` runs four strategies over it, streaming and in-order, the way ingestion actually sees events.

## Results

175 events, 7 true root causes:

| strategy | issues created | duplicate issues | overmerged issues | events in wrong cluster | purity |
|---|---|---|---|---|---|
| `raw` (hash the event) | 175 | 168 | 0 | 0 | 1.000 |
| `shallow` (exception + outermost frame) | 6 | 0 | 1 | 50 | 0.857 |
| `fingerprint` (normalized stack signature) | 9 | 2 | 0 | 0 | 1.000 |
| `fingerprint+nn` (fingerprint, then cosine ≥ 0.72) | 6 | 1 | 2 | 93 | 0.754 |

The honest baseline is the third row: zero bad merges, two duplicate issues, entirely from wording drift.

The interesting row is the fourth — and the sweep:

| cosine threshold | issues | duplicate issues | overmerged issues | events in wrong cluster |
|---|---|---|---|---|
| 0.55 | 5 | 0 | 2 | 100 |
| 0.65 | 5 | 0 | 2 | 100 |
| 0.72 | 6 | 1 | 2 | 93 |
| 0.80 | 7 | 1 | 1 | 50 |
| 0.85 | 9 | 2 | 0 | 0 |
| 0.90 | 9 | 2 | 0 | 0 |
| 0.95 | 9 | 2 | 0 | 0 |

**There is no threshold that wins both columns.** Every setting that reduces duplicate issues below the fingerprint baseline pays for it in wrong clusters — and at 0.85+ the fallback stops contributing anything at all, collapsing to the fingerprint. Two bugs sharing an outer call path score higher cosine similarity than one bug with reworded messages does, so similarity cannot separate "same bug, new wording" from "different bug, same neighbourhood."

That is the empirical case for a *learned* grouping signal rather than a tuned cutoff: the decision needs features a token-overlap score doesn't have (exception class, frame depth, leaf-frame divergence, release correlation), and it needs to be evaluated on overgrouping as loudly as on duplicates.

## Limitations

- Seven synthetic root causes, not real traffic; the numbers demonstrate the tradeoff, they don't estimate Sentry's.
- The fallback is TF-IDF-ish cosine over normalized tokens, not an embedding or a model — deliberately, to keep it dependency-free.
- Fingerprints normalize `\d+` to `<n>`, which is aggressive; real traces need per-token rules (ports and line numbers should keep separating bugs that differ only by endpoint).
- No cross-release drift, no user-impact weighting, no manual merge history.

## Run it

```bash
python3 run_eval.py          # 175 events, prints the tables, writes report.md
python3 run_eval.py 100      # 700 events
```

Pure standard library, no install step.
