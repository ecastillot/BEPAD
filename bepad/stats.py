"""Dataset statistics: tables that describe what is in a BEPAD split.

Every function takes a loaded split (``bepad.load(split)``, with labels) and
returns a pandas DataFrame; ``bepad.plots`` draws them.

    network_scales(split)     network -> "local" | "regional" | "global"
    source_events(split)      one row per source earthquake (catalog values + how often it is used)
    event_pairs(split)        one row per pair of earthquakes in the same window: distance, time apart
    window_geometry(split)    one row per window: stations, spacing, aperture, distances
    pick_distances(split)     one row per pick: type, phase, distance to its earthquake, travel time

Large splits are sampled with ``max_windows`` (per network) where the table is per pick or
per station, so the functions stay fast on the full release.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .build.geo import haversine_km

#: typical pick distance [km] separating the three scales
SCALE_EDGES = (150.0, 1500.0)
SCALES = ("local", "regional", "global")


def _sample_ids(split, max_windows, seed=0):
    w = split.windows
    if max_windows is None:
        return set(w.window_id)
    return set(w.groupby("network", group_keys=False)
               .apply(lambda g: g.sample(min(len(g), max_windows), random_state=seed)).window_id)


def _coords(split):
    st = split.window_stations.drop_duplicates(["network", "station"]).set_index(["network", "station"])
    return st[["latitude", "longitude"]]


def pick_distances(split, max_windows=200):
    """Picks of (a sample of) windows with the hypocentral distance to their own earthquake
    (event picks) or to the nearest earthquake (noise), and the travel time of event picks."""
    p = _pick_distances(split, max_windows)
    p["scale"] = p.network.map(network_scales(split))
    return p[["window_id", "network", "scale", "station", "phase", "pick_type", "prob", "event_idx",
              "distance_km", "travel_time_s"]]


def _pick_distances(split, max_windows):
    ids = _sample_ids(split, max_windows)
    net = split.windows.set_index("window_id").network
    p = split.picks[split.picks.window_id.isin(ids)].copy()
    p["network"] = p.window_id.map(net)
    xy = _coords(split).reindex(pd.MultiIndex.from_arrays([p.network, p.station])).to_numpy()
    ev = split.events[split.events.window_id.isin(ids)]
    out = np.full(len(p), np.nan)
    tt = np.full(len(p), np.nan)
    for wid, rows in p.groupby("window_id").indices.items():
        e = ev[ev.window_id == wid]
        d = np.hypot(haversine_km(e.latitude.to_numpy()[:, None], e.longitude.to_numpy()[:, None],
                                  xy[rows, 0][None, :], xy[rows, 1][None, :]),
                     (e.depth.to_numpy() / 1e3)[:, None])                        # (E, n)
        own = p.event_idx.to_numpy()[rows]
        pos = {k: i for i, k in enumerate(e.event_idx)}
        idx = np.array([pos.get(k, -1) for k in own])
        out[rows] = np.where(idx >= 0, d[np.maximum(idx, 0), np.arange(len(rows))], d.min(axis=0))
        t0 = e.set_index("event_idx").t0_rel_s.reindex(own).to_numpy()      # NaN for noise (-1)
        tt[rows] = p.t_rel_s.to_numpy()[rows] - t0
    p["distance_km"], p["travel_time_s"] = out, tt
    return p


def network_scales(split, max_windows=50):
    """Scale of each network from the 90th percentile of the hypocentral distance of its real picks:
    local (< 150 km), regional (150-1500 km) or global (> 1500 km)."""
    p = _pick_distances(split, max_windows)
    p90 = p[p.pick_type == "real"].groupby("network").distance_km.quantile(0.9)
    return p90.map(lambda v: SCALES[int(np.searchsorted(SCALE_EDGES, v))])


def source_events(split):
    """One row per source earthquake: catalog location, depth, magnitude, farthest station,
    stations and gap in its first window, and the number of windows it appears in."""
    ev = split.events.merge(split.windows[["window_id", "network"]], on="window_id")
    uses = ev.groupby("src_event_id").size().rename("n_windows")
    first = ev.sort_values(["src_event_id", "is_edge"]).drop_duplicates("src_event_id")
    out = first.set_index("src_event_id").join(uses).reset_index()
    out["depth_km"] = out.depth / 1e3
    out["scale"] = out.network.map(network_scales(split))
    return out[["src_event_id", "network", "scale", "latitude", "longitude", "depth_km", "magnitude",
                "magnitude_type", "last_station_km", "n_stations", "gap_deg", "n_windows"]]


def event_pairs(split):
    """Every pair of earthquakes in the same window: epicentral distance and origin-time difference.

    Pairs close in both are the hardest to associate: their picks overlap in time at the same
    stations."""
    ev = split.events.merge(split.windows[["window_id", "network", "scenario"]], on="window_id")
    rows = []
    for wid, g in ev.groupby("window_id"):
        if len(g) < 2:
            continue
        la, lo, t = g.latitude.to_numpy(), g.longitude.to_numpy(), g.t0_rel_s.to_numpy()
        i, j = np.triu_indices(len(g), 1)
        rows.append(pd.DataFrame({"window_id": wid, "network": g.network.iloc[0], "scenario": g.scenario.iloc[0],
                                  "distance_km": haversine_km(la[i], lo[i], la[j], lo[j]),
                                  "dt_s": np.abs(t[i] - t[j])}))
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["window_id", "network", "scenario", "distance_km", "dt_s"])
    out["scale"] = out.network.map(network_scales(split))
    return out


def window_geometry(split, max_windows=300):
    """Per window: number of stations, median nearest-neighbour station spacing, aperture
    (largest inter-station distance), and median distance from the earthquakes to the stations
    that picked them."""
    ids = _sample_ids(split, max_windows)
    w = split.windows[split.windows.window_id.isin(ids)]
    ws = split.window_stations[split.window_stations.window_id.isin(ids)]
    real = split.picks[split.picks.window_id.isin(ids) & (split.picks.real == 1)]
    from scipy.spatial import cKDTree

    n_pick = real.groupby("window_id").station.nunique()
    rows = []
    for wid, g in ws.groupby("window_id"):
        la, lo = np.radians(g.latitude.to_numpy()), np.radians(g.longitude.to_numpy())
        xyz = np.c_[np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)]      # unit sphere
        chord, _ = cKDTree(xyz).query(xyz, k=2)
        nn_km = 2 * 6371.0 * np.arcsin(np.clip(chord[:, 1] / 2, 0, 1))
        # aperture: farthest station from the farthest station of an arbitrary one (two passes)
        a = np.argmax(haversine_km(g.latitude.iloc[0], g.longitude.iloc[0], g.latitude, g.longitude))
        aperture = float(np.max(haversine_km(g.latitude.iloc[a], g.longitude.iloc[a], g.latitude, g.longitude)))
        rows.append({"window_id": wid, "n_stations": len(g), "spacing_km": float(np.median(nn_km)),
                     "aperture_km": aperture, "n_picking_stations": int(n_pick.get(wid, 0))})
    out = pd.DataFrame(rows).merge(w[["window_id", "network", "scenario", "max_hyp_dist_km"]], on="window_id")
    out["scale"] = out.network.map(network_scales(split))
    return out
