"""Persistent dataset of classified emails and human labels.

Every email classified by the system is appended to dataset.jsonl with the
sender, snippet (what the model saw), score, and bucket.  The user can then
label entries via ``email-flagger --review`` and the labels are stored
separately in labels.json.

An agent or benchmark script can import this module to:
- iterate over labeled examples
- compute accuracy against human preferences
- re-classify saved snippets with a different prompt or model
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".email-flagger"
DATASET_FILE = CONFIG_DIR / "dataset.jsonl"
LABELS_FILE = CONFIG_DIR / "labels.json"

# Human feedback categories → model bucket they map to
LABEL_TO_BUCKET = {"ignore": "none", "glance": "blue", "read": "red"}


# ── dataset ──────────────────────────────────────────────────────────────

def _snippet_hash(sender: str, snippet: str) -> str:
    """Stable hash of an email's identity for dedup."""
    return hashlib.sha256(f"{sender}\n{snippet}".encode()).hexdigest()[:16]


def existing_hashes() -> set[str]:
    """Return the set of snippet hashes already in the dataset."""
    hashes = set()
    for e in load_entries():
        h = e.get("hash")
        if h:
            hashes.add(h)
    return hashes


def append_entry(sender: str, snippet: str, score: float, classification: str,
                 _known: set[str] | None = None) -> bool:
    """Append a classified email to the dataset. Returns False if duplicate.

    Pass *_known* (from ``existing_hashes()``) to avoid re-reading the file
    on every call during bulk operations.
    """
    import datetime
    h = _snippet_hash(sender, snippet)

    if _known is not None:
        if h in _known:
            return False
    elif DATASET_FILE.exists():
        if h in existing_hashes():
            return False

    subject = snippet.split("\n", 1)[0][:200]
    entry = {
        "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "hash": h,
        "from": sender,
        "subject": subject,
        "snippet": snippet,
        "score": score,
        "class": classification,
    }
    try:
        with DATASET_FILE.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    if _known is not None:
        _known.add(h)
    return True


def load_entries() -> list[dict]:
    """Load all dataset entries from dataset.jsonl."""
    if not DATASET_FILE.exists():
        return []
    entries = []
    with DATASET_FILE.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
    return entries


# ── labels ───────────────────────────────────────────────────────────────

def load_labels() -> dict[str, str]:
    """Load human labels (ts → 'ignore'|'glance'|'read')."""
    if LABELS_FILE.exists():
        try:
            return json.load(LABELS_FILE.open())
        except Exception:
            return {}
    return {}


def save_labels(labels: dict[str, str]):
    """Persist human labels to labels.json."""
    with LABELS_FILE.open("w") as f:
        json.dump(labels, f, indent=2)


# ── metrics ──────────────────────────────────────────────────────────────

def compute_accuracy(entries: list[dict] | None = None,
                     labels: dict[str, str] | None = None) -> dict:
    """Compare model classifications against human labels.

    Returns a dict with overall accuracy, per-bucket breakdown, and a list
    of mismatches — everything an agent needs to evaluate a prompt/model
    change.
    """
    if entries is None:
        entries = load_entries()
    if labels is None:
        labels = load_labels()

    labeled = []
    for e in entries:
        ts = e.get("ts")
        if ts in labels:
            expected = LABEL_TO_BUCKET[labels[ts]]
            labeled.append({
                "class": e.get("class", "none"),
                "score": e.get("score", -1),
                "label": labels[ts],
                "expected": expected,
                "subject": e.get("subject", ""),
                "from": e.get("from", ""),
            })

    n = len(labeled)
    if n == 0:
        return {"n": 0, "accuracy": 0.0, "buckets": {}, "misses": []}

    correct = sum(1 for r in labeled if r["class"] == r["expected"])
    buckets = {}
    for bucket in ("red", "blue", "none"):
        total = sum(1 for r in labeled if r["expected"] == bucket)
        right = sum(1 for r in labeled if r["expected"] == bucket
                    and r["class"] == bucket)
        buckets[bucket] = {"correct": right, "total": total}

    return {
        "n": n,
        "accuracy": correct / n,
        "buckets": buckets,
        "misses": [r for r in labeled if r["class"] != r["expected"]],
    }
