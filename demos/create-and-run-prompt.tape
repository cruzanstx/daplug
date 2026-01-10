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
Sleep 300ms
Show

# User types the create-prompt command
Type '/create-prompt "add a login form with email validation"'
Sleep 1500ms
Enter
Sleep 3500ms

# User reads the prompt created, then selects option 1
Type "1"
Sleep 1000ms
Enter
Sleep 3500ms

# User reviews model options, selects codex
Type "3"
Sleep 1000ms
Enter
Sleep 4500ms
