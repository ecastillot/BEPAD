Metrics
=======

The metrics follow `Puente Huerta et al. (2025), Seismica
<https://seismica.library.mcgill.ca/article/view/1559>`_.

**Matching.** In each window, true and predicted earthquakes are paired one-to-one to maximise
shared picks (Hungarian algorithm). A pair counts as a match when it shares at least 3 picks.
Every true earthquake counts: each one has ≥ 4 real P picks on ≥ 3 stations inside its window.

Counts are summed over all windows, then turned into ratios.

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Metric
     - Definition
   * - Event precision
     - matched / predicted earthquakes
   * - Event recall
     - matched / true earthquakes
   * - Pick precision
     - picks assigned to the right earthquake / picks you assigned to any earthquake
   * - Pick recall
     - picks assigned to the right earthquake / picks of all earthquakes (real and generated)
   * - Noise rejection
     - noise picks left unassociated / all noise picks
   * - Split rate
     - true earthquakes spread over ≥ 2 predicted earthquakes
   * - Merge rate
     - predicted earthquakes that contain ≥ 2 true earthquakes
   * - ARI
     - adjusted Rand index of the pick grouping, averaged over windows

F1 is 2PR / (P + R). Sanity values: the true labels give 1.0 everywhere; marking every pick as
noise gives recall 0.

Location (optional)
-------------------

Associators that also locate (see :doc:`../benchmark`) get location errors for every **matched**
earthquake, against the catalog location of the network:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Metric
     - Definition
   * - ``epi_median_km``, ``epi_p90_km``
     - epicentral distance between predicted and catalog location: median, 90th percentile
   * - ``depth_median_km``, ``depth_p90_km``
     - absolute depth difference
   * - ``t0_median_s``, ``t0_p90_s``
     - absolute origin-time difference
   * - ``located_frac``
     - share of matched earthquakes that received a location

The catalog location has its own uncertainty (typically kilometres), so errors below that level are
not meaningful. On the leaderboard, location errors are shown next to the association scores but do
not change the ranking.
