# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added — v6: Per-IP behavioral scoring (path-agnostic)

A second, **optional** pass that scores individual IPs by their behavioral
fingerprint regardless of how many requests they made. Disabled by default;
enable in config with `per_ip_enabled=true`.

The motivation is **distributed scraping** — bot operators that spread requests
across hundreds of cloud IPs, each making 1-2 requests. The v5 subnet pass
cannot detect this by design (no /24 accumulates enough traffic to trip).
Per-IP scoring uses signals that work even at N=1: cloud ASN, no-referer,
no-asset-loads, headless UA, old Chrome version.

- New CLI flags:
  - `--per-ip` — run only the v6 pass
  - `--show-per-ip` — diagnostic top-50 candidates (read-only)
- New output file: `blocked-ips.conf` (separate from `blocked-subnets.conf`)
- New config keys: `per_ip_enabled`, `per_ip_threshold`, `per_ip_ttl_days`,
  `blocked_ips_conf`, `internal_ref_hosts`, `self_ips`, `per_ip_chrome_min_version`
- `--cleanup` now also expires per-IP bans
- `nginx/blacklist.conf` now includes both files in the same geo block

Validated on a Laravel site (116k log lines, 25k unique IPs over 48h):
- threshold=9 → 399 IPs flagged
- 0% false-positive rate (top 35 sampled against ip-api.com — 95% agreement,
  remaining 5% were residential-IP scrapers ip-api could not classify)
- Top scrapers identified: Baidu Netcom, Tencent, Huawei Cloud, Alibaba,
  DigitalOcean / OVH / Hetzner / AWS VMs running scrapers — all with score
  12-13 out of ~14 possible.

The pass uses verified-bot whitelist with PTR-suffix mapping for Googlebot,
bingbot, YandexBot, AhrefsBot, etc. Currently the script trusts the UA
substring; full PTR + forward-DNS verification is implementation-ready but
not wired by default (see backtest scripts in repo discussions).

### Changed

- `nginx/blacklist.conf` now sources two block files instead of one. Both are
  optional — nginx degrades gracefully when either is absent.

### Notes for v5 users

This release is **fully backward compatible**. If you do not set
`per_ip_enabled=true`, behavior is identical to v5.1. The new `blocked-ips.conf`
include in `nginx/blacklist.conf` is safe even when the file does not exist
(nginx logs a warning at reload but continues).

To start using v6, see [README.md § Per-IP scoring](README.md#v6--per-ip-scoring-distributed-scraping).

---

## [v5.1] - 2026-05-15

### Fixed

- `blocked-subnets.conf` accumulated duplicate `# Auto-added` header lines on
  every run (one per cron tick × 24h = 144 duplicates/day in practice).
  Root cause: `read_blocked()` parsed managed-header comments as manual content,
  `write_blocked()` re-added them each rewrite. Fix introduces sentinel markers
  `# === AUTOBLOCK AUTO SECTION BEGIN ===` / `END` wrapping the auto section;
  everything between markers is owned by the script, everything outside is
  manual. Legacy header strings are stripped on first rewrite.

## [v5.0] - 2026-05-14

### Added

- ip-api.com batch reputation enrichment with persistent per-subnet cache.
- AI-bot whitelist generator (OpenAI ChatGPT-User, GPTBot, OAI-SearchBot,
  Anthropic ClaudeBot) via `scripts/refresh-ai-whitelist.sh`.
- Offline ASN keyword matching as fallback when ip-api is unreachable.

### Changed

- Project renamed for open-source release (was `ytg-autoblock`).
- MIT license; full README, CONTRIBUTING, SECURITY, issue/PR templates added.

## [v1.0] - 2026-05-11

Initial release: subnet-aggregation behavioral scoring (UA diversity, target
paths, top-3 concentration, referer rate, ASN keyword). Designed for
CDN-fronted sites where per-IP rate limiting misses distributed crawls inside
a single /24.
