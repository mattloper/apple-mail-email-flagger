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
            "red_min": 80,
            "blue_min": 60
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
        return "none"
    
    scoring = config.get("scoring", {})
    red_min = scoring.get("red_min", 80)
    blue_min = scoring.get("blue_min", 60)
    
    if score >= red_min:
        return "red"
    elif score >= blue_min:
        return "blue"
    else:
        return "none"

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
                body = payload.decode(charset, errors="replace")
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
                    # Simple regex to strip HTML tags
                    body = re.sub('<[^<]+?>', '', html_body)
                    break
                except Exception:
                    continue
    
    # Final check for non-multipart HTML email
    if not body.strip() and not msg.is_multipart() and msg.get_content_type() == "text/html":
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            html_body = payload.decode(charset, errors="replace")
            body = re.sub('<[^<]+?>', '', html_body)
        except Exception:
            pass

    extract = (subject + "\n" + body).strip()[:max_bytes]
    return sender, extract

def classify_message_file(path_str: str, config: dict, return_score: bool = False) -> str:
    """Orchestrates the classification of a single email file."""
    log_message("-" * 40)
    log_message(f"Processing file: {path_str}")
    
    path = Path(path_str.strip())
    if not path.exists():
        log_message("Error: File does not exist.")
        return "none"

    sender, snippet = extract_snippet(path, config)
    if not snippet:
        log_message("Error: Could not extract snippet.")
        return "none"
        
    log_message(f"Extracted Sender: {sender}")
    log_message(f"Extracted Snippet:\n---\n{snippet}\n---")

    # Build prompt from config
    personal_context = build_personal_context(config)
    
    prompt_template = (
        "### ROLE\n"
        "You are an **e-mail triage assistant**. Your job is to decide how urgently the recipient needs to personally handle an incoming message.\n\n"

        "### RECIPIENT PROFILE\n"
        "{personal_context}\n\n"

        "### INCOMING MESSAGE METADATA\n"
        "From: {sender}\n\n"

        "### INCOMING MESSAGE CONTENT\n"
        "----- BEGIN MESSAGE -----\n{extract}\n----- END MESSAGE -----\n\n"

        "### TASK\n"
        "Analyse the message *in context* and produce a **care score** between 0.00 and 100.00 inclusive.\n"
        "A higher score means the recipient must act quickly; a lower score means it can wait or be ignored.\n\n"

        "### OUTPUT FORMAT (MUST-FOLLOW)\n"
        "Return ONLY the score as a decimal with exactly two digits after the point, e.g.\n"
        "`42.00`\n"
    )
    
    prompt = prompt_template.format(
        extract=snippet, 
        personal_context=personal_context, 
        sender=sender
    )
    
    score = query_ollama(prompt, config)
    log_message(f"Ollama Score: {score}")
    
    classification = get_classification_for_score(score, config)

    # Structured log entry for easy post-processing
    try:
        import json, datetime
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

    if return_score:
        return classification, score
    else:
        return classification

def main() -> None:
    """Main entry point: read path, classify, print result."""
    if len(sys.argv) < 2:
        log_message("Error: No file path provided to script.")
        print("none")
        sys.exit(0)  # Don't fail, just return "none"

    # Load configuration (always succeeds with defaults)
    config = load_config()

    path_str = sys.argv[1]
    result = classify_message_file(path_str, config)
    print(result)

if __name__ == "__main__":
    main()