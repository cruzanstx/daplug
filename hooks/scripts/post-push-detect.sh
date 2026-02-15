#!/usr/bin/env bash

# PostToolUse hook: detect successful `git push` and nudge Claude to spawn the
# pipeline-deploy-monitor agent. Exits 0 with no output for non-push commands.

set -o pipefail

input="$(cat)"
if [[ -z "${input//[[:space:]]/}" ]]; then
  exit 0
fi

cmd="$(
  printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null
)" || cmd=""

if [[ -z "$cmd" ]]; then
  exit 0
fi

# Regex per task: ^git\s+push\b (word boundary approximated as whitespace or EOL).
if ! printf '%s\n' "$cmd" | grep -Eq '^git[[:space:]]+push([[:space:]]|$)'; then
  exit 0
fi

exit_code="$(
  printf '%s' "$input" | jq -r '.tool_response.exit_code // .tool_response.exitCode // empty' 2>/dev/null
)" || exit_code=""

if [[ -n "$exit_code" && "$exit_code" != "0" ]]; then
  exit 0
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
plugin_root="$(cd -- "$script_dir/../.." && pwd -P)"
config_reader="$plugin_root/skills/config-reader/scripts/config.py"

if [[ -f "$config_reader" ]]; then
  auto_pipeline_monitor="$(
    python3 "$config_reader" --quiet get auto_pipeline_monitor 2>/dev/null | head -n 1 | tr -d '\r'
  )" || auto_pipeline_monitor=""

  auto_pipeline_monitor="$(printf '%s' "$auto_pipeline_monitor" | tr '[:upper:]' '[:lower:]')"
  if [[ "$auto_pipeline_monitor" == "disabled" ]]; then
    exit 0
  fi
fi

remote=""
branch=""
remote_from_option="0"

read -r -a tokens <<< "$cmd"
positional=()

idx=2
while (( idx < ${#tokens[@]} )); do
  tok="${tokens[idx]}"

  if [[ "$tok" == "--" ]]; then
    ((idx++))
    while (( idx < ${#tokens[@]} )); do
      positional+=("${tokens[idx]}")
      ((idx++))
    done
    break
  fi

  if [[ "$tok" == --repo ]]; then
    if (( idx + 1 < ${#tokens[@]} )); then
      remote="${tokens[idx + 1]}"
      remote_from_option="1"
      idx=$((idx + 2))
      continue
    fi
    ((idx++))
    continue
  fi

  if [[ "$tok" == --repo=* ]]; then
    remote="${tok#--repo=}"
    remote_from_option="1"
    ((idx++))
    continue
  fi

  case "$tok" in
    -o|--push-option|--receive-pack|--exec|--upload-pack|--server-option)
      idx=$((idx + 2))
      continue
      ;;
  esac

  if [[ "$tok" == -* ]]; then
    ((idx++))
    continue
  fi

  positional+=("$tok")
  ((idx++))
done

if [[ -z "$remote" ]]; then
  if (( ${#positional[@]} >= 1 )); then
    remote="${positional[0]}"
    positional=("${positional[@]:1}")
  fi
else
  if [[ "$remote_from_option" == "0" ]]; then
    if (( ${#positional[@]} >= 1 )) && [[ "${positional[0]}" == "$remote" ]]; then
      positional=("${positional[@]:1}")
    fi
  fi
fi

if (( ${#positional[@]} >= 1 )); then
  branch="${positional[0]}"
fi

remote="${remote:-default}"
branch="${branch:-default}"

context="Detected successful \`git push\` (remote: \`$remote\`, branch: \`$branch\`). Spawn the \`pipeline-deploy-monitor\` agent to monitor the CI/CD pipeline and verify deployments."

jq -n --arg context "$context" '{hookSpecificOutput:{additionalContext:$context}}'

