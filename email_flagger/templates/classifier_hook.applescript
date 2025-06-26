-- classifier_hook.applescript
-- Email Flagger AppleScript hook for Apple Mail
-- Automatically installed by email-flagger package

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