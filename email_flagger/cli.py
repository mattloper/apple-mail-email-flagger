#!/usr/bin/env python3
"""
Email Flagger CLI - Main entry point
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
import shutil
import importlib.resources

# Configuration paths
CONFIG_DIR = Path.home() / ".email-flagger"
CONFIG_FILE = CONFIG_DIR / "config.json"
MAIL_SCRIPTS_DIR = Path.home() / "Library" / "Application Scripts" / "com.apple.mail"

def get_config_template():
    """Return the default config template."""
    return {
        "name": "Your Name",
        "llm_instructions": "Prioritize emails from my family (especially my mom, Susan) and anything related to the 'Project X' deadline. Deprioritize social media notifications and promotional content. If an email is from my boss, Mark, it's always high priority, unless it's a weekly digest.",
        "ollama": {
            "model": "llama3",
            "endpoint": "http://localhost:11434",
            "timeout": 60
        },
        "scoring": {
            "read_threshold": 80,
            "glance_threshold": 60
        },
        "max_bytes": 2048
    }

def check_config():
    """Check if config exists and is valid."""
    if not CONFIG_FILE.exists():
        return False, "Configuration file not found"
    
    try:
        with open(CONFIG_FILE) as f:
            config = json.load(f)
        
        # Basic validation - only require fields that don't have defaults
        required_fields = ["name", "llm_instructions"]
        for field in required_fields:
            if field not in config:
                return False, f"Missing required field: {field}"
        
        # Validate structure of nested fields if they exist
        if "ollama" in config and not isinstance(config["ollama"], dict):
            return False, "ollama field must be an object"
        if "scoring" in config and not isinstance(config["scoring"], dict):
            return False, "scoring field must be an object"
        
        return True, "Configuration valid"
    except json.JSONDecodeError:
        return False, "Invalid JSON in configuration file"
    except Exception as e:
        return False, f"Error reading config: {e}"

def create_config():
    """Create config directory and config file."""
    print("📝 Creating config file...")
    
    # Create config directory
    CONFIG_DIR.mkdir(exist_ok=True)
    
    # Create config file with template
    if not CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(get_config_template(), f, indent=2)
            print(f"✅ Created config at {CONFIG_FILE}")
            print("💡 Edit with: email-flagger --edit-config")
        except Exception as e:
            print(f"❌ Failed to create config file: {e}")
            return False
    return True

def check_python_setup():
    """Check if email-flagger-classify command is available."""
    print("🐍 Checking Python setup...")
    
    # Check if the console script is available
    if shutil.which('email-flagger-classify'):
        print("   ✅ email-flagger-classify command found")
        return True
    else:
        print("   ❌ email-flagger-classify command not found")
        print("   This should be installed automatically by pip")
        return False

def check_ollama():
    """Check if Ollama is available."""
    print("🤖 Checking Ollama...")
    
    # Check if ollama command exists
    if not shutil.which('ollama'):
        print("   ❌ Ollama not found")
        print("   📥 Install with: brew install ollama")
        return False
    
    # Simple check using curl
    try:
        result = subprocess.run(['curl', '-s', 'http://localhost:11434/api/tags'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("   ✅ Ollama is running")
            
            # Check if model exists
            try:
                result = subprocess.run(['ollama', 'list'], 
                                      capture_output=True, text=True, check=True)
                if 'llama' in result.stdout:
                    print("   ✅ Ollama model found")
                    return True
                else:
                    print("   ⚠️  No llama model found")
                    print("   📥 Install with: ollama pull llama3")
                    return False
            except subprocess.CalledProcessError:
                print("   ⚠️  Could not check Ollama models")
                return False
        else:
            print("   ❌ Ollama not running")
            print("   🚀 Start with: ollama serve")
            return False
    except subprocess.TimeoutExpired:
        print("   ❌ Ollama not responding")
        print("   🚀 Start with: ollama serve")
        return False
    except Exception as e:
        print(f"   ❌ Failed to check Ollama: {e}")
        return False

def install_applescript():
    """Install AppleScript to Mail directory."""
    print("📧 Installing AppleScript...")
    
    # Create Mail scripts directory
    MAIL_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Copy AppleScript
    try:
        applescript_content = importlib.resources.files('email_flagger').joinpath('templates/classifier_hook.applescript').read_text()
        
        applescript_path = MAIL_SCRIPTS_DIR / "classifier_hook.applescript"
        with open(applescript_path, 'w') as f:
            f.write(applescript_content)
        
        print("   ✅ AppleScript installed")
        return True
    except Exception as e:
        print(f"   ❌ Failed to install AppleScript: {e}")
        return False

def show_mail_rule_instructions():
    """Show instructions for creating Mail rule."""
    print("\n📋 Final step - Create Apple Mail rule:")
    print("   1. Open Apple Mail")
    print("   2. Go to Mail > Preferences > Rules (or Mail > Settings > Rules)")
    print("   3. Click 'Add Rule'")
    print("   4. Configure:")
    print("      - Description: Email Flagger")
    print("      - If: Every Message")
    print("      - Then: Run AppleScript > classifier_hook.applescript")
    print("   5. Click OK")
    print("\n🎉 Email Flagger is ready!")

def setup_command():
    """Setup and edit configuration."""
    # Create config if it doesn't exist
    if not CONFIG_FILE.exists():
        create_config()
    
    # Open editor - try TextEdit first, then fall back to nano
    editors = ['open', 'nano']
    editor_used = None
    
    for editor in editors:
        try:
            if editor == 'open':
                subprocess.run([editor, '-a', 'TextEdit', str(CONFIG_FILE)])
            else:
                subprocess.run([editor, str(CONFIG_FILE)])
            editor_used = editor
            break
        except Exception:
            continue
    
    if not editor_used:
        print(f"❌ Failed to open editor")
        return
    
    print("")
    print("📧 Final step - Create Mail rule:")
    print("   1. Mail > Preferences > Rules > Add Rule")
    print("   2. Name: Email Flagger")
    print("   3. If: Every Message")
    print("   4. Then: Run AppleScript > classifier_hook.applescript")
    print("")
    print("✅ Setup complete!")


def classify_file(file_path):
    """Classify a single email file."""
    if not Path(file_path).exists():
        print(f"❌ File not found: {file_path}")
        return
    
    try:
        result = subprocess.run(['email-flagger-classify', file_path], 
                              capture_output=True, text=True)
        classification = result.stdout.strip()
        print(f"📧 {file_path} → {classification}")
    except Exception as e:
        print(f"❌ Classification failed: {e}")

def test_classification():
    """Test classification with a sample email."""
    # Create a test email that should be classified as high priority
    test_email = """From: boss@company.com
To: user@company.com
Subject: URGENT: Board Meeting Tomorrow - Your Presentation Required

Hi,

The board meeting has been moved to tomorrow at 9 AM. We need your quarterly presentation ready by 8 AM sharp. This is critical for our Q4 numbers and the CEO will be attending.

Please confirm you can deliver this ASAP.

Thanks,
Sarah (your manager)
"""
    
    try:
        # Create temp file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.eml', delete=False) as f:
            f.write(test_email)
            temp_path = f.name
        
        # Classify it
        result = subprocess.run(['email-flagger-classify', temp_path], 
                              capture_output=True, text=True)
        classification = result.stdout.strip()
        
        # Clean up
        Path(temp_path).unlink()
        
        print(f"🧪 Test email classification: {classification}")
        if classification in ['read', 'glance', 'ignore']:
            print("✅ Classification working correctly")
        else:
            print("⚠️  Unexpected classification result")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")

IMPORT_APPLESCRIPT = '''\
tell application "Mail"
    set output to ""
    repeat with i from 1 to {n}
        try
            set m to message i of inbox
            set tmpPath to "/tmp/email_import_" & i & ".eml"
            set msgSource to source of m
            do shell script "echo " & quoted form of msgSource & " > " & quoted form of tmpPath
            set output to output & tmpPath & linefeed
        on error
            -- skip emails that can't be exported
        end try
    end repeat
    return output
end tell
'''


def import_mail_command(count):
    """Pull the last N emails from Apple Mail, classify each, save to dataset."""
    from email_flagger.classifier import (
        classify_content, extract_snippet, load_config,
    )
    from email_flagger.dataset import append_entry, existing_hashes, _snippet_hash

    print(f"Exporting last {count} emails from Apple Mail...")
    script = IMPORT_APPLESCRIPT.format(n=count)
    try:
        # ~1-2s per email for AppleScript export; be generous
        timeout = max(300, count * 3)
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            print(f"AppleScript error: {result.stderr.strip()}")
            return
    except subprocess.TimeoutExpired:
        print("Timed out waiting for Mail. Is Mail running?")
        return

    paths = [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]
    if not paths:
        print("No emails exported. Is Mail running with messages in inbox?")
        return

    config = load_config()
    known = existing_hashes()
    added, skipped = 0, 0

    print(f"Exported {len(paths)} emails. Classifying new ones...\n")
    for i, path in enumerate(paths, 1):
        p = Path(path)
        if not p.exists():
            continue

        sender, snippet = extract_snippet(p, config)
        if not snippet:
            continue

        # Skip if already in dataset
        if _snippet_hash(sender, snippet) in known:
            subj = snippet.split("\n", 1)[0][:60]
            print(f"  [{i}/{len(paths)}] {subj}  (already in dataset)")
            skipped += 1
            try:
                p.unlink()
            except Exception:
                pass
            continue

        subj = snippet.split("\n", 1)[0][:60]
        print(f"  [{i}/{len(paths)}] {subj}...", end=" ", flush=True)
        classification, score = classify_content(sender, snippet, config)
        print(f"score={score:.0f} ({classification})")

        append_entry(sender, snippet, score, classification, _known=known)
        added += 1

        try:
            p.unlink()
        except Exception:
            pass

    print(f"\nDone. {added} new, {skipped} already in dataset.")
    if added:
        print("Run: email-flagger --review")


def review_command(count):
    """Review recent classifications and label them."""
    from email_flagger.dataset import load_entries, load_labels, save_labels

    entries = load_entries()
    if not entries:
        print("No emails in dataset yet. Classifications are saved automatically.")
        return

    labels = load_labels()
    unreviewed = [e for e in entries if e["ts"] not in labels]

    if not unreviewed:
        print(f"All {len(entries)} emails have been reviewed.")
        print("Run --accuracy to see how well the model matches your preferences.")
        return

    # Show the most recent N unreviewed
    to_review = unreviewed[-count:]
    print(f"{len(unreviewed)} unreviewed emails. Showing {len(to_review)}.\n")
    print("For each email, choose:")
    print("  [i]gnore  = don't care about this email")
    print("  [g]lance  = want to see subject/sender but don't need to open it")
    print("  [r]ead    = need to actually open and read it")
    print("  [s]kip    = skip this one for now")
    print("  [q]uit    = stop reviewing\n")

    reviewed = 0
    for entry in to_review:
        score = entry.get("score", -1)
        cls = entry.get("class", "?")
        subj = entry.get("subject", "(no subject)")
        sender = entry.get("from", "(unknown)")
        ts = entry.get("ts", "")

        print(f"  Score: {score:.0f} ({cls})  |  {ts}")
        print(f"  From:  {sender}")
        print(f"  Subj:  {subj}")

        while True:
            try:
                ans = input("  [i]gnore / [g]lance / [r]ead / [s]kip / [q]uit ? ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                ans = "q"
            if ans in ("i", "ignore"):
                labels[ts] = "ignore"
                reviewed += 1
                break
            elif ans in ("g", "glance"):
                labels[ts] = "glance"
                reviewed += 1
                break
            elif ans in ("r", "read"):
                labels[ts] = "read"
                reviewed += 1
                break
            elif ans in ("s", "skip"):
                break
            elif ans in ("q", "quit"):
                save_labels(labels)
                print(f"\nSaved {reviewed} labels.")
                return
            else:
                print("  Type i, g, r, s, or q.")
        print()

    save_labels(labels)
    print(f"Saved {reviewed} labels. Total labeled: {len(labels)}/{len(entries)}")
    if len(labels) >= 5:
        print("Run --accuracy to see how the model is doing.")


BUILD_FILE = CONFIG_DIR / "build.json"


def deploy_command():
    """Reinstall the package from source so Apple Mail uses the latest code."""
    if not BUILD_FILE.exists():
        print("No build.json found. Run install.sh first.")
        return

    build = json.load(BUILD_FILE.open())
    source_dir = build.get("source_dir", "")
    if not source_dir or not Path(source_dir).is_dir():
        print(f"Source directory not found: {source_dir}")
        print("Re-run install.sh from the source checkout.")
        return

    import datetime
    venv_pip = CONFIG_DIR / "venv" / "bin" / "pip"
    print(f"Reinstalling from {source_dir} ...")
    result = subprocess.run(
        [str(venv_pip), "install", source_dir],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"pip install failed:\n{result.stderr}")
        return

    # Update build timestamp
    build["built_at"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with BUILD_FILE.open("w") as f:
        json.dump(build, f, indent=2)

    print(f"Deployed at {build['built_at']}")
    print("Apple Mail will use the new code on the next incoming message.")


def version_command():
    """Show installed version and build timestamp."""
    if BUILD_FILE.exists():
        build = json.load(BUILD_FILE.open())
        print(f"Source:  {build.get('source_dir', '?')}")
        print(f"Built:   {build.get('built_at', '?')}")
    else:
        print("No build.json found (installed via install.sh?)")

    # Show package version
    try:
        from importlib.metadata import version as pkg_version
        print(f"Package: email-flagger {pkg_version('email-flagger')}")
    except Exception:
        print("Package: email-flagger (version unknown)")


def accuracy_command():
    """Report classification accuracy against human labels."""
    from email_flagger.dataset import load_entries, load_labels, compute_accuracy

    entries = load_entries()
    labels = load_labels()

    if not labels:
        print("No labels yet. Run --review first to label some emails.")
        return

    metrics = compute_accuracy(entries, labels)
    n = metrics["n"]
    acc = metrics["accuracy"]

    print(f"Accuracy against your labels: "
          f"{int(acc * n)}/{n} ({100*acc:.0f}%)\n")

    # Per-bucket breakdown
    print(f"  {'Bucket':<8} {'Correct':>8} {'Total':>7} {'Accuracy':>10}")
    print(f"  {'-'*8} {'-'*8} {'-'*7} {'-'*10}")
    for bucket in ("read", "glance", "ignore"):
        b = metrics["buckets"].get(bucket, {"correct": 0, "total": 0})
        pct = f"{100*b['correct']/b['total']:.0f}%" if b["total"] else "n/a"
        print(f"  {bucket:<8} {b['correct']:>8} {b['total']:>7} {pct:>10}")

    # Show mismatches
    misses = metrics["misses"]
    if misses:
        print(f"\nMismatches ({len(misses)}):")
        for m in misses:
            print(f"  model={m['class']:4s}  you={m['label']:6s}  "
                  f"score={m['score']:5.0f}  {m['subject'][:60]}")
    else:
        print("\nPerfect match!")

    print(f"\nDataset: {len(labels)} labeled / {len(entries)} total")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="AI-powered email prioritization")
    parser.add_argument('--setup', action='store_true',
                       help='Setup and edit configuration')
    parser.add_argument('--classify', metavar='FILE',
                       help='Classify a single email file')
    parser.add_argument('--test', action='store_true',
                       help='Test classification with a sample email')
    parser.add_argument('--recent', metavar='N', type=int,
                       help='Show the last N classification scores from the log')
    parser.add_argument('--import-mail', metavar='N', type=int,
                       help='Import last N emails from Apple Mail into dataset')
    parser.add_argument('--review', metavar='N', type=int, nargs='?', const=10,
                       help='Review N recent emails (default 10) and label them')
    parser.add_argument('--accuracy', action='store_true',
                       help='Show accuracy against your labels')
    parser.add_argument('--deploy', action='store_true',
                       help='Reinstall package from source (after code changes)')
    parser.add_argument('--version', action='store_true',
                       help='Show installed version and build timestamp')

    args = parser.parse_args()

    import_n = getattr(args, 'import_mail', None)

    if args.deploy:
        deploy_command()
    elif args.version:
        version_command()
    elif args.setup:
        setup_command()
    elif args.classify:
        classify_file(args.classify)
    elif args.test:
        test_classification()
    elif import_n is not None:
        import_mail_command(import_n)
    elif args.review is not None:
        review_command(args.review)
    elif args.accuracy:
        accuracy_command()
    elif args.recent:
        # Ensure log exists
        log_path = CONFIG_DIR / "classifier.log"
        if not log_path.exists():
            print("No log file found yet.")
            sys.exit(0)

        entries = []
        with log_path.open() as f:
            for line in f:
                if " ENTRY " in line:
                    try:
                        payload = json.loads(line.split(" ENTRY ",1)[1])
                        entries.append(payload)
                    except Exception:
                        continue

        if not entries:
            print("No structured entries found in log.")
            sys.exit(0)

        print("Care scores (most recent first):")
        for item in entries[-args.recent:][::-1]:
            score = item.get("score")
            cls = item.get("class")
            subj = item.get("subject", "")
            print(f"{score:6.2f} ({cls}) : {subj}")

        print(f"\nFull log available at: {log_path}")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()