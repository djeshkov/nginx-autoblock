"""Regression test for the UA-cluster ↔ per-IP dedup fix.

An IP blocked by the per-IP pass must not also be written to the UA-cluster
block file: both files are included in the same nginx geo block, and a CIDR
present in two included files makes nginx log a "duplicate network" warning
on every reload.

The UA-cluster pass must:
  1. skip cluster member IPs already owned by the per-IP pass, and
  2. drop stale entries already in its own file that the per-IP pass now owns
     (cleans duplicates accumulated before the fix).
"""
import textwrap


def _make_cfg(tmp_path, ua_file, ips_file):
    return {
        "blocked_ua_cluster_conf": str(ua_file),
        "blocked_ips_conf":        str(ips_file),
        "asn_db":                  str(tmp_path / "nonexistent-asn.tsv.gz"),
        "ua_cluster_threshold":    7,
        "ua_cluster_min_ips":      30,
    }


def test_ua_cluster_skips_and_drops_per_ip_owned_ips(autoblock_mod, tmp_path, monkeypatch):
    ua_file = tmp_path / "blocked-ua-clusters.conf"
    ips_file = tmp_path / "blocked-ips.conf"

    # per-IP pass already owns 1.1.1.1 and 9.9.9.9
    ips_file.write_text(textwrap.dedent(f"""\
        {autoblock_mod.AUTO_BEGIN_MARKER}
        1.1.1.1 1; # auto added=2026-05-19T00:00:00Z expires=2026-05-26T00:00:00Z reason=per-ip
        9.9.9.9 1; # auto added=2026-05-19T00:00:00Z expires=2026-05-26T00:00:00Z reason=per-ip
        {autoblock_mod.AUTO_END_MARKER}
        """))

    # UA-cluster file already has a STALE duplicate (1.1.1.1, now owned by
    # per-IP) plus a legitimate own entry (2.2.2.2)
    ua_file.write_text(textwrap.dedent(f"""\
        {autoblock_mod.AUTO_BEGIN_MARKER}
        1.1.1.1 1; # auto added=2026-05-18T00:00:00Z expires=2026-05-25T00:00:00Z reason=ua-cluster
        2.2.2.2 1; # auto added=2026-05-18T00:00:00Z expires=2026-05-25T00:00:00Z reason=ua-cluster
        {autoblock_mod.AUTO_END_MARKER}
        """))

    # One cluster whose members overlap per-IP (1.1.1.1, 9.9.9.9) and add new
    # IPs (2.2.2.2 extend, 3.3.3.3 new)
    cluster = {
        "ua": "Mozilla/5.0 Firefox/133.0", "score": 12, "ip_count": 200,
        "hosting_ratio": 0.95, "reasons": "noassets,noref,host95%",
        "ips": ["1.1.1.1", "9.9.9.9", "2.2.2.2", "3.3.3.3"],
        "added": "2026-05-19T10:00:00Z", "expires": "2026-05-26T10:00:00Z",
    }

    monkeypatch.setattr(autoblock_mod, "find_blockable_ua_clusters",
                        lambda *a, **k: [cluster])
    monkeypatch.setattr(autoblock_mod, "nginx_reload", lambda: True)

    cfg = _make_cfg(tmp_path, ua_file, ips_file)
    autoblock_mod.cmd_ua_cluster(cfg, dry_run=False)

    manual, auto = autoblock_mod.read_blocked(str(ua_file))
    cidrs = {e["cidr"] for e in auto}

    # per-IP-owned IPs must NOT be in the UA-cluster file
    assert "1.1.1.1" not in cidrs, "stale per-IP-owned dup must be dropped"
    assert "9.9.9.9" not in cidrs, "per-IP-owned IP must be skipped, not added"
    # UA-cluster's own IPs stay
    assert "2.2.2.2" in cidrs, "UA-cluster's own IP must be kept"
    assert "3.3.3.3" in cidrs, "new non-overlapping cluster IP must be added"


def test_ua_cluster_no_per_ip_file_is_safe(autoblock_mod, tmp_path, monkeypatch):
    """When blocked_ips_conf does not exist, dedup is a no-op — all cluster
    IPs are written normally."""
    ua_file = tmp_path / "blocked-ua-clusters.conf"
    ips_file = tmp_path / "does-not-exist.conf"

    cluster = {
        "ua": "Mozilla/5.0 Firefox/133.0", "score": 12, "ip_count": 200,
        "hosting_ratio": 0.95, "reasons": "noassets,noref",
        "ips": ["4.4.4.4", "5.5.5.5"],
        "added": "2026-05-19T10:00:00Z", "expires": "2026-05-26T10:00:00Z",
    }
    monkeypatch.setattr(autoblock_mod, "find_blockable_ua_clusters",
                        lambda *a, **k: [cluster])
    monkeypatch.setattr(autoblock_mod, "nginx_reload", lambda: True)

    cfg = _make_cfg(tmp_path, ua_file, ips_file)
    autoblock_mod.cmd_ua_cluster(cfg, dry_run=False)

    _, auto = autoblock_mod.read_blocked(str(ua_file))
    cidrs = {e["cidr"] for e in auto}
    assert cidrs == {"4.4.4.4", "5.5.5.5"}


def test_ua_cluster_same_ip_two_clusters_not_duplicated(autoblock_mod, tmp_path, monkeypatch):
    """An IP appearing in two clusters in one run must be written once, not
    twice (the auto_by_cidr index must be updated as entries are appended)."""
    ua_file = tmp_path / "blocked-ua-clusters.conf"
    ips_file = tmp_path / "no-per-ip.conf"

    clusters = [
        {"ua": "UA-A", "score": 10, "ip_count": 50, "hosting_ratio": 0.9,
         "reasons": "x", "ips": ["7.7.7.7"],
         "added": "2026-05-19T10:00:00Z", "expires": "2026-05-26T10:00:00Z"},
        {"ua": "UA-B", "score": 10, "ip_count": 50, "hosting_ratio": 0.9,
         "reasons": "x", "ips": ["7.7.7.7"]},  # same IP, second cluster
    ]
    # second cluster reuses added/expires from first via .get fallback in code;
    # provide them to be safe
    clusters[1]["added"] = "2026-05-19T10:00:00Z"
    clusters[1]["expires"] = "2026-05-26T10:00:00Z"

    monkeypatch.setattr(autoblock_mod, "find_blockable_ua_clusters",
                        lambda *a, **k: clusters)
    monkeypatch.setattr(autoblock_mod, "nginx_reload", lambda: True)

    cfg = _make_cfg(tmp_path, ua_file, ips_file)
    autoblock_mod.cmd_ua_cluster(cfg, dry_run=False)

    _, auto = autoblock_mod.read_blocked(str(ua_file))
    cidrs = [e["cidr"] for e in auto]
    assert cidrs.count("7.7.7.7") == 1, "IP in two clusters must appear once"
