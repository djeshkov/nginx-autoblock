# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added — UA-cluster scoring pass (path-agnostic)

An optional third pass that groups requests by **User-Agent** and scores the
cluster — the set of distinct IPs sharing one UA.

The motivation: the subnet pass scores `/24`s and the per-IP pass scores
`/32`s; both score IPs in isolation. A distributed scraping botnet defeats
both by design — hundreds of IPs, ~1 request each, every IP individually
innocent. But such a botnet rotates a tiny pool of User-Agent strings across
its whole fleet. That sharing is an **aggregate property** invisible to any
per-IP scorer.

The UA-cluster pass detects it: for each UA seen from `>= ua_cluster_min_ips`
distinct IPs, it scores the cluster on hosting-ASN ratio, cluster-wide
behavioral homogeneity (no assets, no referers, 4xx probing) and UA quality.
The member IPs of a cluster scoring `>= ua_cluster_threshold` are blocked.

A genuinely popular real-browser UA is also shared by many IPs — but those IPs
are residential and behave normally, so the cluster scores low. ASN type and
behavior are the discriminators, not raw IP count.

- New CLI flags:
  - `--ua-cluster` — run only the UA-cluster pass
  - `--show-ua-cluster` — diagnostic list of flagged clusters (read-only)
- New output file: `blocked-ua-clusters.conf` (separate from the other passes)
- New config keys: `ua_cluster_enabled`, `blocked_ua_cluster_conf`,
  `ua_cluster_min_ips`, `ua_cluster_threshold`, `ua_cluster_ttl_days`
- `--cleanup` now also expires UA-cluster bans
- `nginx/blacklist.conf` now includes all three block files in the geo block
- Added `ROADMAP.md`

### Backward compatibility

Fully backward compatible. The pass is disabled unless `ua_cluster_enabled=true`
is set; with it unset, behaviour is identical to v1.1.0. The new
`blocked-ua-clusters.conf` include is safe even when the file does not exist
(nginx logs a warning at reload but continues).

## [v1.1.0] - 2026-05-15

### Added — Per-IP behavioral scoring (path-agnostic)

An optional second pass that scores individual IPs by their behavioral
fingerprint regardless of how many requests they made. Disabled by default;
enable in config with `per_ip_enabled=true`.

The motivation is **distributed scraping** — bot operators that spread
requests across hundreds of cloud IPs, each making 1-2 requests. The subnet
pass cannot detect this by design (no /24 accumulates enough traffic to trip).
Per-IP scoring uses signals that work even at N=1: cloud ASN, no-referer,
no-asset-loads, headless UA, old Chrome version.

- New CLI flags:
  - `--per-ip` — run only the per-IP pass
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

The pass ships PTR-suffix mappings for verified bots (Googlebot → `.googlebot.com`,
bingbot → `.search.msn.com`, etc.) but currently trusts UA substring without
DNS verification. Full PTR + forward-DNS verification is implementation-ready
and tracked for v1.2.

### Changed

- `nginx/blacklist.conf` now sources two block files instead of one. Both are
  optional — nginx degrades gracefully when either is absent.
- README, docs/SCORING.md restructured around two pass concepts:
  *subnet pass* (existing, default) and *per-IP pass* (new, opt-in).

### Backward compatibility

Fully backward compatible. If `per_ip_enabled=true` is not set, behaviour is
identical to v1.0.1. The new `blocked-ips.conf` include in `nginx/blacklist.conf`
is safe even when the file does not exist (nginx logs a warning at reload but
continues).

To start using the per-IP pass, see [README.md § Per-IP scoring](README.md#per-ip-scoring-distributed-scraping).

## [v1.0.1] - 2026-05-15

### Fixed

- `blocked-subnets.conf` accumulated duplicate `# Auto-added` header lines on
  every run (one per cron tick × 24h = 144 duplicates/day in practice).
  Root cause: `read_blocked()` parsed managed-header comments as manual content,
  `write_blocked()` re-added them each rewrite. Fix introduces sentinel markers
  `# === AUTOBLOCK AUTO SECTION BEGIN ===` / `END` wrapping the auto section;
  everything between markers is owned by the script, everything outside is
  manual. Legacy header strings are stripped on first rewrite.

## [v1.0.0] - 2026-05-11

Initial public release.

- Subnet-aggregation behavioral scoring (`/24` IPv4 / `/64` IPv6).
- Five signals: UA diversity, target-path concentration, top-3 URL
  concentration, referer rate, ip-api.com hosting/proxy/mobile reputation.
- ip-api.com batch enrichment with persistent per-subnet cache; offline ASN
  keyword matching as fallback when ip-api is unreachable.
- AI-bot whitelist generator (OpenAI ChatGPT-User, GPTBot, OAI-SearchBot,
  Anthropic ClaudeBot) via `scripts/refresh-ai-whitelist.sh`.
- Cron-driven; default threshold ≥7/11; default TTL 7 days.
- MIT license; README, CONTRIBUTING, SECURITY, issue/PR templates.

Designed for CDN-fronted sites where per-IP rate limiting misses distributed
crawls within a single /24.
