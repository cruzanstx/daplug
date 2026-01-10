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
Sleep 300ms
Show

# Create first prompt
Type '/create-prompt "add a billing summary table"'
Sleep 1200ms
Enter
Sleep 2000ms

# Create second prompt
Type '/create-prompt "add audit log filters"'
Sleep 1200ms
Enter
Sleep 2000ms

# Create third prompt
Type '/create-prompt "add CSV export"'
Sleep 1200ms
Enter
Sleep 2500ms

# Run all prompts in parallel with gemini
Type "/run-prompt 001 002 003 --parallel --model gemini"
Sleep 1500ms
Enter
Sleep 5500ms
