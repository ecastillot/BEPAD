"""One row per pool network: size, geometry and seismicity, to choose the core networks of the leaderboard.

    python pipeline/01_pool/network_table.py <out.csv>

Columns: events, picks, stations, picks per event, S fraction, scale (local / regional / global, from
the 90th percentile of the hypocentral distance of the picks), aperture (largest distance between two
stations), station spacing (median distance to the nearest station), event depth and magnitude,
time span and events per year, and the UTDQuake catalog.
"""
import json
import sys

import numpy as np
import pandas as pd

from bepad.build.config import load_pool_config
from bepad.build.geo import haversine_km
from bepad.build.pool import list_networks, load_network, pool_dir


def scale(p90_km):
    return "local" if p90_km < 150 else "regional" if p90_km < 1500 else "global"


def geometry(st):
    lat, lon = st.latitude.to_numpy(), st.longitude.to_numpy()
    if len(st) > 3000:                                   # aperture / spacing on a sample of big networks
        k = np.random.default_rng(0).choice(len(st), 3000, replace=False)
        lat, lon = lat[k], lon[k]
    d = haversine_km(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    np.fill_diagonal(d, np.inf)
    return float(d[np.isfinite(d)].max()) if len(lat) > 1 else 0.0, float(np.median(d.min(axis=1)))


cfg = load_pool_config("configs/pool.yaml")
rows = []
for net in list_networks(cfg["data_root"]):
    ev, pk, st = load_network(cfg["data_root"], net)
    man = json.loads((pool_dir(cfg["data_root"]) / f"network={net}" / "manifest.json").read_text())
    p90 = float(pk.hyp_distance_km.quantile(0.9))
    aperture, spacing = geometry(st)
    years = max((ev.time.max() - ev.time.min()).days / 365.25, 1 / 365.25)
    rows.append({
        "network": net, "catalog": man.get("utdquake_network", {}).get("catalog"),
        "events": len(ev), "test_events": int((ev.split == "test").sum()), "picks": len(pk),
        "stations": len(st), "picks_per_event": round(len(pk) / max(len(ev), 1), 1),
        "s_fraction": round(float((pk.phase == "S").mean()), 3),
        "p90_hyp_distance_km": round(p90, 1), "scale": scale(p90),
        "aperture_km": round(aperture, 1), "station_spacing_km": round(spacing, 1),
        "median_depth_km": round(float(ev.depth.median()) / 1e3, 1),
        "median_magnitude": round(float(pd.to_numeric(ev.magnitude, errors="coerce").median()), 2),
        "years": round(years, 2), "events_per_year": round(len(ev) / years, 1),
    })
    print(net, rows[-1]["scale"], rows[-1]["stations"], flush=True)
out = pd.DataFrame(rows).sort_values(["scale", "aperture_km"])
out.to_csv(sys.argv[1], index=False)
print(out.to_string(index=False))
