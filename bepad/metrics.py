"""Association metrics (event level, pick level, split/merge, ARI).

Predictions are one row per pick: ``window_id, pick_idx, pred_event``
(``pred_event = -1`` for noise / unassociated). Picks missing from the
prediction table count as -1.

Event matching, per window: a contingency table of shared picks between
true events and predicted events is solved with the Hungarian algorithm; a
pair is a match when they share >= ``min_shared`` picks.

- Only ``scorable`` true events count for recall (FN).
- A predicted event counts as FP when it is unmatched, unless most of its
  picks belong to a non-scorable true event (e.g. an edge event with few
  visible picks) -- those are neither rewarded nor penalised.
- Picks of non-scorable events are left out of the pick-level metrics.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

NOISE = -1


def _ari(a, b):
    """Adjusted Rand index; noise picks are singletons on both sides."""
    a = np.asarray(a).copy()
    b = np.asarray(b).copy()
    n = len(a)
    if n < 2:
        return np.nan
    a[a == NOISE] = -np.arange(1, (a == NOISE).sum() + 1) - 10**6
    b[b == NOISE] = -np.arange(1, (b == NOISE).sum() + 1) - 10**6
    _, ai = np.unique(a, return_inverse=True)
    _, bi = np.unique(b, return_inverse=True)
    cont = np.zeros((ai.max() + 1, bi.max() + 1), dtype=np.int64)
    np.add.at(cont, (ai, bi), 1)
    comb = lambda x: x * (x - 1) / 2  # noqa: E731
    s_ij = comb(cont).sum()
    s_a = comb(cont.sum(1)).sum()
    s_b = comb(cont.sum(0)).sum()
    expected = s_a * s_b / comb(n)
    max_ = (s_a + s_b) / 2
    return 1.0 if max_ == expected else float((s_ij - expected) / (max_ - expected))


def _score_window(df, scorable, min_shared):
    true = df["event_idx"].to_numpy()
    pred = df["pred_event"].to_numpy()

    t_ids = np.unique(true[true != NOISE])
    p_ids = np.unique(pred[pred != NOISE])
    cont = np.zeros((len(t_ids), len(p_ids)), dtype=int)
    if len(t_ids) and len(p_ids):
        ti = np.searchsorted(t_ids, true)
        pi = np.searchsorted(p_ids, pred)
        m = (true != NOISE) & (pred != NOISE)
        np.add.at(cont, (ti[m], pi[m]), 1)

    match = {}  # true id -> pred id
    if cont.size:
        r, c = linear_sum_assignment(-cont)
        for i, j in zip(r, c):
            if cont[i, j] >= min_shared:
                match[t_ids[i]] = p_ids[j]
    pred_matched = set(match.values())

    is_sc = np.array([t in scorable for t in t_ids], dtype=bool)
    tp = sum(1 for t in match if t in scorable)
    fn = int(is_sc.sum()) - tp
    fp = 0
    for j, p in enumerate(p_ids):
        if p in pred_matched:
            continue
        col = cont[:, j]
        n_pred = int((pred == p).sum())
        owner = t_ids[col.argmax()] if col.size and col.max() > 0 else None
        if owner is not None and owner not in scorable and col.max() * 2 > n_pred:
            continue  # dominated by a non-scorable event
        fp += 1

    # split / merge, with the same min_shared support
    split = int(sum(((cont[i] >= min_shared).sum() > 1) for i in range(len(t_ids)) if is_sc[i]))
    merge = int(sum(((cont[:, j] >= min_shared).sum() > 1) for j in range(len(p_ids))))

    # pick level (picks of non-scorable events excluded)
    in_sc = np.isin(true, list(scorable))
    use = in_sc | (true == NOISE)
    expected_pred = np.array([match.get(t, -2) for t in true])
    correct = in_sc & (pred != NOISE) & (pred == expected_pred)
    assigned = use & (pred != NOISE)
    noise = true == NOISE

    return {
        "n_true_events": int(is_sc.sum()),
        "n_pred_events": len(p_ids),
        "event_tp": tp, "event_fp": fp, "event_fn": fn,
        "n_split": split, "n_merge": merge,
        "pick_correct": int(correct.sum()),
        "pick_assigned": int(assigned.sum()),
        "pick_true": int(in_sc.sum()),
        "noise_total": int(noise.sum()),
        "noise_rejected": int((noise & (pred == NOISE)).sum()),
        "ari": _ari(true[use], pred[use]),
        "_match": [(t, p) for t, p in match.items() if t in scorable],
    }


def score_windows(truth_picks, truth_events, pred, min_shared=3, windows=None):
    """Return (per_window, summary). ``windows`` (optional) adds grouping columns."""
    df = truth_picks[["window_id", "pick_idx", "event_idx"]].merge(
        pred[["window_id", "pick_idx", "pred_event"]], on=["window_id", "pick_idx"], how="left")
    df["pred_event"] = df["pred_event"].fillna(NOISE).astype(int)
    scorable = truth_events[truth_events["scorable"]].groupby("window_id")["event_idx"].apply(set).to_dict()

    rows, matches = [], []
    for wid, g in df.groupby("window_id", sort=False):
        r = _score_window(g, scorable.get(wid, set()), min_shared)
        matches += [(wid, int(t), int(p)) for t, p in r.pop("_match")]
        rows.append({"window_id": wid, **r})
    per_window = pd.DataFrame(rows)
    matches = pd.DataFrame(matches, columns=["window_id", "event_idx", "pred_event"])
    if windows is not None:
        per_window = per_window.merge(windows[["window_id", "network", "split", "scenario"]], on="window_id")
    return per_window, summarize(per_window), matches


# ----------------------------------------------------------------------
# Locations (optional: only for associators that also locate)
# ----------------------------------------------------------------------
LOCATION_COLUMNS = ("latitude", "longitude", "depth_km", "t0_rel_s")


def score_locations(matches, truth_events, locations):
    """One row per matched event: epicentral [km], depth [km] and origin-time [s] errors
    against the catalog (NaN where the associator gave no value)."""
    from .build.geo import haversine_km

    loc = locations.rename(columns={"event": "pred_event"})
    m = matches.merge(truth_events[["window_id", "event_idx", "latitude", "longitude", "depth", "t0_rel_s"]],
                      on=["window_id", "event_idx"])
    m = m.merge(loc, on=["window_id", "pred_event"], how="left", suffixes=("", "_pred"))
    for c in LOCATION_COLUMNS:
        col = c + "_pred" if c in ("latitude", "longitude", "t0_rel_s") else c
        if col not in m:
            m[col] = np.nan
    m["epi_err_km"] = haversine_km(m.latitude, m.longitude, m.latitude_pred, m.longitude_pred)
    m["depth_err_km"] = (m.depth_km - m.depth / 1e3).abs()
    m["t0_err_s"] = (m.t0_rel_s_pred - m.t0_rel_s).abs()
    return m[["window_id", "event_idx", "pred_event", "epi_err_km", "depth_err_km", "t0_err_s"]]


def summarize_locations(loc, by=None):
    """Median and 90th percentile of the errors, and the share of matched events that were located."""
    def agg(g):
        return pd.Series({
            "located_frac": g.epi_err_km.notna().mean() if len(g) else np.nan,
            "epi_median_km": g.epi_err_km.median(), "epi_p90_km": g.epi_err_km.quantile(0.9),
            "depth_median_km": g.depth_err_km.median(), "depth_p90_km": g.depth_err_km.quantile(0.9),
            "t0_median_s": g.t0_err_s.median(), "t0_p90_s": g.t0_err_s.quantile(0.9),
        })
    if not by:
        return agg(loc).to_frame().T
    return loc.groupby(by).apply(agg, include_groups=False).reset_index()


def _ratios(s):
    def div(a, b):
        return a / b if b else np.nan
    p = div(s["event_tp"], s["event_tp"] + s["event_fp"])
    r = div(s["event_tp"], s["event_tp"] + s["event_fn"])
    pp = div(s["pick_correct"], s["pick_assigned"])
    pr = div(s["pick_correct"], s["pick_true"])
    return pd.Series({
        "n_windows": s["n_windows"],
        "event_precision": p, "event_recall": r,
        "event_f1": div(2 * p * r, p + r) if p == p and r == r else np.nan,
        "pick_precision": pp, "pick_recall": pr,
        "pick_f1": div(2 * pp * pr, pp + pr) if pp == pp and pr == pr else np.nan,
        "noise_rejection": div(s["noise_rejected"], s["noise_total"]),
        "split_rate": div(s["n_split"], s["n_true_events"]),
        "merge_rate": div(s["n_merge"], s["n_pred_events"]),
        "ari_mean": s["ari_mean"],
    })


def summarize(per_window, by=None):
    """Micro-averaged metrics (counts summed over windows), optionally grouped."""
    count_cols = ["n_true_events", "n_pred_events", "event_tp", "event_fp", "event_fn", "n_split",
                  "n_merge", "pick_correct", "pick_assigned", "pick_true", "noise_total", "noise_rejected"]

    def agg(g):
        s = g[count_cols].sum()
        s["n_windows"] = len(g)
        s["ari_mean"] = g["ari"].mean()
        return _ratios(s)

    if not by:
        return agg(per_window).to_frame().T
    return per_window.groupby(by).apply(agg, include_groups=False).reset_index()


# ----------------------------------------------------------------------
# Reference predictions (sanity checks for the metrics, not associators)
# ----------------------------------------------------------------------
def oracle(truth_picks):
    return truth_picks[["window_id", "pick_idx"]].assign(pred_event=truth_picks["event_idx"])


def all_noise(truth_picks):
    return truth_picks[["window_id", "pick_idx"]].assign(pred_event=NOISE)


def one_event(truth_picks):
    return truth_picks[["window_id", "pick_idx"]].assign(pred_event=0)


# ----------------------------------------------------------------------
# Benchmark entry point
# ----------------------------------------------------------------------
class Report:
    """Evaluation of one predictions table on one split of a release."""

    def __init__(self, per_window, meta, locations=None):
        """``locations``: per matched event location errors (see score_locations), or None."""
        self.per_window = per_window
        self.meta = meta
        self.locations = locations
        self.overall = summarize(per_window)
        self.by_network = summarize(per_window, by=["network"])
        self.by_scenario = summarize(per_window, by=["scenario"])
        self.by_network_scenario = summarize(per_window, by=["network", "scenario"])
        if locations is not None and len(locations):
            loc = locations.merge(per_window[["window_id", "network", "scenario"]], on="window_id")
            self.overall = pd.concat([self.overall, summarize_locations(loc)], axis=1)
            for attr, by in (("by_network", ["network"]), ("by_scenario", ["scenario"]),
                             ("by_network_scenario", ["network", "scenario"])):
                setattr(self, attr, getattr(self, attr).merge(summarize_locations(loc, by), on=by, how="left"))

    def save(self, out_dir):
        import json
        from pathlib import Path

        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        self.per_window.to_csv(out / "per_window.csv", index=False)
        self.by_network.to_csv(out / "by_network.csv", index=False)
        self.by_scenario.to_csv(out / "by_scenario.csv", index=False)
        self.by_network_scenario.to_csv(out / "by_network_scenario.csv", index=False)
        if self.locations is not None:
            self.locations.to_csv(out / "location_errors.csv", index=False)
        with open(out / "summary.json", "w") as f:
            json.dump({**self.meta, "overall": self.overall.iloc[0].to_dict()}, f, indent=2, default=float)
        return out

    def __repr__(self):
        cols = ["event_precision", "event_recall", "event_f1", "pick_precision", "pick_recall", "pick_f1",
                "noise_rejection", "split_rate", "merge_rate", "ari_mean"]
        cols += [c for c in ("located_frac", "epi_median_km", "depth_median_km", "t0_median_s") if c in self.overall]
        return f"<bepad.Report {self.meta}>\n" + self.overall[cols].round(4).to_string(index=False)


def check_predictions(pred, truth_picks):
    """Validate a predictions table against the picks it should cover."""
    need = {"window_id", "pick_idx", "pred_event"}
    missing = need - set(pred.columns)
    if missing:
        raise ValueError(f"predictions are missing columns {sorted(missing)}")
    if pred.duplicated(["window_id", "pick_idx"]).any():
        raise ValueError("predictions contain duplicated (window_id, pick_idx) rows")
    if not pd.api.types.is_integer_dtype(pred["pred_event"]):
        raise ValueError("pred_event must be integer (-1 = noise / not associated)")
    unknown = set(pred["window_id"]) - set(truth_picks["window_id"])
    if unknown:
        raise ValueError(f"{len(unknown)} window_id(s) not in this split, e.g. {sorted(unknown)[:3]}")
    covered = truth_picks[["window_id", "pick_idx"]].merge(pred[["window_id", "pick_idx"]], how="left",
                                                           indicator=True)
    n_missing = int((covered["_merge"] == "left_only").sum())
    return {"n_predictions": len(pred), "n_picks": len(truth_picks), "n_missing_picks": n_missing}


def evaluate(predictions, release, split="test", networks=None, min_shared=3, window_ids=None, locations=None):
    """Score ``predictions`` (DataFrame or parquet/csv path) on ``split`` of ``release``
    (a loaded :class:`bepad.data.Split`, a :class:`bepad.data.Release` or a local release folder).

    Picks without a prediction count as noise (-1). ``networks`` limits scoring
    to those networks; ``window_ids`` to those windows (a partial run).
    ``locations`` (optional): one row per predicted event -- window_id, event (its pred_event
    number), latitude, longitude, depth_km, t0_rel_s -- scored against the matched true events.
    """
    from pathlib import Path

    from .data import Release, Split

    if isinstance(release, Split):          # a loaded split: score its own split and networks
        networks = networks or sorted(release.windows["network"].unique())
        split, release = release.name, release.release
    rel = release if isinstance(release, Release) else Release(release)
    if not isinstance(predictions, pd.DataFrame):
        p = Path(predictions)
        predictions = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
    keep = set(window_ids) if window_ids is not None else None     # a partial run: read only its rows
    windows = rel._read(split, "windows", networks)
    if keep is not None:
        windows = windows[windows.window_id.isin(keep)]
    picks = rel._read(split, "picks", networks, columns=["window_id", "pick_idx", "event_idx"], window_ids=keep)
    events = rel._read(split, "events", networks, columns=["window_id", "event_idx", "scorable", "latitude",
                                                           "longitude", "depth", "t0_rel_s"], window_ids=keep)
    checks = check_predictions(predictions, picks)
    if checks["n_missing_picks"]:
        print(f"[evaluate] warning: {checks['n_missing_picks']} picks have no prediction -> counted as noise")
    per_window, _, matches = score_windows(picks, events, predictions, min_shared=min_shared, windows=windows)
    loc = None
    if locations is not None:
        if not isinstance(locations, pd.DataFrame):
            locations = pd.read_parquet(locations)
        loc = score_locations(matches, events, locations)
    meta = {"release": rel.path.name, "split": split, "min_shared": min_shared,
            "networks": networks or "all", "n_windows": int(len(windows)), **checks}
    return Report(per_window, meta, loc)
