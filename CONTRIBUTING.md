# Contributing to nginx-autoblock

Contributions welcome — bug reports, feature ideas, code, documentation improvements.

## Quick start

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/nginx-autoblock.git`
3. Create a branch: `git checkout -b feature/your-thing`
4. Make changes, test, commit
5. Push to your fork: `git push origin feature/your-thing`
6. Open a Pull Request

## Setting up locally

Requirements: Python 3.8+ (only stdlib, no pip install needed).

```bash
git clone https://github.com/djeshkov/nginx-autoblock.git
cd nginx-autoblock
chmod +x autoblock
```

Test the script against a sample log:

```bash
# Create a minimal config pointing to your test data
cat > /tmp/test-config.env <<EOF
access_log=/tmp/sample-access.log
blocked_conf=/tmp/blocked-subnets.conf
whitelist=$(pwd)/whitelist.example.conf
asn_db=/tmp/ip2asn-combined.tsv.gz
rep_cache=/tmp/reputation.json
log_file=/tmp/autoblock-test.log
use_ipapi=false
min_requests=50
EOF

# Fetch ASN database
curl -L https://iptoasn.com/data/ip2asn-combined.tsv.gz > /tmp/ip2asn-combined.tsv.gz

# Run in show-scores mode
./autoblock --config /tmp/test-config.env --show-scores
```

## What kind of contributions are welcome

### High-value

- **New behavioral signals.** Did you find a pattern that discriminates well between bots and humans on your traffic? Add it as an optional signal with its own threshold and weight. Document the trade-off in `docs/SCORING.md`.

- **Better defaults for specific platforms.** Different web stacks have different "natural" target paths. If you've tuned this for WordPress / Laravel / Django / Rails / etc. and want to share a config preset — open a PR with a new file in `presets/`.

- **Test cases.** We don't have unit tests yet. PRs welcome that add `pytest` coverage for the scoring functions (using captured log samples).

- **Documentation.** Especially: comparison with other tools, deployment guides (Ansible/Salt/Docker), troubleshooting recipes.

### Medium-value

- **Additional reputation providers.** The current architecture is built for ip-api.com but the code is structured to make adding Scamalytics, IPQualityScore, AbuseIPDB, etc. straightforward. PRs welcome — see `enrich_with_reputation()` in `autoblock`.

- **Per-locale path patterns.** Currently `target_paths` is a flat list. A configurable pattern matching system (regex, glob) could be useful.

- **IPv6 /48 vs /64 heuristics.** Currently fixed at `/64`. Auto-detection of mobile carrier IPv6 ranges (which typically issue /64 per customer) vs hosting /48 ranges could improve accuracy.

### Lower priority

- **Static-asset signal for non-CDN deployments.** Mentioned in README as future work. Behind a CDN it's broken, but for direct-to-origin nginx it could be useful. Would need to detect CDN presence and toggle automatically.

- **GUI / web dashboard.** Tempting but out of scope for v1. The text-based `--show-scores` output is the diagnostic interface.

## What's NOT a good fit

- **Adding paid services** (Cloudflare Bot Management API, etc.) as core dependencies. The point of this project is to work without paid services. Optional integration is fine.

- **Removing the AI bot whitelist.** Default whitelist for ChatGPT/Claude/etc. is intentional — these crawlers benefit your AI search visibility. If you don't want them, remove from your local whitelist.

- **Aggressive defaults that block more by default.** The project errs on the side of fewer false positives. PRs that lower thresholds without strong justification will be redirected to a config flag.

## Code style

- **Python 3.8+ stdlib only.** No `pip install` requirements. If you need a third-party lib, discuss in an issue first.
- **PEP 8** with relaxed line length (100 chars OK).
- **No type hints required** but welcome on new code.
- **Comments**: only when the *why* is non-obvious. Don't restate the *what*.
- **Configuration over code**: new settings should be exposed in `config.example.env`, not hardcoded.

## Testing your changes

There's no formal test suite yet. Until there is, please verify your change manually:

1. Run `--show-scores` on a sample log (yours or anonymized) and confirm the score breakdown matches expectations.
2. Run `--dry-run` and confirm no unexpected entries.
3. If you changed scoring, walk through `docs/SCORING.md` examples and verify they still produce the documented results.

For backtests on real logs:

```bash
# Combine N days of logs
cat /var/log/nginx/access.log.* > /tmp/big-log.gz  # or however your rotation works
# Point access_log to it in test config
# Run --show-scores with lowered min_requests
```

## Filing a good issue

**Bugs**: include OS, Python version, nginx version, sanitized config file, sanitized log snippet showing the issue, and `--show-scores` output if relevant. Anonymize real IPs before posting.

**Feature requests**: explain the *use case* — what bot/scenario you're trying to detect, why current scoring doesn't catch it.

**Security issues**: see `SECURITY.md` — do **not** open public issues for security vulnerabilities.

## Pull Request expectations

- One logical change per PR. Split unrelated changes.
- Update docs if behavior changes (README, SCORING.md, config.example.env).
- If adding a new signal, include the math: how it scores on a known bot sample, how it scores on real traffic.
- Squash trivial commits before requesting review.

## Code of conduct

Be kind. Disagree on substance. Don't make it personal.

## Maintainer response time

This is a side project. Expect responses within a few days, possibly slower. If something is time-sensitive (security issue), use the contact in `SECURITY.md`.
