"""Synthetic error corpus for grouping experiments.

Models what Sentry actually receives: the same underlying bug arriving many
times with volatile noise (ids, ports, temp paths, line numbers), plus pairs of
*nearly identical but semantically distinct* errors - the overgrouping trap
described in blog.sentry.io/enhancing-issue-grouping/.
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field


@dataclass
class Frame:
    module: str
    function: str
    lineno: int


@dataclass
class Event:
    group_id: str          # ground truth
    exc_type: str
    message: str
    frames: list[Frame]
    payload: dict = field(default_factory=dict)


# (group_id, exception, app frame chain (module, function), message template)
# Chains deliberately share prefixes: `checkout-*` differ only in the leaf frame
# and exception, which is what a shallow fingerprint gets wrong.
TEMPLATES = [
    ("timeout-autofix", "TimeoutError", [
        ("autofix", "generate_summary_and_run_automation"),
        ("issue_summary", "get_issue_summary"),
        ("issue_summary", "run_automation"),
        ("signed_seer_api", "make_signed_seer_api_request"),
        ("signed_seer_api", "urlopen"),
    ], "Read timed out after {timeout}s while calling seer for issue {issue_id} (req {rid})"),

    ("timeout-autofix-state", "TimeoutError", [
        ("autofix", "generate_summary_and_run_automation"),
        ("issue_summary", "get_issue_summary"),
        ("issue_summary", "run_automation"),
        ("utils", "get_autofix_state"),
        ("signed_seer_api", "make_signed_seer_api_request"),
        ("signed_seer_api", "urlopen"),
    ], "Read timed out after {timeout}s fetching autofix state for {issue_id} (req {rid})"),

    ("conn-refused-db", "ConnectionRefusedError", [
        ("api", "handle_request"),
        ("api", "list_projects"),
        ("db", "connection"),
        ("db", "connect"),
    ], "Connection refused to postgres at 10.0.0.{dbnode}:5432 (req {rid})"),

    ("conn-refused-cache", "ConnectionRefusedError", [
        ("api", "handle_request"),
        ("api", "list_projects"),
        ("cache", "get_many"),
        ("cache", "connect"),
    ], "Connection refused to redis at 10.0.0.{dbnode}:6379 (req {rid})"),

    ("keyerror-config", "KeyError", [
        ("web", "dispatch"),
        ("web", "render_issue"),
        ("views", "issue_detail"),
        ("views", "context_from_org"),
    ], "KeyError: 'sentry:features' for org {org_id} user {user_id}"),

    ("jsondecode-upstream", "JSONDecodeError", [
        ("web", "dispatch"),
        ("integrations", "handle_webhook"),
        ("integrations", "parse_body"),
    ], "Expecting value: line 1 column 1 (char 0) from {host} (delivery {rid})"),

    ("typeerror-none", "TypeError", [
        ("worker", "process_event"),
        ("worker", "normalize"),
        ("normalize", "apply_defaults"),
    ], "NoneType is not subscriptable at /tmp/sentry-{token}/event.json user {user_id}"),
]


# Same frames, same bug, different wording - what an SDK bump or a reworded
# upstream error actually produces. Lexical fingerprinting splits these.
MESSAGE_VARIANTS = {
    "conn-refused-db": "could not connect to database server 10.0.0.{dbnode}:5432 (req {rid})",
    "keyerror-config": "Missing config key sentry:features while rendering org {org_id}",
}


def _noisy_message(tmpl: str, rng: random.Random) -> str:
    return tmpl.format(
        timeout=rng.choice([5, 10, 30]),
        issue_id=rng.randint(100000, 999999),
        rid=uuid.UUID(int=rng.getrandbits(128)),
        dbnode=rng.randint(2, 9),
        org_id=rng.randint(1, 5000),
        user_id=rng.randint(1, 900000),
        host=f"hooks-{rng.choice(['a','b','c'])}{rng.randint(1,9)}.example.com",
        token=uuid.UUID(int=rng.getrandbits(128)).hex[:12],
    )


def generate(n_per_group: int = 25, seed: int = 7) -> list[Event]:
    rng = random.Random(seed)
    events: list[Event] = []
    for gid, exc, chain, msg in TEMPLATES:
        for _ in range(n_per_group):
            frames = [Frame(m, f, rng.randint(40, 900)) for m, f in chain]
            # minified/bundled builds shift line numbers wildly; add a wrapper
            if rng.random() < 0.35:
                frames.insert(0, Frame("sentry", "handle_exception", rng.randint(1, 4000)))
            events.append(Event(
                group_id=gid,
                exc_type=exc,
                message=_noisy_message(
                    MESSAGE_VARIANTS.get(gid, msg) if rng.random() < 0.3 else msg, rng
                ),
                frames=frames,
                payload={"request_id": str(uuid.UUID(int=rng.getrandbits(128))),
                         "pid": rng.randint(1, 65000),
                         "thread": rng.randint(1, 16)},
            ))
    rng.shuffle(events)
    return events
