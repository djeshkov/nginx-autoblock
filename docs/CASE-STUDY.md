# Case study — 1-hour production observation

Real-world data from the first hour after the per-IP pass was enabled on a Laravel-fronted reference site behind Cloudflare. All site/customer identifiers anonymized; only public hostile-source data (scraper IPs, ASNs, user-agents) is shown.

## TL;DR

| Metric | Value |
|--------|-------|
| **Bot IPs banned in the first run** | 402 |
| **New IPs caught in the next 5 cron ticks** (50 min) | 4 |
| **`nginx 444` responses** (actual blocks fired) | 89 |
| **Subnet-pass candidates above threshold** during the hour | 0 |
| **False positives observed** | 0 |
| **Customer support tickets / regressions** | 0 |
| **Server load impact** | ~10-15 sec per cron run, no nginx reload errors |

## Background

The site was already running the **subnet pass** (`/24` aggregation) with default settings, but had recently noticed a wave of distributed Chinese-cloud bots hitting `/<some-public-url>/<UUID>` pages — each IP making 1-2 requests over a 24h window. None of these triggered the subnet pass because no single `/24` accumulated enough volume.

The per-IP pass was enabled with the default threshold (`per_ip_threshold=9`).

## T+0 — first scan after enabling per-IP

Output of `autoblock --show-per-ip` on the 30-minute window of access logs immediately after enabling:

```
Per-IP pass: threshold=9, candidates=402
SCORE  REQS IP                  ASN                                  reasons
-----  ---- ------------------  -----------------------------------  ------------------------------------------------
   13    20 202.46.62.24        BAIDU Beijing Netcom                 noassets,noref,4xx,upath,cloud,ua:oldchrome
   13    15 202.46.62.81        BAIDU Beijing Netcom                 noassets,noref,4xx,upath,cloud,ua:oldchrome
   13    15 202.46.62.117       BAIDU Beijing Netcom                 noassets,noref,4xx,upath,cloud,ua:oldchrome
   13    15 202.46.62.20        BAIDU Beijing Netcom                 noassets,noref,4xx,upath,cloud,ua:oldchrome
   ... (~30 more from 202.46.62.0/24 at score 11-13)
   10     6 104.210.56.225      MICROSOFT-CORP-MSN-AS-BLOCK          noassets,noref,cloud,ua:oldchrome  (HubSeedsBot/1.0)
   10     7 95.211.164.101      LEASEWEB-NL-AMS-01 Netherlands       noassets,noref,upath,cloud         (VacancyValidator/1.0)
   10     8 182.242.168.225     CHINANET-BACKBONE                    noref,4xx,upath,cloud,ua:oldchrome
   ... (~370 more)
```

All 402 entries written to `/etc/nginx/blocked-ips.conf`, nginx reloaded automatically by the script.

## T+10 to T+50 — five cron ticks

The script runs every 10 minutes. Each tick re-scans the 30-minute window and either adds new candidates or refreshes the TTL of existing ones.

```
T+10:  +1 new block   |  402 existing IPs extended  |  511 subnets scanned
T+20:  +1 new block   |  403 existing IPs extended  |  498 subnets scanned
T+30:  +2 new blocks  |  404 existing IPs extended  |  553 subnets scanned
T+40:  +0 new blocks  |  406 existing IPs extended  |  563 subnets scanned
T+50:  +0 new blocks  |  406 existing IPs extended  |  604 subnets scanned
```

**Four new scrapers caught autonomously:**

```
T+10  2a09:bac5:50ee:3032::4cd:b   IPv6 cloud, score 9   noassets,extref,upath,cloud
T+20  45.148.10.21                 score 10              26 req, 4xx probing, old Chrome
T+30  139.199.162.133              score 10              cloud + old Chrome
T+30  100.24.210.54                AMAZON-AES, score 10  cloud + old Chrome
```

Each was first observed in the access log between scan ticks, scored above the threshold once it had enough requests to evaluate, and added to the block list at the next tick.

## Actual nginx blocks fired (`HTTP 444`)

Counting `444` responses in the access log over the first hour:

```
89 total 444 responses to bot retry attempts

Top hit IPs:
  5  45.148.10.21       (the new scraper caught at T+20 — its remaining attempts blocked)
  3  100.24.210.54
  2  54.193.6.55
  2  202.46.62.88
  2  202.46.62.79
  ... (~15 more Baidu Netcom IPs at 2 hits each)
```

Pattern: most scrapers came back 2-5 times within the hour, each time getting `444` (silent close, zero response body). The Baidu Netcom subnet is "polite" enough to keep some interval between attempts; the more aggressive ones (AWS-hosted, generic VPS) retry harder.

## Score signal distribution across the 402 first-pass IPs

| Signals present | Count | Typical source |
|-----------------|-------|----------------|
| cloud + ua:oldchrome + noref + noassets + upath + 4xx (score 13) | ~120 | Coordinated probing botnets (Baidu Netcom, parts of CHINANET) |
| cloud + ua:oldchrome + noref + noassets (score 10) | ~180 | One-shot cloud scrapers (AWS, Azure, GCP, OVH, Hetzner) |
| cloud + ua:oldchrome + upath (score 8-9) | ~70 | Low-volume scanning from cloud |
| cloud + ua:headless (score 6, didn't pass) | not blocked | Edge cases — held under threshold for safety |

The signals composed naturally: every IP had a different combination, and the score reflected how confident the fingerprint was.

## What the subnet pass would NOT have caught

The Baidu Netcom subnet `202.46.62.0/24` — the largest single concentration in the data — **did** previously trigger the subnet pass after the operator manually added a one-off `/24` block (because the original cron was misconfigured and scanning the wrong access log). After fixing that, the subnet pass would have caught it eventually — but only as one block of the entire `/24`.

The per-IP pass produced:
- **30+ separate `/32` bans** with individual evidence trails (score, signals, request count, ASN)
- The remaining 370 unrelated scrapers from **other cloud sources** — none of which would have triggered the subnet pass because each one came from a different `/24` with only 1-5 requests.

That's the architectural difference between concentration-based and behavior-based detection.

## Resource cost

- **Cron run time**: 8-15 seconds per tick (down from ~30 sec when the script was hitting the larger main access log without any tuning; jumped up because parsing a 12 MB log on each scan and running ip-api batches takes time).
- **nginx reload**: handled inside the script after each successful write; no errors, no observable downtime.
- **`blocked-ips.conf` file size**: ~50 KB after first hour (~400 entries × ~120 bytes per line including comment).
- **Cleanup cron**: at 03:30 UTC daily, removes expired entries (default 7-day TTL). Tested working.

## What this doesn't show

- **Long-term FP rate**. The 0% false-positive number is after manual review of the top 35 candidates against ip-api.com. A small fraction of edge-case real users (VPN exit + old browser + ad blocker + direct link, no referer) could theoretically score 8-10. Recommend monitoring `444` responses by country/device in Cloudflare analytics for the first week.
- **Comparison against other tools**. We didn't run Cloudflare Bot Fight Mode or fail2ban in parallel for A/B benchmarking. Just internal validation against ip-api.com reputation flags.
- **Effect on actual server load**. The site was already healthy before per-IP enable; nothing to "rescue" — this is preventive defense, not incident response.

## Recommended defaults from this data

For a similar setup (Laravel/PHP CMS behind Cloudflare, mostly residential ISP traffic + cloud-hosted scrapers):

```ini
per_ip_enabled=true
per_ip_threshold=9                   # default; ~1.5% of IPs flagged
per_ip_ttl_days=7
per_ip_chrome_min_version=142        # ~6mo behind current Chrome stable
internal_ref_hosts=your-domain.com   # critical for noref/extref signals
self_ips=YOUR.SERVER.IP              # exclude your own IP for health-checks
```

Threshold 9 was tested against this traffic profile. Sites with heavy power-user / VPN traffic might raise to 10 (cuts to ~80 IPs in first run, very conservative). Sites that want maximum coverage and have CF + Turnstile or similar as fallback might drop to 8 (extends to ~600 IPs but admits some borderline cases).
