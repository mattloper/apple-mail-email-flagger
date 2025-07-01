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
            "red_min": 80,
            "blue_min": 60
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
        if classification in ['red', 'blue', 'none']:
            print("✅ Classification working correctly")
        else:
            print("⚠️  Unexpected classification result")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")

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
    
    args = parser.parse_args()
    
    if args.setup:
        setup_command()
    elif args.classify:
        classify_file(args.classify)
    elif args.test:
        test_classification()
    elif args.recent:
        from datetime import datetime
        # Ensure log exists
        log_path = CONFIG_DIR / "classifier.log"
        if not log_path.exists():
            print("No log file found yet.")
            sys.exit(0)

        entries = []
        with log_path.open() as f:
            for line in f:
                if line.startswith("ENTRY "):
                    try:
                        import json
                        payload = json.loads(line[len("ENTRY "):])
                        entries.append(payload)
                    except Exception:
                        continue

        if not entries:
            print("No structured entries found in log.")
            sys.exit(0)

        for item in entries[-args.recent:][::-1]:
            ts = item.get("ts", "")
            score = item.get("score")
            subj = item.get("subject", "")
            print(f"{score:6.2f} | {subj}")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()