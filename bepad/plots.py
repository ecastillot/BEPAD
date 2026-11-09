"""Figures for understanding BEPAD windows, labels, scenarios and statistics.

Every function returns the matplotlib Figure and accepts ``save_path`` (saved
at ``dpi=400``, tight bounding box). Sizes follow journal widths: single column
3.5 in, double column 7.2 in.

Window-level
    plot_window(w)            distance-time view of one window (real / generated / noise, bands)
    plot_window_map(w)        where the events and stations of one window are
    plot_window_anatomy(w)    map + distance-time + pick counts, annotated (the "what is a window" figure)
    plot_event_labels(w)      each event: travel time vs distance, band, picks coloured by prob
    plot_prediction(w, pred)  truth vs an associator's prediction, errors circled

Dataset-level
    plot_scenario_grid(split, network)   events-per-window x noise-level examples
    plot_gap_sweep(split, network)       out-of-network sweep: maps of the three gap scenarios
    plot_label_model(model)              prob vs distance per magnitude, and sigma(r)
    plot_difficulty(split)               phase-association difficulty per scenario
    plot_release_stats(split)            window length, gap, magnitude, picks per network
    plot_scores(summary)                 metric heatmap over the scenario grid
    plot_events_overview(split)          source earthquakes: map, magnitude, depth, gap, detection distance
    plot_station_geometry(split)         stations per window, spacing, aperture
    plot_picks_overview(split)           travel times, picks per earthquake, distances, prob
    plot_event_proximity(split)          earthquake pairs: distance vs time between origins
    plot_representative_windows(split)   easy / typical / hard windows per scale
    plot_core_networks(split)            map of each core network: stations, earthquakes by depth
    release_gallery(release_dir, cfg)    all of the above for a release
"""

from __future__ import annotations

from pathlib import Path

import matplotlib  # no backend is forced: figures show in notebooks, and matplotlib uses Agg without a display
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.lines import Line2D

from .build.geo import haversine_km

# Validated categorical order (dataviz reference palette); events cycle with their index printed.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
NOISE_C = "#8f8f89"
BAND_C = "#d9d8d2"
INK, INK2 = "#1f1f1c", "#62625d"
PROB_CMAP = LinearSegmentedColormap.from_list("prob", ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
COL1, COL2 = 3.5, 7.2          # inches
DPI = 400

STYLE = {
    "font.size": 7, "axes.titlesize": 7.5, "axes.labelsize": 7, "xtick.labelsize": 6.5, "ytick.labelsize": 6.5,
    "legend.fontsize": 6.5, "font.family": "sans-serif",
    "axes.linewidth": 0.6, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
    "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.major.size": 2.5, "ytick.major.size": 2.5,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#ecebe5",
    "grid.linewidth": 0.5, "legend.frameon": False, "savefig.dpi": DPI, "figure.dpi": 120,
    "pdf.fonttype": 42, "ps.fonttype": 42,
}
plt.rcParams.update(STYLE)


def _finish(fig, save_path, dpi=DPI):
    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
    return fig


def _window_id(ax, wid):
    """The window_id in a corner of a panel, so the window can be loaded again: bepad.load(window_ids=[...])."""
    ax.text(0.99, 0.02, wid, transform=ax.transAxes, ha="right", va="bottom", fontsize=4.5, color=INK2, zorder=10,
            bbox=dict(boxstyle="square,pad=0.15", fc="white", ec="none", alpha=0.85))


def _panel(ax, letter):
    ax.text(-0.02, 1.02, letter, transform=ax.transAxes, fontweight="bold", fontsize=8.5, ha="right", va="bottom",
            color=INK)


def _ecolor(k):
    return SERIES[int(k) % len(SERIES)]


def _stations_xy(w):
    return w.stations.drop_duplicates("station").set_index("station")


def _hyp(e, st_rows):
    return np.hypot(haversine_km(e["latitude"], e["longitude"], st_rows["latitude"].to_numpy(),
                                 st_rows["longitude"].to_numpy()), e["depth"] / 1e3)


def _nearest_event_dist(w, picks):
    st = _stations_xy(w).loc[picks["station"]]
    d = np.stack([_hyp(e, st) for _, e in w.events.iterrows()])
    return d.min(axis=0)


def _band_curves(w, e, model, network, r_grid):
    """Predicted arrival (absolute window time) of one event from its real picks in the window."""
    from .build.labels import EventArrivals

    pe = w.picks[(w.picks.event_idx == e.event_idx) & (w.picks.real == 1)]
    st = _stations_xy(w).loc[pe["station"]]
    r = _hyp(e, st)
    arr = EventArrivals(model, network, r, pe["t_rel_s"].to_numpy() - e.t0_rel_s, pe["phase"].to_numpy(),
                        e.get("last_station_km", np.nan) if np.isfinite(e.get("last_station_km", np.nan)) else r.max())
    return {ph: e.t0_rel_s + arr.mu(ph, r_grid) for ph in ("P", "S")}


# ----------------------------------------------------------------------
# Window-level
# ----------------------------------------------------------------------
def plot_window(w, model=None, ax=None, show_bands=True, legend=True, title=None, save_path=None, dpi=DPI):
    """Distance-time view of one window.

    Event picks are drawn at their distance from their own event (y = 0 at its
    origin); noise at its distance from the nearest event. Real picks: filled
    (P) / open (S) circles; generated picks: diamonds; noise: grey crosses.
    With ``model`` (``Release.label_model``) the band of each event is shaded.
    """
    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(COL2, 3.0))
    fig = ax.figure
    st = _stations_xy(w)
    ev = w.events.sort_values("event_idx")
    ymax = 1.0

    for _, e in ev.iterrows():
        k, c = int(e.event_idx), _ecolor(e.event_idx)
        alpha = 1.0 if e.scorable else 0.4
        pe = w.picks[w.picks.event_idx == k]
        y = _hyp(e, st.loc[pe["station"]])
        ymax = max(ymax, float(y.max()) if len(y) else 0)
        if show_bands and model is not None and (pe.real == 1).sum() >= 2:
            rg = np.linspace(0, max(e.get("last_station_km", y.max()), 1), 120)
            sig = model.sigma(rg)
            for ph, mu in _band_curves(w, e, model, w.meta["network"], rg).items():
                ax.fill_betweenx(rg, mu - model.band_k * sig, mu + model.band_k * sig, color=c, alpha=0.08, lw=0)
        for ph, filled in (("P", True), ("S", False)):
            m = ((pe.phase == ph) & (pe.real == 1)).to_numpy()
            ax.scatter(pe.t_rel_s[m], y[m], s=9, lw=0.6, alpha=alpha, zorder=3,
                       facecolors=c if filled else "white", edgecolors=c)
            g = ((pe.phase == ph) & (pe.pick_type == "generated")).to_numpy()
            ax.scatter(pe.t_rel_s[g], y[g], s=12, marker="D", lw=0.6, alpha=alpha, zorder=3,
                       facecolors="none", edgecolors=c)
        big = e.get("role") == "mainshock"                 # sequences: the mainshock is a larger star
        ax.scatter([e.t0_rel_s], [0], marker="*", s=140 if big else 55, color=c, alpha=alpha,
                   edgecolors=INK if big else "white", lw=0.6 if big else 0.4, zorder=5 if big else 4)
        ax.annotate(str(k), (e.t0_rel_s, 0), xytext=(0, 3.5), textcoords="offset points", ha="center",
                    fontsize=5.5, color=INK)

    noise = w.picks[w.picks.pick_type == "noise"]
    if len(noise):
        yn = _nearest_event_dist(w, noise)
        ax.scatter(noise.t_rel_s, yn, s=7, marker="x", lw=0.5, color=NOISE_C, zorder=2)
    ax.set_ylim(1.12 * ymax, -0.06 * ymax)
    ax.set_xlim(min(0, ev.t0_rel_s.min()) - 1, w.meta["length_s"] + 1)
    ax.set_xlabel("Window time [s]")
    ax.set_ylabel("Hypocentral distance [km]")
    if title:
        ax.set_title(title, loc="left")
    elif own:
        ax.set_title(w.window_id, loc="left", fontsize=7, color=INK2)
    if legend:
        h = [Line2D([], [], marker="o", ls="", ms=3.5, color=INK2, label="real P"),
             Line2D([], [], marker="o", ls="", ms=3.5, mfc="white", color=INK2, label="real S"),
             Line2D([], [], marker="D", ls="", ms=3.5, mfc="none", color=INK2, label="generated"),
             Line2D([], [], marker="x", ls="", ms=3.5, color=NOISE_C, label="noise"),
             Line2D([], [], marker="*", ls="", ms=6, color=INK2, label="origin (event #)")]
        if model is not None and show_bands:
            h.append(plt.Rectangle((0, 0), 1, 1, color=INK2, alpha=0.15, label="band (±2σ)"))
        ax.legend(handles=h, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=len(h), fontsize=5.5,
                  handletextpad=0.2, columnspacing=0.9)
    return _finish(fig, save_path, dpi) if own else fig


def plot_window_map(w, ax=None, all_stations=None, legend=True, save_path=None, dpi=DPI):
    """Map of one window: epicentres (size ~ magnitude, colour = event), stations that picked
    (dark), silent stations of the window (light) and, optionally, the rest of the network."""
    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(COL1, COL1))
    fig = ax.figure
    st = _stations_xy(w)
    active = set(w.picks.loc[w.picks.get("real", pd.Series(1, index=w.picks.index)) == 1, "station"]) \
        if "real" in w.picks else set(w.picks["station"])
    if all_stations is not None:
        ax.scatter(all_stations.longitude, all_stations.latitude, s=4, marker="^", color="#e4e3dc", lw=0, zorder=1)
    silent = st[~st.index.isin(active)]
    ax.scatter(silent.longitude, silent.latitude, s=8, marker="^", color="#c9c8c1", lw=0, zorder=2,
               label="station, no picks")
    act = st[st.index.isin(active)]
    ax.scatter(act.longitude, act.latitude, s=10, marker="^", color=INK2, lw=0, zorder=3, label="station with picks")
    ev = w.events.sort_values("event_idx")
    if ev is not None and len(ev):
        mags = pd.to_numeric(ev.magnitude, errors="coerce").fillna(ev.magnitude.median() if ev.magnitude.notna().any() else 1)
        size = 12 + 18 * (mags - mags.min() + 0.5)
        for (_, e), s_ in zip(ev.iterrows(), size):
            ax.scatter(e.longitude, e.latitude, marker="*", s=s_, color=_ecolor(e.event_idx), edgecolors="white",
                       lw=0.4, zorder=4, alpha=1 if e.scorable else 0.45)
            dx, dy = [(4, 3), (-8, 3), (4, -8), (-8, -8)][int(e.event_idx) % 4]      # staggered labels
            ax.annotate(str(int(e.event_idx)), (e.longitude, e.latitude), xytext=(dx, dy), textcoords="offset points",
                        fontsize=5.5, color=INK)
    focus = pd.concat([act[["longitude", "latitude"]], ev[["longitude", "latitude"]]]) if len(act) else st
    x0, x1 = focus.longitude.min(), focus.longitude.max()
    y0, y1 = focus.latitude.min(), focus.latitude.max()
    pad = 0.12 * max(x1 - x0, y1 - y0, 0.2)
    ax.set_xlim(x0 - pad, x1 + pad)
    ax.set_ylim(y0 - pad, y1 + pad)
    _map_aspect(ax, (y0 + y1) / 2)
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(3))
    ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(4))
    ax.set_xlabel("Longitude [°]")
    ax.set_ylabel("Latitude [°]")
    if own:
        ax.set_title(w.window_id, loc="left", fontsize=6, color=INK2)
    if legend:
        h = [Line2D([], [], marker="^", ls="", ms=4, color=INK2, label="station with picks"),
             Line2D([], [], marker="^", ls="", ms=4, color="#c9c8c1", label="station, no picks"),
             Line2D([], [], marker="*", ls="", ms=7, color=INK2, label="epicentre (size ~ M)")]
        ax.legend(handles=h, loc="upper center", bbox_to_anchor=(0.5, -0.3), ncol=1, fontsize=5.5)
    return _finish(fig, save_path, dpi) if own else fig


def _map_aspect(ax, lat0):
    ax.set_aspect(1 / max(np.cos(np.radians(lat0)), 0.2))
    try:  # coastlines when cartopy is available (optional)
        import cartopy.io.shapereader as shpreader  # noqa: F401
        from cartopy.feature import COASTLINE
        for geom in COASTLINE.geometries():
            for line in getattr(geom, "geoms", [geom]):
                x, y = line.xy
                ax.plot(x, y, color="#b8b7b0", lw=0.4, zorder=0)
    except Exception:
        pass


def plot_window_anatomy(w, model=None, all_stations=None, save_path=None, dpi=DPI):
    """The 'what is a window' figure: (a) map, (b) distance-time with bands, (c) pick counts."""
    fig = plt.figure(figsize=(COL2, 3.2))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.25, 2.3, 0.55], wspace=0.38)
    ax_m, ax_t, ax_c = fig.add_subplot(gs[0]), fig.add_subplot(gs[1]), fig.add_subplot(gs[2])
    plot_window_map(w, ax=ax_m, all_stations=all_stations, legend=True)
    plot_window(w, model=model, ax=ax_t, legend=True)
    counts = w.picks.pick_type.value_counts().reindex(["real", "generated", "noise"]).fillna(0)
    colors = [INK2, "#86b6ef", NOISE_C]
    ax_c.barh(range(3), counts.values, color=colors, height=0.6)
    for i, v in enumerate(counts.values):
        ax_c.text(v, i, f" {int(v)}", va="center", fontsize=6, color=INK)
    ax_c.set_yticks(range(3), ["real", "generated", "noise"])
    ax_c.invert_yaxis()
    ax_c.set_xlabel("Picks")
    ax_c.grid(axis="y", visible=False)
    ax_c.set_xlim(0, counts.max() * 1.35 + 1)
    for ax, l in zip((ax_m, ax_t, ax_c), "abc"):
        _panel(ax, l)
    m = w.meta
    fig.suptitle(f"{m['window_id']}  ·  {int(m['n_events'])} events  ·  "
                 f"{int(m['n_stations'])} stations  ·  {m['length_s']:.0f} s", x=0.01, ha="left", fontsize=7.5,
                 color=INK)
    return _finish(fig, save_path, dpi)


def plot_event_labels(w, model, events=None, ncols=3, save_path=None, dpi=DPI):
    """Per event: travel time vs distance, the band (±2σ, only where generation is allowed shaded
    darker), real and generated picks coloured by prob, noise near the event, last station."""
    from .build.labels import EventArrivals

    ev = w.events.sort_values("event_idx")
    if events is not None:
        ev = ev[ev.event_idx.isin(events)]
    n = len(ev)
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(COL2, 2.1 * nrows), squeeze=False)
    st = _stations_xy(w)
    norm = Normalize(0.5, 1)
    for ax, (_, e) in zip(axes.ravel(), ev.iterrows()):
        pe = w.picks[w.picks.event_idx == e.event_idx]
        r = _hyp(e, st.loc[pe.station])
        tt = pe.t_rel_s.to_numpy() - e.t0_rel_s
        real = (pe.real == 1).to_numpy()
        last = e.get("last_station_km", np.nan)
        last = r[real].max() if not np.isfinite(last) and real.any() else last
        if real.sum() >= 2:
            arr = EventArrivals(model, w.meta["network"], r[real], tt[real], pe.phase.to_numpy()[real], last)
            rg = np.linspace(0, max(last, r.max()) * 1.05, 300)
            sig = model.sigma(rg)
            for ph in ("P", "S"):
                mu = arr.mu(ph, rg)
                ax.fill_between(rg, mu - model.band_k * sig, mu + model.band_k * sig, color=BAND_C, lw=0, zorder=0)
                ok = arr.can_generate(ph, rg)
                ax.fill_between(rg, np.where(ok, mu - model.band_k * sig, np.nan),
                                np.where(ok, mu + model.band_k * sig, np.nan), color="#b9d3f1", lw=0, zorder=1)
                ax.plot(rg, mu, color=INK2, lw=0.5, zorder=2)
        for ph, mk in (("P", "o"), ("S", "s")):
            m = (pe.phase == ph).to_numpy()
            for typ, face in (("real", True), ("generated", False)):
                s_ = m & (pe.pick_type == typ).to_numpy()
                if s_.any():
                    ax.scatter(r[s_], tt[s_], c=pe.prob.to_numpy()[s_], cmap=PROB_CMAP, norm=norm,
                               marker=mk if face else "D", s=10, lw=0.5, zorder=3, edgecolors=INK2)
        noise = w.picks[w.picks.pick_type == "noise"]
        if len(noise):
            rn = _hyp(e, st.loc[noise.station])
            tn = noise.t_rel_s.to_numpy() - e.t0_rel_s
            keep = (tn > -5) & (rn <= max(last, r.max()) * 1.05) & (tn <= tt.max() * 1.3 + 5)
            ax.scatter(rn[keep], tn[keep], marker="x", s=6, lw=0.4, color=NOISE_C, zorder=2)
        if np.isfinite(last):
            ax.axvline(last, color=SERIES[1], lw=0.7, ls="--")
        ax.set_title(f"event {int(e.event_idx)}: {e.magnitude_type} {e.magnitude:.1f}, "
                     f"{e.depth / 1e3:.0f} km deep", loc="left", fontsize=6.5)
        ax.set_xlabel("Hypocentral distance [km]")
        ax.set_ylabel("Travel time [s]")
        ax.set_ylim(bottom=min(0, np.nanmin(tt)) - 1)
    for ax in axes.ravel()[n:]:
        ax.set_visible(False)
    sm = matplotlib.cm.ScalarMappable(norm=norm, cmap=PROB_CMAP)
    fig.subplots_adjust(top=0.9 if nrows > 1 else 0.82, hspace=0.55, wspace=0.35, right=0.88)
    cax = fig.add_axes([0.905, 0.15, 0.012, 0.65])
    cb = fig.colorbar(sm, cax=cax)
    cb.set_label("prob (real and generated picks)")
    h = [Line2D([], [], marker="o", ls="", ms=3.5, mfc="#3987e5", mec=INK2, label="real P"),
         Line2D([], [], marker="s", ls="", ms=3.5, mfc="#3987e5", mec=INK2, label="real S"),
         Line2D([], [], marker="D", ls="", ms=3.5, mfc="#86b6ef", mec=INK2, label="generated"),
         Line2D([], [], marker="x", ls="", ms=3.5, color=NOISE_C, label="noise"),
         plt.Rectangle((0, 0), 1, 1, color=BAND_C, label="band: no noise"),
         plt.Rectangle((0, 0), 1, 1, color="#b9d3f1", label="band: generation allowed"),
         Line2D([], [], color=SERIES[1], ls="--", lw=0.8, label="last station")]
    fig.legend(handles=h, loc="upper center", ncol=7, bbox_to_anchor=(0.45, 1.0), fontsize=5.5)
    fig.suptitle(w.window_id, x=0.01, y=1.04, ha="left", fontsize=7, color=INK2)
    return _finish(fig, save_path, dpi)


def _pick_distance(w, picks):
    """Distance of each pick to its own event (event picks) or to the nearest event (noise)."""
    st = _stations_xy(w).loc[picks["station"]]
    ev = w.events.set_index("event_idx")
    d = np.stack([_hyp(e, st) for _, e in w.events.sort_values("event_idx").iterrows()])     # (E, N)
    own = picks["event_idx"].to_numpy() if "event_idx" in picks else np.full(len(picks), -1)
    out = d.min(axis=0)
    m = own >= 0
    out[m] = d[np.searchsorted(ev.index.to_numpy(), own[m]), np.flatnonzero(m)]
    return out


def plot_prediction(w, predictions, locations=None, min_shared=4, min_stations=3, save_path=None, dpi=DPI):
    """Truth (left) vs an associator's prediction (right) for one window.

    ``w`` must be loaded with labels; ``predictions`` has window_id, pick_idx,
    pred_event (as written by ``Associator.run`` / ``predictions_frame``).
    Picks keep the same position in both panels; predicted events take the
    colour of the true event they are matched to (black if unmatched). Red
    circles mark errors: a pick in the wrong event, noise put in an event, or
    an event pick left unassociated. With ``locations`` (``result.locations``),
    a map adds the true epicentres (stars) joined to the predicted ones (circles).
    """
    from .metrics import _score_window, match_events

    pk = w.picks.merge(predictions[predictions.window_id == w.window_id][["pick_idx", "pred_event"]],
                       on="pick_idx", how="left")
    pk["pred_event"] = pk["pred_event"].fillna(-1).astype(int)
    y = _pick_distance(w, pk)
    true, pred = pk.event_idx.to_numpy(), pk.pred_event.to_numpy()

    t_ids, p_ids, _, _, m_ = match_events(true, pred, pk.station.to_numpy(), min_shared, min_stations)
    match = {p: t for t, p in m_.items()}                                     # predicted -> true
    mapped = np.array([match.get(p, -2) if p >= 0 else -1 for p in pred])      # -2 = unmatched event
    wrong = (mapped != true) & ~((true < 0) & (pred < 0))

    scorable = set(w.events.loc[w.events.scorable, "event_idx"])
    sc = _score_window(pk, scorable, min_shared, min_stations)
    ev_f1 = 2 * sc["event_tp"] / max(2 * sc["event_tp"] + sc["event_fp"] + sc["event_fn"], 1)

    loc = None
    if locations is not None:
        loc = locations[locations.window_id == w.window_id]
    if loc is not None and len(loc):
        fig = plt.figure(figsize=(COL2, 3.0))
        gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 0.75], wspace=0.3)
        axes = [fig.add_subplot(gs[0])]
        axes.append(fig.add_subplot(gs[1], sharey=axes[0], sharex=axes[0]))
        ax_map = fig.add_subplot(gs[2])
    else:
        fig, axes = plt.subplots(1, 2, figsize=(COL2, 3.0), sharey=True, sharex=True)
        ax_map = None
    t = pk.t_rel_s.to_numpy()
    filled = (pk.phase == "P").to_numpy()
    for ax, lab, title in ((axes[0], true, f"Truth: {len(t_ids)} events"),
                           (axes[1], mapped, f"Prediction: {len(p_ids)} events · F1 {ev_f1:.2f} · "
                                             f"{int(wrong.sum())} errors")):
        noise = lab == -1
        ax.scatter(t[noise], y[noise], marker="x", s=7, lw=0.5, color=NOISE_C, zorder=2)
        for k in np.unique(lab[lab != -1]):
            m = lab == k
            c = INK if k == -2 else _ecolor(k)
            ax.scatter(t[m & filled], y[m & filled], s=9, color=c, lw=0.5, zorder=3)
            ax.scatter(t[m & ~filled], y[m & ~filled], s=9, facecolors="white", edgecolors=c, lw=0.6, zorder=3)
        for _, e in w.events.iterrows():
            ax.scatter([e.t0_rel_s], [0], marker="*", s=45, color=_ecolor(e.event_idx), edgecolors="white",
                       lw=0.4, zorder=4, alpha=1 if e.scorable else 0.4)
        ax.set_title(title, loc="left")
        ax.set_xlabel("Window time [s]")
    axes[1].scatter(t[wrong], y[wrong], s=42, facecolors="none", edgecolors=SERIES[7], lw=0.8, zorder=5)
    if ax_map is not None:
        st = _stations_xy(w)
        used = st[st.index.isin(pk.station)]
        ax_map.scatter(used.longitude, used.latitude, marker="^", s=8, color="#c9c8c1", lw=0, zorder=1)
        inv = {tv: pv for pv, tv in match.items()}
        for _, e in w.events.iterrows():
            c = _ecolor(e.event_idx)
            ax_map.scatter(e.longitude, e.latitude, marker="*", s=60, color=c, edgecolors="white", lw=0.4, zorder=4)
            pv = inv.get(e.event_idx)
            row = loc[loc.event == pv] if pv is not None else loc.iloc[0:0]
            if len(row) and np.isfinite(row.latitude.iloc[0]):
                ax_map.plot([e.longitude, row.longitude.iloc[0]], [e.latitude, row.latitude.iloc[0]],
                            color=c, lw=0.7, zorder=2)
        for _, r in loc.iterrows():
            c = _ecolor(match[r.event]) if r.event in match else INK
            ax_map.scatter(r.longitude, r.latitude, s=16, facecolors="white", edgecolors=c, lw=0.9, zorder=3)
        _map_aspect(ax_map, used.latitude.mean())
        ax_map.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(3))
        ax_map.set_xlabel("Longitude [°]")
        ax_map.set_ylabel("Latitude [°]")
        ax_map.set_title("★ true  ○ predicted", loc="left")
    axes[0].set_ylabel("Distance [km]")
    axes[0].set_ylim(1.1 * max(y.max(), 1), -0.06 * max(y.max(), 1))
    h = [Line2D([], [], marker="o", ls="", ms=3.5, color=INK2, label="P"),
         Line2D([], [], marker="o", ls="", ms=3.5, mfc="white", color=INK2, label="S"),
         Line2D([], [], marker="x", ls="", ms=3.5, color=NOISE_C, label="noise / unassociated"),
         Line2D([], [], marker="o", ls="", ms=3.5, color=INK, label="predicted event with no true match"),
         Line2D([], [], marker="o", ls="", ms=6, mfc="none", mec=SERIES[7], label="error")]
    fig.legend(handles=h, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.04))
    fig.suptitle(w.window_id, x=0.01, ha="left", fontsize=7, color=INK2)
    if ax_map is None:
        fig.tight_layout(rect=(0, 0.05, 1, 1))
    else:
        fig.subplots_adjust(bottom=0.24, top=0.86, left=0.07, right=0.98)
    return _finish(fig, save_path, dpi)


# ----------------------------------------------------------------------
# Dataset-level
# ----------------------------------------------------------------------
def _level(scenario, axis):
    for part in str(scenario).split("__"):
        if part.startswith(axis + "-"):
            return part[len(axis) + 1:]
    return None


def plot_scenario_grid(split, network, ev_levels=("sparse", "low", "med", "high"),
                       noise_levels=("none", "med", "extreme"), model=None, index=0, save_path=None, dpi=DPI):
    """One example window per (events-per-window, noise level) for one network."""
    fig, axes = plt.subplots(len(noise_levels), len(ev_levels), figsize=(COL2, 1.55 * len(noise_levels) + 0.3),
                             squeeze=False)
    ids = set(split.windows.window_id)
    for i, nl in enumerate(noise_levels):
        for j, el in enumerate(ev_levels):
            ax = axes[i][j]
            wid = f"{network}.{split.name}.ev-{el}__noise-{nl}.{index:05d}"
            if wid not in ids:
                ax.set_visible(False)
                continue
            w = split[wid]
            plot_window(w, model=model, ax=ax, legend=False, show_bands=False)
            ax.set_title(f"{el} ({int(w.meta['n_events'])} ev.) · noise {nl}", loc="left", fontsize=6)
            _window_id(ax, wid)
            if i < len(noise_levels) - 1:
                ax.set_xlabel("")
            if j > 0:
                ax.set_ylabel("")
    h = [Line2D([], [], marker="o", ls="", ms=3, color=INK2, label="real P"),
         Line2D([], [], marker="o", ls="", ms=3, mfc="white", color=INK2, label="real S"),
         Line2D([], [], marker="D", ls="", ms=3, mfc="none", color=INK2, label="generated"),
         Line2D([], [], marker="x", ls="", ms=3, color=NOISE_C, label="noise"),
         Line2D([], [], marker="*", ls="", ms=5, color=INK2, label="origin")]
    fig.legend(handles=h, loc="upper center", ncol=5, bbox_to_anchor=(0.5, 1.02))
    fig.suptitle(f"Scenarios — {network}: columns = events per window, rows = noise level", y=1.07, fontsize=7.5,
                 color=INK)
    fig.tight_layout(h_pad=0.8, w_pad=0.6)
    return _finish(fig, save_path, dpi)


def plot_gap_sweep(split, network, scenarios=("gap-000-090", "gap-090-180", "gap-180-270"), index=0,
                   save_path=None, dpi=DPI):
    """Out-of-network sweep: one window per azimuthal-gap scenario, map (top) and distance-time (bottom)."""
    fig, axes = plt.subplots(2, len(scenarios), figsize=(COL2, 4.6), gridspec_kw={"height_ratios": [1.1, 1]})
    for j, sc in enumerate(scenarios):
        wid = f"{network}.{split.name}.{sc}.{index:05d}"
        if wid not in set(split.windows.window_id):
            axes[0][j].set_visible(False)
            axes[1][j].set_visible(False)
            continue
        w = split[wid]
        plot_window_map(w, ax=axes[0][j], legend=(j == 0))
        lo, hi = sc.split("-")[1:]
        axes[0][j].set_title(f"azimuthal gap {int(lo)}–{int(hi)}°", loc="left")
        plot_window(w, ax=axes[1][j], legend=False, show_bands=False)
        _window_id(axes[1][j], wid)
        if j:
            axes[0][j].set_ylabel("")
            axes[1][j].set_ylabel("")
    fig.tight_layout()
    return _finish(fig, save_path, dpi)


SEQUENCE_TITLES = {"mainshock_first": "Mainshock first", "foreshocks": "Foreshocks, then mainshock",
                   "late": "Late in a sequence (no mainshock)", "two_sequences": "Two sequences"}


def plot_sequence_types(split, network, scenario="seq-med__noise-low", save_path=None, dpi=DPI):
    """Sequence scenarios: the first window of each sequence type of ``scenario``, map (top) and
    distance-time (bottom). Large stars: mainshocks."""
    w_ = split.windows
    w_ = w_[(w_.network == network) & (w_.scenario == scenario)].sort_values("window_id")
    types = [t for t in SEQUENCE_TITLES if (w_.sequence_type == t).any()]
    if not types:
        return None
    fig, axes = plt.subplots(2, len(types), figsize=(COL2, 4.6), gridspec_kw={"height_ratios": [1.1, 1]},
                             squeeze=False)
    for j, t in enumerate(types):
        row = w_[w_.sequence_type == t].iloc[0]
        w = split[row.window_id]
        plot_window_map(w, ax=axes[0][j], legend=(j == 0))
        axes[0][j].set_title(SEQUENCE_TITLES[t], loc="left", fontsize=6.5)
        plot_window(w, ax=axes[1][j], legend=False, show_bands=False)
        roles = w.events.role.value_counts()
        parts = [f"{roles[k]} {k}{'s' if roles[k] > 1 and k != 'background' else ''}"
                 for k in ("mainshock", "foreshock", "aftershock", "background") if k in roles]
        axes[1][j].set_title(", ".join(parts[:2]) + ("\n" + ", ".join(parts[2:]) if parts[2:] else ""),
                             loc="left", fontsize=5.5)
        _window_id(axes[1][j], row.window_id)
        if j:
            axes[0][j].set_ylabel("")
            axes[1][j].set_ylabel("")
    fig.tight_layout()
    return _finish(fig, save_path, dpi)


def plot_label_model(model, magnitudes=range(0, 8), save_path=None, dpi=DPI):
    """(a) prob of a real pick vs distance per magnitude; (b) generated-pick prob vs z;
    (c) timing uncertainty sigma(r) and the band half-width."""
    fig, axes = plt.subplots(1, 3, figsize=(COL2, 2.3), gridspec_kw={"width_ratios": [1.5, 1, 1.2]})
    r = np.logspace(0, 4.2, 300)
    ramp = ["#b7d3f6", "#86b6ef", "#5598e7", "#3987e5", "#2a78d6", "#1c5cab", "#184f95", "#0d366b"]
    for M, c in zip(magnitudes, ramp):
        axes[0].plot(r, model.prob_real(M, r), color=c, lw=1.1, label=f"M{M}")
    axes[0].legend(ncol=2, fontsize=5.5, loc="lower left", handlelength=1.2, columnspacing=0.8)
    for lo, hi, lab in ((1, 150, "local"), (150, 1500, "regional"), (1500, 16000, "global")):
        axes[0].axvspan(lo, hi, color="#f4f3ee" if lab == "regional" else "white", zorder=0)
        axes[0].text(np.sqrt(lo * hi), 1.035, lab, ha="center", fontsize=5.5, color=INK2)
    axes[0].axhline(0.5, color=INK2, lw=0.5, ls="--")
    axes[0].set(xscale="log", xlim=(1, 2.5e4), ylim=(0.45, 1.06), xlabel="Hypocentral distance [km]",
                ylabel="prob of a real pick")
    z = np.linspace(-model.band_k, model.band_k, 200)
    for M, rr, c in ((3, 20, ramp[5]), (3, 300, ramp[3]), (1.5, 300, ramp[1])):
        axes[1].plot(z, model.prob_generated(M, rr, z), color=c, lw=1.1, label=f"M{M}, {rr} km")
    axes[1].axhline(0.5, color=INK2, lw=0.5, ls="--")
    axes[1].set(xlabel="z = (t − predicted) / σ", ylabel="prob of a generated pick", ylim=(0.45, 1.02))
    axes[1].legend(fontsize=5.5, loc="lower center")
    axes[2].plot(r, model.sigma(r), color=INK, lw=1.2, label="σ(r)")
    axes[2].plot(r, model.band_k * model.sigma(r), color=INK, lw=0.8, ls="--", label=f"band half-width ({model.band_k:g}σ)")
    axes[2].set(xscale="log", yscale="log", xlabel="Hypocentral distance [km]", ylabel="Timing uncertainty [s]")
    axes[2].legend(fontsize=5.5, loc="upper left")
    for ax, l in zip(axes, "abc"):
        _panel(ax, l)
    fig.tight_layout(w_pad=1.2)
    return _finish(fig, save_path, dpi)


def _overlap_fraction(picks, events):
    """Per window: fraction of real picks that arrive while >= 2 events are active."""
    out = {}
    ev = events.dropna(subset=["first_pick_s"]).groupby("window_id")
    for wid, p in picks[picks.real == 1].groupby("window_id"):
        if wid not in ev.groups:
            continue
        e = ev.get_group(wid)
        f, l = e.first_pick_s.to_numpy(), e.last_pick_s.to_numpy()
        t = p.t_rel_s.to_numpy()[:, None]
        out[wid] = float((((t >= f) & (t <= l)).sum(axis=1) >= 2).mean())
    return pd.Series(out)


def plot_difficulty(split, ev_levels=("sparse", "low", "med", "high"),
                    noise_levels=("none", "low", "med", "high", "extreme"), save_path=None, dpi=DPI):
    """Phase-association difficulty of a split, by scenario level:
    (a) events active at once, (b) real picks arriving during overlap, (c) closest origins,
    (d) picks per window, (e) prob per pick type, (f) distance of each pick type to the nearest event."""
    w = split.windows.copy()
    w["ev"] = w.scenario.map(lambda s: _level(s, "ev") or (f"seq {_level(s, 'seq')}" if _level(s, "seq") else None))
    w["noise"] = w.scenario.map(lambda s: _level(s, "noise"))
    seq_levels = tuple(f"seq {lv}" for lv in ("low", "med", "high") if (w.ev == f"seq {lv}").any())
    ev_levels = tuple(ev_levels) + seq_levels             # sequences next to random windows of the same count
    w["overlap"] = w.window_id.map(_overlap_fraction(split.picks, split.events))
    fig, axes = plt.subplots(2, 3, figsize=(COL2, 4.4))

    def box(ax, col, by, order, ylabel, log=False):
        data = [w.loc[w[by] == lv, col].dropna() for lv in order]
        b = ax.boxplot(data, positions=range(len(order)), widths=0.55, patch_artist=True, showfliers=False)
        for p_ in b["boxes"]:
            p_.set(facecolor="#86b6ef", edgecolor="white", lw=0.6)
        for part in ("whiskers", "caps"):
            for line in b[part]:
                line.set(color=INK2, lw=0.6)
        for line in b["medians"]:
            line.set(color=INK, lw=1)
        ax.set_xticks(range(len(order)), [o.replace(" ", "\n") for o in order])
        ax.set_ylabel(ylabel)
        if log:
            ax.set_yscale("log")

    box(axes[0, 0], "max_concurrent_events", "ev", ev_levels, "Events active at once (max)")
    axes[0, 0].set_xlabel("Events per window")
    box(axes[0, 1], "overlap", "ev", ev_levels, "Real picks during overlap")
    axes[0, 1].set_xlabel("Events per window")
    axes[0, 1].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    box(axes[0, 2], "min_origin_sep_s", "ev", ev_levels[1:], "Closest origins [s]", log=True)
    axes[0, 2].set_xlabel("Events per window")
    box(axes[1, 0], "n_picks", "noise", noise_levels, "Picks per window", log=True)
    axes[1, 0].set_xlabel("Noise level")

    p = split.picks
    bins = np.linspace(0, 1, 41)
    bins = np.linspace(0.5, 1, 26)
    for typ, c in (("real", INK2), ("generated", "#3987e5")):
        v = p.loc[p.pick_type == typ, "prob"]
        if len(v):
            axes[1, 1].hist(v, bins=bins, color=c, alpha=0.7, label=f"{typ} ({len(v):,})",
                            weights=np.full(len(v), 1 / len(v)))
    n_noise = int((p.pick_type == "noise").sum())
    axes[1, 1].set(xlabel=f"prob  (noise: {n_noise:,} picks, all = 0)", ylabel="Fraction of picks")
    axes[1, 1].legend(fontsize=5.5)

    sample = w.window_id.sample(min(300, len(w)), random_state=0)
    dists = {"real": [], "generated": [], "noise": []}
    for wid in sample:
        wd = split[wid]
        d = _nearest_event_dist(wd, wd.picks)
        for typ in dists:
            dists[typ].append(d[(wd.picks.pick_type == typ).to_numpy()])
    edges = np.logspace(0, 4.2, 40)
    for typ, c in (("real", INK2), ("generated", "#3987e5"), ("noise", NOISE_C)):
        v = np.concatenate(dists[typ]) if dists[typ] else np.array([])
        if len(v):
            axes[1, 2].hist(v, bins=edges, color=c, alpha=0.6, label=typ, weights=np.full(len(v), 1 / len(v)))
    axes[1, 2].set(xscale="log", xlabel="Distance to nearest event [km]", ylabel="Fraction of picks")
    axes[1, 2].legend(fontsize=5.5)
    for ax, l in zip(axes.ravel(), "abcdef"):
        _panel(ax, l)
    fig.tight_layout(h_pad=1.2, w_pad=1.0)
    return _finish(fig, save_path, dpi)


def plot_release_stats(split, save_path=None, dpi=DPI):
    """Per network: windows length, picks per window, gap and magnitude of scorable events."""
    w, ev = split.windows, split.events.merge(split.windows[["window_id", "network"]], on="window_id")
    nets = sorted(w.network.unique())
    if len(nets) > 4:
        w = w.assign(network="all networks")
        ev = ev.assign(network="all networks")
        nets = ["all networks"]
    fig, axes = plt.subplots(1, 4, figsize=(COL2, 1.9))
    specs = [(w, "length_s", "Window length [s]", True), (w, "n_picks", "Picks per window", True),
             (ev[ev.scorable], "gap_deg", "Azimuthal gap [°]", False), (ev[ev.scorable], "magnitude", "Magnitude", False)]
    for ax, (df, col, lab, log) in zip(axes, specs):
        vals = df[col].dropna()
        edges = np.logspace(np.log10(max(vals.min(), 1e-1)), np.log10(vals.max()), 30) if log else 30
        for i, n in enumerate(nets):
            v = df.loc[df.network == n, col].dropna()
            ax.hist(v, bins=edges, color=SERIES[i % 8], alpha=0.65, label=n, weights=np.full(len(v), 1 / max(len(v), 1)))
        ax.set_xlabel(lab)
        if log:
            ax.set_xscale("log")
    axes[0].set_ylabel("Fraction")
    axes[0].legend(fontsize=5.5)
    for ax, l in zip(axes, "abcd"):
        _panel(ax, l)
    fig.tight_layout(w_pad=0.8)
    return _finish(fig, save_path, dpi)


def plot_scores(summary_by_scenario, metric="event_f1", ev_levels=("sparse", "low", "med", "high"),
                noise_levels=("none", "low", "med", "high", "extreme"), title=None, save_path=None, dpi=DPI):
    """Heatmap of one metric over the events x noise grid (from ``Report.by_scenario``)."""
    s = summary_by_scenario.copy()
    s["ev"] = s.scenario.map(lambda x: _level(x, "ev") or (f"seq {_level(x, 'seq')}" if _level(x, "seq") else None))
    s["noise"] = s.scenario.map(lambda x: _level(x, "noise"))
    ev_levels = tuple(ev_levels) + tuple(f"seq {lv}" for lv in ("low", "med", "high") if (s.ev == f"seq {lv}").any())
    m = s.pivot_table(index="noise", columns="ev", values=metric).reindex(index=list(noise_levels),
                                                                          columns=list(ev_levels))
    fig, ax = plt.subplots(figsize=(COL1 * (1.5 if len(ev_levels) > 4 else 1), 2.3))
    im = ax.imshow(m.to_numpy(float), cmap=PROB_CMAP, vmin=0, vmax=1, aspect="auto")
    for (i, j), v in np.ndenumerate(m.to_numpy(float)):
        if v == v:
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=6, color="white" if v > 0.55 else INK)
    ax.set_xticks(range(len(ev_levels)), [e.replace(" ", "\n") for e in ev_levels])
    ax.set_yticks(range(len(noise_levels)), noise_levels)
    ax.set(xlabel="Events per window (random, then sequences)" if len(ev_levels) > 4 else "Events per window",
           ylabel="Noise level")
    ax.grid(False)
    ax.set_title(title or metric, loc="left")
    fig.colorbar(im, ax=ax, fraction=0.05, pad=0.02)
    fig.tight_layout()
    return _finish(fig, save_path, dpi)


# ----------------------------------------------------------------------
# Dataset statistics (bepad.stats)
# ----------------------------------------------------------------------
SCALE_COLOR = {"local": SERIES[0], "regional": SERIES[1], "global": SERIES[2]}


def _by_scale(ax, df, col, bins, log=False, label=True):
    for sc, c in SCALE_COLOR.items():
        v = df.loc[df.scale == sc, col].dropna()
        if len(v):
            ax.hist(v, bins=bins, color=c, alpha=0.65, weights=np.full(len(v), 1 / len(v)),
                    label=f"{sc} ({len(v):,})" if label else None)
    if log:
        ax.set_xscale("log")


def _logbins(v, n=35):
    v = np.asarray(v, float)
    v = v[np.isfinite(v) & (v > 0)]
    return np.logspace(np.log10(v.min()), np.log10(v.max()), n) if len(v) else 10


def plot_events_overview(split, save_path=None, dpi=DPI):
    """The source earthquakes of a split: (a) map, (b) magnitude, (c) depth, (d) azimuthal gap,
    (e) farthest station against magnitude, (f) windows each earthquake appears in."""
    from .stats import source_events

    ev = source_events(split)
    fig, axes = plt.subplots(2, 3, figsize=(COL2, 4.6))
    ax = axes[0, 0]
    for sc, c in SCALE_COLOR.items():
        e = ev[ev.scale == sc]
        ax.scatter(e.longitude, e.latitude, s=2, color=c, lw=0, alpha=0.6, label=sc, rasterized=True)
    ax.set(xlim=(-180, 180), ylim=(-90, 90), xlabel="Longitude [°]", ylabel="Latitude [°]")
    ax.set_aspect("equal")
    ax.legend(markerscale=4, fontsize=5.5, loc="lower left")
    _by_scale(axes[0, 1], ev, "magnitude", np.arange(-1, 8.01, 0.25))
    axes[0, 1].set(xlabel="Magnitude", ylabel="Fraction of earthquakes")
    _by_scale(axes[0, 2], ev, "depth_km", _logbins(ev.depth_km.clip(lower=0.1)), log=True, label=False)
    axes[0, 2].set(xlabel="Depth [km]")
    _by_scale(axes[1, 0], ev, "gap_deg", np.linspace(0, 360, 37), label=False)
    axes[1, 0].set(xlabel="Azimuthal gap in window [°]", ylabel="Fraction of earthquakes")
    ax = axes[1, 1]
    for sc, c in SCALE_COLOR.items():
        e = ev[ev.scale == sc]
        ax.scatter(e.magnitude, e.last_station_km, s=3, color=c, lw=0, alpha=0.4, rasterized=True)
    ax.set(yscale="log", xlabel="Magnitude", ylabel="Farthest station [km]")
    ax.set_title("detection distance grows with M", loc="left", fontsize=6, color=INK2)
    _by_scale(axes[1, 2], ev, "n_windows", np.arange(0.5, ev.n_windows.max() + 1.5, 1), label=False)
    axes[1, 2].set(xlabel="Windows per earthquake")
    for a, l in zip(axes.ravel(), "abcdef"):
        _panel(a, l)
    fig.tight_layout(h_pad=1.0, w_pad=0.8)
    return _finish(fig, save_path, dpi)


def plot_station_geometry(split, max_windows=300, save_path=None, dpi=DPI):
    """Station geometry of the windows, per scale: (a) stations available, (b) stations with real
    picks, (c) median spacing between neighbouring stations, (d) aperture (widest separation)."""
    from .stats import window_geometry

    g = window_geometry(split, max_windows)
    scales = [sc for sc in SCALE_COLOR if (g.scale == sc).any()]
    fig, axes = plt.subplots(1, 4, figsize=(COL2, 2.0))
    specs = [("n_stations", "Stations in window"), ("n_picking_stations", "Stations with real picks"),
             ("spacing_km", "Station spacing [km]"), ("aperture_km", "Aperture [km]")]
    for ax, (col, lab) in zip(axes, specs):
        data = [g.loc[g.scale == sc, col].dropna() for sc in scales]
        b = ax.boxplot(data, positions=range(len(scales)), widths=0.55, patch_artist=True, showfliers=False)
        for patch, sc in zip(b["boxes"], scales):
            patch.set(facecolor=SCALE_COLOR[sc], alpha=0.75, edgecolor="white")
        for part in ("whiskers", "caps"):
            for line in b[part]:
                line.set(color=INK2, lw=0.6)
        for line in b["medians"]:
            line.set(color=INK, lw=1)
        ax.set_yscale("log")
        ax.set_xticks(range(len(scales)), scales)
        ax.set_title(lab, loc="left", fontsize=6.5)
        ax.grid(axis="x", visible=False)
    for a, l in zip(axes, "abcd"):
        _panel(a, l)
    fig.tight_layout(w_pad=0.8)
    return _finish(fig, save_path, dpi)


def plot_picks_overview(split, max_windows=200, save_path=None, dpi=DPI):
    """Picks: (a) travel time against distance (real P and S), (b) real picks per earthquake,
    (c) distance to the earthquake by pick type, (d) prob by pick type."""
    from .stats import pick_distances

    p = pick_distances(split, max_windows)
    fig, axes = plt.subplots(1, 4, figsize=(COL2, 2.1))
    ax = axes[0]
    r = p[p.pick_type == "real"]
    for ph, mk in (("P", "o"), ("S", "s")):
        q = r[r.phase == ph]
        for sc, c in SCALE_COLOR.items():
            qq = q[q.scale == sc]
            ax.scatter(qq.distance_km, qq.travel_time_s, s=1, marker=mk, color=c, lw=0,
                       alpha=0.25 if ph == "P" else 0.12, rasterized=True)
    ax.set(xscale="log", yscale="log", xlabel="Hypocentral distance [km]", ylabel="Travel time [s]")
    ax.text(0.03, 0.95, "real P and S", transform=ax.transAxes, fontsize=5.5, color=INK2, va="top")
    per = r.groupby(["window_id", "event_idx"]).agg(n=("station", "size"), scale=("scale", "first")).reset_index()
    _by_scale(axes[1], per, "n", _logbins(per.n), log=True)
    axes[1].set(xlabel="Real picks per earthquake", ylabel="Fraction")
    axes[1].legend(fontsize=5.5)
    for typ, c in (("real", INK2), ("generated", "#3987e5"), ("noise", NOISE_C)):
        v = p.loc[p.pick_type == typ, "distance_km"].dropna()
        if len(v):
            axes[2].hist(v, bins=_logbins(p.distance_km), color=c, alpha=0.6, label=typ,
                         weights=np.full(len(v), 1 / len(v)))
    axes[2].set(xscale="log", xlabel="Distance to its earthquake [km]")
    axes[2].legend(fontsize=5.5)
    for typ, c in (("real", INK2), ("generated", "#3987e5")):
        v = p.loc[p.pick_type == typ, "prob"]
        if len(v):
            axes[3].hist(v, bins=np.linspace(0.5, 1, 26), color=c, alpha=0.7, label=typ,
                         weights=np.full(len(v), 1 / len(v)))
    axes[3].set(xlabel="prob (noise = 0)")
    axes[3].legend(fontsize=5.5)
    for a, l in zip(axes, "abcd"):
        _panel(a, l)
    fig.tight_layout(w_pad=0.6)
    return _finish(fig, save_path, dpi)


def plot_event_proximity(split, save_path=None, dpi=DPI):
    """Every pair of earthquakes in the same window: epicentral distance against origin-time
    difference, one panel per scale. Pairs near the lower left (close in space AND time) are
    the hardest: their picks arrive together at the same stations."""
    from matplotlib.colors import LogNorm

    from .stats import event_pairs

    d = event_pairs(split)
    scales = [sc for sc in SCALE_COLOR if (d.scale == sc).any()]
    fig, axes = plt.subplots(1, len(scales), figsize=(COL2, 2.3), squeeze=False)
    cmap = LinearSegmentedColormap.from_list("seq", ["#e6eefa", "#86b6ef", "#2a78d6", "#0d366b"])
    for ax, sc in zip(axes[0], scales):
        q = d[(d.scale == sc) & (d.distance_km > 0) & (d.dt_s > 0)]
        xb, yb = _logbins(q.distance_km, 40), _logbins(q.dt_s, 40)
        h = ax.hist2d(q.distance_km, q.dt_s, bins=[xb, yb], cmap=cmap, norm=LogNorm(), rasterized=True)
        ax.set(xscale="log", yscale="log", xlabel="Distance between epicentres [km]")
        ax.set_title(f"{sc}: {len(q):,} pairs", loc="left")
        within = (q.dt_s < 10).mean() if len(q) else 0
        ax.text(0.03, 0.04, f"{within:.0%} of pairs: origins < 10 s apart", transform=ax.transAxes,
                fontsize=5.5, color=INK)
        ax.grid(False)
    axes[0][0].set_ylabel("Time between origins [s]")
    fig.colorbar(h[3], ax=axes[0].tolist(), fraction=0.02, pad=0.01, label="Pairs")
    return _finish(fig, save_path, dpi)


def plot_representative_windows(split, by="max_concurrent_events", quantiles=(0.1, 0.5, 0.9), networks=None,
                                model=None, save_path=None, dpi=DPI):
    """Easy, typical and hard windows (rows: quantiles of ``by``) for one network per scale (columns)."""
    from .stats import network_scales

    scales = network_scales(split)
    nets = networks or [scales[scales == sc].index[0] for sc in SCALE_COLOR if (scales == sc).any()]
    names = {0.1: "easy", 0.5: "typical", 0.9: "hard"}
    fig, axes = plt.subplots(len(quantiles), len(nets), figsize=(COL2, 1.8 * len(quantiles) + 0.3), squeeze=False)
    for j, n in enumerate(nets):
        w = split.windows[split.windows.network == n]
        for i, q in enumerate(quantiles):
            target = w[by].quantile(q)
            wid = w.iloc[(w[by] - target).abs().argsort().iloc[0]].window_id
            ax = axes[i][j]
            win = split[wid]
            plot_window(win, model=model, ax=ax, legend=False, show_bands=False)
            ax.set_title(f"{n} ({scales[n]}) · {names.get(q, q)} · {by.replace('_', ' ')} = {int(win.meta[by])}",
                         loc="left", fontsize=5.8)
            _window_id(ax, wid)
            if i < len(quantiles) - 1:
                ax.set_xlabel("")
            if j:
                ax.set_ylabel("")
    fig.tight_layout(h_pad=0.8, w_pad=0.6)
    return _finish(fig, save_path, dpi)


# What makes each core network hard (shown under its map).
CORE_CHALLENGES = {
    "R05": "fracking microseismicity,\ncrowded picks",
    "R07": "dense nodal array,\nevents outside it",
    "R01": "geothermal field (Iceland),\ntiny events, many S picks",
    "nc": "San Andreas and Geysers,\nshallow, almost only P",
    "tx": "induced seismicity,\nwell-spread stations",
    "JMA": "dense national network,\ncrust to slab",
    "CM": "sparse stations,\nintermediate depth",
    "R09": "coastal line of stations,\ndeep events offshore",
    "ak": "long arc,\nlarge gaps offshore",
    "NOA": "land and islands,\nsmall events",
}
CORE_NAMES = {"R05": "ToC2ME", "R07": "LASSO", "R01": "COSEISMIQ", "nc": "N. California", "tx": "Texas", "JMA": "Japan",
              "CM": "Colombia", "R09": "N. Chile", "ak": "Alaska", "NOA": "Greece"}


def plot_core_networks(split, networks=None, ncols=5, save_path=None, dpi=DPI):
    """One map per core network: its stations and its test earthquakes coloured by depth, with what
    makes the network hard. ``split``: a loaded split with labels (e.g. ``bepad.load("test",
    networks=["core"])``)."""
    from .data import CORE_NETWORKS

    networks = list(networks or CORE_NETWORKS)
    ev = split.events.assign(network=split.events.window_id.str.split(".").str[0]) \
        .drop_duplicates(["network", "src_event_id"])
    st = split.window_stations.drop_duplicates(["network", "station"])
    norm = matplotlib.colors.LogNorm(1, 600)
    cmap = plt.get_cmap("viridis_r")
    nrows = int(np.ceil(len(networks) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(COL2, 1.9 * nrows + 0.4), squeeze=False)
    for ax, n in zip(axes.ravel(), networks):
        e, s_ = ev[ev.network == n], st[st.network == n]
        elon, slon = e.longitude.to_numpy(), s_.longitude.to_numpy()
        glob = n in ("ISC", "R08")
        if not glob and np.ptp(elon % 360) < np.ptp(elon):     # across the antimeridian (Aleutians)
            elon, slon = elon % 360, slon % 360
        ax.scatter(slon, s_.latitude, s=1 if glob or len(s_) > 500 else 3, marker="^", color=INK2, lw=0,
                   alpha=0.7, zorder=2, rasterized=True)
        ax.scatter(elon, e.latitude, s=1.2, c=(e.depth / 1e3).clip(1, 600), cmap=cmap, norm=norm, lw=0,
                   zorder=3, rasterized=True)
        if glob:
            x0, x1, y0, y1 = -180, 180, -70, 80
        else:                                          # zoom on the earthquakes, with stations around
            (x0, x1), (y0, y1) = np.nanpercentile(elon, [1, 99]), np.nanpercentile(e.latitude, [1, 99])
            k = 1 / max(np.cos(np.radians((y0 + y1) / 2)), 0.2)
            half = 0.75 * max((x1 - x0) / k, y1 - y0, 0.01)
            xc, yc = (x0 + x1) / 2, (y0 + y1) / 2
            x0, x1, y0, y1 = xc - half * k, xc + half * k, yc - half, yc + half
        ax.set(xlim=(x0, x1), ylim=(y0, y1), xticks=[], yticks=[])
        ax.set_aspect("auto")
        ax.grid(False)
        for sp in ax.spines.values():
            sp.set_visible(True)
            sp.set_color(BAND_C)
        km = 111.2 * (y1 - y0)                         # north-south size of the map
        ax.set_title(f"{n} · {CORE_NAMES.get(n, n)}", loc="left", fontweight="bold", fontsize=6.5)
        ax.set_xlabel(CORE_CHALLENGES.get(n, ""), fontsize=5.8, color=INK2, linespacing=1.15)
        ax.text(0.97, 0.04, f"{len(s_):,} stations" + ("" if glob else f"\nscale: ~{km:,.0f} km"),
                transform=ax.transAxes, ha="right", va="bottom", fontsize=4.8, color=INK2)
    for ax in axes.ravel()[len(networks):]:
        ax.axis("off")
    fig.subplots_adjust(wspace=0.08, hspace=0.45, bottom=0.17)
    cax = fig.add_axes([0.3, 0.05, 0.4, 0.018])
    cb = fig.colorbar(matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax, orientation="horizontal")
    cb.set_ticks([1, 10, 100, 600], labels=["1", "10", "100", "600"])
    cb.set_label("Earthquake depth [km]   ·   triangles: stations", fontsize=6)
    return _finish(fig, save_path, dpi)


def release_gallery(release_dir, cfg, out_dir=None, networks=None, split="test"):
    """All gallery figures of a release, written to ``<release>/figures`` (or ``out_dir``)."""
    from .data import Release

    rel = Release(release_dir)
    out = Path(out_dir or Path(release_dir) / "figures")
    model = rel.label_model
    nets = networks or rel.networks(split)
    axes = cfg.get("axes", {})
    ev_levels = tuple(axes.get("ev", {}).get("levels", {})) or ("sparse", "low", "med", "high")
    noise_levels = tuple(axes.get("noise", {}).get("levels", {})) or ("none", "low", "med", "high", "extreme")
    plot_label_model(model, save_path=out / "label_model.png")
    s_all = rel.load(split)
    plot_difficulty(s_all, ev_levels, noise_levels, save_path=out / "difficulty.png")
    plot_release_stats(s_all, save_path=out / "release_stats.png")
    stations = pd.read_parquet(Path(release_dir) / "stations.parquet")
    for n in nets:
        s = rel.load(split, networks=[n])
        rows = [lv for lv in noise_levels if lv in ("none", "med", "extreme")] or list(noise_levels)
        plot_scenario_grid(s, n, ev_levels, rows, save_path=out / f"scenarios_{n}.png")
        plot_gap_sweep(s, n, save_path=out / f"gap_sweep_{n}.png")
        if "sequence_type" in s.windows and s.windows.sequence_type.notna().any():
            plot_sequence_types(s, n, save_path=out / f"sequences_{n}.png")
        wid = f"{n}.{split}.ev-low__noise-med.00000"
        if wid in set(s.windows.window_id):
            w = s[wid]
            plot_window_anatomy(w, model=model, all_stations=stations[stations.network == n],
                                save_path=out / f"window_anatomy_{n}.png")
            plot_event_labels(w, model, save_path=out / f"event_labels_{n}.png")
        plt.close("all")
    return out
