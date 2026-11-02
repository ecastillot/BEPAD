Python API
==========

Data
----

.. autofunction:: bepad.load
.. autofunction:: bepad.download
.. autofunction:: bepad.open
.. autoclass:: bepad.data.Split
   :members:
.. autoclass:: bepad.data.WindowData
.. autofunction:: bepad.predictions_frame

Evaluation
----------

.. autofunction:: bepad.evaluate
.. autoclass:: bepad.metrics.Report
   :members: save

Associators and leaderboard
---------------------------

.. autoclass:: bepad.Associator
   :members: associate, fit, run
.. autoclass:: bepad.associator.Result
   :members: save, submission
.. autofunction:: bepad.load_associator
.. autofunction:: bepad.associator.new_associator
.. autofunction:: bepad.leaderboard.verify
.. autofunction:: bepad.leaderboard.submit
.. autofunction:: bepad.leaderboard.build

Deep learning
-------------

.. autoclass:: bepad.torch.ReleaseWindowDataset
.. autoclass:: bepad.torch.GeneratedWindowDataset
   :members: set_epoch
.. autofunction:: bepad.torch.collate_windows

Statistics
----------

.. automodule:: bepad.stats
   :members: network_scales, source_events, event_pairs, window_geometry, pick_distances

Figures
-------

Every function returns a figure and takes ``save_path`` (saved at 400 dpi).

.. automodule:: bepad.plots
   :members: plot_window, plot_window_map, plot_window_anatomy, plot_event_labels, plot_prediction, plot_scenario_grid,
             plot_events_overview, plot_station_geometry, plot_picks_overview, plot_event_proximity,
             plot_representative_windows,
             plot_gap_sweep, plot_label_model, plot_difficulty, plot_release_stats, plot_scores, release_gallery

Building (maintainers)
----------------------

.. automodule:: bepad.build.labels
   :members: LabelModel, EventArrivals, fit_label_model
.. autofunction:: bepad.build.windows.generate_window
.. autofunction:: bepad.build.pool.build_network
.. autofunction:: bepad.build.release.build_release
