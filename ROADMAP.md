# Roadmap

`nginx-autoblock` evolves along two axes: **detection intelligence** (what it
can catch) and **delivery latency** (how fast a block applies). The guiding
principle is **teach it to detect before making it fast** — a realtime pipeline
that delivers a wrong decision quickly is worse than a slow correct one.

## Released

### v1.0 — Subnet pass
Composite scoring per `/24` / `/64`. Catches concentrated botnets where one
subnet produces 100+ req/h. Cron-driven (batch).

### v1.1 — Per-IP pass
Path-agnostic per-`/32` behavioral scoring. Catches distributed scrapers that
make 1-2 requests per IP, where no subnet accumulates enough traffic to trip.
Opt-in (`per_ip_enabled`).

## Planned

### v1.2 — UA-cluster pass
Adds a third aggregation axis: **group by User-Agent, count distinct IPs**.

Motivation: the subnet and per-IP passes both score IPs (or subnets) in
isolation. A distributed scraping botnet defeats both by design — hundreds of
IPs, one request each, every IP individually "innocent". But the botnet shares
a tiny pool of User-Agent strings across its whole IP fleet. That sharing is an
**aggregate property** invisible to any per-IP scorer.

The UA-cluster pass groups requests by UA, and for each UA seen from an
abnormal number of distinct IPs, scores the *cluster* on hosting-ASN ratio,
cluster-wide behavioral homogeneity (no assets, no referer), and UA quality.
A confirmed botnet cluster contributes all its member IPs to the block list.

A genuinely popular real-browser UA (e.g. a current Chrome) is also shared by
many IPs — but those IPs are residential, behaviorally normal, and so the
cluster scores low. ASN type and behavior are the discriminators, not IP count.

Opt-in (`ua_cluster_enabled`). Separate output file.

### v1.2 — PTR verification of claimed bots
Wire the already-implemented PTR + forward-DNS verification helpers so that a
UA claiming to be Googlebot/bingbot/etc. is only whitelisted if its reverse DNS
resolves into the vendor's domain. Without this, a fake-bot UA spoofing
Googlebot is skipped unscored.

### v2.0 — Realtime delivery
Move the decision from a 10-minute cron batch to an inline per-request check.

The detection logic (all three passes' scoring) is unchanged — v2.0 only
changes *when* the decision is made. Two candidate architectures:

- **`auth_request` → scoring daemon** — nginx issues a subrequest to a local
  daemon holding rolling per-IP / per-UA state. Language-agnostic, the current
  Python logic ports with little change. Cost: one loopback roundtrip per
  request; risk: the daemon becomes a single point of failure — must run with a
  hard timeout and `error_page` fail-open.
- **In-process (Lua / njs)** — scoring runs inside nginx with shared memory
  (`lua_shared_dict`) for cross-worker rolling counters. No external daemon, no
  network hop, no extra SPOF. Cost: requires OpenResty or the `lua-nginx`
  dynamic module.

Realtime unlocks two things the batch model cannot do:
- act on the **first** request from a new IP, if its UA/ASN/fingerprint already
  matches a flagged cluster;
- issue a **challenge** (JS / cookie) instead of a hard block, separating
  humans from bots without needing request history.

### Backlog (unversioned)

- **JA3 / JA4 TLS fingerprint signal** — a botnet's TLS handshake is identical
  across its whole IP fleet; an IP-independent cluster key. Requires nginx with
  a JA3/JA4 module.
- **Rotated-log support** — currently only the live `access.log` is scanned.
  Reading `.gz` rotations would widen the analysis window.
- **`self_ips` auto-detection** — resolve via `hostname -I` when set to `auto`.
- **Prometheus / textfile metrics** — export block counts, scores, pass timings
  for dashboards.

## Non-goals

- ML / statistical-model scoring — the composite-signal approach is auditable
  and tunable by hand; an opaque model is explicitly out of scope.
- Replacing a CDN's bot management — `nginx-autoblock` is an origin-side
  complement, useful with or without a CDN in front.
