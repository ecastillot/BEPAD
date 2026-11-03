Train a model
=============

Every pick has a label (``event_idx``) and a confidence (``prob``), which is what a supervised
associator needs.

.. code-block:: python

   from torch.utils.data import DataLoader
   from bepad.torch import ReleaseWindowDataset, collate_windows

   train = ReleaseWindowDataset(split="train", networks=["tx", "CM"])     # 46,000 windows, 0.6 GB download
   loader = DataLoader(train, batch_size=16, shuffle=True, collate_fn=collate_windows, num_workers=4)

   for batch in loader:
       batch["pick_time"]       # (N,)  seconds from window start
       batch["pick_phase"]      # (N,)  0 = P, 1 = S
       batch["station_coords"]  # (S, 3) latitude, longitude, elevation
       batch["pick_station"]    # (N,)  row of station_coords for each pick
       batch["pick_label"]      # (N,)  earthquake within its window, -1 = noise
       batch["pick_prob"]       # (N,)  soft target: 1.0-0.5 arrivals, 0 noise
       batch["pick_batch"]      # (N,)  which window each pick belongs to

Leave ``networks`` out to train on every network (the whole train split: 2 million windows, a
26 GB download, once).

**Memory.** The windows stay on disk: each one is read when the ``DataLoader`` asks for it, so even
the whole train split fits any machine (about 1 GB per worker; how:
:ref:`stored-in-blocks`). Reading costs about 20 ms per window;
``num_workers=4`` gives about 0.1 s per batch of 16. To train on part of BEPAD, choose
``networks``, ``max_windows`` (a fixed random sample per network), ``scenarios`` or ``window_ids``
(any filter of the window metadata, or by station: :ref:`choose-windows`). ``lazy=False`` keeps
the chosen windows in memory instead (faster per window, but the whole train split does not fit on
most machines).

Use ``split="val"`` to choose the model; keep ``test`` for the final numbers.

.. warning::

   Train only on BEPAD ``train`` / ``val``. The original UTDQuake catalogs contain the test
   earthquakes.

All batch keys
--------------

.. list-table::
   :header-rows: 1
   :widths: 25 20 55

   * - Key
     - Shape
     - Content
   * - ``pick_time``, ``pick_phase``, ``pick_station``
     - (N,)
     - the inputs of each pick
   * - ``station_coords``
     - (S, 3)
     - latitude, longitude [°], elevation [m]
   * - ``pick_label``
     - (N,)
     - earthquake index in the window, −1 = noise
   * - ``pick_prob``
     - (N,)
     - confidence of being an arrival (≥ 0.5) or noise (0)
   * - ``pick_real``, ``pick_type``
     - (N,)
     - real pick? / 0 real, 1 generated, 2 noise
   * - ``pick_sigma``
     - (N,)
     - timing uncertainty [s] at that distance
   * - ``event_origin``
     - (E, 4)
     - origin time [s], latitude, longitude, depth [km]
   * - ``pick_batch``, ``station_batch``, ``event_batch``
     -
     - window of each pick / station / event

More training data: generated windows
-------------------------------------

Optional. The **pool** (the checked earthquakes and picks, 0.8 GB) can make *new* windows while you
train, with the same generator that built BEPAD: the same real train earthquakes, combined into
different windows every epoch, like data augmentation. These are not the released windows. They are
reproducible with the same settings (``base_seed``, networks, scenarios, ``length``), and making one
takes about 0.1 s, so use ``num_workers``. Download the pool once:

.. code-block:: bash

   hf download ecastillot/BEPAD --repo-type dataset --include "pool/*" --local-dir BEPAD

.. code-block:: python

   import bepad
   from torch.utils.data import DataLoader
   from bepad.build.pool import list_networks
   from bepad.torch import GeneratedWindowDataset, collate_windows

   scenarios = bepad.open(bepad.download(splits=())).scenarios()     # BEPAD's 23 scenarios (small files only)
   gen = GeneratedWindowDataset("BEPAD", networks=list_networks("BEPAD"), length=10_000,  # folder with pool/
                                scenarios=scenarios)
   loader = DataLoader(gen, batch_size=16, collate_fn=collate_windows, num_workers=4)
   for epoch in range(n_epochs):
       gen.set_epoch(epoch)        # new, reproducible windows each epoch
       for batch in loader:
           ...

``length`` is the number of windows per epoch. Only ``train`` earthquakes are used (``split="train"``,
the default); networks without any, such as the test-only R06, are left out. Batches have the same
keys as above.
