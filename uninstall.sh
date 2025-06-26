#!/bin/bash

echo "Uninstalling Email Flagger..."

# Define paths
CONFIG_DIR="$HOME/.email-flagger"
MAIL_SCRIPT="$HOME/Library/Application Scripts/com.apple.mail/classifier_hook.applescript"

# Remove files (preserve config.json)
if [ -d "$CONFIG_DIR" ]; then
    # Backup config to temp location if it exists
    if [ -f "$CONFIG_DIR/config.json" ]; then
        cp "$CONFIG_DIR/config.json" "/tmp/email-flagger-config.json.backup"
        CONFIG_BACKUP_EXISTS=true
    else
        CONFIG_BACKUP_EXISTS=false
    fi
    
    rm -rf "$CONFIG_DIR"
    
    # Restore config from temp location
    if [ "$CONFIG_BACKUP_EXISTS" = true ]; then
        mkdir -p "$CONFIG_DIR"
        mv "/tmp/email-flagger-config.json.backup" "$CONFIG_DIR/config.json"
        echo "Removed ~/.email-flagger directory (preserved config.json)"
    else
        echo "Removed ~/.email-flagger directory"
    fi
fi

if [ -f "$MAIL_SCRIPT" ]; then
    rm "$MAIL_SCRIPT"
    echo "Removed AppleScript"
fi

if [ -f "$HOME/.email-flagger/email_flagger_log.txt" ]; then
    rm "$HOME/.email-flagger/email_flagger_log.txt"
    echo "Removed AppleScript log file"
fi

# Note: Smart alias remains in shell config and will automatically deactivate

echo ""
echo "Uninstall complete!"
echo ""
echo "Manually remove the 'Email Flagger' rule from Mail > Preferences > Rules"