# nginx-autoblock

Behavioral autoblocker for Nginx. Detects bot crawlers by **composite scoring** across multiple signals (UA diversity, request patterns, IP reputation, behavioral fingerprint) and adds offending **subnets and individual IPs** to nginx's block-list with TTL.

Designed for two threat classes that per-IP rate-limiting (`limit_req_zone $binary_remote_addr`) misses:
- **Concentrated botnets** — same /24 producing 100+ req/h, each IP individually below per-IP limits (v5 subnet pass).
- **Distributed scraping** — hundreds of cloud IPs from many ASNs, 1-2 requests each, mass-scraping public URLs harvested from sitemaps or tournament/product pages (v6 per-IP pass, opt-in).

```
                ┌─────────────────────────────────────────────────┐
   nginx logs ──┤  autoblock (every 10 min via cron)              │
                │                                                 │
                │   v5 subnet pass (default):                     │
                │     group requests by /24 or /64                │
                │     score 0-11 against 5 behavioral signals     │
                │     enrich via ip-api.com (free)                │
                │     block /24 if score ≥ 7                      │
                │                                                 │
                │   v6 per-IP pass (opt-in):                      │
                │     score each IP 0-14 (path-agnostic)          │
                │     catches distributed scrapers (1 req/IP)     │
                │     block /32 if score ≥ 9                      │
                └────────────────┬────────────────────────────────┘
                                 │
                                 ▼
                 /etc/nginx/blocked-subnets.conf   (v5)
                 /etc/nginx/blocked-ips.conf       (v6)
                                 │
                                 ▼
                       nginx returns 444 to bot
```

## Why this exists

Per-IP rate limits (`limit_req_zone $binary_remote_addr`) don't catch distributed crawls: a bot operator with 25 IPs inside one /24 emits 1.5 req/min per IP — far below the per-IP threshold, but ~38 req/min from the subnet in aggregate, with one User-Agent and identical request patterns.

Existing tools occupy adjacent niches:

| Tool | Approach | Limitation |
|------|----------|------------|
| [nginx-ultimate-bad-bot-blocker](https://github.com/mitchellkrogza/nginx-ultimate-bad-bot-blocker) | Static UA/referrer/IP block-lists + fail2ban | Not adaptive — won't catch new bots without list updates |
| [fail2ban-subnets](https://github.com/XaF/fail2ban-subnets) / [recidive-subnet](https://github.com/ruppel/fail2ban-recidive-subnet) | Escalate per-IP bans to /24 when enough hits | Counter-only — no behavioral analysis; depends on per-IP bans firing first |
| [Cloudflare Bot Management](https://developers.cloudflare.com/bots/concepts/bot-score/) | ML scoring 1-99 | Paid, vendor lock-in |

`nginx-autoblock` sits in the middle: **adaptive behavioral scoring with free reputation data**, no fail2ban dependency.

## How it works

For each `/24` (IPv4) or `/64` (IPv6) seen in the last 30 minutes, score against 5 signals (max 11 points). Block if score ≥ 7.

| Signal | Points | What it detects |
|--------|--------|-----------------|
| `≤ 2` unique User-Agents | **+2** | Homogeneous bot farm |
| Target paths ≥ 50% / ≥ 80% of requests | **+1 / +1** additional | Focused API or search hammering |
| Top-3 URLs ≥ 50% / ≥ 80% of requests | **+1 / +1** additional | Low URL diversity (bot vs human browsing) |
| Referer rate < 30% / < 10% | **+1 / +1** additional | Real browsers send referer on link clicks |
| ip-api.com `hosting=true` OR `proxy=true` | **+3** | Datacenter / proxy origin |
| ip-api.com `mobile=true` | **-1** | Mobile carrier — likely real users |

**Gates:**
- Subnet must have ≥ `min_requests` (default 200) in the window — below this, not evaluated.
- Whitelist hits (search engines, AI bots, your own IPs) are skipped before scoring.

**Static-asset ratio is NOT a signal.** Behind a CDN, static files (CSS/JS/images) are served from the edge cache — only ~5% of static traffic reaches origin nginx, so this ratio is similar between humans and bots at origin and provides no discrimination.

**ip-api.com batch enrichment** queries up to 100 IPs in one HTTP request, free, no signup. Results cached for 7 days per subnet. Falls back to offline ASN keyword matching (via `iptoasn.com` database) if the API is unreachable.

## v6 — Per-IP scoring (distributed scraping)

The subnet pass has an architectural limit: when bot operators spread requests across **many cloud IPs, 1-2 requests each**, no /24 accumulates enough volume to trip. v6 adds a second, **opt-in** pass that scores each IP on its own behavioral fingerprint.

```ini
# /etc/nginx-autoblock/config.env
per_ip_enabled=true
per_ip_threshold=9
internal_ref_hosts=example.com,www.example.com   # for noref/extref signal
self_ips=203.0.113.1                              # your origin IP(s)
```

Then either let the regular cron run pick it up (subnet pass runs first, then per-IP pass), or invoke it directly:

```bash
sudo autoblock --show-per-ip   # diagnostic — top 50 candidates, read-only
sudo autoblock --per-ip --dry-run   # what would be blocked
sudo autoblock --per-ip   # actually block
```

Output goes to `/etc/nginx/blocked-ips.conf` — separate from the subnet file. Both are included in the same `geo $blocked_subnet` block (see `nginx/blacklist.conf`).

### Signal set (path-agnostic)

| Signal | Trigger | Points | Min req |
|--------|---------|--------|---------|
| **noassets** | Asset-loading ratio < 5% | +3 | N ≥ 3 |
| **noref** | No-referer ratio > 80% | +2 | N ≥ 2 |
| **extref** | External-referer ratio > 50% | +1 | has-ref ≥ 3 |
| **4xx** | 4xx-response ratio > 30% | +1 | N ≥ 5 |
| **upath** | Unique-paths ratio ≥ 95% | +2 | N ≥ 5 |
| **cloud** | ASN description matches hosting/cloud keywords | +3 | — |
| **ua:oldchrome** | Chrome major version < threshold (default 142) | +2 | — |
| **ua:headless** | UA matches HeadlessChrome / Puppeteer / Selenium / Scrapy | +3 | — |
| **ua:short** | UA length < 20 | +2 | — |

**Maximum score: 14.** Default threshold: 9. Whitelisted UAs (Privacy Preserving Prefetch Proxy, imgix, monitoring services, claimed search-engine bots) skip scoring entirely.

The first 3 path-volume signals (noassets/noref/upath) require multiple requests to fire. The cloud/UA signals work at N=1 — they're what catches single-hit distributed scrapers.

### When to enable

Enable v6 when you observe **either**:
- Your access log shows many distinct cloud IPs each hitting one specific endpoint (e.g., `/reservation/<UUID>`, `/product/<ID>`, `/profile/<USER>`) once each.
- Session-recording or analytics tools show short bot-like sessions (< 5s, 0 clicks) from many countries / IPs — but `--show-scores` (v5 subnet pass) finds nothing because no /24 is hot enough.

Backtest details and signal calibration: [docs/SCORING.md § v6](docs/SCORING.md#v6--per-ip-pass-opt-in).

## Quick install

```bash
git clone https://github.com/djeshkov/nginx-autoblock.git
cd nginx-autoblock
sudo ./scripts/install.sh
```

The installer:
- Copies `autoblock` to `/usr/local/bin/`
- Creates `/etc/nginx-autoblock/config.env` from the template
- Creates `/etc/nginx/blocked-subnets.conf` (empty) and `/etc/nginx/autoblock-whitelist.conf` (template)
- Installs `/etc/nginx/conf.d/blacklist.conf` (the `geo $blocked_subnet` map)
- Fetches the ASN database (~9 MB) to `/var/lib/nginx-autoblock/`
- Installs cron schedule

**Manual nginx step:** add this inside your `server { }` block:

```nginx
if ($blocked_subnet) {
    return 444;
}
```

(See `nginx/server-snippet.conf`. `444` closes the connection without sending a response — cheapest possible block.)

Then:

```bash
sudo nginx -t && sudo nginx -s reload
sudo /usr/local/bin/autoblock --dry-run     # see what would block
sudo /usr/local/bin/autoblock --show-scores # diagnostic — top 30 with score breakdown
```

## Configuration

Edit `/etc/nginx-autoblock/config.env`. Most important settings:

```ini
access_log=/var/log/nginx/access.log

# Tune target_paths to your application — bots hammer specific endpoints.
# For a typical web app: APIs and search are common targets.
target_paths=/api/,/search

# Exclude paths that look like targets but are legitimate (admin panels, etc.)
excluded_paths=/api/admin/

# Volume gate — raise if you have a lot of organic traffic from active power users.
min_requests=200

# Score threshold for blocking (max 11).
# 7 = balanced (default). 8-9 = more conservative (fewer blocks, fewer false positives).
score_threshold=7

ttl_days=7
```

Full reference: see `config.example.env`.

## Whitelist

`/etc/nginx/autoblock-whitelist.conf` — CIDRs that are **never** auto-blocked.

The default template includes:
- Major search engines (Google, Bing, Yandex, Baidu, DuckDuckGo)
- AI bots that benefit your AI search visibility (OpenAI ChatGPT-User/GPTBot/SearchBot, Anthropic ClaudeBot)
- Social crawlers (Facebook, Twitter)
- Cloudflare ranges (defense-in-depth: if your real_ip module ever breaks, origin sees CF IPs — don't auto-block all your users)

**Always add your own IPs:** office, monitoring services (UptimeRobot, Pingdom), partner API clients, VPN exits used by your team.

To keep AI bot ranges current, run periodically:

```bash
sudo ./scripts/refresh-ai-whitelist.sh
```

## Operating

```bash
# Default mode (run by cron)
sudo autoblock

# Dry run — log what would be blocked, don't write
sudo autoblock --dry-run

# Diagnostic — show top 30 scored subnets with full breakdown
sudo autoblock --show-scores

# Remove expired bans (runs nightly via cron)
sudo autoblock --cleanup

# Alternative config
sudo autoblock --config /path/to/config.env
```

**Log:** `/var/log/nginx-autoblock.log` — one line per decision (`BLOCK`, `EXTEND`, `UNBLOCK`).

**Unblock a false positive:**

```bash
sudo vim /etc/nginx/blocked-subnets.conf  # delete the offending line
sudo nginx -t && sudo nginx -s reload
```

Manual entries (lines without an `# auto added=...` comment) are **never** touched by the cleanup job, so you can add permanent bans by hand.

## Known limitations & risks

- **VPN power users.** A single human using NordVPN/ExpressVPN can match `hosting/proxy + 1 UA`, scoring near the threshold. Realistically rare for most sites, but if your audience is privacy-conscious tech users, monitor `--show-scores` for VPN exits in the score-5 to score-6 range and consider raising `score_threshold` to 8.

- **Mobile app traffic.** A native mobile app sends ONE User-Agent and hits APIs almost exclusively — that's exactly the bot signature. If you have a mobile app, whitelist its backend IPs or the carrier ranges it uses.

- **Partner integrations / cron clients hitting your API.** Same pattern as a bot — one UA, all API. Always whitelist these by IP.

- **Microsoft Azure as a whole** is NOT flagged as hosting by default. This is intentional — many legitimate AI bots (ChatGPT-User, GPTBot) live on Azure, and we'd rather let them through than block ChatGPT. The trade-off: less-known bots from generic Azure subnets are caught only if `ip-api` flags them specifically.

- **Single Cloudflare-fronted setup tested.** The static-ratio caveat assumes a CDN cache in front. For direct-to-origin nginx, you might benefit from re-adding a static-asset-ratio signal — or enable the v6 per-IP pass which uses asset-ratio at the individual-IP level.

- **Per-IP pass (v6) trusts claimed-bot UAs without PTR verification** in v6.0. If a scraper spoofs `Googlebot` in its User-Agent, the v6 pass currently skips it. Full PTR + forward-DNS verification is implementation-ready and tracked for v6.1. Until then, the v5 subnet pass still catches concentrated spoofers, and the UA whitelist for AI bots is separately verified via published IP ranges (`scripts/refresh-ai-whitelist.sh`).

## Data sources

- **ip2asn-combined.tsv.gz** — from [iptoasn.com](https://iptoasn.com/), free, no signup, daily updates. ~700k entries (522k IPv4 + 176k IPv6 ranges).
- **ip-api.com** — free tier, 45 batch requests/min, no signup. Used for `proxy`/`hosting`/`mobile` flags on candidate subnets.
- **OpenAI bot ranges** — official JSON at `openai.com/chatgpt-user.json` (and similar for GPTBot, OAI-SearchBot).
- **Cloudflare ranges** — official at `cloudflare.com/ips-v4` and `ips-v6`.

All data fetched at runtime / install time. No vendor secrets, no API keys required for default operation.

## Contributing

Contributions welcome — bug reports, feature ideas, code, docs improvements. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, code style, and what kinds of contributions are most useful.

- **Bugs**: open an [issue](https://github.com/djeshkov/nginx-autoblock/issues/new?template=bug_report.yml).
- **Feature ideas / new signals**: open an [issue](https://github.com/djeshkov/nginx-autoblock/issues/new?template=feature_request.yml).
- **Questions / tuning advice / sharing configs**: open a [Discussion](https://github.com/djeshkov/nginx-autoblock/discussions).
- **Security vulnerabilities**: see [SECURITY.md](SECURITY.md) — please do **not** file public issues.

## License

MIT. See [LICENSE](LICENSE).

## Acknowledgements

Inspired by frustration with distributed bot crawls slipping past `limit_req_zone $binary_remote_addr` and observation that headless-Chrome bots show up in Google Analytics as "real users" while staying nearly invisible in server-log top-IP statistics.
