# Scoring details

`nginx-autoblock` ships **two independent scoring passes** with different
target threat classes:

| Pass | Aggregation | Threat class | Default state |
|------|-------------|--------------|---------------|
| **Subnet pass** | `/24` (IPv4) / `/64` (IPv6) | Concentrated botnets — same /24 produces 100+ req/h | Enabled |
| **Per-IP pass** | `/32` per individual IP | Distributed scraping — many IPs, 1-2 req each | Opt-in (`per_ip_enabled=true`, added v1.1) |

The passes run independently and write to **separate** files
(`blocked-subnets.conf` and `blocked-ips.conf`). Use whichever combination fits
your threat profile.

---

# Subnet pass (default)

Each subnet (`/24` for IPv4, `/64` for IPv6) is scored across these signals. Total ranges 0-11; default block threshold is 7.

## Signal table

| # | Signal | Threshold | Points | Why it discriminates |
|---|--------|-----------|--------|----------------------|
| 1 | UA diversity | ≤ 2 unique UAs | +2 | Bot farms typically use one or two fixed UA strings. A real /24 (corp NAT, mobile carrier) shows 5-50+ UA variants. |
| 2a | Target path ratio | ≥ 50% | +1 | Bots focus on specific endpoints (API, search). Humans browse broadly. |
| 2b | Target path ratio | ≥ 80% | +1 additional | Strong concentration on target paths. |
| 3a | Top-3 path concentration | ≥ 50% | +1 | Bots loop over 2-3 endpoints; humans walk many pages. |
| 3b | Top-3 path concentration | ≥ 80% | +1 additional | Very low URL diversity. |
| 4a | Referer rate | < 30% | +1 | Browsers send a `Referer:` header when navigating from another page. Bots often have empty or fixed referers. |
| 4b | Referer rate | < 10% | +1 additional | Almost no referers = scripted access. |
| 5a | ip-api hosting OR proxy | true | +3 | Real users typically come from ISP, not datacenter. Confirmed proxy = bot operator infrastructure. |
| 5b | ip-api mobile | true | **−1** | Mobile carriers serve real users. Negate if other signals trip due to homogeneous mobile traffic. |

**Maximum possible score: 11.**

When `ip-api` is unavailable (network error, rate limit, or disabled in config), signal 5 falls back to **ASN keyword matching** against the description from `iptoasn.com`. Matches `hosting`, `cloud`, `aws`, `digitalocean`, `baidu`, etc.

## Calibration examples

### Bot: `202.46.62.0/24` (Baidu Netcom, China)

```
Volume: 18,030 requests over 48 hours
UAs:    1 ("Chrome/133.0.6943.141")
Target: 70%  (mostly /api/catalog/items, /api/catalog/filters)
Top-3:  56%
Referer: 63%
ip-api: hosting=true

Score breakdown:
  ua1            → +2
  tgt70%         → +1   (≥50%, not ≥80%)
  top3_56%       → +1   (≥50%, not ≥80%)
  ref63%         → 0    (not < 30%)
  ipapi:host     → +3
  ─────────────────────
  TOTAL          → 7    → BLOCK
```

### Bot: `216.73.217.0/24` (Amazon AWS scraper)

```
Volume: 122,715 requests over 14 days
UAs:    1
Target: 33%
Top-3:  4% (varies across many catalog pages)
Referer: 2%
ip-api: hosting=true

Score:
  ua1            → +2
  tgt33%         → 0    (below 50%)
  top3_4%        → 0    (low concentration — bot scans many URLs)
  ref2%          → +1, ref+ → +1 additional (very low)
  ipapi:host     → +3
  ─────────────────────
  TOTAL          → 7    → BLOCK
```

Notice: this bot does NOT match the API or path-concentration signals (it spiders broadly). It still scores 7 thanks to UA + low referer + hosting ASN.

### Real user: corporate NAT

```
UAs:    8 different browsers
Target: 2%   (mostly HTML pages)
Top-3:  ~30%
Referer: 50%
ip-api: hosting=false, proxy=false

Score:
  ua8            → 0    (more than 2 UAs)
  tgt2%          → 0
  top3_30%       → 0
  ref50%         → 0
  ipapi          → 0
  ─────────────────────
  TOTAL          → 0    → not blocked
```

### Edge case: ChatGPT-User on Microsoft Azure

```
UAs:    1 ("ChatGPT-User/1.0")
Target: 0% (visits HTML content, not API)
Top-3:  ~10%
Referer: 0%
ip-api: hosting=true

Score (if NOT whitelisted):
  ua1            → +2
  ref0%, ref+    → +2
  ipapi:host     → +3
  ─────────────────────
  TOTAL          → 7    → would block

→ Whitelist saves it. Default whitelist includes OpenAI ChatGPT-User ranges.
```

## Tuning

- **Too many false positives:** raise `score_threshold` to 8 or 9. Or raise `min_requests` to require larger volume before evaluation.
- **Missing obvious bots:** lower `score_threshold` to 6, but watch `--show-scores` carefully for collateral damage on real users.
- **Bots get blocked but you want to allow them** (e.g., SEO crawlers you actually use): add their CIDR or ASN range to the whitelist.
- **One signal is too aggressive on your traffic:** customize `target_paths` (most-tuned setting in practice — depends entirely on your application).

## Why static-asset ratio is NOT a signal (subnet pass)

Earlier subnet-pass versions used "static-ratio < 10% → +3" (real browsers download CSS/JS/images, bots don't). This is **broken behind a CDN**.

When Cloudflare (or any CDN with static caching) sits in front of nginx, static files are served from edge cache — the origin nginx sees only ~5% static traffic for everyone. Real users and bots both look like 0-5% static at origin. The signal fires on both, providing no discrimination.

The per-IP pass re-introduces this signal because it operates per-IP at a finer granularity — see below.

---

# Per-IP pass (opt-in)

The subnet pass has an architectural limit: it cannot detect **distributed
scraping** where 200 individual cloud IPs each make 1 request. No /24
accumulates enough traffic to trip, even though the aggregate effect is real.

The per-IP pass scores each IP independently using **behavioral signals that
work at N=1** (cloud ASN, headless UA, old Chrome) plus volume-dependent
signals that activate when more data is available (no-assets, no-referer,
unique-paths, 4xx-probing). Score range 0-14; default threshold 9.

## Signal table

| # | Signal | Trigger | Points | Min req | Why it discriminates |
|---|--------|---------|--------|---------|----------------------|
| 1 | **noassets** | Asset-loading ratio < 5% | +3 | N ≥ 3 | Real browsers fetch CSS/JS/images alongside HTML. Headless scrapers usually don't (origin only sees the HTML hit). |
| 2 | **noref** | No-referer ratio > 80% | +2 | N ≥ 2 | Real users mostly arrive via in-site links (referer present). Bots paste URLs from a list (no referer). |
| 3 | **extref** | External-referer ratio > 50% (of referers present) | +1 | has-ref ≥ 3 | Coming exclusively from external sites is a scraping pattern (target list from a 3rd-party source). |
| 4 | **4xx** | 4xx-response ratio > 30% | +1 | N ≥ 5 | Scanners hit non-existent paths probing for vulnerabilities. |
| 5 | **upath** | Unique-paths ratio ≥ 95% | +2 | N ≥ 5 | Classic crawler pattern — every request a different URL. |
| 6 | **cloud** | ASN description matches hosting/cloud keywords | +3 | — | Real users come from ISP, not datacenter. Reuses the same keyword list as the subnet-pass ASN fallback. |
| 7 | **ua:oldchrome** | Chrome major version < `per_ip_chrome_min_version` (default 142, ~6mo behind current) | +2 | — | Real users auto-update Chrome. Scrapers pin old versions (116, 120, 133 are common). |
| 7 | **ua:headless** | UA matches HeadlessChrome / Puppeteer / Playwright / Selenium / Scrapy / python-requests / Go-http-client / etc. | +3 | — | Direct self-identification. |
| 7 | **ua:short/empty** | UA length < 20 or UA is "-" | +2 | — | Real browsers have long UAs; bots sometimes set placeholder or omit. |

**Maximum possible score: 14.** Signals 7 (UA quality) take the max of the matched flags, not sum.

## Whitelisting

Three whitelist layers run before scoring:

1. **`self_ips`** — server's own IPs (configured via `self_ips=` config key, comma-separated). Health checks, self-curls, autoblock probes.
2. **UA whitelist** — built-in regex matches infrastructure UAs:
   - `Privacy Preserving Prefetch Proxy` (Google Privacy Sandbox prefetch — real users)
   - `imgix/`, `Pingdom`, `UptimeRobot`, `StatusCake`, `Site24x7` (monitoring / CDN image fetchers)
3. **Claimed-bot UA** — built-in regex matches well-known crawler UAs: Googlebot, bingbot, YandexBot, AhrefsBot, DuckDuckBot, Amzn-SearchBot, Amazonbot, Applebot, FacebookBot, meta-externalagent, Sogou web spider, YisouSpider, Bytespider, PetalBot, baiduspider, SemrushBot, MJ12bot, DataForSeoBot, MojeekBot, BLEXBot, GoogleOther, CCBot, ClaudeBot, GPTBot, ChatGPT-User, PerplexityBot, Twitterbot, TelegramBot, etc.

The script ships PTR-suffix mappings for the claimed-bot list (e.g., Googlebot → `.googlebot.com`, `.google.com`). Full PTR + forward-DNS verification is **implementation-ready but not wired as of v1.1** — claimed bots are held aside without verification. If a fake-bot UA spoofs Googlebot, this version will skip it. PTR verification can be added by uncommenting `verify_ptr` helpers in `autoblock` and gating `is_claimed_bot` on a passing PTR check; tracked for v1.2.

## Calibration examples

### Bot: Single-hit distributed scraper, DigitalOcean droplet

```
Volume: 1 request to /reservation/<UUID>
UA:     "Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36"
Referer: -
ASN:    DIGITALOCEAN-ASN

Score:
  cloud          → +3
  oldchrome (120 < 142) → +2
  ── below min_req gates for noassets/noref/upath ──
  ─────────────────────
  TOTAL          → 5    → not blocked at default threshold 9
```

Single-hit borderline. At threshold=9 we accept FN; at threshold=6 we'd catch it but with higher FP risk on legitimate one-shot visitors from cloud IPs.

### Bot: Multi-hit distributed scraper (3 reservations)

```
Volume: 3 requests, 3 different /reservation/<UUID>
UA:     "Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36"
Referer: all empty
ASN:    BAIDU Beijing Netcom

Score:
  noassets (0% / N=3 ≥ 3)    → +3
  noref    (100% / N=3 ≥ 2)  → +2
  cloud                       → +3
  ua:oldchrome (120 < 142)   → +2
  ─────────────────────────────
  TOTAL                       → 10  → BLOCK
```

The Baidu Netcom example: real production hit, 30+ IPs from this /24 scored 12-13 each in a 48h window — the per-IP pass catches every individual IP with full evidence trail.

### Real user: Mac Chrome 148, internal navigation

```
Volume:  30 requests
Assets:  18 (.js, .css, images)  → 60% asset ratio
Referer: 27 internal + 1 external + 2 empty
UA:      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/148.0.0.0 Safari/537.36"
ASN:     Vodafone Espana

Score:
  noassets → 0 (60% >> 5%)
  noref    → 0 (only 2/30 = 7%, far below 80%)
  cloud    → 0 (ISP, not hosting)
  ua       → 0 (current Chrome)
  ─────────────────────
  TOTAL    → 0  → not blocked
```

### Edge case: Googlebot Mobile

```
UA: "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X) ... Chrome/W.X.Y.Z ...
     (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
ASN: GOOGLE

Without claimed-bot whitelist, this would trip:
  noassets, noref, cloud, ua:oldchrome → score 10 → ban

With claimed-bot whitelist (regex matches "Googlebot"):
  → held aside, not scored, not blocked.
```

**Important — UA length:** the Googlebot Mobile UA is ~198 chars long. The script stores the first **250 characters** of each UA (`UA_MAX_LENGTH=250`). Earlier prototypes truncated at 140 and lost the `Googlebot/2.1` suffix, incorrectly scoring Googlebot as score-13 unclaimed.

## Tuning per-IP

- **Default threshold 9** is calibrated for a typical Laravel/PHP site with mixed real-user + bot traffic. Real-world backtest: 0% FP rate, ~1.5% of all IPs flagged as bot.
- **Lower threshold (7-8)** catches more single-hit cloud scrapers but admits more borderline cases (one-shot visitors from cloud IPs, VPN users with old browsers). Pair with a careful whitelist.
- **Higher threshold (10-11)** essentially only blocks IPs that hit multiple signals — very conservative.
- **`per_ip_chrome_min_version`** drifts over time. Current Chrome major version moves every ~6 weeks. Set to roughly "current minus 6 months" — too aggressive (e.g., current Chrome - 1) catches legitimate users who delayed an update; too lax misses scraper fingerprints.
- **`internal_ref_hosts`** is important for the noref / extref signals. If empty, all referers are treated as external — making the extref signal fire on legitimate users navigating from your own site.

## How the two passes interact

Both passes run on the same log and may flag the same incident from different angles. Examples:

- A botnet hitting 200 IPs in one /24 will be detected by **both** — subnet pass blocks the /24, per-IP pass blocks each IP. Net effect: nginx blocks via /24 (cheaper match). Per-IP entries become redundant — but harmless (they expire on TTL).
- A distributed scraper using 1 IP per /24 across 200 /24s — only **per-IP** sees it.
- A high-volume single API client with one UA from one /24 — only **subnet** sees it (the per-IP score on one IP may not reach threshold).

Both files are included in the same `geo $blocked_subnet` block. nginx checks both — either match returns the block decision.
