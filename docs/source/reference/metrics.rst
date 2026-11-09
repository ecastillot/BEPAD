Metrics
=======

The metrics follow `Puente Huerta et al. (2025), Seismica
<https://seismica.library.mcgill.ca/article/view/1559>`_.

**Matching.** Your earthquake numbers are arbitrary, so in each window BEPAD first pairs your
earthquakes with the true ones: one-to-one, to share as many picks as possible (Hungarian
algorithm). A pair counts as a **match** when it shares **at least 4 picks on at least 3
stations**, the same evidence BEPAD asks of an earthquake (each true earthquake has ≥ 4 real P
picks on ≥ 3 stations in its window). A true earthquake with a match is *found*.

Counts are summed over all windows, then turned into ratios.

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Metric
     - Definition
   * - Event precision
     - matched earthquakes / your earthquakes
   * - Event recall
     - matched earthquakes / true earthquakes
   * - Pick precision
     - picks in the earthquake matched to their true earthquake / picks you put in any earthquake
   * - Pick recall
     - picks in the earthquake matched to their true earthquake / picks of all true earthquakes
       (real and generated)
   * - Noise rejection
     - noise picks you left unassociated / all noise picks
   * - Split rate
     - true earthquakes cut into pieces / true earthquakes. *Cut*: two or more of your earthquakes
       each hold ≥ 4 of its picks on ≥ 3 stations.
   * - Merge rate
     - your earthquakes that glue true ones together / your earthquakes. *Glue*: it holds ≥ 4 picks
       on ≥ 3 stations from each of two or more true earthquakes.
   * - ARI
     - adjusted Rand index (Hubert & Arabie, 1985) of the pick grouping, averaged over windows. It
       uses no matching: for every pair of picks, are they together in both groupings, or apart in
       both? 1 = perfect grouping, 0 = chance.

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
