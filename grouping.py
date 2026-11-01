"""Four grouping strategies, evaluated the way Sentry frames the problem.

    raw            - hash the event as-received          (undergroups badly)
    shallow        - exception + outermost app frame      (overgroups badly)
    fingerprint    - normalized stack signature           (the baseline Sentry ships)
    fingerprint+nn - fingerprint, then cosine fallback    (the v2 idea, minus the ML)

The point of the exercise is the tradeoff, not a leaderboard: every point of
overgrouping you remove tends to cost you duplicate issues, and vice versa.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict

from corpus import Event

VOLATILE = [
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I), "<uuid>"),
    (re.compile(r"0x[0-9a-f]+", re.I), "<addr>"),
    (re.compile(r"\b\d{1,3}(\.\d{1,3}){3}\b"), "<ip>"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "<email>"),
    (re.compile(r"/tmp/[^\s:]+"), "<tmp>"),
    (re.compile(r"(hooks-|sentry-)[a-z0-9]+"), r"\1<x>"),
    (re.compile(r"\b\d+(\.\d+)?(s|ms)\b"), "<dur>"),
    (re.compile(r"\b\d+\b"), "<n>"),
]

SYSTEM_HINTS = ("site-packages", "node_modules", "stdlib", "dist-packages")
# SDK wrapper frames carry no signal and appear/disappear with SDK version
SDK_FRAMES = {"sentry.handle_exception", "sentry_sdk.handle_exception"}
MAX_FRAMES = 5


def normalize_text(s: str) -> str:
    for rx, repl in VOLATILE:
        s = rx.sub(repl, s)
    return re.sub(r"\s+", " ", s).strip().lower()


def app_frames(event: Event) -> list[str]:
    frames = [f for f in event.frames
              if not any(h in f.module for h in SYSTEM_HINTS)
              and f"{f.module}.{f.function}" not in SDK_FRAMES]
    return [f"{f.module}.{f.function}" for f in frames[-MAX_FRAMES:]]


def signature(event: Event) -> str:
    """Lexical fingerprint: exception class + normalized app call path."""
    return f"{event.exc_type}|" + ">".join(app_frames(event)) + f"|{normalize_text(event.message)[:120]}"


class Clusterer:
    def __init__(self, strategy: str, threshold: float = 0.72):
        assert strategy in {"raw", "shallow", "fingerprint", "fingerprint+nn"}
        self.strategy = strategy
        self.threshold = threshold
        self.clusters: list[dict] = []
        self.index: dict[str, int] = {}

    # -- keys -------------------------------------------------------------
    def key(self, e: Event) -> str:
        if self.strategy == "raw":
            blob = f"{e.exc_type}|{e.message}|" + "|".join(f"{f.module}.{f.function}:{f.lineno}" for f in e.frames)
            return hashlib.sha256(blob.encode()).hexdigest()[:16]
        if self.strategy == "shallow":
            frames = app_frames(e)
            return f"{e.exc_type}|{frames[0] if frames else '?'}"
        return signature(e)

    # -- cosine fallback ---------------------------------------------------
    def _tokens(self, e: Event) -> Counter:
        text = normalize_text(f"{e.exc_type} {e.message} " + " ".join(app_frames(e)))
        return Counter(t for t in re.findall(r"[a-z_]{3,}", text))

    @staticmethod
    def _cos(a: Counter, b: Counter) -> float:
        if not a or not b:
            return 0.0
        dot = sum(v * b.get(k, 0) for k, v in a.items())
        return dot / (math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values())))

    def add(self, e: Event) -> int:
        k = self.key(e)
        if k in self.index:
            cid = self.index[k]
            self.clusters[cid]["events"] += 1
            return cid

        if self.strategy == "fingerprint+nn" and self.clusters:
            toks = self._tokens(e)
            best, best_sim = None, 0.0
            for cid, c in enumerate(self.clusters):
                sim = self._cos(toks, c["tokens"])
                if sim > best_sim:
                    best, best_sim = cid, sim
            if best is not None and best_sim >= self.threshold:
                self.clusters[best]["events"] += 1
                self.index[k] = best
                return best

        cid = len(self.clusters)
        self.clusters.append({"key": k, "events": 1, "tokens": self._tokens(e) if self.strategy == "fingerprint+nn" else Counter()})
        self.index[k] = cid
        return cid


def evaluate(events: list[Event], strategy: str, threshold: float = 0.72) -> dict:
    c = Clusterer(strategy, threshold)
    assigned = [(e.group_id, c.add(e)) for e in events]

    by_true: dict[str, set[int]] = defaultdict(set)
    by_pred: dict[int, set[str]] = defaultdict(set)
    for gid, cid in assigned:
        by_true[gid].add(cid)
        by_pred[cid].add(gid)

    duplicates = sum(len(v) - 1 for v in by_true.values())          # undergrouping
    overmerged = sum(len(v) - 1 for v in by_pred.values())          # overgrouping
    wrong_events = sum(1 for _, cid in assigned if len(by_pred[cid]) > 1)
    purity = sum(max(Counter(g for g, cid in assigned if cid == p).values()) for p in by_pred) / len(assigned)
    return {
        "strategy": strategy,
        "issues": len(c.clusters),
        "true_issues": len(by_true),
        "duplicate_issues": duplicates,
        "overmerged_issues": overmerged,
        "events": len(assigned),
        "purity": round(purity, 4),
        "wrong_events": wrong_events,
    }
