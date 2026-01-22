#!/bin/bash
# Test all available models end-to-end
# Usage: ./scripts/test-all-models.sh [--quick] [--local] [--premium] [--all]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
EXECUTOR="$REPO_ROOT/skills/prompt-executor/scripts/executor.py"
LOG_DIR="$HOME/.claude/cli-logs"
RESULTS_DIR="/tmp/model-tests-$(date +%Y%m%d-%H%M%S)"

mkdir -p "$RESULTS_DIR"

# Test prompt content
TEST_PROMPT='Create a file /tmp/model-test-MODEL_PLACEHOLDER.txt containing exactly:
Model: MODEL_PLACEHOLDER
Timestamp: (current time)
Description: (one sentence about this model)

Then cat the file to show its contents.

Keep your response brief - just create the file and show it.'

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Model groups
QUICK_MODELS="codex gemini opencode"
LOCAL_MODELS="local qwen devstral"
PREMIUM_MODELS="codex-high codex-xhigh gemini-high gemini-xhigh gpt52 gpt52-high"

run_test() {
    local model="$1"
    local prompt_file="$RESULTS_DIR/prompt-$model.md"
    local log_file="$RESULTS_DIR/log-$model.txt"
    local result_file="/tmp/model-test-$model.txt"

    echo -e "${YELLOW}Testing: $model${NC}"

    # Create model-specific prompt
    echo "${TEST_PROMPT//MODEL_PLACEHOLDER/$model}" > "$prompt_file"

    # Get routing info
    local routing
    routing=$(python3 "$REPO_ROOT/skills/cli-detector/scripts/router.py" --resolve "$model" 2>/dev/null || echo '{"error": true}')
    local cli=$(echo "$routing" | jq -r '.cli // "unknown"')
    local model_id=$(echo "$routing" | jq -r '.model_id // "unknown"')

    echo "  CLI: $cli | Model: $model_id"

    # Run the test
    local start_time=$(date +%s)
    if python3 "$EXECUTOR" --model "$model" --prompt-file "$prompt_file" --run > "$log_file" 2>&1; then
        # Wait for completion (check for result file)
        local timeout=120
        local elapsed=0
        while [ ! -f "$result_file" ] && [ $elapsed -lt $timeout ]; do
            sleep 2
            elapsed=$((elapsed + 2))
        done

        local end_time=$(date +%s)
        local duration=$((end_time - start_time))

        if [ -f "$result_file" ]; then
            echo -e "  ${GREEN}✅ PASSED${NC} (${duration}s)"
            echo "  Result: $(head -1 "$result_file")"
            echo "$model,PASSED,$duration,$cli,$model_id" >> "$RESULTS_DIR/results.csv"
        else
            echo -e "  ${RED}❌ FAILED${NC} - No result file after ${timeout}s"
            echo "$model,FAILED,$timeout,$cli,$model_id" >> "$RESULTS_DIR/results.csv"
        fi
    else
        echo -e "  ${RED}❌ FAILED${NC} - Executor error"
        echo "$model,ERROR,0,$cli,$model_id" >> "$RESULTS_DIR/results.csv"
    fi
    echo ""
}

show_results() {
    echo ""
    echo "========================================="
    echo "TEST RESULTS"
    echo "========================================="
    echo ""

    if [ -f "$RESULTS_DIR/results.csv" ]; then
        echo "Model,Status,Duration(s),CLI,Model ID"
        cat "$RESULTS_DIR/results.csv"
        echo ""

        local passed=$(grep -c ",PASSED," "$RESULTS_DIR/results.csv" || echo 0)
        local failed=$(grep -c ",FAILED\|,ERROR," "$RESULTS_DIR/results.csv" || echo 0)
        local total=$((passed + failed))

        echo "Summary: $passed/$total passed"
    fi

    echo ""
    echo "Result files:"
    ls -la /tmp/model-test-*.txt 2>/dev/null || echo "No result files found"

    echo ""
    echo "Logs: $RESULTS_DIR/"
}

# Parse arguments
RUN_QUICK=false
RUN_LOCAL=false
RUN_PREMIUM=false

if [ $# -eq 0 ]; then
    echo "Usage: $0 [--quick] [--local] [--premium] [--all]"
    echo ""
    echo "Model groups:"
    echo "  --quick   : $QUICK_MODELS"
    echo "  --local   : $LOCAL_MODELS"
    echo "  --premium : $PREMIUM_MODELS"
    echo "  --all     : All models"
    exit 0
fi

for arg in "$@"; do
    case $arg in
        --quick) RUN_QUICK=true ;;
        --local) RUN_LOCAL=true ;;
        --premium) RUN_PREMIUM=true ;;
        --all) RUN_QUICK=true; RUN_LOCAL=true; RUN_PREMIUM=true ;;
    esac
done

# Initialize results
echo "model,status,duration,cli,model_id" > "$RESULTS_DIR/results.csv"

# Run tests
if $RUN_QUICK; then
    echo "=== Quick Models ==="
    for model in $QUICK_MODELS; do
        run_test "$model"
    done
fi

if $RUN_LOCAL; then
    echo "=== Local Models ==="
    for model in $LOCAL_MODELS; do
        run_test "$model"
    done
fi

if $RUN_PREMIUM; then
    echo "=== Premium Models ==="
    for model in $PREMIUM_MODELS; do
        run_test "$model"
    done
fi

show_results
