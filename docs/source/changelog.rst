Changelog
=========

0.1.1
-----

Same data (BEPAD v0.1).

* ``bepad.load(..., max_windows=, scenarios=, window_ids=)``: load only some windows, with little
  memory (only their rows are read). With ``window_ids`` alone, only their networks are downloaded.
* ``Associator.run`` takes the same options and reads only those windows; ``max_windows`` is now
  the same fixed random sample as in ``bepad.load`` (was: the first windows).
* Documentation examples load a few windows; every one-window figure gives its ``window_id``.

0.1.0 (BEPAD v0.1)
------------------

First public release, built from UTDQuake 1.0 (Hugging Face commit ``8524c6f0``).

* Every seismic network of UTDQuake 1.0, with UTDQuake's network codes (``R01``–``R09`` for the
  research catalogs, e.g. ``R08`` = ComCat events deeper than 30 km, formerly ``comcat_deep30``).
* Stations are ``NET.STA`` (FDSN network and station code); picks join stations on it.
  UTDQuake 1.0 gives the FDSN code of every pick and station, including the ISC stations it
  resolved from the ISC station registry.
* No pick is ever merged or removed: two earthquakes' picks close in time at one station are both
  kept, each with its true earthquake (columns ``ambiguous``, ``n_merged_picks`` and
  ``n_ambiguous_picks`` and the window setting ``min_pick_sep_s`` are gone).
* A network with fewer than 200 quality-controlled earthquakes is test only
  (``split.test_only_below`` in ``configs/pool.yaml``).
* A network without enough paired P/S picks for its own S/P travel-time ratio uses the ratio fitted
  on all networks (``sp_ratio`` of ``label_model.json``).
* The pool and release manifests record the UTDQuake version and Hugging Face revision.
* ``pipeline/``: the recipe of a release as a SLURM chain (pool, release, baselines).

Development versions (not released)
-----------------------------------

dev 0.5
~~~~~~~

* Every earthquake in a window has ≥ 4 real P picks on ≥ 3 stations inside it (edge events too).
* Window counts per scenario: 1,000 train / 200 val / 100 test per network.
* Location metrics for associators that also locate; ``eqt-utils_simple`` associator.
* ``bepad.stats`` and dataset figures: earthquakes, stations, picks, earthquake pairs,
  representative windows.
* Fix: station codes shared by two FDSN networks (e.g. AV.SPU and UU.SPU) are kept apart.

dev 0.4
~~~~~~~

* ``bepad.Associator``: a template class; ``bepad new`` / ``bepad run`` / ``bepad submit``.
* Leaderboard on Hugging Face: submissions checked by recomputing scores from predictions;
  ``bepad leaderboard build`` / ``review``.
* ``plot_prediction``: truth vs an associator's grouping, errors circled.
* Figure gallery page; every figure in the docs shows the code that made it (``docs/gallery``).

dev 0.3
~~~~~~~

* Three kinds of picks: real, generated (inside an earthquake's predicted-arrival band) and noise
  (never inside a band). New labels ``pick_type``, ``real``, ``prob``, ``sigma_s``.
* Label model fitted once on all networks (``label_model.json``).
* Split at random per earthquake, each network independently.
* Package: ``bepad.load``, ``bepad.evaluate``, ``bepad.torch``, ``bepad.plots``; building code in
  ``bepad.build``.
* Figure gallery (400 dpi).

dev 0.2
~~~~~~~

* Sharded releases, loader, evaluation command, PyTorch datasets, PyOcto example.

dev 0.1
~~~~~~~

* First pool, window generator and metrics.
