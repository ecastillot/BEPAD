Train a model
=============

Every pick has a label (``event_idx``) and a confidence (``prob``), which is what a supervised
associator needs.

.. code-block:: python

   from torch.utils.data import DataLoader
   from bepad.torch import ReleaseWindowDataset, collate_windows

   train = ReleaseWindowDataset(split="train")        # downloads the train split
   loader = DataLoader(train, batch_size=16, shuffle=True, collate_fn=collate_windows)

   for batch in loader:
       batch["pick_time"]       # (N,)  seconds from window start
       batch["pick_phase"]      # (N,)  0 = P, 1 = S
       batch["station_coords"]  # (S, 3) latitude, longitude, elevation
       batch["pick_station"]    # (N,)  row of station_coords for each pick
       batch["pick_label"]      # (N,)  earthquake within its window, -1 = noise
       batch["pick_prob"]       # (N,)  soft target: 1.0-0.5 arrivals, 0 noise
       batch["pick_batch"]      # (N,)  which window each pick belongs to

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

More training data
------------------

The released 23,000 training windows per network (1,000 per scenario) are usually enough. To make new windows every epoch
(for example, with more noise), download the **pool** (the checked earthquakes and picks) and use
the same generator that built BEPAD:

.. code-block:: python

   from bepad.torch import GeneratedWindowDataset

   gen = GeneratedWindowDataset("BEPAD", networks=["tx"], length=10_000,   # folder that contains pool/
                                scenarios={"hard": {"n_events": [8, 20], "noise_ratio": 1.0}})
   for epoch in range(n_epochs):
       gen.set_epoch(epoch)        # new, reproducible windows each epoch
