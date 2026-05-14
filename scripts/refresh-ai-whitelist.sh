#!/usr/bin/env bash
# Fetch current AI bot IP ranges from OpenAI and append to whitelist.
# Run periodically (monthly) — OpenAI updates these lists occasionally.
#
# IMPORTANT: this appends, doesn't replace. Old entries stay unless you edit
# the whitelist manually. The autoblocker uses ip_network.overlaps() so duplicate
# entries are harmless.

set -euo pipefail

WHITELIST="${1:-/etc/nginx/autoblock-whitelist.conf}"
TIMESTAMP=$(date +%Y-%m-%d)

if [[ ! -w "$WHITELIST" ]]; then
    echo "Cannot write to $WHITELIST (run as root?)" >&2
    exit 1
fi

fetch_openai() {
    local name="$1" url="$2"
    echo "" >> "$WHITELIST"
    echo "# === OpenAI $name (auto-fetched $TIMESTAMP from $url) ===" >> "$WHITELIST"
    curl -sf "$url" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for p in d.get('prefixes', []):
    if 'ipv4Prefix' in p:
        print(p['ipv4Prefix'])
    if 'ipv6Prefix' in p:
        print(p['ipv6Prefix'])
" >> "$WHITELIST"
}

echo "==> Backing up current whitelist"
cp "$WHITELIST" "${WHITELIST}.bak-${TIMESTAMP}"

echo "==> Fetching OpenAI ranges"
fetch_openai "ChatGPT-User"   "https://openai.com/chatgpt-user.json"
fetch_openai "GPTBot"         "https://openai.com/gptbot.json"
fetch_openai "OAI-SearchBot"  "https://openai.com/searchbot.json"

echo "==> Testing nginx config"
if nginx -t 2>&1; then
    nginx -s reload
    echo "✓ Whitelist refreshed, nginx reloaded"
else
    echo "✗ nginx -t failed — rolling back"
    mv "${WHITELIST}.bak-${TIMESTAMP}" "$WHITELIST"
    exit 1
fi

echo "Backup kept at: ${WHITELIST}.bak-${TIMESTAMP}"
