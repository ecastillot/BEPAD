"""UTDQuake tables as the pool reads them (UTDQuake 1.0 and later).

UTDQuake names things this way:

* ``utdq_net``: the UTDQuake network, i.e. the catalog or project that reported the
  events and picks (``tx``, ``AEIC``, ``R05`` ...). Key of every UTDQuake table.
* ``network``: the FDSN code of the station that recorded a pick (stations and picks
  tables only).

In BEPAD, ``network`` is the UTDQuake network (it names windows, pool folders and release
files), the FDSN code of a station is ``station_network``, and a station is ``NET.STA``
(``2T.EF51``): unique within a UTDQuake network, where a plain code may not be (``UU.SPU`` in
Utah and ``AV.SPU`` in Alaska are both in ISC). UTDQuake is read from ``$UTDQUAKE_ROOT`` at
``$UTDQUAKE_REVISION`` (a Hugging Face commit; ``main`` if unset).
"""
from __future__ import annotations

import os

import pandas as pd


def revision():
    """The UTDQuake Hugging Face revision the build reads (``UTDQUAKE_REVISION``), None = main."""
    return os.environ.get("UTDQUAKE_REVISION", "").strip() or None


def network_table():
    """UTDQuake's (non-DAS) network table, one row per ``utdq_net``: the local copy under
    ``$UTDQUAKE_ROOT`` if there is one (parallel pool jobs then never query the Hub), else the Hub."""
    import utdquake as utdq

    ds = utdq.Dataset(das=False)
    try:
        return ds.local_networks
    except FileNotFoundError:
        return ds.networks


def list_networks():
    return sorted(network_table()["utdq_net"].astype(str))


def station_key(network, station):
    """``NET.STA`` from FDSN network and station codes (arrays or Series)."""
    return pd.Series(network, dtype="string").str.cat(pd.Series(station, dtype="string").to_numpy(), sep=".") \
        .to_numpy(dtype=object)


def load_network(name):
    """(events, picks, stations) of one UTDQuake network.

    The ``utdq_net`` column is dropped; picks and stations get ``station_network`` (FDSN code)
    and ``station`` = ``NET.STA``, so picks join stations on ``station``.
    """
    import utdquake as utdq

    net = utdq.Dataset(das=False).get_network(name=name)
    events = net.events.drop(columns=["utdq_net"], errors="ignore")
    out = []
    for df in (net.picks, net.stations):
        df = df.drop(columns=["utdq_net"], errors="ignore").rename(columns={"network": "station_network"})
        df["code"] = df["station"].astype(str)
        df["station"] = station_key(df["station_network"], df["code"])
        out.append(df)
    return events, out[0], out[1]


def network_info(name):
    """Provenance of one network for the pool manifest (catalog, UTDQuake dataset version)."""
    try:
        row = network_table().set_index("utdq_net").loc[name]
        return {k: (None if pd.isna(row.get(k)) else str(row.get(k)))
                for k in ("catalog", "catalog_type", "dataset_version", "provider")}
    except Exception as exc:  # informative only
        return {"error": repr(exc)}
