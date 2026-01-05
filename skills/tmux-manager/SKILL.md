---
name: tmux-manager
description: Manage tmux sessions for background tasks. Use when user asks about background processes, wants to monitor running tasks, attach to sessions, list active sessions, or kill stuck processes.
allowed-tools:
  - Bash(tmux:*)
  - Bash(sleep:*)
  - Read
  - Glob
---

# tmux Session Management

Create, monitor, and manage tmux sessions for background task execution.

## When to Use This Skill

- User asks "what's running in the background?"
- User wants to "attach to a session" or "check on a task"
- User asks to "list sessions" or "kill a stuck process"
- User wants to run something in the background
- After spawning parallel tasks, to monitor progress

## Core Operations

### List All Sessions

```bash
tmux ls
```

### List Sessions by Pattern

```bash
# Find sessions from a specific run
RUN_ID="20241213-153012"
tmux ls 2>/dev/null | grep "$RUN_ID" || echo "No sessions matching $RUN_ID"

# Find prompt-related sessions
tmux ls 2>/dev/null | grep "prompt-" || echo "No prompt sessions found"

# Find codex sessions
tmux ls 2>/dev/null | grep "codex-" || echo "No codex sessions found"
```

### Create a Background Session

```bash
SESSION_NAME="my-task-$(date +%Y%m%d-%H%M%S)"
WORKING_DIR="/path/to/directory"

# Create session with specific working directory
tmux new-session -d -s "$SESSION_NAME" -c "$WORKING_DIR"

# Send commands to the session
tmux send-keys -t "$SESSION_NAME" "echo 'Starting task...'" C-m
tmux send-keys -t "$SESSION_NAME" "your-command-here" C-m

echo "Session started: $SESSION_NAME"
echo "Attach with: tmux attach -t $SESSION_NAME"
```

### Launch Claude in Background Session

```bash
SESSION_NAME="claude-task-$(date +%Y%m%d-%H%M%S)"
WORKING_DIR="/path/to/worktree"

tmux new-session -d -s "$SESSION_NAME" -c "$WORKING_DIR"
tmux send-keys -t "$SESSION_NAME" "claude" C-m
sleep 2  # Wait for directory trust prompt
tmux send-keys -t "$SESSION_NAME" C-m  # Auto-approve
sleep 2  # Wait for Claude to be ready
tmux send-keys -t "$SESSION_NAME" "Your task instructions here" C-m

echo "Claude session started: $SESSION_NAME"
```

### Check Session Status

```bash
SESSION_NAME="prompt-005-20241213-153012"

# Check if session exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "Session $SESSION_NAME is running"

    # Capture recent output (last 100 lines)
    tmux capture-pane -t "$SESSION_NAME" -p -S -100
else
    echo "Session $SESSION_NAME has ended"
fi
```

### Capture Session Output

```bash
SESSION_NAME="my-session"

# Capture visible pane content
tmux capture-pane -t "$SESSION_NAME" -p

# Capture with history (last N lines)
tmux capture-pane -t "$SESSION_NAME" -p -S -500

# Save to file
tmux capture-pane -t "$SESSION_NAME" -p -S -1000 > session-output.txt
```

### Attach to Session

```bash
# Attach to specific session
tmux attach -t "$SESSION_NAME"

# Detach: Press Ctrl+B, then D
```

### Kill a Session

```bash
# Kill specific session
tmux kill-session -t "$SESSION_NAME"

# Kill all sessions matching pattern
for session in $(tmux ls -F "#{session_name}" 2>/dev/null | grep "prompt-"); do
    tmux kill-session -t "$session"
    echo "Killed: $session"
done
```

### Wait for Session to Complete

```bash
SESSION_NAME="my-task"

echo "Waiting for $SESSION_NAME to complete..."
while tmux has-session -t "$SESSION_NAME" 2>/dev/null; do
    sleep 5
done
echo "Session $SESSION_NAME has ended"
```

### Monitor Multiple Sessions

```bash
# List all sessions with their status
echo "Active tmux sessions:"
tmux ls -F "#{session_name}: #{session_windows} windows, created #{session_created_string}" 2>/dev/null || echo "No active sessions"

# Check specific sessions from a run
RUN_ID="20241213-153012"
SESSIONS=("prompt-005-$RUN_ID" "prompt-006-$RUN_ID" "prompt-007-$RUN_ID")

for session in "${SESSIONS[@]}"; do
    if tmux has-session -t "$session" 2>/dev/null; then
        echo "$session: RUNNING"
    else
        echo "$session: COMPLETED"
    fi
done
```

## Parallel Task Patterns

### Launch Multiple Sessions

```bash
declare -A SESSIONS
TASKS=("task1" "task2" "task3")
RUN_ID="$(date +%Y%m%d-%H%M%S)"

for task in "${TASKS[@]}"; do
    SESSION_NAME="${task}-${RUN_ID}"
    tmux new-session -d -s "$SESSION_NAME"
    tmux send-keys -t "$SESSION_NAME" "echo 'Running $task'" C-m
    SESSIONS[$task]="$SESSION_NAME"
    echo "Started: $SESSION_NAME"
done

echo ""
echo "Monitor with: tmux ls | grep $RUN_ID"
```

### Wait for All Sessions

```bash
SESSIONS=("session1" "session2" "session3")

echo "Waiting for all sessions to complete..."
all_done=false
while [ "$all_done" = false ]; do
    all_done=true
    for session in "${SESSIONS[@]}"; do
        if tmux has-session -t "$session" 2>/dev/null; then
            all_done=false
            break
        fi
    done
    [ "$all_done" = false ] && sleep 5
done
echo "All sessions completed"
```

## Troubleshooting

**tmux not installed**
```bash
# Check installation
which tmux || echo "tmux not installed"

# Install
sudo apt install tmux  # Debian/Ubuntu
brew install tmux      # macOS
```

**Session not found**
```bash
# List all sessions to find correct name
tmux ls

# Check if session ended
# (no output means session doesn't exist)
tmux has-session -t "session-name" 2>/dev/null && echo "exists" || echo "not found"
```

**Can't attach (already attached elsewhere)**
```bash
# Detach other clients first
tmux detach-client -t "session-name"
# Then attach
tmux attach -t "session-name"
```

**Session stuck/frozen**
```bash
# Force kill
tmux kill-session -t "session-name"
```
