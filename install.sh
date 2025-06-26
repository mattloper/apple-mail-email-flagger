#!/bin/bash

set -e

# Function to handle cleanup on exit
cleanup() {
    local exit_code=$?
    # Clean up any temp files
    rm -f /tmp/test_email_*.eml 2>/dev/null || true
    rm -f /tmp/test_applescript.scpt 2>/dev/null || true
    exit $exit_code
}

trap cleanup EXIT INT TERM

echo "Installing Email Flagger..."

# Check for Python
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: Python 3 required. Please install Python 3.7+ first."
    exit 1
fi

# Set up directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.email-flagger"
VENV_DIR="$CONFIG_DIR/venv"
BIN_DIR="$CONFIG_DIR/bin"

# Create virtual environment and install
mkdir -p "$CONFIG_DIR" "$BIN_DIR"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip >/dev/null 2>&1
pip install "$SCRIPT_DIR" >/dev/null 2>&1

# Create wrapper scripts
cat > "$BIN_DIR/email-flagger" << EOF
#!/bin/bash
source "$VENV_DIR/bin/activate"
exec python -m email_flagger.cli "\$@"
EOF

cat > "$BIN_DIR/email-flagger-classify" << EOF
#!/bin/bash
source "$VENV_DIR/bin/activate"
exec python -m email_flagger.classifier "\$@"
EOF

chmod +x "$BIN_DIR/email-flagger" "$BIN_DIR/email-flagger-classify"
CLASSIFY_PATH="$BIN_DIR/email-flagger-classify"

# Install AppleScript
MAIL_SCRIPTS_DIR="$HOME/Library/Application Scripts/com.apple.mail"
mkdir -p "$MAIL_SCRIPTS_DIR"

cat > "$MAIL_SCRIPTS_DIR/classifier_hook.applescript" << 'EOF'
-- classifier_hook.applescript
-- Email Flagger AppleScript hook for Apple Mail

using terms from application "Mail"
	on perform mail action with messages theMessages for rule theRule
		-- Ensure log directory exists and define log file path in ~/.email-flagger
		do shell script "mkdir -p $HOME/.email-flagger"
		set logFile to POSIX file ((POSIX path of (path to home folder) & ".email-flagger/email_flagger_log.txt"))
		
		tell application "Mail"
			repeat with eachMessage in theMessages
				try
					-- Save the raw source of the email to a temporary file with unique name.
					set tmpPath to "/tmp/email_" & (random number from 10000 to 99999) & "_" & (do shell script "date +%s") & ".eml"
					set msgSource to source of eachMessage
					do shell script "echo " & quoted form of msgSource & " > " & quoted form of tmpPath
					
					-- Use the installed classifier with full path
					set fullCommand to "$HOME/.email-flagger/bin/email-flagger-classify " & quoted form of tmpPath
					
					-- Log the command we're about to run
					my log_to_file("Running command: " & fullCommand, logFile)
					
					-- Call the Python script and get the result
					set resultClassification to do shell script fullCommand
					
					-- Clean up temp file
					do shell script "rm -f " & quoted form of tmpPath
					
					-- Log the result
					my log_to_file("Python script result: [" & resultClassification & "]", logFile)
					
					-- Set the flag/color based on the Python script's output.
					if resultClassification is "red" then
						set background color of eachMessage to red
					else if resultClassification is "blue" then
						set background color of eachMessage to blue
					else
						-- For "none" or any other result, clear the background color.
						set background color of eachMessage to none
					end if
					
				on error errMsg number errNum
					-- If anything above fails, log the error.
					my log_to_file("AppleScript Error: " & errNum & ": " & errMsg, logFile)
				end try
			end repeat
		end tell
	end perform mail action with messages
end using terms from

-- Helper function to append text to a log file
on log_to_file(log_string, log_file_path)
	do shell script "echo \"$(date '+%Y-%m-%d %H:%M:%S'): " & quoted form of log_string & "\" >> " & quoted form of POSIX path of log_file_path
end log_to_file
EOF

# Validate AppleScript syntax
if ! osacompile -o /tmp/test_applescript.scpt "$MAIL_SCRIPTS_DIR/classifier_hook.applescript" 2>/dev/null; then
    echo "ERROR: AppleScript syntax error"
    exit 1
fi
rm -f /tmp/test_applescript.scpt

# Function to create Mail rule automatically
create_mail_rule() {
    echo "📧 Creating Apple Mail rule..."
    
    # Create AppleScript to add the rule
    local rule_script=$(cat << 'RULE_EOF'
tell application "Mail"
    try
        -- Check if rule already exists
        set ruleExists to false
        set ruleList to every rule
        repeat with i from 1 to count of ruleList
            set currentRule to item i of ruleList
            if name of currentRule is "Email Flagger" then
                set ruleExists to true
                exit repeat
            end if
        end repeat
        
        if not ruleExists then
            -- Create new rule
            set newRule to make new rule at end of rules with properties {name:"Email Flagger", enabled:true}
            
            -- Add condition: matches any content (effectively every message)
            make new rule condition at end of rule conditions of newRule with properties {rule type:any recipient, qualifier:does not contain value, expression:"@@@NONEXISTENT@@@"}
            
            -- Add action: run AppleScript
            tell newRule
                set run script to "classifier_hook.applescript"
            end tell
            
            return "SUCCESS: Email Flagger rule created"
        else
            return "INFO: Email Flagger rule already exists"
        end if
        
    on error errorMessage number errorNumber
        return "ERROR: " & errorMessage & " (" & errorNumber & ")"
    end try
end tell
RULE_EOF
)
    
    # Execute the AppleScript
    local result=$(osascript -e "$rule_script" 2>&1)
    
    if [[ $result == "SUCCESS:"* ]]; then
        echo "   ✅ Mail rule created successfully"
        return 0
    elif [[ $result == "INFO:"* ]]; then
        echo "   ℹ️  Mail rule already exists"
        return 0
    else
        echo "   ❌ Failed to create Mail rule: $result"
        return 1
    fi
}

# Note: Automatic Mail rule creation is complex due to AppleScript limitations
# For now, we'll provide clear manual instructions
RULE_CREATED=false

# Add smart alias to shell config (only if not already there)
python3 << 'EOF'
import os

shell_config = os.path.expanduser("~/.zshrc")
smart_alias = '''# Email Flagger auto-alias (safe to leave permanently)
if [ -f "$HOME/.email-flagger/bin/email-flagger" ]; then
    alias email-flagger="$HOME/.email-flagger/bin/email-flagger"
fi'''

# Read existing file
if os.path.exists(shell_config):
    with open(shell_config, 'r') as f:
        content = f.read()
else:
    content = ""

# Check if our smart alias already exists
if "Email Flagger auto-alias" in content:
    print("Smart alias already exists")
else:
    # Append our smart alias
    with open(shell_config, 'a') as f:
        f.write("\n" + smart_alias + "\n")
    print(f"Added smart alias to {shell_config}")
EOF

echo ""
echo "Installation complete!"
echo "Created ~/.email-flagger directory" 
echo "Created $MAIL_SCRIPTS_DIR/classifier_hook.applescript"
echo "Added 'email-flagger' command alias"
echo ""
echo "IMPORTANT: Restart your terminal to use the 'email-flagger' command"
echo "Then run: email-flagger --setup"

echo ""
echo "📋 Final step – add the Apple Mail rule in Apple Mail (cannot be automated reliably):"
echo "   1. Open Apple Mail"
echo "   2. Go to Mail > Preferences > Rules (or Settings > Rules)"
echo "   3. Click 'Add Rule'"
echo "   4. Configure:"
echo "        • Description: Email Flagger"
echo "        • If: Every Message"
echo "        • Then: Run AppleScript > classifier_hook.applescript"
echo "   5. Click OK"