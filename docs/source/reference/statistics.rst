Dataset statistics
==================

What is inside a BEPAD split: its earthquakes, stations, picks and windows. Every figure is drawn
from the release tables (``bepad.stats`` computes the tables, ``bepad.plots`` draws them), so it
describes exactly the earthquakes and picks that BEPAD contains. Statistics of the full source
catalogs, before BEPAD's selection, are in the `UTDQuake documentation
<https://utdquake.readthedocs.io>`_.

Networks are grouped by **scale**, from the 90th percentile of the distance of their real picks:
**local** (< 150 km), **regional** (150–1,500 km) and **global** (> 1,500 km).

.. note::

   The figures below come from the small development release (three networks, one per scale).
   With every network of v0.1 they become distributions over many networks.

Earthquakes
-----------

.. figure:: ../_static/figures/stats_events_overview.png
   :width: 100%

   The source earthquakes. (a) Epicentres. (b) Magnitude and (c) depth. (d) Azimuthal gap of the
   stations that picked them in the window. (e) Farthest station against magnitude: larger
   earthquakes are recorded farther away — the limit BEPAD respects when generating picks.
   (f) Number of windows each earthquake appears in.

.. literalinclude:: ../../gallery/stats_events_overview.py

Stations
--------

.. figure:: ../_static/figures/stats_station_geometry.png
   :width: 100%

   Per window: (a) stations available, (b) stations with real picks, (c) median distance between
   neighbouring stations, (d) aperture (widest distance between two stations).

.. literalinclude:: ../../gallery/stats_station_geometry.py

Picks
-----

.. figure:: ../_static/figures/stats_picks_overview.png
   :width: 100%

   (a) Travel time against distance of the real P and S picks. (b) Real picks per earthquake.
   (c) Distance from each pick to its earthquake (noise: to the nearest one) — noise is spread over
   the same distances as real picks. (d) ``prob`` of real and generated picks (noise is 0).

.. literalinclude:: ../../gallery/stats_picks_overview.py

Earthquakes close in space and time
-----------------------------------

.. figure:: ../_static/figures/stats_event_proximity.png
   :width: 100%

   Every pair of earthquakes in the same window: distance between epicentres against time between
   origins. Pairs close in both (lower left) are the hardest to associate: their picks reach the
   same stations at the same time.

.. literalinclude:: ../../gallery/stats_event_proximity.py

Representative windows
----------------------

.. figure:: ../_static/figures/stats_representative_windows.png
   :width: 100%

   An easy, a typical and a hard window (10th, 50th and 90th percentile of the number of
   earthquakes active at once) for one network of each scale.

.. literalinclude:: ../../gallery/stats_representative_windows.py

The tables
----------

.. code-block:: python

   import bepad
   from bepad import stats

   test = bepad.load("test")
   stats.source_events(test)      # one row per source earthquake
   stats.event_pairs(test)        # one row per pair of earthquakes in a window
   stats.window_geometry(test)    # one row per window: stations, spacing, aperture
   stats.pick_distances(test)     # one row per pick: type, distance, travel time
   stats.network_scales(test)     # network -> local / regional / global
