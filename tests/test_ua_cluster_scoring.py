"""TDD contract for the UA-cluster pass (v1.2).

The UA-cluster pass groups requests by User-Agent and scores the *cluster* —
the discriminator between a botnet and a genuinely popular browser UA is the
hosting-ASN ratio of the cluster's IPs plus cluster-wide behavioral homogeneity,
NOT the raw IP count (a real Chrome UA is also shared by many IPs).

Each signal is tested in isolation, then composition through threshold gating.
"""


# ─────────────────────────────────────────────────────────────────────
# Individual signals

def test_hosting_ratio_signal_fires_at_50pct(autoblock_mod, base_ua_cluster_stats):
    _, sigs = autoblock_mod.score_ua_cluster(base_ua_cluster_stats,
                                             hosting_ratio=0.5, cfg={})
    assert any("host" in s for s in sigs)


def test_hosting_ratio_signal_adds_more_at_80pct(autoblock_mod, base_ua_cluster_stats):
    score_50, _ = autoblock_mod.score_ua_cluster(base_ua_cluster_stats,
                                                 hosting_ratio=0.5, cfg={})
    score_90, _ = autoblock_mod.score_ua_cluster(base_ua_cluster_stats,
                                                 hosting_ratio=0.9, cfg={})
    assert score_90 > score_50


def test_hosting_ratio_signal_silent_for_residential_cluster(autoblock_mod, base_ua_cluster_stats):
    _, sigs = autoblock_mod.score_ua_cluster(base_ua_cluster_stats,
                                             hosting_ratio=0.06, cfg={})
    assert not any("host" in s for s in sigs)


def test_noassets_signal_fires_when_cluster_loads_no_assets(autoblock_mod, base_ua_cluster_stats):
    stats = base_ua_cluster_stats
    stats["reqs"] = 3000
    stats["assets"] = 0
    _, sigs = autoblock_mod.score_ua_cluster(stats, hosting_ratio=0.0, cfg={})
    assert "noassets" in sigs


def test_noassets_signal_silent_when_cluster_loads_assets(autoblock_mod, base_ua_cluster_stats):
    _, sigs = autoblock_mod.score_ua_cluster(base_ua_cluster_stats,
                                             hosting_ratio=0.0, cfg={})
    assert "noassets" not in sigs


def test_noref_signal_fires_when_cluster_has_no_referers(autoblock_mod, base_ua_cluster_stats):
    stats = base_ua_cluster_stats
    stats["reqs"] = 3000
    stats["no_ref"] = 2900
    _, sigs = autoblock_mod.score_ua_cluster(stats, hosting_ratio=0.0, cfg={})
    assert "noref" in sigs


def test_4xx_signal_fires_on_probing_cluster(autoblock_mod, base_ua_cluster_stats):
    stats = base_ua_cluster_stats
    stats["reqs"] = 1000
    stats["status_4xx"] = 400
    _, sigs = autoblock_mod.score_ua_cluster(stats, hosting_ratio=0.0, cfg={})
    assert "4xx" in sigs


def test_ua_quality_signal_fires_for_old_chrome_cluster(autoblock_mod, base_ua_cluster_stats):
    stats = base_ua_cluster_stats
    stats["ua"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
    _, sigs = autoblock_mod.score_ua_cluster(stats, hosting_ratio=0.0, cfg={})
    assert any("oldchrome" in s for s in sigs)


def test_ua_quality_signal_fires_for_headless_cluster(autoblock_mod, base_ua_cluster_stats):
    stats = base_ua_cluster_stats
    stats["ua"] = "Mozilla/5.0 HeadlessChrome/120.0.0.0 Safari/537.36"
    _, sigs = autoblock_mod.score_ua_cluster(stats, hosting_ratio=0.0, cfg={})
    assert any("headless" in s for s in sigs)


# ─────────────────────────────────────────────────────────────────────
# Composition — the May 18 2026 incident as the reference scenario

def test_distributed_botnet_cluster_crosses_threshold(autoblock_mod, botnet_ua_cluster_stats):
    """May 18 fingerprint: ~250 hosting IPs sharing one plausible Firefox UA,
    no assets, no referer. hosting(+4) + noassets(+3) + noref(+2) = 9 >= 7."""
    score, sigs = autoblock_mod.score_ua_cluster(botnet_ua_cluster_stats,
                                                 hosting_ratio=0.9, cfg={})
    assert score >= 7, f"expected >=7, got {score} with signals {sigs}"


def test_popular_real_browser_cluster_does_NOT_cross_threshold(autoblock_mod, base_ua_cluster_stats):
    """A current Chrome UA shared by many residential IPs with normal behavior
    must score below the block threshold — IP count alone is not a signal."""
    score, sigs = autoblock_mod.score_ua_cluster(base_ua_cluster_stats,
                                                 hosting_ratio=0.06, cfg={})
    assert score < 7, f"real browser cluster got score {score} with sigs {sigs}"


# ─────────────────────────────────────────────────────────────────────
# Helpers

def test_hosting_ratio_computes_fraction_on_cloud_asn(autoblock_mod):
    """hosting_ratio_for_ips counts what fraction of IPs resolve to a
    hosting/cloud ASN via the supplied lookup."""
    ips = {"1.1.1.1", "2.2.2.2", "3.3.3.3", "4.4.4.4"}
    # 3 of 4 on hosting ASNs
    asn_map = {
        "1.1.1.1": "DIGITALOCEAN-ASN, US",
        "2.2.2.2": "AMAZON-AES, US",
        "3.3.3.3": "Tencent cloud computing",
        "4.4.4.4": "Vodafone Espana",
    }
    ratio = autoblock_mod.hosting_ratio_for_ips(ips, lambda ip: asn_map.get(ip, ""))
    assert abs(ratio - 0.75) < 0.01
