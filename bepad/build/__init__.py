"""Building BEPAD (maintainers only).

Users never need this subpackage: they download the finished dataset with
``bepad.load``. The build runs in four steps:

    pool.py     UTDQuake network -> quality-controlled events, picks, stations
    labels.py   fit the label model: detectability q(M, r), timing sigma(r),
                per-network travel-time curves and S/P ratios
    windows.py  pool + label model + seed -> one window
    release.py  thousands of windows per network/split/scenario -> Parquet
"""
