Output demos/multi-model-delegation.gif
Set FontSize 18
Set Width 1200
Set Height 700
Set Theme "Dracula"
Set TypingSpeed 60ms
Set Framerate 30
Set WindowBar Colorful
Set Padding 20

Hide
Type "python3 demos/demo-shell.py multi-model-delegation"
Enter
Sleep 300ms
Show

Type '/create-prompt "add a billing summary table"'
Sleep 400ms
Enter
Sleep 1500ms

Type '/create-prompt "add audit log filters"'
Sleep 400ms
Enter
Sleep 1500ms

Type '/create-prompt "add CSV export"'
Sleep 400ms
Enter
Sleep 2000ms

Type "/run-prompt 001 002 003 --parallel --model gemini"
Sleep 400ms
Enter
Sleep 4000ms
