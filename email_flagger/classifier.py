#!/usr/bin/env python3
"""
Email classifier - All the actual logic for classification
"""
import email
import json
import os
import re
import sys
from pathlib import Path

import requests

# Configuration
CONFIG_DIR = Path.home() / ".email-flagger"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = CONFIG_DIR / "classifier.log"

def log_message(message):
    """Appends a timestamped message to the log file."""
    with LOG_FILE.open("a") as f:
        f.write(f"[{os.getpid()}] {message}\n")

def deep_merge_config(default, user, _depth=0):
    """Deep merge user config into default config with recursion protection."""
    # Prevent infinite recursion
    if _depth > 10:
        log_message("Warning: Config merge depth limit reached, using shallow merge")
        result = default.copy()
        result.update(user)
        return result
    
    result = default.copy()
    for key, value in user.items():
        if (key in result and 
            isinstance(result[key], dict) and 
            isinstance(value, dict) and
            key not in ['__circular__']):  # Avoid obvious circular references
            result[key] = deep_merge_config(result[key], value, _depth + 1)
        else:
            result[key] = value
    return result

def load_config():
    """Load configuration from JSON file with fallback defaults."""
    default_config = {
        "name": "User",
        "llm_instructions": "Prioritize work and family emails, deprioritize newsletters and promotions.",
        "ollama": {
            "model": "llama3",
            "endpoint": "http://localhost:11434",
            "timeout": 60,
            "temperature": 0.0
        },
        "scoring": {
            "read_threshold": 80,
            "glance_threshold": 60
        },
        "max_bytes": 2048
    }
    
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                user_config = json.load(f)
            # Deep merge user config with defaults
            return deep_merge_config(default_config, user_config)
        else:
            log_message("Config file not found, using defaults")
            return default_config
    except Exception as e:
        log_message(f"Error loading config, using defaults: {e}")
        return default_config

def build_personal_context(config):
    """Build personal context string from config."""
    name = config.get("name", "User")
    llm_instructions = config.get("llm_instructions", "")
    
    context = f"The recipient is {name}."
    
    if llm_instructions:
        context += f"\n\n{llm_instructions}"
    
    return context

def query_ollama(prompt: str, config: dict) -> float:
    """Return a 0–100 float care score from Ollama (blocking)."""
    ollama_config = config.get("ollama", {})
    model = ollama_config.get("model", "llama3")
    endpoint = ollama_config.get("endpoint", "http://localhost:11434")
    timeout = ollama_config.get("timeout", 60)
    
    # Build options for the Ollama API. Start with any user-supplied dict under
    # ``ollama.options`` and then allow top-level convenience keys such as
    # ``temperature`` to override or populate it.
    options = ollama_config.get("options", {}).copy()

    # Convenience: a top-level ``temperature`` key is promoted into the options
    # object so that users can simply write "temperature": 0.1 in their config
    # without needing to nest it.
    if "temperature" in ollama_config:
        options["temperature"] = ollama_config["temperature"]

    url = f"{endpoint.rstrip('/')}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}
    if options:
        payload["options"] = options

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
    except Exception as exc:
        print(f"ERROR: failed to contact Ollama – {exc}", file=sys.stderr)
        return -1

    try:
        data = resp.json()
        if "response" not in data:
            raise ValueError(f"malformed Ollama response: {data}")
        text = data.get("response", "").strip()
        # Require exactly two digits after the decimal point (e.g. 42.00).
        float_pattern = r"\b(?:100\.00|[0-9]{1,2}\.\d{2})\b"
        match = re.search(float_pattern, text)
        if not match:
            raise ValueError(f"no valid 0–100 number in LLM output: {text}")
        score = float(match.group(0))
        return score
    except Exception as exc:
        print(f"ERROR: failed to parse Ollama response – {exc}", file=sys.stderr)
        return -1

def get_classification_for_score(score: float, config: dict) -> str:
    """Return a classification string for a given 0-100 score."""
    if score < 0:
        return "ignore"

    scoring = config.get("scoring", {})
    read_threshold = scoring.get("read_threshold", 80)
    glance_threshold = scoring.get("glance_threshold", 60)

    if score >= read_threshold:
        return "read"
    elif score >= glance_threshold:
        return "glance"
    else:
        return "ignore"

def clean_html(html: str) -> str:
    """Strip HTML to plain text using BeautifulSoup.

    Removes script/style elements, extracts visible text, and
    collapses excess whitespace.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return re.sub(r'\s+', ' ', soup.get_text(separator=" ")).strip()


def extract_snippet(msg_path: Path, config: dict) -> tuple[str, str]:
    """Return (sender, subject + snippet of body) for LLM context."""
    max_bytes = config.get("max_bytes", 2048)
    try:
        with msg_path.open("rb") as f:
            msg = email.message_from_binary_file(f)
    except Exception as exc:
        print(f"ERROR: reading {msg_path}: {exc}", file=sys.stderr)
        return "", ""

    sender = str(email.header.make_header(email.header.decode_header(msg.get("From", "(unknown sender)"))))
    subject = str(email.header.make_header(email.header.decode_header(msg.get("Subject", "(no subject)"))))
    
    body = ""
    # First, try to find a text/plain part
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                    break
                except Exception:
                    continue
    else: # Not multipart, try to get payload directly
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                raw = payload.decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    body = clean_html(raw)
                else:
                    body = raw
        except Exception:
            body = ""
            
    # If no plain text body was found, fall back to HTML
    if not body.strip() and msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    html_body = payload.decode(charset, errors="replace")
                    body = clean_html(html_body)
                    break
                except Exception:
                    continue
    
    # Final check for non-multipart HTML email
    if not body.strip() and not msg.is_multipart() and msg.get_content_type() == "text/html":
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            html_body = payload.decode(charset, errors="replace")
            body = clean_html(html_body)
        except Exception:
            pass

    extract = (subject + "\n" + body).strip()[:max_bytes]
    return sender, extract

CALIBRATION_FILE = CONFIG_DIR / "calibration.txt"

# Scores used when converting category names to numeric values for the LLM.
CATEGORY_SCORES = {"read": 78.00, "glance": 55.00, "ignore": 30.00}


def load_calibration() -> str:
    """Load calibration examples from ~/.email-flagger/calibration.txt.

    Each non-blank, non-comment line should look like:
        "Subject line" -> category (reason)
    where category is read, glance, or ignore.

    Returns the formatted calibration section for the prompt.
    """
    if not CALIBRATION_FILE.exists():
        return ""

    lines = []
    for raw in CALIBRATION_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Parse: "Subject" -> category (reason)
        m = re.match(r'^"(.+?)"\s*->\s*(read|glance|ignore)\s*\((.+?)\)\s*$', line)
        if not m:
            continue
        subject, category, reason = m.group(1), m.group(2), m.group(3)
        score = CATEGORY_SCORES[category]
        lines.append(f'- "{subject}" -> {score:.2f} ({reason})\n')

    return "".join(lines)


PROMPT_TEMPLATE = (
    "### ROLE\n"
    "You are an e-mail triage assistant. Score how much the recipient would want to know about this message.\n\n"

    "### RECIPIENT PROFILE\n"
    "{personal_context}\n\n"

    "### SCORING RUBRIC\n"
    "90-100  Must act NOW: direct personal request from a known person, urgent deadline, family emergency\n"
    "70-89   Should read soon: personal message needing a response, important work discussion requiring input, "
    "time-sensitive personal matter (child support, legal, health insurance case), password reset the recipient initiated\n"
    "50-69   Worth a glance: child's school district emails and class updates (gradebook, weekly summary, "
    "school closure notice), delivery/shipping notification, account login or signup confirmation, calendar invite or "
    "meeting update, personal correspondence or art from a friend, invoice/receipt/refund for a software service, "
    "GitHub PR notification from work repo, tax document (1099, W-2), new account welcome email, after-visit medical summary, "
    "labor negotiation update from school district, payment confirmation for a software or cloud service, "
    "someone reaching out to connect personally\n"
    "30-49   Probably skip: daily digest or summary email, automated billing/payment confirmation (carrier, bank, utility), "
    "news article or headline, product update announcement, political newsletter, social media notification, "
    "FICO/credit score alert, dry cleaner or retail receipt, SaaS product update, "
    "school newsletter that is purely informational with no action required\n"
    " 0-29   Noise: marketing spam, unsolicited ad, mass mailing, coupon/sale offer, recruiter spam, LinkedIn suggestion\n\n"

    "Key distinctions:\n"
    "- Child's school emails are \"glance\" (50-65) even if the subject says \"important\" or \"learning resources.\" "
    "Only score them 70+ if they explicitly ask the parent to sign up, attend, or respond.\n"
    "- Emails from the school district about closures, labor negotiations, or learning resources are informational updates -> 55.\n"
    "- Personal correspondence (including art-related emails from friends) -> 55. "
    "This includes casual emails with a friend's name in the subject.\n"
    "- After-visit medical summaries -> 55 (informational, glance).\n"
    "- Tax documents (1099, W-2, tax return document) -> 55 (glance).\n"
    "- Payment confirmation for a software/cloud service (e.g. Docker, Cursor, Intuit) -> 50 (glance, not skip).\n"
    '- "I want to connect" or "still waiting for your response" from a real person -> 52 (personal, glance).\n'
    "- New account welcome/signup email -> 52 (glance).\n"
    '- School newsletters (e.g. "Eagles\' Nest Newsletter") -> 52 (glance, parent wants to stay informed).\n'
    "- Carrier/utility billing (e.g. AT&T payment processed) -> 35 (skip).\n"
    '- Any "Re:" reply in a support case thread -> 75 (active case, read).\n'
    '- Any "Re: Friend, ..." email is personal correspondence -> 55 (glance), even if the subject sounds abstract.\n\n'

    "### CALIBRATION\n"
    "{calibration}"

    "### MESSAGE\n"
    "From: {sender}\n"
    "----- BEGIN -----\n{extract}\n----- END -----\n\n"

    "### OUTPUT FORMAT\n"
    "Return ONLY the score as a decimal with exactly two digits after the point, e.g. `42.00`\n"
)


def classify_content(sender: str, snippet: str, config: dict) -> tuple[str, float]:
    """Core classification: build prompt, query model, return (class, score).

    Works with any (sender, snippet) pair — from a live .eml file or a saved
    dataset entry — so the same scoring path is used for live email and
    benchmarking.
    """
    personal_context = build_personal_context(config)
    calibration = load_calibration()
    prompt = PROMPT_TEMPLATE.format(
        extract=snippet,
        personal_context=personal_context,
        sender=sender,
        calibration=calibration,
    )
    score = query_ollama(prompt, config)
    classification = get_classification_for_score(score, config)
    return classification, score


def classify_message_file(path_str: str, config: dict, return_score: bool = False) -> str:
    """Extract content from an .eml file, classify it, and log results."""
    log_message("-" * 40)
    log_message(f"Processing file: {path_str}")

    path = Path(path_str.strip())
    if not path.exists():
        log_message("Error: File does not exist.")
        return "ignore"

    sender, snippet = extract_snippet(path, config)
    if not snippet:
        log_message("Error: Could not extract snippet.")
        return "ignore"

    log_message(f"Extracted Sender: {sender}")
    log_message(f"Extracted Snippet:\n---\n{snippet}\n---")

    classification, score = classify_content(sender, snippet, config)
    log_message(f"Ollama Score: {score}")

    # Structured log entry for easy post-processing
    try:
        import datetime
        subject_preview = snippet.split("\n", 1)[0][:200]
        log_payload = {
            "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "score": score,
            "class": classification,
            "subject": subject_preview,
            "from": sender,
        }
        log_message("ENTRY " + json.dumps(log_payload, ensure_ascii=False))
    except Exception:
        pass

    log_message(f"Final Classification: {classification}")

    # Save to dataset for human review / tuning
    from email_flagger.dataset import append_entry
    append_entry(sender, snippet, score, classification)

    # Ring buffer: keep only the last 300 lines of the log file to avoid
    # unbounded growth when the classifier is invoked once per message via
    # AppleScript.
    try:
        MAX_LINES = 300
        lines = LOG_FILE.read_text().splitlines()
        if len(lines) > MAX_LINES:
            LOG_FILE.write_text("\n".join(lines[-MAX_LINES:]) + "\n")
    except Exception:
        pass

    if return_score:
        return classification, score
    else:
        return classification

def main() -> None:
    """Main entry point: read path, classify, print result."""
    if len(sys.argv) < 2:
        log_message("Error: No file path provided to script.")
        print("ignore")
        sys.exit(0)  # Don't fail, just return "ignore"

    # Load configuration (always succeeds with defaults)
    config = load_config()

    path_str = sys.argv[1]
    result = classify_message_file(path_str, config)
    print(result)

if __name__ == "__main__":
    main()