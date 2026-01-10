Output demos/create-and-run-prompt.gif
Set FontSize 18
Set Width 1200
Set Height 750
Set Theme "Dracula"
Set TypingSpeed 50ms
Set Framerate 30
Set WindowBar Colorful
Set Padding 20

Hide
Type "python3 demos/demo-shell.py create-and-run-prompt"
Enter
Sleep 200ms
Show

# User types the create-prompt command at the > prompt
Type '/create-prompt "add a login form with email validation"'
Sleep 300ms
Enter
Sleep 2000ms

# User selects option 1 (Run prompt now)
Type "1"
Sleep 200ms
Enter
Sleep 2000ms

# User selects option 3 (codex)
Type "3"
Sleep 200ms
Enter
Sleep 3000ms
