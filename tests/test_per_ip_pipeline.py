"""Integration tests for the per-IP pipeline: log → stats → score → block list."""
import textwrap


SAMPLE_LOG = textwrap.dedent("""\
    1.2.3.4 - - [15/May/2026:08:30:01 +0000] "GET /reservation/abc HTTP/2.0" 200 12345 "-" "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0.0.0 Safari/537.36"
    1.2.3.4 - - [15/May/2026:08:30:02 +0000] "GET /reservation/def HTTP/2.0" 200 12345 "-" "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0.0.0 Safari/537.36"
    1.2.3.4 - - [15/May/2026:08:30:03 +0000] "GET /reservation/ghi HTTP/2.0" 200 12345 "-" "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0.0.0 Safari/537.36"
    5.6.7.8 - - [15/May/2026:08:30:02 +0000] "GET / HTTP/2.0" 200 5000 "https://google.com/" "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/148.0.0.0 Safari/537.36"
    5.6.7.8 - - [15/May/2026:08:30:03 +0000] "GET /app.js HTTP/2.0" 200 80000 "https://example.com/" "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/148.0.0.0 Safari/537.36"
    5.6.7.8 - - [15/May/2026:08:30:04 +0000] "GET /style.css HTTP/2.0" 200 20000 "https://example.com/" "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/148.0.0.0 Safari/537.36"
    66.249.66.1 - - [15/May/2026:08:30:05 +0000] "GET /catalog/spain HTTP/2.0" 200 8000 "-" "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    """)


def test_scan_log_per_ip_aggregates_correctly(autoblock_mod, tmp_path):
    log_path = tmp_path / "access.log"
    log_path.write_text(SAMPLE_LOG)
    cfg = {"access_log": str(log_path), "internal_ref_hosts": ["example.com"]}
    stats = autoblock_mod.scan_log_per_ip(cfg, window_start=None)
    # 1.2.3.4 made 1 request, 5.6.7.8 made 3, googlebot 1
    assert stats["1.2.3.4"]["reqs"] == 3
    assert stats["5.6.7.8"]["reqs"] == 3
    assert stats["5.6.7.8"]["assets"] == 2  # .js + .css
    assert stats["5.6.7.8"]["int_ref"] == 2
    assert stats["5.6.7.8"]["ext_ref"] == 1


def test_find_blockable_ips_returns_scrapers_only(autoblock_mod, tmp_path):
    log_path = tmp_path / "access.log"
    log_path.write_text(SAMPLE_LOG)
    cfg = {
        "access_log":            str(log_path),
        "per_ip_threshold":      6,
        "internal_ref_hosts":    ["example.com"],
        "self_ips":              [],
    }
    # Stub ASN lookup — pretend 1.2.3.4 is from a cloud
    def stub_asn(ip):
        return "DIGITALOCEAN-ASN, US" if ip == "1.2.3.4" else "Vodafone Espana"
    blockable = autoblock_mod.find_blockable_ips(cfg, asn_lookup_fn=stub_asn, window_start=None)
    ips = {b["ip"] for b in blockable}
    assert "1.2.3.4" in ips         # cloud + noref + old chrome
    assert "5.6.7.8" not in ips     # real user (assets, referer, current chrome)
    # Googlebot — claimed bot, must be excluded
    assert "66.249.66.1" not in ips


def test_self_ips_skipped(autoblock_mod, tmp_path):
    log_path = tmp_path / "access.log"
    log_path.write_text(SAMPLE_LOG)
    cfg = {
        "access_log":            str(log_path),
        "per_ip_threshold":      6,
        "internal_ref_hosts":    ["example.com"],
        "self_ips":              ["1.2.3.4"],  # mark as self
    }
    blockable = autoblock_mod.find_blockable_ips(
        cfg,
        asn_lookup_fn=lambda ip: "DIGITALOCEAN-ASN, US",
        window_start=None,
    )
    ips = {b["ip"] for b in blockable}
    assert "1.2.3.4" not in ips


def test_write_blocked_ips_conf_format(autoblock_mod, tmp_path):
    blockable = [
        {"ip": "1.2.3.4", "score": 10, "reasons": "noref,cloud,oldchrome",
         "added": "2026-05-15T12:00:00Z", "expires": "2026-05-22T12:00:00Z"},
    ]
    out = tmp_path / "blocked-ips.conf"
    autoblock_mod.write_blocked_ips(str(out), manual=[], auto=blockable)
    content = out.read_text()
    assert "1.2.3.4 1; # auto added=" in content
    assert autoblock_mod.AUTO_BEGIN_MARKER in content
    assert autoblock_mod.AUTO_END_MARKER in content
    assert "reason=noref,cloud,oldchrome" in content


def test_read_blocked_ips_preserves_manual_and_parses_auto(autoblock_mod, tmp_path):
    f = tmp_path / "blocked-ips.conf"
    f.write_text(textwrap.dedent(f"""\
        # Manually-blocked IP — keep
        9.9.9.9 1;

        {autoblock_mod.AUTO_BEGIN_MARKER}
        # Managed by autoblock per-IP pass.
        1.2.3.4 1; # auto added=2026-05-15T12:00:00Z expires=2026-05-22T12:00:00Z reason=cloud
        {autoblock_mod.AUTO_END_MARKER}
        """))
    manual, auto = autoblock_mod.read_blocked(str(f))
    assert any("9.9.9.9" in line for line in manual)
    assert len(auto) == 1
    assert auto[0]["cidr"] == "1.2.3.4"
