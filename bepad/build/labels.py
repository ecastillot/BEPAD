"""Label model: predicted arrivals, timing uncertainty and pick probabilities.

Three kinds of picks in a window::

    real       UTDQuake pick                       prob = 0.5 + 0.5 * q(M, r) ** gamma      (>= 0.5)
    generated  artificial pick inside a band       prob = 0.5 + 0.5 * (q(M, r) * g(z)) ** gamma
    noise      never inside any band               prob = 0

    q(M, r)  detectability of magnitude M at hypocentral distance r: sigmoid((M - B(r)) / w),
             B smooth and increasing in log10 r. ONE curve for all networks.
    sigma(r) timing uncertainty of a predicted arrival, non-decreasing with r. ONE curve.
    g(z)     exp(-z^2 / 2), z = (t - predicted arrival) / sigma(r)
    band     predicted arrival +/- band_k * sigma(r)

Predicted arrival of an event at distance r (``EventArrivals.mu``)::

    - between its first and last real pick of that phase: monotone interpolation of its own picks
    - outside that range: the network's travel-time curve, shifted to join the event's picks
      (network S curve = network P curve x network S/P ratio, clipped to 1.5-2.0; a network
      without enough paired P/S picks uses the S/P ratio of all networks)
    - S for an event without S picks: network S/P ratio x the event's own P prediction

Generated picks are allowed only between the event's first and last real pick
(never beyond its last station: the magnitude limit), and only where its
neighbouring real picks are at most ``max_gap_frac * r`` apart. Noise is
rejected inside the band of every event, at every distance.

``fit_label_model`` fits everything from the pool; the result is
``data/pool/label_model.json`` and is copied into every release.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit

from .geo import haversine_km

KNOTS = np.arange(0.0, 4.26, 0.25)          # log10 r [km] for B(r)
SIGMA_BINS = np.logspace(0, 4.1, 30)        # km
CURVE_BINS = np.logspace(0, 4.3, 45)        # km, network travel-time curves and S/P ratio


# ----------------------------------------------------------------------
# The model
# ----------------------------------------------------------------------
class LabelModel:
    """Evaluate the fitted label model (loaded from label_model.json)."""

    def __init__(self, params: dict):
        self.params = params
        q = params["q"]
        self._knots = np.asarray(q["knots_log10_km"], float)
        self._B = np.asarray(q["B"], float)
        self._w = float(q["w"])
        s = params["sigma"]
        self._sig_r = np.log(np.asarray(s["r_km"], float))
        self._sig_s = np.log(np.asarray(s["sigma_s"], float))
        self.gamma = float(params["gamma"])
        self.band_k = float(params["band_k"])
        self.max_gap_frac = float(params["max_gap_frac"])
        self.networks = params["networks"]

    # --- global -----------------------------------------------------------
    def B(self, r):
        return np.interp(np.log10(np.clip(r, 1.0, 2e4)), self._knots, self._B)

    def q(self, M, r):
        return expit((np.asarray(M, float) - self.B(r)) / self._w)

    def sigma(self, r):
        return np.exp(np.interp(np.log(np.clip(r, 1e-3, None)), self._sig_r, self._sig_s))

    def prob_real(self, M, r):
        return 0.5 + 0.5 * self.q(M, r) ** self.gamma

    def prob_generated(self, M, r, z):
        return 0.5 + 0.5 * (self.q(M, r) * np.exp(-0.5 * np.asarray(z) ** 2)) ** self.gamma

    # --- per network --------------------------------------------------------
    def _net(self, network):
        if network not in self.networks:
            raise KeyError(f"label model has no curves for network {network!r}; run `bepad pool fit-labels`")
        return self.networks[network]

    #: smallest slowness [s/km] allowed when extrapolating the P curve (1 / 25 km/s)
    MIN_SLOWNESS = 0.04
    #: physical range of the S/P travel-time ratio
    SP_RANGE = (1.5, 2.0)

    def tt_curve(self, network, phase, r):
        """Network travel-time curve.

        P: median of the pool P picks vs hypocentral distance; beyond the last
        node it continues with the mean slope of its last three nodes (never
        flatter than MIN_SLOWNESS). S: the P curve x the network S/P ratio
        (from stations that picked both), which stays well behaved where S
        picks are sparse (e.g. teleseismic distances).
        """
        r = np.asarray(r, float)
        if phase == "S":
            return self.tt_curve(network, "P", r) * self.sp_ratio(network, r)
        c = self._net(network)["tt"]["P"]
        x, y = np.asarray(c["r_km"], float), np.asarray(c["tt_s"], float)
        out = np.interp(r, x, y)
        beyond = r > x[-1]
        if not beyond.any():
            return out
        k = min(3, len(x) - 1)
        slope = (y[-1] - y[-1 - k]) / max(x[-1] - x[-1 - k], 1e-6) if k else self.MIN_SLOWNESS * 4
        return np.where(beyond, y[-1] + max(slope, self.MIN_SLOWNESS) * (r - x[-1]), out)

    def sp_ratio(self, network, r):
        c = self._net(network)["sp_ratio"] or self.params["sp_ratio"]   # too few P/S pairs: all networks' curve
        return np.clip(np.interp(r, c["r_km"], c["ratio"]), *self.SP_RANGE)

    def median_magnitude(self, network):
        return float(self._net(network)["median_magnitude"])

    # --- io -----------------------------------------------------------------
    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()))

    def save(self, path):
        Path(path).write_text(json.dumps(self.params, indent=2))


class EventArrivals:
    """Predicted arrivals of one event, from its own real picks (see module doc)."""

    def __init__(self, model: LabelModel, network, r_km, tt_s, phase, last_station_km):
        self.m, self.network, self.last = model, network, float(last_station_km)
        self.own = {}
        for ph in ("P", "S"):
            sel = np.asarray(phase) == ph
            r, t = np.asarray(r_km, float)[sel], np.asarray(tt_s, float)[sel]
            o = np.argsort(r)
            self.own[ph] = (r[o], np.maximum.accumulate(t[o]) if len(t) else t)

    def _from_own(self, ph, r):
        rr, tt = self.own[ph]
        net = self.m.tt_curve(self.network, ph, r)
        if len(rr) == 0:
            return None
        if len(rr) == 1:
            return net + (tt[0] - self.m.tt_curve(self.network, ph, rr[0]))
        inside = np.interp(r, rr, tt)
        lo = net + (tt[0] - self.m.tt_curve(self.network, ph, rr[0]))
        hi = net + (tt[-1] - self.m.tt_curve(self.network, ph, rr[-1]))
        return np.where(r < rr[0], lo, np.where(r > rr[-1], hi, inside))

    def mu(self, phase, r):
        """Predicted travel time [s] at hypocentral distance r [km]."""
        r = np.asarray(r, float)
        out = self._from_own(phase, r) if len(self.own[phase][0]) >= 2 or phase == "P" else None
        if out is None and phase == "S" and len(self.own["P"][0]):
            out = self._from_own("P", r) * self.m.sp_ratio(self.network, r)
        if out is None:
            out = self.m.tt_curve(self.network, phase, r)
        return out

    def can_generate(self, phase, r):
        """Where a generated pick of this phase is allowed (range + gap rule)."""
        r = np.asarray(r, float)
        rr = self.own[phase][0] if len(self.own[phase][0]) >= 2 else self.own["P"][0]
        if len(rr) < 2:
            return np.zeros(r.shape, bool)
        j = np.clip(np.searchsorted(rr, r), 1, len(rr) - 1)
        gap = rr[j] - rr[j - 1]
        return (r >= rr[0]) & (r <= min(rr[-1], self.last)) & (gap <= self.m.max_gap_frac * np.maximum(r, 1e-6))


# ----------------------------------------------------------------------
# Fitting
# ----------------------------------------------------------------------
def _robust_sigma(x):
    return 1.4826 * np.median(np.abs(x - np.median(x)))


def _pava(y, w):
    """Non-decreasing (isotonic) regression, pool-adjacent-violators."""
    blocks = [[yi, wi, 1] for yi, wi in zip(y, w)]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] > blocks[i + 1][0]:
            a, b = blocks[i], blocks[i + 1]
            ws = a[1] + b[1]
            blocks[i] = [(a[0] * a[1] + b[0] * b[1]) / ws, ws, a[2] + b[2]]
            del blocks[i + 1]
            i = max(i - 1, 0)
        else:
            i += 1
    return np.concatenate([[v] * n for v, _, n in blocks])


def detection_pairs(ev, pk, st, active_days, n_events, max_pairs, rng):
    """(event, available station) pairs: hypocentral distance, magnitude, picked?"""
    ev = ev.dropna(subset=["magnitude"]).reset_index(drop=True)
    if ev.empty:
        return pd.DataFrame(columns=["r_km", "M", "picked"])
    st = st.set_index("station")
    t_ev = ev["time"].to_numpy("datetime64[s]").astype(np.int64)
    pt = pk[["event_id", "station"]].merge(ev[["event_id", "time"]], on="event_id")
    pt = pt.assign(t=pt["time"].to_numpy("datetime64[s]").astype(np.int64)).sort_values("t")
    ts, ss = pt["t"].to_numpy(), pt["station"].to_numpy()
    picked = pk.groupby("event_id")["station"].apply(set).to_dict()
    rows = []
    for i in rng.choice(len(ev), size=min(n_events, len(ev)), replace=False):
        e = ev.iloc[i]
        lo, hi = np.searchsorted(ts, [t_ev[i] - active_days * 86400, t_ev[i] + active_days * 86400])
        avail = np.unique(ss[lo:hi])
        s = st.loc[avail]
        r = np.hypot(haversine_km(e["latitude"], e["longitude"], s["latitude"], s["longitude"]), e["depth"] / 1e3)
        rows.append(pd.DataFrame({"r_km": r, "M": e["magnitude"],
                                  "picked": np.isin(avail, list(picked.get(e["event_id"], ())))}))
    d = pd.concat(rows, ignore_index=True)
    return d.sample(max_pairs, random_state=0) if len(d) > max_pairs else d


def fit_q(det, smooth=30.0):
    """Global detectability: every network weighs the same (weights 1/len per network)."""
    logr = np.log10(np.clip(det["r_km"].to_numpy(float), 1, 2e4))
    M, y, wts = det["M"].to_numpy(float), det["picked"].to_numpy(float), det["w"].to_numpy(float)

    def B_of(p):
        steps = np.log1p(np.exp(p[1:len(KNOTS)]))
        return np.interp(logr, KNOTS, p[0] + np.concatenate([[0.0], np.cumsum(steps)])), steps

    def nll(p):
        B, steps = B_of(p)
        qv = np.clip(expit((M - B) / np.exp(p[-1])), 1e-9, 1 - 1e-9)
        return (-np.sum(wts * (y * np.log(qv) + (1 - y) * np.log(1 - qv))) / wts.sum()
                + smooth * np.sum(np.diff(steps) ** 2) / len(det) * 1e3)

    p0 = np.concatenate([[-1.0], np.full(len(KNOTS) - 1, 0.15), [np.log(0.5)]])
    p = minimize(nll, p0, method="L-BFGS-B").x
    steps = np.log1p(np.exp(p[1:len(KNOTS)]))
    return {"knots_log10_km": KNOTS.round(4).tolist(),
            "B": (p[0] + np.concatenate([[0.0], np.cumsum(steps)])).round(4).tolist(),
            "w": round(float(np.exp(p[-1])), 4)}


def loo_residuals(pk):
    """Predict each interior pick from its two neighbours (same event + phase)."""
    d = pk.sort_values(["event_id", "phase", "hyp_distance_km"])
    key = (d["event_id"] + "|" + d["phase"]).to_numpy()
    r, t = d["hyp_distance_km"].to_numpy(float), d["travel_time"].to_numpy(float)
    same_prev = np.r_[False, key[1:] == key[:-1]]
    same_next = np.r_[key[:-1] == key[1:], False]
    r0, t0, r1, t1 = np.roll(r, 1), np.roll(t, 1), np.roll(r, -1), np.roll(t, -1)
    ok = same_prev & same_next & (r1 - r0 > 0)
    pred = t0 + (t1 - t0) * (r - r0) / np.where(r1 - r0 > 0, r1 - r0, 1)
    return pd.DataFrame({"r_km": r[ok], "res": (t - pred)[ok]})


def fit_sigma(res, floor):
    """Per bin: robust sigma per network, averaged in log (networks weighted equally);
    then non-decreasing and lightly smoothed."""
    rows = []
    for k in range(1, len(SIGMA_BINS)):
        s = res[(res.r_km >= SIGMA_BINS[k - 1]) & (res.r_km < SIGMA_BINS[k])]
        per = [_robust_sigma(g.res.to_numpy()) for _, g in s.groupby("network") if len(g) >= 50]
        if per:
            rows.append((np.sqrt(SIGMA_BINS[k - 1] * SIGMA_BINS[k]),
                         np.exp(np.mean(np.log(np.maximum(per, 1e-3)))), len(per)))
    r_nodes, sig, w = map(np.array, zip(*rows))
    logs = _pava(np.log(sig), w)
    logs = np.convolve(np.pad(logs, 1, mode="edge"), np.ones(3) / 3, mode="valid")
    sig = np.maximum(np.exp(np.maximum.accumulate(logs)), floor)
    return {"r_km": r_nodes.round(3).tolist(), "sigma_s": sig.round(4).tolist()}


#: Paired P/S picks per network in the S/P curve of all networks.
SP_PAIRS_PER_NETWORK = 20_000


def network_curves(ev, pk):
    """Median travel time per phase vs hypocentral distance, and the S/P ratio."""
    idx = np.digitize(pk["hyp_distance_km"], CURVE_BINS)
    tt = {}
    for ph in ("P", "S"):
        g = pk[pk.phase == ph].groupby(idx[pk.phase == ph]).agg(
            r=("hyp_distance_km", "median"), t=("travel_time", "median"), n=("travel_time", "size"))
        g = g[g.n >= 20]
        r = np.r_[0.0, g.r.to_numpy()]
        t = np.maximum.accumulate(np.r_[0.0, g.t.to_numpy()])
        tt[ph] = {"r_km": r.round(3).tolist(), "tt_s": t.round(4).tolist()}
    p = pk[pk.phase == "P"][["event_id", "station", "hyp_distance_km", "travel_time"]]
    s = pk[pk.phase == "S"][["event_id", "station", "travel_time"]]
    m = p.merge(s, on=["event_id", "station"], suffixes=("_p", "_s"))
    m = m[m.travel_time_p > 0]
    m = m.assign(ratio=m.travel_time_s / m.travel_time_p)
    mag = pd.to_numeric(ev["magnitude"], errors="coerce").median()
    return {"tt": tt, "sp_ratio": sp_curve(m), "median_magnitude": float(mag) if mag == mag else 2.0}, \
        m[["hyp_distance_km", "ratio"]]


def sp_curve(pairs):
    """Median S/P travel-time ratio per distance bin (bins with >= 30 pairs); None if no bin has enough."""
    g = pairs.groupby(np.digitize(pairs.hyp_distance_km, CURVE_BINS)).agg(
        r=("hyp_distance_km", "median"), ratio=("ratio", "median"), n=("ratio", "size"))
    g = g[g.n >= 30]
    return {"r_km": g.r.round(3).tolist(), "ratio": g.ratio.round(4).tolist()} if len(g) else None


def fit_label_model(data_root, networks, cfg, previous=None, refit_global=True, seed=0):
    """Fit (or extend) the label model from the pool.

    ``refit_global=False`` keeps q(M, r) and sigma(r) of ``previous`` and only
    adds per-network curves -- used when a network is added to an existing release.
    """
    from .pool import load_network

    rng = np.random.default_rng(seed)
    params = dict(previous or {})
    params.setdefault("networks", {})
    det, res, sp_pairs = [], [], []
    for n in networks:
        ev, pk, st = load_network(data_root, n)
        params["networks"][n], pairs = network_curves(ev, pk)
        if refit_global or not previous:
            k = min(len(pairs), SP_PAIRS_PER_NETWORK)          # every network weighs about the same
            sp_pairs.append(pairs.iloc[rng.choice(len(pairs), k, replace=False)] if k else pairs)
            pk_m = pk.merge(ev[["event_id", "magnitude"]], on="event_id")
            d = detection_pairs(ev, pk_m, st, cfg["active_days"], cfg["events_per_network"],
                                cfg.get("pairs_per_network", 200_000), rng)
            det.append(d.assign(network=n, w=1.0 / max(len(d), 1)))
            res.append(loo_residuals(pk).assign(network=n))
        print(f"[labels] {n}: curves done")
    if refit_global or not previous:
        params["q"] = fit_q(pd.concat(det, ignore_index=True))
        params["sigma"] = fit_sigma(pd.concat(res, ignore_index=True), cfg["sigma_floor_s"])
        params["sp_ratio"] = sp_curve(pd.concat(sp_pairs, ignore_index=True))
    params.update({"gamma": cfg["gamma"], "band_k": cfg["band_k"], "max_gap_frac": cfg["max_gap_frac"]})
    return LabelModel(params)
