"""Pool: quality-controlled events, picks and stations, one folder per network.

    data/pool/
      pool_config.json               QC + split config every network was built with
      qc_report.csv                  QC funnel per network
      label_model.json               fitted by bepad.build.labels (all networks)
      network=<name>/events.parquet  one row per event (with its split)
      network=<name>/picks.parquet   one row per pick (P/S, travel time, distances)
      network=<name>/stations.parquet
      network=<name>/manifest.json   UTDQuake version + revision, source hashes, QC report

<name> is the UTDQuake network (``utdq_net``); a station is ``NET.STA`` (see bepad.build.utdquake).

QC mirrors hypogt test/09252026 v8:
  1. event filters: >= 4 P-family picks, >= 3 stations, catalog gap <= 270 deg,
     depth, RMS, horizontal/vertical uncertainty
  2. P/S families only; per-pick abs(z-score) <= 3 trimming, reverted if the
     event would drop below 3 stations or above 270 deg gap
  3. drop negative travel times; earliest pick per (event, station, P/S);
     re-check >= 4 P picks on >= 3 stations

Split: random per event, sha256(salt | network | event_id) -> train/val/test;
a network with fewer than ``split.test_only_below`` events is test only.
Networks are treated independently, and adding a network never moves an
existing event.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd

from .geo import P_PHASES, S_PHASES, azimuthal_gap_deg, haversine_km, stable_uniform

_FAMILY = {p: "P" for p in P_PHASES} | {s: "S" for s in S_PHASES}

EVENT_COLUMNS = [
    "event_id", "network", "time", "latitude", "longitude", "depth", "magnitude",
    "magnitude_type", "catalog_azimuthal_gap", "standard_error",
    "horizontal_uncertainty", "vertical_uncertainty", "n_p", "n_s", "n_picks",
    "n_stations", "gap_deg", "duration_s", "max_dist_km", "last_station_km", "split",
]
PICK_COLUMNS = [
    "event_id", "network", "station", "phase", "phase_raw", "time", "travel_time",
    "distance_km", "hyp_distance_km", "travel_time_zscore", "evaluation_mode", "pick_id",
]
STATION_COLUMNS = ["network", "station_network", "station", "latitude", "longitude", "elevation"]


def pool_dir(data_root) -> Path:
    return Path(data_root) / "pool"


# ----------------------------------------------------------------------
# Stations
# ----------------------------------------------------------------------
def _station_table(stations, network):
    """One row per available, located station (``NET.STA``): confirmed coordinates, else the
    ones UTDQuake calculated from the picks (elevation 0)."""
    st = stations[stations["available"].fillna(False).astype(bool)]
    conf = st["confirmed"].fillna(False).astype(bool).to_numpy()
    out = pd.DataFrame({
        "network": network,
        "station_network": st["station_network"].astype(str).to_numpy(),
        "station": st["station"].to_numpy(),
        "latitude": np.where(conf, st["confirmed_latitude"], st["calculated_latitude"]).astype(float),
        "longitude": np.where(conf, st["confirmed_longitude"], st["calculated_longitude"]).astype(float),
        "elevation": np.where(conf, st["confirmed_elevation"], 0.0).astype(float),
    })
    out["elevation"] = out["elevation"].fillna(0.0)
    out = out.dropna(subset=["latitude", "longitude"])
    return out.drop_duplicates(subset="station").reset_index(drop=True)


# ----------------------------------------------------------------------
# QC
# ----------------------------------------------------------------------
def _passes(ev, col, max_value, keep_missing):
    values = pd.to_numeric(ev[col], errors="coerce") if col in ev else pd.Series(np.nan, index=ev.index)
    return (values <= max_value) | (values.isna() & keep_missing)


def run_qc(events, picks, stations, qc, network):
    """Return (events, picks, report) after the three QC stages."""
    rep = OrderedDict()
    rep["events_raw"] = len(events)
    rep["picks_raw"] = len(picks)

    ev = events.dropna(subset=["time", "latitude", "longitude", "depth"])
    ev = ev.drop_duplicates(subset="event_id").copy()
    ev["event_id"] = ev["event_id"].astype(str)
    rep["events_with_origin"] = len(ev)

    # some networks already carry event_* columns in their picks; ours come from the events table
    pk = picks.drop(columns=["event_time", "event_latitude", "event_longitude", "latitude", "longitude"],
                    errors="ignore").copy()
    pk["event_id"] = pk["event_id"].astype(str)
    pk = pk.merge(stations[["station", "latitude", "longitude"]], on="station", how="inner")
    pk = pk[pk["event_id"].isin(ev["event_id"])]
    rep["picks_with_station_coords"] = len(pk)

    # --- stage 1: event filters (hypogt pre_filter) -------------------
    fam = pk["phase"].map(_FAMILY)
    counts = pd.DataFrame({
        "n_p": (fam == "P").groupby(pk["event_id"]).sum(),
        "n_s": (fam == "S").groupby(pk["event_id"]).sum(),
        "n_sta": pk.groupby("event_id")["station"].nunique(),
    })
    ev = ev.join(counts, on="event_id")
    ev[["n_p", "n_s", "n_sta"]] = ev[["n_p", "n_s", "n_sta"]].fillna(0)

    keep_missing = qc["keep_missing"]
    steps = [
        ("min_p_s", (ev["n_p"] >= qc["min_p"]) & (ev["n_s"] >= qc["min_s"])),
        ("min_stations", ev["n_sta"] >= qc["min_stations"]),
        ("max_gap", _passes(ev, "azimuthal_gap", qc["max_gap_deg"], keep_missing)),
        ("max_depth", _passes(ev, "depth", qc["max_depth_m"], keep_missing)),
        ("max_rms", _passes(ev, "standard_error", qc["max_rms_s"], keep_missing)),
        ("max_h_unc", _passes(ev, "horizontal_uncertainty", qc["max_horizontal_uncertainty_m"], keep_missing)),
        ("max_v_unc", _passes(ev, "vertical_uncertainty", qc["max_vertical_uncertainty_m"], keep_missing)),
    ]
    mask = pd.Series(True, index=ev.index)
    for name, m in steps:
        mask &= m.fillna(False)
        rep[f"events_after_{name}"] = int(mask.sum())
    ev = ev[mask].drop(columns=["n_p", "n_s", "n_sta"])

    # --- stage 2: P/S family + z-score trimming with revert ------------
    pk = pk[pk["event_id"].isin(ev["event_id"])].copy()
    pk["phase_raw"] = pk["phase"]
    pk["phase"] = pk["phase_raw"].map(_FAMILY)
    pk = pk[pk["phase"].notna()]
    rep["picks_ps_family"] = len(pk)

    pk = pk.merge(
        ev[["event_id", "time", "latitude", "longitude"]].rename(
            columns={"time": "event_time", "latitude": "event_latitude", "longitude": "event_longitude"}),
        on="event_id", how="left",
    )
    rep["zscore_coverage"] = round(float(pd.to_numeric(pk["travel_time_zscore"], errors="coerce").notna().mean())
                                   if "travel_time_zscore" in pk and len(pk) else 0.0, 4)
    pk = _zscore_trim(pk, qc)
    rep["picks_after_zscore"] = len(pk)

    # --- stage 3: BEPAD cleaning --------------------------------------
    pk["travel_time"] = (pk["time"] - pk["event_time"]).dt.total_seconds()
    pk = pk[pk["travel_time"] >= 0]
    rep["picks_after_positive_tt"] = len(pk)
    pk = pk.sort_values(["event_id", "station", "phase", "time"])
    pk = pk.drop_duplicates(subset=["event_id", "station", "phase"], keep="first")
    rep["picks_after_one_per_station_phase"] = len(pk)

    final = pd.DataFrame({
        "n_p": (pk["phase"] == "P").groupby(pk["event_id"]).sum(),
        "n_s": (pk["phase"] == "S").groupby(pk["event_id"]).sum(),
        "n_stations": pk.groupby("event_id")["station"].nunique(),
    })
    ok = final.index[(final["n_p"] >= qc["min_p"]) & (final["n_s"] >= qc["min_s"])
                     & (final["n_stations"] >= qc["min_stations"])]
    ev = ev[ev["event_id"].isin(ok)]
    pk = pk[pk["event_id"].isin(ok)]
    rep["events_final"] = len(ev)
    rep["picks_final"] = len(pk)
    rep["p_picks_final"] = int((pk["phase"] == "P").sum())
    rep["s_picks_final"] = int((pk["phase"] == "S").sum())

    pk["distance_km"] = haversine_km(pk["event_latitude"], pk["event_longitude"],
                                     pk["latitude"], pk["longitude"])
    depth_km = pk["event_id"].map(ev.set_index("event_id")["depth"]).to_numpy(float) / 1e3
    pk["hyp_distance_km"] = np.hypot(pk["distance_km"].to_numpy(float), depth_km)
    pk["network"] = network
    for col in ("travel_time_zscore", "evaluation_mode", "pick_id"):
        if col not in pk.columns:
            pk[col] = pd.NA

    ev = _event_summary(ev, pk, network)
    return ev, pk[PICK_COLUMNS].reset_index(drop=True), rep


def _zscore_trim(pk, qc):
    z = pd.to_numeric(pk["travel_time_zscore"], errors="coerce") if "travel_time_zscore" in pk else \
        pd.Series(np.nan, index=pk.index)
    keep = (z.abs() <= qc["zscore_sigma"]) | (z.isna() & qc["keep_nan_zscore"])
    touched = set(pk.loc[~keep, "event_id"])
    if not touched:
        return pk

    revert = set()
    trimmed = pk[keep & pk["event_id"].isin(touched)]
    n_sta = trimmed.groupby("event_id")["station"].nunique()
    for eid in touched:
        if n_sta.get(eid, 0) < qc["min_stations"]:
            revert.add(eid)
    for eid, grp in trimmed[~trimmed["event_id"].isin(revert)].groupby("event_id"):
        sta = grp.drop_duplicates(subset="station")
        gap = azimuthal_gap_deg(sta["event_latitude"].iloc[0], sta["event_longitude"].iloc[0],
                                sta["latitude"].to_numpy(), sta["longitude"].to_numpy())
        if gap > qc["max_gap_deg"]:
            revert.add(eid)

    return pk[keep | pk["event_id"].isin(revert)]


def _event_summary(ev, pk, network):
    g = pk.groupby("event_id")
    summ = pd.DataFrame({
        "n_p": (pk["phase"] == "P").groupby(pk["event_id"]).sum(),
        "n_s": (pk["phase"] == "S").groupby(pk["event_id"]).sum(),
        "n_picks": g.size(),
        "n_stations": g["station"].nunique(),
        "duration_s": g["travel_time"].max(),
        "max_dist_km": g["distance_km"].max(),
        "last_station_km": g["hyp_distance_km"].max(),
    })
    gaps = {}
    for eid, grp in pk.drop_duplicates(subset=["event_id", "station"]).groupby("event_id"):
        gaps[eid] = azimuthal_gap_deg(grp["event_latitude"].iloc[0], grp["event_longitude"].iloc[0],
                                      grp["latitude"].to_numpy(), grp["longitude"].to_numpy())
    summ["gap_deg"] = pd.Series(gaps)

    ev = ev.rename(columns={"azimuthal_gap": "catalog_azimuthal_gap"}).join(summ, on="event_id")
    ev["network"] = network
    for col in EVENT_COLUMNS:
        if col not in ev.columns:
            ev[col] = pd.NA
    return ev


# ----------------------------------------------------------------------
# Split
# ----------------------------------------------------------------------
SPLITS = ("train", "val", "test")


def assign_split(network, event_ids, salt="bepad-v1", fractions=None, test_only_below=0):
    """Random split per event: sha256(salt | network | event_id) vs cumulative fractions.

    A network with fewer than ``test_only_below`` events is test only (too few to train on).
    """
    if len(event_ids) < test_only_below:
        return np.full(len(event_ids), "test")
    fractions = fractions or {"train": 0.7, "val": 0.1, "test": 0.2}
    names = [s for s in SPLITS if fractions.get(s, 0) > 0]
    edges = np.cumsum([fractions[s] for s in names])
    if not np.isclose(edges[-1], 1.0):
        raise ValueError(f"split fractions must sum to 1, got {fractions}")
    u = np.array([stable_uniform(f"{network}|{e}", salt) for e in event_ids])
    return np.array(names)[np.minimum(np.searchsorted(edges, u, side="right"), len(names) - 1)]


# ----------------------------------------------------------------------
# Build / manifest
# ----------------------------------------------------------------------
def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _source_fingerprint(name):
    try:
        from utdquake.core.config import get_utdq_paths
        paths = get_utdq_paths(name)
        return {k: _sha256(paths[k]) for k in ("events", "picks", "stations") if Path(paths[k]).exists()}
    except Exception as exc:  # fingerprint is informative only
        return {"error": repr(exc)}


def read_manifest(data_root):
    """{"pool_config": ..., "networks": {name: entry}} assembled from per-network files."""
    root = pool_dir(data_root)
    cfg_path = root / "pool_config.json"
    if not cfg_path.exists():
        return None
    with open(cfg_path) as f:
        manifest = {"pool_config": json.load(f), "networks": {}}
    for m in sorted(root.glob("network=*/manifest.json")):
        with open(m) as f:
            manifest["networks"][m.parent.name.split("=", 1)[1]] = json.load(f)
    return manifest


def write_qc_report(data_root):
    manifest = read_manifest(data_root)
    rows = [{"network": n, **e["qc_report"]} for n, e in sorted(manifest["networks"].items())]
    pd.DataFrame(rows).to_csv(pool_dir(data_root) / "qc_report.csv", index=False)


def _check_pool_config(data_root, cfg_key):
    root = pool_dir(data_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "pool_config.json"
    if not path.exists():
        tmp = path.with_suffix(f".tmp{os.getpid()}")
        with open(tmp, "w") as f:
            json.dump(cfg_key, f, indent=2)
        os.replace(tmp, path)
    with open(path) as f:
        existing = json.load(f)
    if json.loads(json.dumps(cfg_key)) != existing:
        raise ValueError(
            f"Pool config differs from the one this pool was built with ({path}). "
            "Use a new data_root, or rebuild every network with the new config.")


def build_network(name, pool_cfg, force=False):
    """QC one UTDQuake network into the pool and register it in the manifest."""
    import utdquake

    from . import utdquake as U

    data_root = pool_cfg["data_root"]
    root = pool_dir(data_root)
    _check_pool_config(data_root, {"qc": pool_cfg["qc"], "split": pool_cfg["split"]})
    out = root / f"network={name}"
    if (out / "manifest.json").exists() and not force:
        print(f"[pool] {name} already in pool -- skipping (use --force to rebuild)")
        with open(out / "manifest.json") as f:
            return json.load(f)

    print(f"[pool] loading {name} from UTDQuake ...")
    events, picks, stations = U.load_network(name)
    stations = _station_table(stations, name)
    ev, pk, rep = run_qc(events, picks, stations, pool_cfg["qc"], name)
    ev["split"] = assign_split(name, ev["event_id"], **pool_cfg["split"])
    ev = ev[EVENT_COLUMNS].sort_values("time").reset_index(drop=True)
    stations = stations[stations["station"].isin(pk["station"].unique())]

    out.mkdir(exist_ok=True)
    ev.to_parquet(out / "events.parquet", index=False)
    pk.to_parquet(out / "picks.parquet", index=False)
    stations[STATION_COLUMNS].to_parquet(out / "stations.parquet", index=False)

    entry = {
        "built": dt.datetime.now().isoformat(timespec="seconds"),
        "utdquake_version": utdquake.__version__,
        "utdquake_revision": U.revision() or "main",
        "utdquake_network": U.network_info(name),
        "source_sha256": _source_fingerprint(name),
        "n_events": len(ev),
        "n_picks": len(pk),
        "n_stations": len(stations),
        "split_counts": ev["split"].value_counts().to_dict(),
        "qc_report": rep,
    }
    with open(out / "manifest.json", "w") as f:
        json.dump(entry, f, indent=2, default=str)
    write_qc_report(data_root)
    print(f"[pool] {name}: {rep['events_raw']} -> {len(ev)} events, "
          f"{rep['picks_raw']} -> {len(pk)} picks")
    return entry


def remove_network(name, pool_cfg):
    import shutil

    d = pool_dir(pool_cfg["data_root"]) / f"network={name}"
    if not d.exists():
        print(f"[pool] {name} not in pool")
        return
    shutil.rmtree(d)
    write_qc_report(pool_cfg["data_root"])


def missing_networks(pool_cfg):
    """UTDQuake networks (non-DAS) that are not in the pool yet."""
    from .utdquake import list_networks

    listed = set(list_networks())
    manifest = read_manifest(pool_cfg["data_root"]) or {"networks": {}}
    return sorted(listed - set(manifest["networks"]))


def load_network(data_root, name):
    d = pool_dir(data_root) / f"network={name}"
    return (pd.read_parquet(d / "events.parquet"),
            pd.read_parquet(d / "picks.parquet"),
            pd.read_parquet(d / "stations.parquet"))


def list_networks(data_root):
    manifest = read_manifest(data_root)
    return sorted(manifest["networks"]) if manifest else []
