File format
===========

The columns of every table, in the order of the Hugging Face dataset viewer. How the tables fit
together and how the files are stored: :doc:`structure`.

windows
-------

One row per window (also as ``metadata/windows_<split>.csv``).

.. list-table::
   :header-rows: 1
   :widths: 30 12 58

   * - Column
     - Unit
     - Meaning
   * - ``window_id``, ``network``, ``split``, ``scenario``
     -
     - identity
   * - ``seed``, ``attempts``
     -
     - the seed regenerates the window exactly; attempts = draws needed to satisfy the rules
   * - ``t_start``, ``length_s``
     - UTC, s
     - start and length of the window
   * - ``n_stations``, ``n_active_stations``
     -
     - stations available / stations with at least one real pick
   * - ``n_events``, ``n_edge_events``
     -
     - earthquakes / of which started before the window
   * - ``n_picks``, ``n_real_picks``, ``n_generated_picks``, ``n_noise_picks``
     -
     - pick counts by type
   * - ``noise_ratio_target``, ``noise_ratio``, ``noise_shortfall``
     -
     - scenario noise level, achieved noise per real pick, noise picks that could not be placed
   * - ``generated_ratio_target``
     -
     - generated picks per real pick drawn for this window
   * - ``n_truncated_picks``
     -
     - real picks cut by the window edges
   * - ``min_origin_sep_s``
     - s
     - smallest time between two origins
   * - ``n_overlapping_pairs``, ``max_concurrent_events``
     -
     - earthquake pairs whose picks overlap in time / most earthquakes active at once
   * - ``mag_min``, ``mag_max``, ``depth_min_km``, ``depth_max_km``
     - –, km
     - ranges over the earthquakes of the window
   * - ``gap_min_deg``, ``gap_max_deg``
     - °
     - range of the earthquakes' azimuthal gaps
   * - ``max_hyp_dist_km``
     - km
     - farthest real pick of the window
   * - ``src_time_span_days``, ``anchor_event_id``
     - days
     - real-time spread of the source earthquakes; the earthquake the window was built around

events
------

One row per earthquake in a window. Every column is a label (the associator never sees it).

.. list-table::
   :header-rows: 1
   :widths: 25 12 63

   * - Column
     - Unit
     - Meaning
   * - ``window_id``, ``event_idx``
     -
     - window, and the earthquake's number in it (0…E−1, ordered by origin time)
   * - ``t0_rel_s``
     - s
     - origin time from the window start (negative for an edge event)
   * - ``origin_time``
     - UTC
     - absolute origin time in the window
   * - ``latitude``, ``longitude``
     - °
     - epicentre, from the network's catalog
   * - ``depth``
     - m
     - hypocentral depth, from the catalog
   * - ``magnitude``, ``magnitude_type``
     -
     - from the catalog (types differ between networks: ML, mb, Mw, ...)
   * - ``n_picks``, ``n_real_picks``, ``n_generated_picks``
     -
     - picks of this earthquake inside the window: all / real / generated
   * - ``n_p``, ``n_s``, ``n_stations``
     -
     - real P picks, real S picks, stations with real picks (always ≥ 4 P on ≥ 3 stations)
   * - ``gap_deg``
     - °
     - azimuthal gap of the stations that picked it inside the window
   * - ``last_station_km``
     - km
     - hypocentral distance of its farthest real pick in the catalog (the limit for generated picks)
   * - ``first_pick_s``, ``last_pick_s``
     - s
     - time span of its picks in the window
   * - ``is_edge``
     -
     - true if it started before the window
   * - ``scorable``
     -
     - always true: every earthquake is scored
   * - ``src_event_id``, ``src_origin_time``
     -
     - UTDQuake event ID and its real origin time

stations
--------

.. list-table::
   :header-rows: 1
   :widths: 25 12 63

   * - Column
     - Unit
     - Meaning
   * - ``network``
     -
     - UTDQuake network (``utdq_net`` in UTDQuake, e.g. ``tx``, ``R08``)
   * - ``station_network``
     -
     - FDSN network code of the station
   * - ``station``
     -
     - ``NET.STA`` (as in ``picks``)
   * - ``latitude``, ``longitude``
     - °
     - coordinates
   * - ``elevation``
     - m
     - elevation (0 when unknown)

window_stations
---------------

One row per (``window_id``, ``station``): every station available in the window, including those
without picks. Join with ``stations`` on (``network``, ``station``) for coordinates.

picks
-----

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Column
     - Meaning
   * - ``window_id``, ``pick_idx``
     - window and pick number (0…N−1, by time) — **the key of your predictions**
   * - ``station``, ``phase``
     - station, ``NET.STA`` (FDSN network and station code, e.g. ``2T.EF51``); ``P`` or ``S``
   * - ``t_rel_s``, ``time``
     - seconds from the window start; absolute UTC time
   * - ``event_idx`` *(label)*
     - earthquake of the pick (0…E−1, by origin time); −1 = noise
   * - ``pick_type``, ``real`` *(label)*
     - ``real`` / ``generated`` / ``noise``; 1 for real picks
   * - ``prob``, ``sigma_s`` *(label)*
     - confidence of being an arrival (≥ 0.5) or noise (0); timing uncertainty [s]
   * - ``in_scorable_event`` *(label)*
     - pick of a scored earthquake (always true for event picks: every earthquake is scored)
   * - ``src_event_id``, ``src_pick_id`` *(label)*
     - UTDQuake identifiers

Columns marked *(label)* are removed by ``bepad.load(..., labels=False)``.
