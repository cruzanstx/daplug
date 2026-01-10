Output demos/multi-model-delegation.gif
Set FontSize 18
Set Width 1200
Set Height 750
Set Theme "Dracula"
Set TypingSpeed 50ms
Set Framerate 30
Set WindowBar Colorful
Set Padding 20

Hide
Type "python3 demos/demo-shell.py multi-model-delegation"
Enter
Sleep 200ms
Show

# Create first prompt
Type '/create-prompt "add a billing summary table"'
Sleep 300ms
Enter
Sleep 1200ms

# Create second prompt
Type '/create-prompt "add audit log filters"'
Sleep 300ms
Enter
Sleep 1200ms

# Create third prompt
Type '/create-prompt "add CSV export"'
Sleep 300ms
Enter
Sleep 1500ms

# Run all in parallel
Type "/run-prompt 001 002 003 --parallel --model gemini"
Sleep 300ms
Enter
Sleep 4000ms
