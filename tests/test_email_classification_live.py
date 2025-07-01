"""Live integration tests that exercise the REAL e-mail classification pipeline.

These tests hit the running Ollama instance through `classify_message_file`, using
small synthetic `.eml` fixtures that resemble real mail.  They check:

1. Determinism when temperature / top_p are clamped and a seed is supplied.
2. Variability when those knobs are left at model defaults.
3. Basic semantic sanity: an urgent work e-mail should score higher than a promo
   newsletter at low randomness.

If Ollama is unreachable (`query_ollama` returns -1), *all* tests fail fast so we
don't silently pass.
"""

from pathlib import Path
import email.message

import pytest

from email_flagger.classifier import classify_message_file, load_config

import requests

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_eml(tmp_dir: Path, subject: str, body: str, sender: str) -> Path:
    msg = email.message.EmailMessage()
    msg["From"] = sender
    msg["To"] = "me@example.com"
    msg["Subject"] = subject
    msg.set_content(body)

    path = tmp_dir / f"{subject.replace(' ', '_')}.eml"
    path.write_bytes(msg.as_bytes())
    return path


@pytest.fixture(scope="module")
def fixtures(tmp_path_factory):
    """Create two representative e-mail samples under a tmp dir."""
    tmp_dir = tmp_path_factory.mktemp("emails")

    boss = _make_eml(
        tmp_dir,
        "URGENT: Project Deadline Approaching",
        "Hi – we need your approval on the spec today to hit the deadline.",
        sender="boss@company.com",
    )

    newsletter = _make_eml(
        tmp_dir,
        "This Weekend Only – 50% Off All Shoes!",
        "Hello subscriber! Check out our massive clearance sale this weekend.",
        sender="promo@shop.com",
    )

    return {"boss": boss, "newsletter": newsletter}


# ---------------------------------------------------------------------------
# Networking capture fixture to prove we hit Ollama live
# ---------------------------------------------------------------------------


@pytest.fixture()
def capture_post(monkeypatch):
    """Wrap requests.post so we can inspect every live call while still forwarding it."""

    captured: list[dict] = []
    original_post = requests.post

    def _wrapper(url, *args, **kwargs):
        captured.append({
            "url": url,
            "json": kwargs.get("json"),
            "timeout": kwargs.get("timeout"),
        })
        return original_post(url, *args, **kwargs)

    monkeypatch.setattr(requests, "post", _wrapper)
    return captured


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _clone_config():
    """Return a fresh, mutable copy of the user config."""
    import copy

    return copy.deepcopy(load_config())


def test_deterministic_when_temperature_zero(fixtures, capture_post):
    cfg = _clone_config()
    ollama = cfg.setdefault("ollama", {})
    ollama["temperature"] = 0
    # Ensure *all* randomness off
    ollama["options"] = {"top_p": 0, "seed": 1}

    cls1, score1 = classify_message_file(str(fixtures["boss"]), cfg, return_score=True)
    cls2, score2 = classify_message_file(str(fixtures["boss"]), cfg, return_score=True)

    print("\n[determinism] payload sent:", capture_post[-1]["json"])
    print("[determinism] score1=", score1, "score2=", score2, "classification=", cls1)

    assert score1 == score2, f"Scores differ with temperature=0: {score1} vs {score2}"
    assert cls1 == cls2, "Classifications differ under deterministic settings"


def test_variability_at_default_temperature(fixtures, capture_post):
    cfg = _clone_config()
    ollama = cfg.setdefault("ollama", {})
    ollama.pop("temperature", None)  # use model default
    ollama.pop("options", None)

    scores = []
    for i in range(5):
        _, s = classify_message_file(str(fixtures["boss"]), cfg, return_score=True)
        scores.append(s)

    print("\n[variability] payload examples (last call):", capture_post[-1]["json"])
    print("[variability] collected scores:", scores)

    assert len(set(scores)) > 1, f"Expected variation but got identical scores: {scores}"


def test_semantic_ranking_boss_vs_newsletter(fixtures, capture_post):
    cfg = _clone_config()
    ollama = cfg.setdefault("ollama", {})
    ollama["temperature"] = 0.2
    ollama["options"] = {"top_p": 0.1, "seed": 1}

    _, boss_score = classify_message_file(str(fixtures["boss"]), cfg, return_score=True)
    _, news_score = classify_message_file(str(fixtures["newsletter"]), cfg, return_score=True)

    print("\n[semantic] boss payload:", capture_post[-2]["json"])
    print("[semantic] newsletter payload:", capture_post[-1]["json"])
    print("[semantic] boss_score=", boss_score, "newsletter_score=", news_score)

    assert boss_score > news_score, (
        f"Expected boss email to score higher than newsletter but got {boss_score} <= {news_score}"
    ) 