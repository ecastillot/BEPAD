"""One window: real events on a shared timeline, plus generated picks and noise.

A window is a pure function of (pool, label model, window config, seed).

    1. events     n events of one split, all within +/- event_time_neighborhood_days
                  of an anchor event (so the station geometry existed at that time);
                  optionally one edge event starting before t = 0
    2. stations   every pool station that picked any event in that period
    3. timeline   length = length_factor x longest event duration; origins uniform in
                  the first (1 - tail_frac) of the window; the end is extended so every
                  event passes the pool rule inside the window (>= 4 P picks, >= 3 stations);
                  an edge event starts early enough before t = 0 that its late picks pass it too
    4. real       arrival = new origin + REAL travel time; picks outside the window are cut
    5. generated  round(ratio x real picks), ratio ~ U(generated_ratio): at stations that
                  did not pick that event, inside its band, between its first and last
                  real pick and where the gap rule allows (bepad.build.labels)
    6. noise      round(noise_ratio x real picks): 90% uniform in distance to a window
                  event, 10% on any station, uniform in time -- and never inside any
                  event's band (rejection sampling)
    7. labels     event_idx (-1 noise), pick_type, real (1/0), prob, sigma_s. No pick is ever
                  removed or merged: picks of two events close in time at one station are both
                  kept with their own event (a hard case for the associator, as in a swarm)
    8. check      every event has >= event_min_p real P picks, >= event_min_s real S picks and
                  >= event_min_stations stations INSIDE the window; otherwise the window is
                  regenerated from a seed derived from (seed, attempt)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .geo import azimuthal_gap_deg, haversine_km
from .labels import EventArrivals, LabelModel

NOISE = -1
PICK_COLUMNS = ["window_id", "pick_idx", "station", "phase", "t_rel_s", "time", "event_idx", "pick_type",
                "real", "prob", "sigma_s", "in_scorable_event", "src_event_id", "src_pick_id"]


@dataclass
class Window:
    window: dict               # one metadata row
    picks: pd.DataFrame        # one row per pick
    events: pd.DataFrame       # one row per event in the window
    stations: pd.DataFrame     # stations available in the window


class NetworkIndex:
    """In-memory, time-sorted view of one network of the pool + the label model."""

    def __init__(self, events, picks, stations, network, label_model: LabelModel):
        self.network = network
        self.model = label_model
        self.events = events.sort_values("time").reset_index(drop=True)
        self.ev_t = self.events["time"].to_numpy("datetime64[ns]").astype(np.int64) / 1e9
        self.stations = stations.set_index("station")
        mag = pd.to_numeric(self.events["magnitude"], errors="coerce")
        self.magnitude = mag.fillna(label_model.median_magnitude(network)).to_numpy(float)

        picks = picks.merge(self.events[["event_id", "time"]].rename(columns={"time": "event_time"}),
                            on="event_id", how="inner")
        picks = picks.sort_values("event_time").reset_index(drop=True)
        self.pk_ev_t = picks["event_time"].to_numpy("datetime64[ns]").astype(np.int64) / 1e9
        codes, self.station_names = pd.factorize(picks["station"], sort=True)
        self.pk_station = codes.astype(np.int32)           # integer codes: fast unique()
        self.picks = picks[["event_id", "station", "phase", "travel_time", "hyp_distance_km", "pick_id"]]
        self.pick_rows = picks.groupby("event_id").indices

    def neighborhood(self, t, days):
        if days is None:
            return 0, len(self.ev_t)
        return np.searchsorted(self.ev_t, [t - days * 86400, t + days * 86400])

    def active_stations(self, t, days):
        if days is None:
            return np.asarray(self.station_names, dtype=object)
        lo, hi = np.searchsorted(self.pk_ev_t, [t - days * 86400, t + days * 86400])
        present = np.bincount(self.pk_station[lo:hi], minlength=len(self.station_names)) > 0
        return np.asarray(self.station_names, dtype=object)[present]


# ----------------------------------------------------------------------
def _candidate_mask(events, split, cfg):
    m = (events["split"] == split).to_numpy() & (events["duration_s"] > 0).to_numpy()
    for col, key in (("gap_deg", "gap_range"), ("magnitude", "magnitude_range")):
        rng_ = cfg.get(key)
        if rng_ is not None:
            v = pd.to_numeric(events[col], errors="coerce").to_numpy()
            m &= (v >= rng_[0]) & (v <= rng_[1])
    return m


def _sample_events(idx, split, cfg, rng):
    """Anchor + (n - 1) neighbours (+ optional edge event) from the same split."""
    cand_pos = np.flatnonzero(_candidate_mask(idx.events, split, cfg))
    if len(cand_pos) == 0:
        return None
    lo_n, hi_n = cfg["n_events"]
    n = int(rng.integers(lo_n, hi_n + 1))
    want_edge = rng.random() < cfg["edge_event_prob"]
    need = n + int(want_edge)
    anchor = int(rng.choice(cand_pos))
    days = cfg["event_time_neighborhood_days"]
    while True:
        lo, hi = idx.neighborhood(idx.ev_t[anchor], days)
        pool = cand_pos[(cand_pos >= lo) & (cand_pos < hi) & (cand_pos != anchor)]
        if len(pool) >= need - 1 or days is None:
            break
        days = days * 2 if days < 20 * 365 else None   # widen, then give up on locality
    others = rng.choice(pool, size=min(need - 1, len(pool)), replace=False)
    chosen = np.concatenate([[anchor], others]).astype(int)
    edge = chosen[n] if (want_edge and len(chosen) > n) else None
    return chosen[:n], edge, anchor, days


def _overlap_stats(first, last):
    n = len(first)
    pairs = sum(1 for i in range(n) for j in range(i + 1, n) if first[i] <= last[j] and first[j] <= last[i])
    ev = sorted([(f, 1) for f in first] + [(l, -1) for l in last], key=lambda x: (x[0], -x[1]))
    cur = best = 0
    for _, d in ev:
        cur += d
        best = max(best, cur)
    return pairs, best


def _rule_time(p, cfg):
    """Travel time after which an event's real picks pass the rule, or None if they never do."""
    tp = np.sort(p.loc[p.phase == "P", "travel_time"].to_numpy())
    ts = np.sort(p.loc[p.phase == "S", "travel_time"].to_numpy())
    first = np.sort(p.groupby("station")["travel_time"].min().to_numpy())
    kp, ks, kst = cfg["event_min_p"], cfg["event_min_s"], cfg["event_min_stations"]
    if len(tp) < kp or len(ts) < ks or len(first) < kst:
        return None
    return max(tp[kp - 1] if kp else 0.0, ts[ks - 1] if ks else 0.0, first[kst - 1] if kst else 0.0)


def _edge_shift(p, cfg):
    """Largest origin offset before t = 0 that still leaves the rule satisfied by the late picks."""
    tp = np.sort(p.loc[p.phase == "P", "travel_time"].to_numpy())[::-1]
    ts = np.sort(p.loc[p.phase == "S", "travel_time"].to_numpy())[::-1]
    last = np.sort(p.groupby("station")["travel_time"].max().to_numpy())[::-1]
    kp, ks, kst = cfg["event_min_p"], cfg["event_min_s"], cfg["event_min_stations"]
    if len(tp) < kp or len(ts) < ks or len(last) < kst:
        return None
    return min(tp[kp - 1] if kp else np.inf, ts[ks - 1] if ks else np.inf, last[kst - 1] if kst else np.inf)


def _passes_rule(picks, cfg):
    r = picks[picks.real == 1]
    g = r.groupby("event_idx")
    n_p = (r.phase == "P").groupby(r.event_idx).sum()
    n_s = (r.phase == "S").groupby(r.event_idx).sum()
    return bool(((n_p >= cfg["event_min_p"]) & (n_s >= cfg["event_min_s"])
                 & (g.station.nunique() >= cfg["event_min_stations"])).all())


def _truncated_normal(rng, k, size):
    z = rng.standard_normal(size)
    bad = np.abs(z) > k
    while bad.any():
        z[bad] = rng.standard_normal(bad.sum())
        bad = np.abs(z) > k
    return z


# ----------------------------------------------------------------------
def generate_window(idx: NetworkIndex, split, cfg, seed, window_id, scenario="custom", max_attempts=20):
    """One window. Deterministic in ``seed``; retried (derived seeds) until every event passes the rule."""
    from .geo import stable_seed

    for attempt in range(max_attempts):
        s = seed if attempt == 0 else stable_seed(seed, "retry", attempt)
        w = _generate_once(idx, split, cfg, s, window_id, scenario)
        if w is None:
            return None
        if _passes_rule(w.picks, cfg):
            w.window["seed"], w.window["attempts"] = int(seed), attempt + 1
            return w
    return None


def _generate_once(idx: NetworkIndex, split, cfg, seed, window_id, scenario="custom"):
    rng = np.random.default_rng(seed)
    model = idx.model
    sampled = _sample_events(idx, split, cfg, rng)
    if sampled is None:
        return None
    main, edge, anchor, days_used = sampled

    # --- stations ------------------------------------------------------------
    stations = idx.active_stations(idx.ev_t[anchor], days_used)
    if cfg["station_keep_frac"] < 1.0:
        k = max(3, int(round(cfg["station_keep_frac"] * len(stations))))
        stations = np.sort(rng.choice(stations, size=min(k, len(stations)), replace=False))
    st = idx.stations.loc[stations]
    st_lat, st_lon = st["latitude"].to_numpy(), st["longitude"].to_numpy()
    station_set = set(stations)

    # --- events: real picks on window stations, arrivals, distances ------------
    rows = list(main) + ([edge] if edge is not None else [])
    E = len(rows)
    ev_df = idx.events.loc[rows]
    R = np.stack([np.hypot(haversine_km(e.latitude, e.longitude, st_lat, st_lon), e.depth / 1e3)
                  for e in ev_df.itertuples()])                        # (E, S) hypocentral distance
    real, arrivals, pool_have, dur, nth = [], [], [], [], []
    for r in rows:
        eid = idx.events.at[r, "event_id"]
        p = idx.picks.iloc[idx.pick_rows[eid]]
        arrivals.append(EventArrivals(model, idx.network, p["hyp_distance_km"], p["travel_time"], p["phase"],
                                      idx.events.at[r, "last_station_km"]))
        pool_have.append(set(zip(p["phase"], p["station"])))     # every real pick of the event
        p = p[p["station"].isin(station_set)]
        real.append(p)
        dur.append(float(p["travel_time"].max()) if len(p) else 0.0)
        nth.append(_rule_time(p, cfg))
    if any(v is None for v in nth[:len(main)]):
        return None                  # an event cannot pass the rule on these stations (station subsampling)
    edge_shift = _edge_shift(real[-1], cfg) if edge is not None else None
    if edge is not None and edge_shift is None:              # drop an edge event that cannot pass
        rows, real, arrivals, pool_have, dur, nth = rows[:-1], real[:-1], arrivals[:-1], pool_have[:-1], dur[:-1], nth[:-1]
        edge = None
        E = len(rows)
        R = R[:E]
        ev_df = ev_df.iloc[:E]
    dur, nth = np.array(dur), np.array(nth[:len(main)], float)
    n_main = len(main)

    # --- timeline ---------------------------------------------------------------
    length = cfg["length_factor"] * float(dur[:n_main].max()) if cfg["length_s"] == "auto" else float(cfg["length_s"])
    t0 = np.empty(n_main)
    t0[rng.permutation(n_main)] = np.sort(rng.uniform(0, (1 - cfg["tail_frac"]) * length, n_main))
    end = max(length, float(np.max(t0 + nth[:n_main])))
    if edge is not None:
        t0 = np.append(t0, -rng.uniform(0, edge_shift))
    t_ref = idx.events.at[anchor, "time"] - pd.to_timedelta(t0[rows.index(anchor)], unit="s")
    ev_order = np.argsort(t0, kind="stable")
    e_idx = np.empty(E, int)
    e_idx[ev_order] = np.arange(E)                                      # event_idx = rank of origin time
    mag = idx.magnitude[rows]

    # predicted arrivals at every window station (E, S) and timing sigma
    MU = {ph: np.stack([arrivals[j].mu(ph, R[j]) for j in range(E)]) for ph in ("P", "S")}
    SIG = model.sigma(R)
    k_band = model.band_k

    # --- real picks ---------------------------------------------------------------
    pos = {s: i for i, s in enumerate(stations)}
    parts, n_trunc = [], 0
    for j, p in enumerate(real):
        t = t0[j] + p["travel_time"].to_numpy()
        inside = (t >= 0) & (t <= end)
        n_trunc += int((~inside).sum())
        sidx = p["station"].map(pos).to_numpy()[inside]
        r_ = R[j, sidx]
        parts.append(pd.DataFrame({
            "station": p["station"].to_numpy()[inside], "phase": p["phase"].to_numpy()[inside],
            "t_rel_s": t[inside], "event_idx": e_idx[j], "pick_type": "real", "real": 1,
            "prob": model.prob_real(mag[j], r_), "sigma_s": model.sigma(r_),
            "src_event_id": idx.events.at[rows[j], "event_id"], "src_pick_id": p["pick_id"].to_numpy()[inside],
        }))
    picks = pd.concat(parts, ignore_index=True)
    n_real = len(picks)

    # --- generated picks --------------------------------------------------------------
    lo_g, hi_g = cfg["generated_ratio"] if isinstance(cfg["generated_ratio"], (list, tuple)) else \
        (cfg["generated_ratio"], cfg["generated_ratio"])
    gen_ratio = float(rng.uniform(lo_g, hi_g)) if hi_g > lo_g else float(lo_g)
    n_gen_target = int(round(gen_ratio * n_real))
    gen = []
    if n_gen_target:
        slots = []                                     # (event j, phase, station index)
        for j in range(E):
            for ph in ("P", "S"):
                taken = np.isin(stations, [s_ for p_, s_ in pool_have[j] if p_ == ph])
                ok = arrivals[j].can_generate(ph, R[j]) & ~taken
                slots.extend((j, ph, si) for si in np.flatnonzero(ok))
        if slots:
            w = np.array([len(real[j]) + 1.0 for j, _, _ in slots])
            take = rng.choice(len(slots), size=min(n_gen_target, len(slots)), replace=False, p=w / w.sum())
            z = _truncated_normal(rng, k_band, len(take))
            for (j, ph, si), zz in zip((slots[i] for i in take), z):
                t = t0[j] + MU[ph][j, si] + zz * SIG[j, si]
                if 0 <= t <= end:
                    gen.append({"station": stations[si], "phase": ph, "t_rel_s": t, "event_idx": e_idx[j],
                                "pick_type": "generated", "real": 0,
                                "prob": float(model.prob_generated(mag[j], R[j, si], zz)),
                                "sigma_s": float(SIG[j, si]), "src_event_id": idx.events.at[rows[j], "event_id"],
                                "src_pick_id": None})
    if gen:
        picks = pd.concat([picks, pd.DataFrame(gen)], ignore_index=True)

    # --- noise (never inside a band) ----------------------------------------------------
    n_noise_target = int(round(cfg["noise_ratio"] * n_real))
    noise_st, noise_t, tries = [], [], 0
    r_max = 1.1 * float(np.nanmax(R[:, [pos[s] for s in picks.loc[picks.real == 1, "station"].unique()]])) \
        if n_real else float(R.max())
    while len(noise_t) < n_noise_target and tries < 30:
        m = 2 * (n_noise_target - len(noise_t)) + 8
        anyst = rng.random(m) < cfg["noise_any_station_frac"]
        j = rng.integers(0, n_main, m)
        target = rng.uniform(0, r_max, m)
        si = np.where(anyst, rng.integers(0, len(stations), m),
                      np.abs(R[j] - target[:, None]).argmin(axis=1))
        t = rng.uniform(0, end, m)
        dt_ = t[:, None] - t0[None, :]                                  # (m, E)
        inband = np.zeros(m, bool)
        for ph in ("P", "S"):
            inband |= (np.abs(dt_ - MU[ph][:, si].T) <= k_band * SIG[:, si].T).any(axis=1)
        keep = np.flatnonzero(~inband)[: n_noise_target - len(noise_t)]
        noise_st.extend(si[keep])
        noise_t.extend(t[keep])
        tries += 1
    if noise_t:
        n_ = len(noise_t)
        phase_p = (picks["phase"] == "P").mean() if len(picks) else 0.5
        picks = pd.concat([picks, pd.DataFrame({
            "station": stations[np.array(noise_st)], "phase": np.where(rng.random(n_) < phase_p, "P", "S"),
            "t_rel_s": np.array(noise_t), "event_idx": NOISE, "pick_type": "noise", "real": 0, "prob": 0.0,
            "sigma_s": np.nan, "src_event_id": None, "src_pick_id": None})], ignore_index=True)

    # --- ordering, absolute time -------------------------------------------------------------
    picks = picks.sort_values("t_rel_s", kind="stable").reset_index(drop=True)
    picks.insert(0, "pick_idx", np.arange(len(picks)))
    picks.insert(0, "window_id", window_id)
    picks["time"] = t_ref + pd.to_timedelta(picks["t_rel_s"], unit="s")

    # --- events table -----------------------------------------------------------------------
    ev_rows = []
    for k, j in enumerate(ev_order):
        e = idx.events.loc[rows[j]]
        pe = picks[picks["event_idx"] == k]
        pr = pe[pe["real"] == 1]
        sta = pr["station"].unique()
        s_ = idx.stations.loc[sta]
        ev_rows.append({
            "window_id": window_id, "event_idx": k, "t0_rel_s": t0[j],
            "origin_time": t_ref + pd.to_timedelta(t0[j], unit="s"),
            "latitude": e["latitude"], "longitude": e["longitude"], "depth": e["depth"],
            "magnitude": e["magnitude"], "magnitude_type": e["magnitude_type"],
            "n_picks": len(pe), "n_real_picks": len(pr), "n_generated_picks": int((pe["pick_type"] == "generated").sum()),
            "n_p": int((pr["phase"] == "P").sum()), "n_s": int((pr["phase"] == "S").sum()), "n_stations": len(sta),
            "gap_deg": azimuthal_gap_deg(e["latitude"], e["longitude"], s_["latitude"].to_numpy(), s_["longitude"].to_numpy()),
            "last_station_km": e["last_station_km"],
            "first_pick_s": pe["t_rel_s"].min() if len(pe) else np.nan,
            "last_pick_s": pe["t_rel_s"].max() if len(pe) else np.nan,
            "is_edge": rows[j] == edge,
            "scorable": (int((pr["phase"] == "P").sum()) >= cfg["event_min_p"]
                         and int((pr["phase"] == "S").sum()) >= cfg["event_min_s"]
                         and len(sta) >= cfg["event_min_stations"]),
            "src_event_id": e["event_id"], "src_origin_time": e["time"],
        })
    events = pd.DataFrame(ev_rows)
    picks["in_scorable_event"] = picks["event_idx"].isin(set(events.loc[events["scorable"], "event_idx"]))

    # --- window metadata -------------------------------------------------------------------------
    sc = events[events["scorable"]]
    n_type = picks["pick_type"].value_counts()
    seen = events.dropna(subset=["first_pick_s"])
    pairs, conc = _overlap_stats(seen["first_pick_s"].to_numpy(), seen["last_pick_s"].to_numpy())
    t0s = np.sort(events["t0_rel_s"].to_numpy())
    real_pk = picks[picks["real"] == 1]
    src_t = pd.to_datetime(events["src_origin_time"])
    window = {
        "window_id": window_id, "network": idx.network, "split": split, "scenario": scenario, "seed": int(seed),
        "t_start": t_ref, "length_s": end,
        "n_stations": len(station_set), "n_active_stations": int(real_pk["station"].nunique()),
        "n_events": len(events), "n_scorable_events": len(sc), "n_edge_events": int(events["is_edge"].sum()),
        "n_picks": len(picks), "n_real_picks": int(n_type.get("real", 0)),
        "n_generated_picks": int(n_type.get("generated", 0)), "n_noise_picks": int(n_type.get("noise", 0)),
        "noise_ratio_target": cfg["noise_ratio"], "generated_ratio_target": gen_ratio,
        "noise_ratio": n_type.get("noise", 0) / max(n_type.get("real", 0), 1),
        "noise_shortfall": max(n_noise_target - len(noise_t), 0),
        "n_truncated_picks": n_trunc,
        "min_origin_sep_s": float(np.diff(t0s).min()) if len(t0s) > 1 else np.nan,
        "n_overlapping_pairs": pairs, "max_concurrent_events": conc,
        "mag_min": sc["magnitude"].min(), "mag_max": sc["magnitude"].max(),
        "depth_min_km": sc["depth"].min() / 1e3, "depth_max_km": sc["depth"].max() / 1e3,
        "gap_min_deg": sc["gap_deg"].min(), "gap_max_deg": sc["gap_deg"].max(),
        "max_hyp_dist_km": float(np.nanmax(R[:, [pos[s] for s in real_pk["station"].unique()]])) if len(real_pk) else np.nan,
        "src_time_span_days": (src_t.max() - src_t.min()).total_seconds() / 86400,
        "anchor_event_id": idx.events.at[anchor, "event_id"],
    }
    stations_df = pd.DataFrame({"window_id": window_id, "station": sorted(station_set)})
    return Window(window=window, picks=picks[PICK_COLUMNS], events=events, stations=stations_df)


class WindowGenerator:
    """On-the-fly windows: ``WindowGenerator(data_root, "tx", "train", {...}).sample(seed)``."""

    def __init__(self, data_root, network, split, window_cfg=None, scenario="custom"):
        from pathlib import Path

        from .config import WINDOW_DEFAULTS
        from .pool import load_network, pool_dir

        self.cfg = {**WINDOW_DEFAULTS, **(window_cfg or {})}
        self.split, self.scenario = split, scenario
        model = LabelModel.load(pool_dir(data_root) / "label_model.json")
        self.index = NetworkIndex(*load_network(data_root, network), network=network, label_model=model)
        self._root = Path(data_root)

    def sample(self, seed, window_id=None):
        window_id = window_id or f"{self.index.network}.{self.split}.{self.scenario}.s{seed}"
        return generate_window(self.index, self.split, self.cfg, seed, window_id, self.scenario)
