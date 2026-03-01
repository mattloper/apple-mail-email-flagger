#!/usr/bin/env python3
"""Re-classify labeled dataset entries to measure prompt/model/threshold changes.

Usage:
    python3 tests/eval/retune.py                          # baseline with current prompt
    python3 tests/eval/retune.py --red-min 70 --blue-min 40
    python3 tests/eval/retune.py --model llama3
    python3 tests/eval/retune.py --prompt-file prompt.txt
    python3 tests/eval/retune.py --categorical --prompt-file prompt_cat.txt
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import re as _re

import requests

from email_flagger.classifier import (
    PROMPT_TEMPLATE,
    build_personal_context,
    get_classification_for_score,
    load_config,
    query_ollama,
)
from email_flagger.dataset import LABEL_TO_BUCKET, load_entries, load_labels


def query_ollama_raw(prompt: str, config: dict) -> str:
    """Return raw text response from Ollama (for categorical mode)."""
    ollama_config = config.get("ollama", {})
    model = ollama_config.get("model", "llama3")
    endpoint = ollama_config.get("endpoint", "http://localhost:11434")
    timeout = ollama_config.get("timeout", 120)
    options = ollama_config.get("options", {}).copy()
    if "temperature" in ollama_config:
        options["temperature"] = ollama_config["temperature"]

    url = f"{endpoint.rstrip('/')}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}
    if options:
        payload["options"] = options

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as exc:
        print(f"  (Ollama error: {type(exc).__name__})", flush=True)
        return "IGNORE"


CAT_TO_BUCKET = {"read": "read", "glance": "glance", "ignore": "ignore"}


def parse_categorical(text: str) -> str:
    """Parse READ/GLANCE/IGNORE from model output, return bucket name."""
    t = text.upper().strip()
    for cat, bucket in [("READ", "read"), ("GLANCE", "glance"), ("IGNORE", "ignore")]:
        if cat in t:
            return bucket
    return "ignore"


def run_eval(
    prompt_template: str,
    config: dict,
    red_min: float,
    blue_min: float,
    entries: list[dict],
    labels: dict[str, str],
    categorical: bool = False,
) -> dict:
    """Re-classify all labeled entries and return metrics."""
    personal_context = build_personal_context(config)
    scoring = {"red_min": red_min, "blue_min": blue_min}

    results = []
    for i, entry in enumerate(entries):
        ts = entry.get("ts")
        if ts not in labels:
            continue

        sender = entry.get("from", "")
        snippet = entry.get("snippet", "")
        human_label = labels[ts]
        expected_bucket = LABEL_TO_BUCKET[human_label]

        prompt = prompt_template.format(
            extract=snippet,
            personal_context=personal_context,
            sender=sender,
        )

        if categorical:
            raw = query_ollama_raw(prompt, config)
            cls = parse_categorical(raw)
            score = -1
        else:
            score = query_ollama(prompt, config)
            cls = get_classification_for_score(score, {"scoring": scoring})

        subj = entry.get("subject", "")[:60]
        ok = "✓" if cls == expected_bucket else "✗"
        if categorical:
            print(
                f"  [{i+1}] {ok} model={cls:4s} you={human_label:6s} | {subj}"
            )
        else:
            print(
                f"  [{i+1}] {ok} score={score:5.1f} model={cls:4s} you={human_label:6s} | {subj}"
            )

        results.append(
            {
                "ts": ts,
                "score": score,
                "class": cls,
                "label": human_label,
                "expected": expected_bucket,
                "subject": subj,
                "from": sender,
            }
        )

    n = len(results)
    if n == 0:
        return {"n": 0, "accuracy": 0.0}

    correct = sum(1 for r in results if r["class"] == r["expected"])
    buckets = {}
    for bucket in ("read", "glance", "ignore"):
        total = sum(1 for r in results if r["expected"] == bucket)
        right = sum(
            1 for r in results if r["expected"] == bucket and r["class"] == bucket
        )
        buckets[bucket] = {"correct": right, "total": total}

    misses = [r for r in results if r["class"] != r["expected"]]

    return {
        "n": n,
        "accuracy": correct / n,
        "correct": correct,
        "buckets": buckets,
        "misses": misses,
        "results": results,
    }


def print_report(metrics: dict):
    n = metrics["n"]
    acc = metrics["accuracy"]
    print(f"\n{'='*60}")
    print(f"Accuracy: {metrics['correct']}/{n} ({100*acc:.1f}%)\n")

    print(f"  {'Bucket':<8} {'Correct':>8} {'Total':>7} {'Accuracy':>10}")
    print(f"  {'-'*8} {'-'*8} {'-'*7} {'-'*10}")
    for bucket in ("read", "glance", "ignore"):
        b = metrics["buckets"].get(bucket, {"correct": 0, "total": 0})
        pct = f"{100*b['correct']/b['total']:.0f}%" if b["total"] else "n/a"
        print(f"  {bucket:<8} {b['correct']:>8} {b['total']:>7} {pct:>10}")

    misses = metrics["misses"]
    if misses:
        print(f"\nMismatches ({len(misses)}):")
        for m in misses:
            print(
                f"  model={m['class']:4s}  you={m['label']:6s}  "
                f"score={m['score']:5.1f}  {m['subject'][:60]}"
            )


def main():
    parser = argparse.ArgumentParser(description="Re-classify labeled emails")
    parser.add_argument("--model", help="Override Ollama model")
    parser.add_argument("--red-min", type=float, help="Red threshold")
    parser.add_argument("--blue-min", type=float, help="Blue threshold")
    parser.add_argument("--prompt-file", help="Path to alternative prompt template")
    parser.add_argument(
        "--json-out", help="Write full results to JSON file"
    )
    parser.add_argument(
        "--categorical", action="store_true",
        help="Use categorical (READ/GLANCE/IGNORE) instead of numeric scoring",
    )
    args = parser.parse_args()

    config = load_config()
    if args.model:
        config["ollama"]["model"] = args.model

    red_min = args.red_min if args.red_min is not None else config["scoring"]["red_min"]
    blue_min = (
        args.blue_min if args.blue_min is not None else config["scoring"]["blue_min"]
    )

    if args.prompt_file:
        prompt_template = Path(args.prompt_file).read_text()
    else:
        prompt_template = PROMPT_TEMPLATE

    entries = load_entries()
    labels = load_labels()
    n_labeled = sum(1 for e in entries if e.get("ts") in labels)

    model_name = config["ollama"]["model"]
    print(f"Model: {model_name}  |  Thresholds: red>={red_min} blue>={blue_min}")
    print(f"Re-classifying {n_labeled} labeled emails...\n")

    t0 = time.time()
    metrics = run_eval(
        prompt_template, config, red_min, blue_min, entries, labels,
        categorical=args.categorical,
    )
    elapsed = time.time() - t0

    print_report(metrics)
    print(f"\nElapsed: {elapsed:.0f}s ({elapsed/max(metrics['n'],1):.1f}s/email)")

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(metrics, f, indent=2)
        print(f"Saved to {args.json_out}")


if __name__ == "__main__":
    main()
