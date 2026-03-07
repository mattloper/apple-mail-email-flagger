# Email Flagger

AI-powered email prioritization for Apple Mail. Runs 100 % locally—no cloud ever.

## Features

• Flags emails: **red flag** (read now), no color (worth a glance), **gray** background (ignore).
• Uses an open-source LLM via [Ollama](https://ollama.ai) (default: `llama3`).
• Fully configurable priorities, thresholds, and model settings.
• One-line install & uninstall scripts, no admin rights required.

## Quick start

```bash
# clone and install to ~/.email-flagger
git clone https://github.com/mattloper/email-flagger.git
cd email-flagger
./install.sh
```

The installer will:

1. Create a private virtual-environment in `~/.email-flagger`
2. Install the `email_flagger` Python package inside it
3. Add smart aliases (`email-flagger`, `email-flagger-classify`) to your shell
4. Copy `classifier_hook.applescript` into `~/Library/Application Scripts/com.apple.mail/`
5. Check for Ollama and automatically pull the `llama3` model if needed
6. Print instructions for adding the Apple Mail rule

Restart your terminal afterwards so the new aliases are picked up, then run:

```bash
email-flagger --setup
```

This opens your config file in TextEdit and repeats the Mail-rule instructions.

## Prerequisites

• macOS with Apple Mail
• Python 3.7 +
• [uv](https://github.com/astral-sh/uv) (`brew install uv`)
• [Ollama](https://ollama.ai) running locally with a pulled model

```bash
# install ollama via Homebrew
brew install ollama
# start the API and enable it to start on reboot
brew services start ollama
# pull the default model (required for classification)
ollama pull llama3
```

## Usage

With the Mail rule enabled every incoming message is evaluated automatically.  
You can also classify a `.eml` file manually:

```bash
# classify a single file via the helper script
email-flagger-classify ~/Desktop/some_message.eml

# …or through the main CLI
email-flagger --classify ~/Desktop/some_message.eml
```

Self-test (runs a synthetic high-priority email):

```bash
email-flagger --test
```

CLI summary:

```
email-flagger --setup                # edit config + rule instructions
email-flagger --classify FILE.eml    # classify a single message
email-flagger --test                 # sanity-check your setup
email-flagger --import-mail 100      # import last N emails from Apple Mail
email-flagger --review               # label emails as ignore/glance/read
email-flagger --accuracy             # measure model accuracy vs your labels
email-flagger --recent 10            # show last N classification scores
email-flagger --deploy               # reinstall package after code changes
email-flagger --version              # show build timestamp and source dir
```

## Configuration

Your personal settings live in `~/.email-flagger/config.json`. A template is written the first time you run `email-flagger --setup`.

Key options:

* `name` – how the LLM should refer to you
* `llm_instructions` – free-form guidance (e.g. "Always prioritize emails from my boss…") 
* `ollama.model`, `ollama.endpoint`, `ollama.timeout`
* `scoring.read_threshold` – minimum care-score for "read" (default 80)
* `scoring.glance_threshold` – minimum care-score for "glance" (default 60)
* `max_bytes` – how many bytes of the email to send to the model

Changes are picked up the next time a message is processed.

## Calibration

You can teach the model what kinds of emails matter to you by editing `~/.email-flagger/calibration.txt`. Each line is an example:

```
"Email from my boss about deadline" -> read (direct request, needs action)
"Weekly school summary" -> glance (stay informed about kid's school)
"Your Daily Digest" -> ignore (automated summary)
```

Categories are `read`, `glance`, and `ignore`. The parenthetical explains why — this helps the model generalize to similar emails. A default set of examples is created on install; add your own for best results.

## How it works

1. An Apple Mail rule saves each new message to a temp file and calls `email-flagger-classify <file>`.
2. The classifier:
   • extracts sender, subject, and body (plain-text or HTML)  
   • builds a prompt using your config  
   • asks Ollama for a "care score" between 0 – 100  
   • maps that score to a category (`read`, `glance`, or `ignore`)
3. The AppleScript applies the matching visual treatment in Mail (red flag, no color, or gray background).

Adjust thresholds in `config.json` to change the sensitivity.

## Development

After editing the Python source, you must reinstall the package for Apple Mail to pick up changes:

```bash
email-flagger --deploy    # quickest way (reads source path from build.json)
./install.sh              # full reinstall (safe to re-run)
```

**Do not use `pip install -e` (editable mode).** Apple Mail runs scripts inside a sandbox that cannot access paths outside `~/.email-flagger`. An editable install symlinks back to your source directory, which the sandbox blocks — you'll see `No module named email_flagger` in `~/.email-flagger/email_flagger_log.txt`.

**Always use `uv pip`, never raw `pip`.** The venv's bundled pip can cache stale builds and silently install old code. `uv` builds fresh every time.

## Uninstall

```bash
./uninstall.sh
```

This removes the virtual-environment, aliases, AppleScript, and logs while preserving your `config.json` (handy if you reinstall later). Don't forget to delete the "Email Flagger" rule in Mail preferences.

## Troubleshooting

* `email-flagger-classify: command not found`  → restart your terminal or run `source ~/.zshrc`
* "Ollama not running" errors  → `brew services start ollama`
* "No model found" errors  → `ollama pull llama3`
* Emails not flagged  → verify the Mail rule points to `classifier_hook.applescript`
* Code changes not taking effect → run `email-flagger --deploy` to reinstall
* Logs for deep-dive debugging: `~/.email-flagger/classifier.log` and `~/.email-flagger/email_flagger_log.txt`

## License

MIT