"""Geometry, phase families and deterministic seeding."""

from __future__ import annotations

import hashlib

import numpy as np

EARTH_RADIUS_KM = 6371.0

#: Same P/S families hypogt uses (hypogt.graph.utils.P_PHASES/S_PHASES).
P_PHASES = frozenset({"P", "Pn", "Pg"})
S_PHASES = frozenset({"S", "Sn", "Sg"})


def phase_family(phase):
    """Map raw phase codes (Pn, Pg, Sg, ...) to "P"/"S"; anything else -> None."""
    if phase in P_PHASES:
        return "P"
    if phase in S_PHASES:
        return "S"
    return None


def haversine_km(lat0, lon0, lat1, lon1):
    lat0, lon0, lat1, lon1 = (np.radians(np.asarray(x, dtype=float)) for x in (lat0, lon0, lat1, lon1))
    a = np.sin((lat1 - lat0) / 2) ** 2 + np.cos(lat0) * np.cos(lat1) * np.sin((lon1 - lon0) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def azimuthal_gap_deg(lat0, lon0, lats, lons):
    """Largest empty angular sector (deg) seen from (lat0, lon0).

    Same formula as hypogt.data.pre_transform._azimuthal_gap_deg; NaN for
    fewer than 2 stations.
    """
    lats = np.asarray(lats, dtype=float)
    lons = np.asarray(lons, dtype=float)
    if len(lats) < 2:
        return np.nan
    lat0_r, lon0_r = np.radians(lat0), np.radians(lon0)
    lat_r, lon_r = np.radians(lats), np.radians(lons)
    dlon = lon_r - lon0_r
    bearing = np.arctan2(
        np.sin(dlon) * np.cos(lat_r),
        np.cos(lat0_r) * np.sin(lat_r) - np.sin(lat0_r) * np.cos(lat_r) * np.cos(dlon),
    )
    b = np.sort(np.degrees(bearing) % 360.0)
    return float(np.diff(np.append(b, b[0] + 360.0)).max())


def stable_uniform(key: str, salt: str = "") -> float:
    """Deterministic pseudo-random number in [0, 1) from a string key.

    Uses sha256, never Python's hash() (which is salted per process).
    """
    h = hashlib.sha256(f"{salt}|{key}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def stable_seed(*parts) -> int:
    """Deterministic 63-bit seed from any sequence of parts."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(h[:8], "big") >> 1
