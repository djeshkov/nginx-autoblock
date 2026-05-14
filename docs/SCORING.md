# Scoring details

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

## Why static-asset ratio is NOT a signal

Earlier versions used "static-ratio < 10% → +3" (real browsers download CSS/JS/images, bots don't). This is **broken behind a CDN**.

When Cloudflare (or any CDN with static caching) sits in front of nginx, static files are served from edge cache — the origin nginx sees only ~5% static traffic for everyone. Real users and bots both look like 0-5% static at origin. The signal fires on both, providing no discrimination.

If you run nginx without a CDN, you might benefit from re-adding this signal. Open an issue or fork.
