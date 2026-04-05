#!/bin/bash
# Token Refresh Script for Claude Code OAuth
#
# Usage:
#   1. Run `claude setup-token` in a terminal, copy the token
#   2. Run: CLAUDE_TOKEN="paste-token-here" bash src/token_refresh.sh
#      OR:  bash src/token_refresh.sh "paste-token-here"
#
# Repos to update (space-separated):
REPOS="Osasuwu/personal-AI-agent SergazyNarynov/redrobot Osasuwu/like_spotify_mobile_app"

set -euo pipefail

# Get token from arg or env
TOKEN="${1:-${CLAUDE_TOKEN:-}}"

if [ -z "$TOKEN" ]; then
    echo "[token-refresh] ERROR: No token provided."
    echo ""
    echo "Steps:"
    echo "  1. Open a terminal and run: claude setup-token"
    echo "  2. Copy the token shown"
    echo "  3. Run: CLAUDE_TOKEN=\"your-token\" bash src/token_refresh.sh"
    exit 1
fi

# Validate looks like a token (basic check)
if [[ ! "$TOKEN" == sk-ant-* ]] && [[ ! "$TOKEN" == oat_* ]]; then
    echo "[token-refresh] WARNING: Token doesn't look like a Claude token (expected sk-ant-* or oat_*). Proceeding anyway."
fi

echo "[token-refresh] Updating GitHub secrets..."

SUCCESS=0
FAIL=0

for REPO in $REPOS; do
    if echo "$TOKEN" | gh secret set CLAUDE_CODE_OAUTH_TOKEN --repo "$REPO" 2>/dev/null; then
        echo "[token-refresh] ✓ $REPO"
        SUCCESS=$((SUCCESS + 1))
    else
        echo "[token-refresh] ✗ $REPO — check gh auth and repo access"
        FAIL=$((FAIL + 1))
    fi
done

echo ""
echo "[token-refresh] Done: $SUCCESS updated, $FAIL failed."
