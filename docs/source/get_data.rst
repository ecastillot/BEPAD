Get the data
============

.. image:: https://colab.research.google.com/assets/colab-badge.svg
   :target: https://colab.research.google.com/github/ecastillot/BEPAD/blob/main/notebooks/01_get_the_data.ipynb
   :alt: Open in Colab

**Try it in Colab:** load windows, look at one, choose windows by their metadata (2 minutes, nothing to install).

BEPAD is a finished dataset on Hugging Face. You download it; you never build it.

With the ``bepad`` package
--------------------------

.. code-block:: bash

   pip install bepad

.. code-block:: python

   import bepad

   test = bepad.load("test", networks=["tx", "CM"], max_windows=20)   # 20 windows per network
   print(test)                                        # <bepad.Split 40 windows, ...>

   w = test[0]          # one window (or: for w in test: ...)
   w.picks              # the picks of the window
   w.stations           # the stations of the window, with coordinates
   w.events             # the true earthquakes (answers)

Only the files you ask for are downloaded, and they are cached, so the second call is instant.
``bepad.load("train")`` and ``bepad.load("val")`` work the same way.

``max_windows`` is a fixed random sample, the same every time. Without it you get every window of
the networks, which can be large (the whole test split: 83 million picks; R07 train alone: 20 GB in
memory). Other ways to choose windows (only their rows are read):

.. code-block:: python

   bepad.load("test", networks=["tx"], scenarios="ev-med__noise-high")
   bepad.load("test", window_ids=["tx.test.ev-low__noise-med.00000"])  # one window
   bepad.load("test", networks="core")                                 # the 10 BEPAD-10 networks
   bepad.load("train", lazy=True)        # every window, each read from disk when you ask for it

Look at a window
----------------

.. code-block:: python

   from bepad.plots import plot_window_anatomy

   one = bepad.load("test", window_ids=["tx.test.ev-low__noise-med.00000"])     # the window below
   plot_window_anatomy(one[0], model=one.release.label_model, save_path="window.png")

.. figure:: _static/figures/window_anatomy_tx.png
   :width: 100%

What the panels and labels mean: :doc:`window`. More figures, each with its code:
:doc:`figures`.

.. _choose-windows:

Choose windows
--------------

Every window has a row of metadata: its network, scenario, number of earthquakes, noise, gap,
magnitudes and more (all columns: :doc:`reference/format`). Filter it, then load only the windows
you chose:

.. code-block:: python

   rel = bepad.open(bepad.download(splits=("test",), networks=["tx", "CM"]))
   meta = rel.table("test", "windows")                   # metadata only: one row per window, small

   crowded = meta[(meta.max_concurrent_events >= 5) & (meta.noise_ratio_target >= 1)]
   test = bepad.load("test", window_ids=crowded.window_id)

Some useful columns: ``scenario``, ``n_events``, ``max_concurrent_events`` (earthquakes active at
the same time), ``noise_ratio`` (noise picks per real pick), ``gap_max_deg`` (azimuthal gap),
``mag_min`` / ``mag_max``, ``depth_max_km``, ``n_stations``.

**By station.** ``window_stations`` lists the stations that were operating during each window
(whether or not they picked). In many networks the stations change over the years:

.. code-block:: python

   rel = bepad.open(bepad.download(splits=("test",), networks=["AEIC"]))
   ws = rel.table("test", "window_stations")
   ids = ws.loc[ws.station == "AK.PS07", "window_id"].unique()    # 613 of the 2,280 AEIC windows
   test = bepad.load("test", window_ids=ids)

The stations that recorded the earthquakes are in the picks (``w.picks.station``); their number per
window is ``n_active_stations`` in the metadata.

The same ``window_ids`` work everywhere: ``bepad.load``, ``Associator.run`` (:doc:`benchmark`) and
``ReleaseWindowDataset`` for training (:doc:`train`). ``rel.table`` also reads ``"events"``,
``"picks"`` and ``"stations"``.

Without the bepad package
-------------------------

Every table is a plain Parquet file, readable with pandas (and ``huggingface_hub`` for the
``hf://`` paths):

.. code-block:: python

   import pandas as pd

   base = "hf://datasets/ecastillot/BEPAD/v0.2"
   picks = pd.read_parquet(f"{base}/test/picks/network=tx.parquet")
   windows = pd.read_csv(f"{base}/metadata/windows_test.csv")

How much data
-------------

2,689,700 windows in three splits, from 91 networks: :doc:`reference/statistics`.
