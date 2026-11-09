Dataset structure
=================

How a BEPAD release is organized: its folders, how the tables fit together, and how the files are
stored. The columns of every table are in :doc:`format`.

Folders
-------

A release is a folder of Parquet files. Each table has **one file per network**, so you download
only the networks you need:

.. code-block:: text

   v0.2/
   ├── train/  val/  test/
   │   ├── windows/network=<name>.parquet          one row per window
   │   ├── events/network=<name>.parquet           one row per earthquake in a window
   │   ├── window_stations/network=<name>.parquet  stations operating in each window
   │   └── picks/network=<name>.parquet            one row per pick
   ├── stations.parquet          station coordinates (all splits)
   ├── metadata/                 windows_<split>.csv, networks.csv (statistics)
   ├── label_model.json          predicted arrivals, σ(r), prob (see Labels)
   ├── scenarios.json            parameters of each scenario
   └── manifest.json             versions, configuration, counts, file layout

How the tables fit together
---------------------------

Every table except ``stations`` has a ``window_id`` column (for example
``tx.test.ev-low__noise-med.00000``: network, split, scenario, number):

.. list-table::
   :header-rows: 1
   :widths: 20 30 50

   * - Table
     - One row per
     - Links
   * - ``windows``
     - window
     - ``window_id``: the key of everything else
   * - ``events``
     - earthquake of a window
     - (``window_id``, ``event_idx``)
   * - ``stations``
     - station
     - (``network``, ``station``)
   * - ``window_stations``
     - station operating in a window
     - (``window_id``, ``station``) → ``stations`` for coordinates
   * - ``picks``
     - pick
     - (``window_id``, ``pick_idx``); ``event_idx`` → ``events`` (−1 = noise)

For example, window ``tx.test.ev-low__noise-med.00000`` has 1 row in ``windows``, 3 in ``events``
(its earthquakes), 317 in ``window_stations`` and 151 in ``picks``. ``bepad.load`` joins them for
you (``w.picks``, ``w.stations``, ``w.events``); by hand:

.. code-block:: python

   import pandas as pd

   base, wid = "v0.2/test", "tx.test.ev-low__noise-med.00000"
   one = [("window_id", "==", wid)]
   picks = pd.read_parquet(f"{base}/picks/network=tx.parquet", filters=one)
   events = pd.read_parquet(f"{base}/events/network=tx.parquet", filters=one)
   picks = picks.merge(events[["event_idx", "magnitude"]], on="event_idx", how="left")   # noise: NaN

.. _stored-in-blocks:

Stored in blocks
----------------

A network file holds thousands of windows: R07's train picks are 67 million rows. To read one
window without reading the whole file, the **events, window_stations and picks** files are sorted
by ``window_id`` and stored in **blocks** (Parquet row groups) of a few thousand rows: about 5,000
for picks and events, 20,000 for window_stations. A block holds whole windows only, and records its
first and last ``window_id``, so a reader goes straight to the block it needs. Inside a window the
rows keep their order (picks by time). The ``windows`` files are small and keep their own order.

What it means for you:

* **With bepad, nothing to do.** ``bepad.load(window_ids=...)``, ``bepad.load(lazy=True)`` and
  ``ReleaseWindowDataset`` read only the blocks they need: about 10 ms per window, so even the
  whole train split can be used for training (:doc:`../train`).
* **Without bepad**, a ``filters`` on ``window_id`` (as above) reads only the matching blocks
  (about 0.4 s for one window of the largest file).
* **Same content, same size.** Blocks change how the rows are stored, not the rows: the files are
  about as large as unsorted ones (zstd compression).
* **Older downloads** (no ``layout`` entry in ``manifest.json``) are not sorted. They still load,
  but bepad reads them whole; download again to get blocks.
