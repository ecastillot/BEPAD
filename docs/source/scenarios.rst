Scenarios
=========

Windows come in **23 scenarios** of increasing difficulty, so you can see where a method breaks.

Events per window × noise
-------------------------

Two difficulty axes:

* **Events per window** (4 levels): sparse 1–2, low 3–5, med 6–10, high 11–20.
* **Noise**, noise picks per real pick (5 levels): none 0, low 0.1, med 0.3, high 1, extreme 3.

Every events level is combined with every noise level: 4 × 5 = 20 scenarios, named like
``ev-med__noise-high``. With the 3 gap scenarios below, 23 in total.

**Every scenario has the same number of windows:** 1,000 train, 200 val and 100 test per network.
Across all networks that is about 9,100 test windows per scenario.

.. figure:: _static/figures/scenarios_tx.png
   :width: 100%

   Local network (Texas). Left to right: more earthquakes at once. Top to bottom: more noise.

.. figure:: _static/figures/scenarios_CM.png
   :width: 100%

   Regional network (Colombia).

.. figure:: _static/figures/scenarios_R08.png
   :width: 100%

   Global network. Windows last tens of minutes and distances reach 10,000 km.

.. literalinclude:: ../gallery/scenarios.py
   :caption: Code for these figures

Earthquakes outside the network
-------------------------------

Three more scenarios select earthquakes by their **azimuthal gap**, the largest angle around the
epicentre without a station. A large gap means the earthquake is at the edge of the network or
outside it, which is harder to associate.

.. figure:: _static/figures/gap_sweep_tx.png
   :width: 100%

   Gap 0–90°, 90–180° and 180–270° (3–5 earthquakes, noise 0.3). Networks with few far-away
   earthquakes may have fewer earthquakes per window in the 180–270° scenario.

.. literalinclude:: ../gallery/gap_sweep.py
   :caption: Code for this figure

How hard is it?
---------------

.. figure:: _static/figures/difficulty.png
   :width: 100%

   Test split. (a) Earthquakes active at the same time. (b) Share of real picks that arrive while
   another earthquake is also active. (c) Time between the two closest origins. (d) Picks per
   window by noise level. (e) ``prob`` of real and generated picks. (f) Distance from each pick to
   the nearest earthquake: noise is found at the same distances as real picks.

.. literalinclude:: ../gallery/difficulty.py
   :caption: Code for this figure

What easy and hard look like:

.. figure:: _static/figures/stats_representative_windows.png
   :width: 100%

   An easy, a typical and a hard window (10th, 50th and 90th percentile of the number of
   earthquakes active at once) for a local, a regional and a global network.

.. literalinclude:: ../gallery/stats_representative_windows.py
   :caption: Code for this figure

Statistics of the earthquakes, stations and picks: :doc:`reference/statistics`.

More figures, each with its code: :doc:`figures`.
