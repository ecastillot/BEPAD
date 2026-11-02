"""eqt-utils_simple: the simple associator of EQTransformer, adapted to BEPAD.

Idea taken from ``EQTransformer/utils/associator.py`` (``run_associator``) by
S. Mostafa Mousavi -- EQTransformer, Mousavi et al. (2020), Nature Communications;
https://github.com/smousavi05/EQTransformer, MIT License (c) 2020-2025 S. Mostafa Mousavi.
This is a re-implementation of the idea for BEPAD windows, not a copy of that code.

How it works (as in the original):
  1. every station has DETECTIONS, each with a start time;
  2. the timeline is cut into fixed, non-overlapping windows of ``moving_window_s`` (15 s);
  3. the detections starting in one window whose stations number >= ``pair_n`` (3) form an event;
     detections of smaller groups are left unassociated;
  4. the event is placed at the station of its first detection, 5 km deep.

Adaptation to BEPAD: EQTransformer outputs one detection per station and event
(a P, an S and an event start time). BEPAD gives single picks, so detections are
rebuilt first: at each station, a P and the next S within ``max_sp_s`` form one
detection starting at the P time; a lone P or S is a detection starting at its own time.
The origin time is set to the first arrival of the event (the original has none).
"""

import numpy as np
import pandas as pd

import bepad


class Associator(bepad.Associator):
    name = "eqt-utils_simple"
    version = "0.1"
    authors = "BEPAD maintainers (adaptation); S. M. Mousavi (original idea, EQTransformer)"
    paper = ""        # Mousavi et al. (2020), Nature Communications -- EQTransformer
    code = "https://github.com/smousavi05/EQTransformer"
    method_type = "classical"
    training = "none"
    description = ("EQTransformer's simple associator: per-station detections grouped in fixed 15 s windows; "
                   ">= 3 stations make an event, located at its first station.")

    def _detections(self, picks):
        """One row per detection: start time, station, the pick_idx it contains."""
        max_sp = self.config["max_sp_s"]
        det = []
        for station, g in picks.sort_values("t_rel_s").groupby("station"):
            used = set()
            ps, ss = g[g.phase == "P"], g[g.phase == "S"]
            for _, p in ps.iterrows():
                s = ss[(ss.t_rel_s > p.t_rel_s) & (ss.t_rel_s - p.t_rel_s <= max_sp) & ~ss.pick_idx.isin(used)]
                members = [p.pick_idx]
                if len(s):
                    members.append(s.pick_idx.iloc[0])
                    used.add(s.pick_idx.iloc[0])
                det.append((p.t_rel_s, station, members))
            for _, s in ss[~ss.pick_idx.isin(used)].iterrows():
                det.append((s.t_rel_s, station, [s.pick_idx]))
        return pd.DataFrame(det, columns=["start", "station", "members"]).sort_values("start")

    def associate(self, picks, stations):
        labels = np.full(len(picks), -1, dtype=np.int64)
        if len(picks) == 0:
            return labels
        pos = {pi: i for i, pi in enumerate(picks.pick_idx)}
        det = self._detections(picks)
        w, n_min = self.config["moving_window_s"], self.config["pair_n"]
        st = stations.set_index("station")
        events, k = [], 0
        t = det.start.min()
        while t <= det.start.max():
            g = det[(det.start >= t) & (det.start < t + w)]
            if g.station.nunique() >= n_min:
                for members in g.members:
                    for pi in members:
                        labels[pos[pi]] = k
                first = g.iloc[0]
                events.append({"event": k, "latitude": st.at[first.station, "latitude"],
                               "longitude": st.at[first.station, "longitude"],
                               "depth_km": self.config["depth_km"], "t0_rel_s": first.start})
                k += 1
            t += w
        return labels, pd.DataFrame(events, columns=["event", "latitude", "longitude", "depth_km", "t0_rel_s"])
