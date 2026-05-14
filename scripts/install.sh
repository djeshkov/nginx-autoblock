#!/usr/bin/env bash
# nginx-autoblock installer — run as root.
# Idempotent: safe to re-run.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Must run as root. Try: sudo $0" >&2
    exit 1
fi

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Installing autoblock script to /usr/local/bin/"
install -m 755 -o root -g root "$REPO_DIR/autoblock" /usr/local/bin/autoblock

echo "==> Creating /etc/nginx-autoblock/ config dir"
install -d -m 755 /etc/nginx-autoblock
if [[ ! -f /etc/nginx-autoblock/config.env ]]; then
    install -m 644 "$REPO_DIR/config.example.env" /etc/nginx-autoblock/config.env
    echo "    Created /etc/nginx-autoblock/config.env — review and edit before running"
else
    echo "    /etc/nginx-autoblock/config.env exists, skipping (compare with config.example.env)"
fi

echo "==> Creating data and cache directories"
install -d -m 755 /var/lib/nginx-autoblock
install -d -m 700 /var/cache/nginx-autoblock
touch /var/log/nginx-autoblock.log
chmod 644 /var/log/nginx-autoblock.log

echo "==> Installing nginx configs (review before nginx reload)"
install -m 644 "$REPO_DIR/nginx/blacklist.conf" /etc/nginx/conf.d/blacklist.conf
echo "    Installed /etc/nginx/conf.d/blacklist.conf"
echo "    You still need to include server-snippet.conf inside your server { } block:"
echo "        cat $REPO_DIR/nginx/server-snippet.conf"

if [[ ! -f /etc/nginx/blocked-subnets.conf ]]; then
    : > /etc/nginx/blocked-subnets.conf
    chmod 644 /etc/nginx/blocked-subnets.conf
    echo "    Created empty /etc/nginx/blocked-subnets.conf"
fi

if [[ ! -f /etc/nginx/autoblock-whitelist.conf ]]; then
    install -m 644 "$REPO_DIR/whitelist.example.conf" /etc/nginx/autoblock-whitelist.conf
    echo "    Created /etc/nginx/autoblock-whitelist.conf — REVIEW IT for your site"
else
    echo "    Whitelist exists, skipping"
fi

echo "==> Fetching ip2asn-combined.tsv.gz (~9MB from iptoasn.com)"
if [[ ! -f /var/lib/nginx-autoblock/ip2asn-combined.tsv.gz ]]; then
    curl -sLo /var/lib/nginx-autoblock/ip2asn-combined.tsv.gz \
        https://iptoasn.com/data/ip2asn-combined.tsv.gz
    echo "    Fetched ASN database ($(du -h /var/lib/nginx-autoblock/ip2asn-combined.tsv.gz | cut -f1))"
else
    echo "    ASN database exists, skipping (refresh via cron daily)"
fi

echo "==> Installing cron schedule"
install -m 644 "$REPO_DIR/cron.d/nginx-autoblock" /etc/cron.d/nginx-autoblock

echo ""
echo "✓ Installation complete."
echo ""
echo "Next steps:"
echo "  1. Edit /etc/nginx-autoblock/config.env — at minimum check access_log path and target_paths"
echo "  2. Edit /etc/nginx/autoblock-whitelist.conf — remove categories you don't need, add your IPs"
echo "  3. Add 'if (\$blocked_subnet) { return 444; }' inside your server { } block"
echo "     (see nginx/server-snippet.conf)"
echo "  4. Test: sudo nginx -t && sudo nginx -s reload"
echo "  5. Dry run: sudo /usr/local/bin/autoblock --dry-run"
echo "  6. Diagnostic view: sudo /usr/local/bin/autoblock --show-scores"
echo ""
echo "Cron runs detection every 10 minutes, refreshes ASN database daily 02:00 UTC,"
echo "cleans up expired bans daily 03:30 UTC."
