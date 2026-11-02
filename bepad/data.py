"""Get BEPAD data: download from Hugging Face (or open a local copy) and read windows.

    >>> import bepad
    >>> test = bepad.load("test", networks=["tx"], labels=False)   # downloads only what is needed
    >>> for w in test:
    ...     w.picks      # pick_idx, station, phase, t_rel_s, time
    ...     w.stations   # station, latitude, longitude, elevation
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

#: Columns of picks.parquet that carry ground truth. Never give them to an associator.
LABEL_COLUMNS = ("event_idx", "pick_type", "real", "prob", "sigma_s", "in_scorable_event",
                 "src_event_id", "src_pick_id")
INPUT_COLUMNS = ("window_id", "pick_idx", "station", "phase", "t_rel_s", "time")


@dataclass
class WindowData:
    window_id: str
    meta: pd.Series            # row of windows.parquet
    picks: pd.DataFrame        # picks of this window (labels only if loaded with labels=True)
    stations: pd.DataFrame     # stations available in this window, with coordinates
    events: pd.DataFrame | None = None  # true events (labels=True only)


class Split:
    """All windows of one split (optionally a subset of networks)."""

    def __init__(self, windows, picks, window_stations, stations, events=None, labels=True):
        self.windows = windows.reset_index(drop=True)
        self.picks = picks
        self.events = events
        self.labels = labels
        net = self.windows.set_index("window_id")["network"]
        ws = window_stations.assign(network=window_stations["window_id"].map(net))
        self.window_stations = ws.merge(stations, on=["network", "station"], how="left")
        self._pick_rows = picks.groupby("window_id", sort=False).indices
        self._sta_rows = self.window_stations.groupby("window_id", sort=False).indices
        self._ev_rows = events.groupby("window_id", sort=False).indices if events is not None else {}

    def __len__(self):
        return len(self.windows)

    def __iter__(self):
        for i in range(len(self.windows)):
            yield self[i]

    def __getitem__(self, i):
        if isinstance(i, str):
            i = int(self.windows.index[self.windows["window_id"] == i][0])
        meta = self.windows.iloc[i]
        wid = meta["window_id"]
        picks = self.picks.iloc[self._pick_rows.get(wid, [])].reset_index(drop=True)
        st = self.window_stations.iloc[self._sta_rows.get(wid, [])]
        st = st[["station", "latitude", "longitude", "elevation"]].reset_index(drop=True)
        ev = self.events.iloc[self._ev_rows[wid]].reset_index(drop=True) if wid in self._ev_rows else None
        return WindowData(wid, meta, picks, st, ev)

    def __repr__(self):
        nets = self.windows["network"].nunique() if len(self.windows) else 0
        return (f"<bepad.Split {len(self)} windows, {len(self.picks)} picks, {nets} networks, "
                f"labels={self.labels}>")


class Release:
    """A BEPAD release folder (local copy of the Hugging Face dataset or a local build)."""

    def __init__(self, path):
        self.path = Path(path)
        if not (self.path / "stations.parquet").exists():
            raise FileNotFoundError(f"{self.path} is not a BEPAD release (no stations.parquet)")
        mf = self.path / "manifest.json"
        self.manifest = json.loads(mf.read_text()) if mf.exists() else {}

    @property
    def splits(self):
        return [d.name for d in sorted(self.path.iterdir()) if (d / "windows").is_dir()]

    def networks(self, split="test"):
        return sorted(f.stem.split("=", 1)[1] for f in (self.path / split / "windows").glob("network=*.parquet"))

    @property
    def label_model(self):
        """The label model of this release (predicted arrivals, sigma(r), prob)."""
        from .build.labels import LabelModel

        return LabelModel.load(self.path / "label_model.json")

    def scenarios(self):
        return json.loads((self.path / "scenarios.json").read_text())

    def _read(self, split, table, networks, columns=None):
        files = sorted((self.path / split / table).glob("network=*.parquet"))
        if networks is not None:
            keep = {f"network={n}.parquet" for n in networks}
            files = [f for f in files if f.name in keep]
        if not files:
            raise FileNotFoundError(f"no {table} files for split={split!r}, networks={networks}")
        return pd.concat([pd.read_parquet(f, columns=columns) for f in files], ignore_index=True)

    def load(self, split, networks=None, labels=True):
        """Load one split. ``labels=False`` returns only what an associator may use."""
        cols = None if labels else list(INPUT_COLUMNS)
        s = Split(
            windows=self._read(split, "windows", networks),
            picks=self._read(split, "picks", networks, columns=cols),
            window_stations=self._read(split, "window_stations", networks),
            stations=pd.read_parquet(self.path / "stations.parquet"),
            events=self._read(split, "events", networks) if labels else None,
            labels=labels,
        )
        s.release, s.name = self, split
        return s

    def __repr__(self):
        return f"<bepad.Release {self.path.name}: splits={self.splits}>"


REPO_ID = "ecastillot/BEPAD"
RELEASE = "v0.1"                     # the current release (a folder of the Hugging Face dataset)
# The core test set: every leaderboard entry must run these networks; the default leaderboard
# view ranks methods by their mean over them. ``"core"`` selects them (``--networks core``).
CORE_NAME = "BEPAD-10"
CORE_NETWORKS = ["R05", "R07", "R01", "nc", "tx", "JMA", "CM", "R09", "ak", "NOA"]


def _networks(networks):
    """``"core"`` in a list of networks stands for the core networks."""
    if networks is None:
        return None
    networks = [networks] if isinstance(networks, str) else list(networks)
    return list(dict.fromkeys(m for n in networks for m in (CORE_NETWORKS if n == "core" else [n])))


def download(release=RELEASE, splits=("test",), networks=None, repo_id=REPO_ID, local_dir=None):
    """Download (and cache) part of a release from Hugging Face; returns the local release folder.

    Only the requested splits/networks are fetched, plus the small shared files
    (stations, scenarios, label model, manifest). Re-running is free: files are cached.
    """
    from huggingface_hub import snapshot_download

    networks = _networks(networks)
    patterns = [f"{release}/*.json", f"{release}/stations.parquet", f"{release}/metadata/*"]
    for sp in splits:
        if networks is None:
            patterns.append(f"{release}/{sp}/*")
        else:
            patterns += [f"{release}/{sp}/*/network={n}.parquet" for n in networks]
    path = snapshot_download(repo_id, repo_type="dataset", allow_patterns=patterns, local_dir=local_dir)
    return Path(path) / release


def open(path):  # noqa: A001 -- mirrors the usual `dataset.open` idiom
    """Open a local release folder."""
    return Release(path)


def load(split="test", networks=None, labels=True, release=RELEASE, root=None, repo_id=REPO_ID):
    """Load one split as a :class:`Split` (iterate it to get windows).

    ``root``: a local release folder (default: the ``BEPAD_ROOT`` environment
    variable); if neither is set, the data are downloaded from Hugging Face
    (``repo_id``, ``release``) and cached.
    ``labels=False`` returns only what an associator may use. ``networks=["core"]``: the
    :data:`CORE_NETWORKS`.
    """
    networks = _networks(networks)
    root = root or os.environ.get("BEPAD_ROOT")        # a local copy, e.g. export BEPAD_ROOT=data/releases/v0.1
    path = Path(root) if root else download(release, splits=(split,), networks=networks, repo_id=repo_id)
    return Release(path).load(split, networks=networks, labels=labels)


def predictions_frame(window_ids, pick_idx, pred_event):
    """Build a predictions table in the expected format."""
    return pd.DataFrame({"window_id": window_ids, "pick_idx": pick_idx, "pred_event": pred_event}) \
        .astype({"pick_idx": "int64", "pred_event": "int64"})
