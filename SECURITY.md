# Security Policy

## Reporting a vulnerability

If you've found a security issue in `nginx-autoblock` — please **do not** open a public GitHub issue. Instead, email **dan@cloudzen.it** with:

- A clear description of the vulnerability
- Steps to reproduce
- Affected version(s) / commit hash
- Your assessment of the impact

You should expect an initial response within 5 business days.

## What counts as a security issue

**In scope:**
- Bypass of the blocklist mechanism that allows blocked subnets to reach upstream
- False-positive triggers that could be exploited to block legitimate users at scale (e.g., crafting requests to score a victim subnet over threshold)
- Crashes / DoS in the autoblock script itself (e.g., malformed log lines causing exceptions)
- Path traversal or injection via config / log file content
- Information disclosure (leaking blocked CIDRs to unauthorized parties)

**Out of scope:**
- Issues in `nginx`, `iptoasn.com`, `ip-api.com`, or other upstream/external services
- Bots evading detection — this is expected; detection is heuristic, not guaranteed. Submit as a feature request instead.
- Issues that require admin access to the host (you already own the box at that point)
- Defaults you disagree with (config it differently)

## Disclosure policy

- Reporter and maintainer coordinate on a fix and disclosure timeline
- Default disclosure timeline: 90 days from report, or sooner if a fix is published
- Credit given in release notes (or anonymous if reporter prefers)

## Supported versions

Latest `main` branch only. Tagged releases (when present) get security patches but no LTS guarantees — this is a small side project.
