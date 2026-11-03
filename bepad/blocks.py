"""Release files stored in blocks, so one window can be read without reading the whole file.

The picks, events and window_stations tables of a release are sorted by ``window_id`` (keeping the
order of the rows inside each window) and written in row groups ("blocks") of about
:data:`BLOCK_ROWS` rows (per table), compressed with zstd. A block holds whole windows only. Parquet keeps the first and last
``window_id`` of every block, so finding a window needs no separate index. The windows table keeps
its own order (it is small and read whole).

Files in the older layout (not sorted) still work: they are read whole.
"""

from __future__ import annotations

import bisect
import os
from pathlib import Path

import numpy as np
import pandas as pd

# Rows per block. Smaller blocks read one window faster but compress less; window_stations has two
# short columns, so its blocks are larger (measured on tx and R07: about the old file sizes).
BLOCK_ROWS = {"picks": 5_000, "events": 5_000, "window_stations": 20_000}
COMPRESSION = "zstd"
BLOCKED_TABLES = ("picks", "events", "window_stations")
LAYOUT = "blocks-v1"          # recorded in manifest.json


def write_blocked(df, path, block_rows=5_000):
    """Write ``df`` sorted by window_id, in blocks of about ``block_rows`` rows of whole windows."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = Path(path)
    df = df.sort_values("window_id", kind="stable", ignore_index=True)
    ids = df["window_id"].to_numpy()
    starts = np.flatnonzero(np.r_[True, ids[1:] != ids[:-1]]) if len(ids) else np.array([], int)
    block = starts // block_rows                                   # block of each window, by its first row
    bounds = list(starts[np.r_[True, block[1:] != block[:-1]]]) + [len(df)] if len(ids) else [0, 0]
    schema = pa.Schema.from_pandas(df, preserve_index=False)
    tmp = path.with_suffix(".tmp")
    with pq.ParquetWriter(tmp, schema, compression=COMPRESSION) as w:
        for a, b in zip(bounds[:-1], bounds[1:]):
            w.write_table(pa.Table.from_pandas(df.iloc[a:b], schema=schema, preserve_index=False),
                          row_group_size=max(b - a, 1))
    os.replace(tmp, path)


def _bounds(md):
    """(first, last) window_id of every row group, or None without statistics."""
    col = md.schema.to_arrow_schema().get_field_index("window_id")
    out = []
    for i in range(md.num_row_groups):
        st = md.row_group(i).column(col).statistics
        if st is None or not st.has_min_max:
            return None
        out.append((st.min, st.max))
    return out


def block_bounds(pf):
    """(first, last) window_id per block if the file is in blocks (sorted, no window across two
    blocks), else None."""
    b = _bounds(pf.metadata)
    if b is None or any(b[i][1] >= b[i + 1][0] for i in range(len(b) - 1)):
        return None
    return b


def check_blocked(path):
    """Problems of one file (empty list = in blocks): sorted rows, whole windows per block."""
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(path)
    if pf.metadata.num_rows == 0:
        return []
    problems = []
    ids = pf.read(columns=["window_id"]).column("window_id").to_numpy(zero_copy_only=False)
    if not (ids[1:] >= ids[:-1]).all():
        problems.append(f"{path}: rows are not sorted by window_id")
    if block_bounds(pf) is None:
        problems.append(f"{path}: a window is split across two blocks (or no statistics)")
    return problems


def read_rows(path, window_ids, columns=None, batch_size=200_000):
    """Rows of one file whose window is in ``window_ids``: only the blocks that hold them are read
    (older files: read in batches, keeping the matching rows)."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(path, pre_buffer=False, buffer_size=1 << 20)
    schema = pa.schema([pf.schema_arrow.field(c) for c in columns]) if columns else pf.schema_arrow
    ids = pa.array(sorted(window_ids), type=schema.field("window_id").type)
    b = block_bounds(pf)
    if b is not None:
        lo = [x[0] for x in b]
        groups = sorted({g for w in ids.to_pylist() if (g := bisect.bisect_right(lo, w) - 1) >= 0 and w <= b[g][1]})
        batches = pf.iter_batches(batch_size=batch_size, row_groups=groups, columns=columns) if groups else []
    else:
        batches = pf.iter_batches(batch_size=batch_size, columns=columns)
    parts = [x.filter(pc.is_in(x.column("window_id"), value_set=ids)) for x in batches]
    return pa.Table.from_batches(parts, schema=schema).to_pandas()


class BlockReader:
    """One file, read one window at a time. Keeps the last block in memory, so windows read in
    order cost one block read per block. Safe in forked DataLoader workers (reopens per process).
    An older file (not in blocks) is read whole once."""

    def __init__(self, path, columns=None):
        self.path, self.columns = Path(path), columns
        self._pid = None

    def __getstate__(self):                     # pickled DataLoader workers reopen the file
        return {"path": self.path, "columns": self.columns, "_pid": None}

    def _open(self):
        import pyarrow.parquet as pq

        self._pf = pq.ParquetFile(self.path)
        b = block_bounds(self._pf)
        self._lo = None if b is None else [x[0] for x in b]
        self._hi = None if b is None else [x[1] for x in b]
        self._key, self._df, self._rows = None, None, {}
        self._pid = os.getpid()

    def _load(self, key):
        if key != self._key:
            t = self._pf.read(columns=self.columns) if key == "all" else \
                self._pf.read_row_group(key, columns=self.columns)
            self._df = t.to_pandas()
            self._rows = self._df.groupby("window_id", sort=False).indices
            self._key = key

    def window(self, wid):
        """The rows of window ``wid`` (an empty frame if it has none)."""
        if self._pid != os.getpid():
            self._open()
        if self._lo is None:
            self._load("all")
        else:
            g = bisect.bisect_right(self._lo, wid) - 1
            if g < 0 or wid > self._hi[g]:
                return self._empty()
            self._load(g)
        rows = self._rows.get(wid)
        return self._df.iloc[rows].reset_index(drop=True) if rows is not None else self._empty()

    def _empty(self):
        if self._df is None:
            self._load(0 if self._lo else "all")
        return self._df.iloc[:0].reset_index(drop=True)


def reblock(release_dir, networks=None, splits=None, block_rows=None):
    """Rewrite the blocked tables of an existing release in blocks (same rows, same content)."""
    release_dir = Path(release_dir)
    done = []
    for split_dir in sorted(p for p in release_dir.iterdir() if (p / "windows").is_dir()):
        if splits is not None and split_dir.name not in splits:
            continue
        for table in BLOCKED_TABLES:
            for f in sorted((split_dir / table).glob("network=*.parquet")):
                if networks is not None and f.stem.split("=", 1)[1] not in networks:
                    continue
                write_blocked(pd.read_parquet(f), f, block_rows or BLOCK_ROWS[table])
                done.append(f)
    return done
