# Email Flagger

AI-powered email prioritization for Apple Mail. Runs 100 % locally—no cloud ever.

## Features

• Flags emails with **red** (urgent) or **blue** (important) background colors automatically.
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
5. Print instructions for adding the Apple Mail rule

Restart your terminal afterwards so the new aliases are picked up, then run:

```bash
email-flagger --setup
```

This opens your config file in TextEdit and repeats the Mail-rule instructions.

## Prerequisites

• macOS with Apple Mail  
• Python 3.7 +  
• [Ollama](https://ollama.ai) running locally with a pulled model

```bash
# install ollama via Homebrew
brew install ollama
# start the API (pulls the model on first run)
ollama serve &
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
```

## Configuration

Your personal settings live in `~/.email-flagger/config.json`. A template is written the first time you run `email-flagger --setup`.

Key options:

* `name` – how the LLM should refer to you
* `llm_instructions` – free-form guidance (e.g. "Always prioritize emails from my boss…") 
* `ollama.model`, `ollama.endpoint`, `ollama.timeout`
* `scoring.red_min` – minimum care-score for a red flag (default 80)
* `scoring.blue_min` – minimum care-score for a blue flag (default 60)
* `max_bytes` – how many bytes of the email to send to the model

Changes are picked up the next time a message is processed.

## How it works

1. An Apple Mail rule saves each new message to a temp file and calls `email-flagger-classify <file>`.
2. The classifier:
   • extracts sender, subject, and body (plain-text or HTML)  
   • builds a prompt using your config  
   • asks Ollama for a "care score" between 0 – 100  
   • maps that score to a color (`red`, `blue`, or none)
3. The AppleScript applies the matching background color in Mail.

Adjust thresholds in `config.json` to change the sensitivity.

## Uninstall

```bash
./uninstall.sh
```

This removes the virtual-environment, aliases, AppleScript, and logs while preserving your `config.json` (handy if you reinstall later). Don't forget to delete the "Email Flagger" rule in Mail preferences.

## Troubleshooting

* `email-flagger-classify: command not found`  → restart your terminal or run `source ~/.zshrc`
* "Ollama not running" errors  → `ollama serve`
* Email not coloured  → verify the Mail rule points to `classifier_hook.applescript`
* Logs for deep-dive debugging: `~/.email-flagger/classifier.log` and `~/.email-flagger/email_flagger_log.txt`

## License

MIT