"""TDD contract for per-IP behavioral scoring.

Each signal is tested in isolation, then composition is tested through threshold
gating. Whitelist (UA substring, claimed-bot, self-IP) tests cover backward-compat
fallback path."""


# ─────────────────────────────────────────────────────────────────────
# Individual signals — each test isolates one signal

def test_score_noassets_signal_fires_when_asset_ratio_below_5pct(autoblock_mod, base_ip_stats):
    stats = base_ip_stats
    stats["reqs"] = 20
    stats["assets"] = 0           # 0% asset ratio
    score, sigs = autoblock_mod.score_ip(stats, asn_desc="", cfg={})
    assert "noassets" in sigs
    assert score >= 3


def test_score_noassets_signal_does_NOT_fire_when_below_min_reqs(autoblock_mod, base_ip_stats):
    stats = base_ip_stats
    stats["reqs"] = 2             # below min_reqs=3
    stats["assets"] = 0
    _, sigs = autoblock_mod.score_ip(stats, asn_desc="", cfg={})
    assert "noassets" not in sigs


def test_score_noref_signal_fires_when_no_referer_dominant(autoblock_mod, base_ip_stats):
    stats = base_ip_stats
    stats["reqs"] = 10
    stats["no_ref"] = 10          # 100% no-referer
    stats["int_ref"] = 0
    stats["ext_ref"] = 0
    score, sigs = autoblock_mod.score_ip(stats, asn_desc="", cfg={})
    assert "noref" in sigs


def test_score_unique_paths_signal_fires_on_perfect_uniqueness(autoblock_mod, base_ip_stats):
    stats = base_ip_stats
    stats["reqs"] = 10
    stats["paths"] = {f"/x/{i}" for i in range(10)}  # 100% unique
    score, sigs = autoblock_mod.score_ip(stats, asn_desc="", cfg={})
    assert "upath" in sigs


def test_score_cloud_asn_signal_fires_for_aws(autoblock_mod, base_ip_stats):
    score, sigs = autoblock_mod.score_ip(base_ip_stats, asn_desc="AMAZON-AES, US", cfg={})
    assert "cloud" in sigs


def test_score_cloud_asn_signal_fires_for_tencent(autoblock_mod, base_ip_stats):
    _, sigs = autoblock_mod.score_ip(base_ip_stats,
                                     asn_desc="TENCENT-NET-AP Shenzhen Tencent Computer", cfg={})
    assert "cloud" in sigs


def test_score_cloud_asn_signal_does_NOT_fire_for_residential_isp(autoblock_mod, base_ip_stats):
    _, sigs = autoblock_mod.score_ip(base_ip_stats,
                                     asn_desc="Vodafone Espana", cfg={})
    assert "cloud" not in sigs


def test_score_old_chrome_signal_fires_for_chrome_120(autoblock_mod, base_ip_stats):
    stats = base_ip_stats
    stats["ua_set"] = {"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
    _, sigs = autoblock_mod.score_ip(stats, asn_desc="", cfg={})
    assert any("oldchrome" in s for s in sigs)


def test_score_old_chrome_does_NOT_fire_for_current_chrome(autoblock_mod, base_ip_stats):
    stats = base_ip_stats
    stats["ua_set"] = {"Mozilla/5.0 Chrome/148.0.0.0 Safari/537.36"}
    _, sigs = autoblock_mod.score_ip(stats, asn_desc="", cfg={})
    assert not any("oldchrome" in s for s in sigs)


def test_score_headless_ua_signal_fires(autoblock_mod, base_ip_stats):
    stats = base_ip_stats
    stats["ua_set"] = {"Mozilla/5.0 HeadlessChrome/120.0.0.0 Safari/537.36"}
    _, sigs = autoblock_mod.score_ip(stats, asn_desc="", cfg={})
    assert any("headless" in s for s in sigs)


# ─────────────────────────────────────────────────────────────────────
# Composition — real scenarios validated in v3 backtest

def test_distributed_scraper_1req_cloud_oldchrome_crosses_threshold(autoblock_mod, scraper_ip_stats):
    """The whole point of v6 — distributed scraper with 1 req from cloud ASN
    with old Chrome should score >= 9 (cloud+3, noref+2, oldchrome+2, noassets needs N>=3)."""
    stats = scraper_ip_stats
    stats["reqs"] = 3    # noassets needs ≥3
    score, sigs = autoblock_mod.score_ip(stats, asn_desc="DIGITALOCEAN-ASN, US", cfg={})
    # cloud(+3) + noref(+2) + noassets(+3) + oldchrome(+2) = 10
    assert score >= 9, f"expected >=9, got {score} with signals {sigs}"


def test_real_user_does_NOT_cross_threshold(autoblock_mod, base_ip_stats):
    """Real browser from residential ISP should score below 6."""
    score, sigs = autoblock_mod.score_ip(base_ip_stats,
                                         asn_desc="Vodafone Espana", cfg={})
    assert score < 6, f"real user got score {score} with sigs {sigs}"


# ─────────────────────────────────────────────────────────────────────
# Whitelists

def test_ua_whitelist_skips_privacy_prefetch_proxy(autoblock_mod, base_ip_stats):
    stats = base_ip_stats
    stats["ua_set"] = {"Chrome Privacy Preserving Prefetch Proxy"}
    assert autoblock_mod.is_ua_whitelisted(stats["ua_set"]) is True


def test_ua_whitelist_skips_imgix(autoblock_mod, base_ip_stats):
    stats = base_ip_stats
    stats["ua_set"] = {"imgix/3.0.0.0"}
    assert autoblock_mod.is_ua_whitelisted(stats["ua_set"]) is True


def test_ua_whitelist_does_NOT_skip_real_chrome(autoblock_mod, base_ip_stats):
    assert autoblock_mod.is_ua_whitelisted(base_ip_stats["ua_set"]) is False


def test_claimed_bot_detects_googlebot(autoblock_mod):
    ua_set = {"Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"}
    assert autoblock_mod.is_claimed_bot(ua_set) is True


def test_claimed_bot_detects_yisouspider(autoblock_mod):
    """Regression — YisouSpider was missed in v2; added after ip-api validation."""
    ua_set = {"YisouSpider"}
    assert autoblock_mod.is_claimed_bot(ua_set) is True


def test_claimed_bot_does_NOT_match_regular_chrome(autoblock_mod, base_ip_stats):
    assert autoblock_mod.is_claimed_bot(base_ip_stats["ua_set"]) is False


# ─────────────────────────────────────────────────────────────────────
# UA parsing helpers

def test_chrome_version_extracts_correctly(autoblock_mod):
    ua = "Mozilla/5.0 Chrome/120.0.6099.130 Safari/537.36"
    assert autoblock_mod.extract_chrome_version(ua) == 120


def test_chrome_version_returns_none_when_absent(autoblock_mod):
    assert autoblock_mod.extract_chrome_version("curl/8.5.0") is None


def test_ua_truncation_stores_at_least_250_chars(autoblock_mod):
    """Googlebot Mobile UA is ~198 chars — must not be truncated past the
    'Googlebot/2.1' marker."""
    long_ua = ("Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) "
               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/W.X.Y.Z Mobile "
               "Safari/537.36 (compatible; Googlebot/2.1; "
               "+http://www.google.com/bot.html)")
    assert len(long_ua) < autoblock_mod.UA_MAX_LENGTH
    assert "Googlebot" in long_ua[:autoblock_mod.UA_MAX_LENGTH]
