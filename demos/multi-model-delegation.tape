Output demos/multi-model-delegation.gif
Set FontSize 22
Set Width 1400
Set Height 800
Set Theme "Dracula"
Set TypingSpeed 80ms
Set Framerate 30
Set WindowBar Colorful

Hide
Type "python3 demos/demo-shell.py multi-model-delegation"
Enter
Sleep 500ms
Show

Type '/create-prompt "add a billing summary table"'
Sleep 500ms
Enter
Sleep 2s

Type '/create-prompt "add audit log filters"'
Sleep 500ms
Enter
Sleep 2s

Type '/create-prompt "add CSV export"'
Sleep 500ms
Enter
Sleep 2s

Type "/run-prompt 001 002 003 --parallel --model gemini"
Sleep 500ms
Enter
Sleep 3s
