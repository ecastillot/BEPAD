How BEPAD is built
==================

This page is for maintainers. Users download the finished dataset (:doc:`../get_data`).

On a Slurm cluster the whole recipe of a release is one chain (``pipeline/README.md``):

.. code-block:: bash

   bash pipeline/run_version.sh v0.2          # pool -> label model -> windows -> finalize -> baselines

The steps below are what it runs. UTDQuake is read from ``$UTDQUAKE_ROOT`` at the Hugging Face
commit ``$UTDQUAKE_REVISION`` (``pipeline/config.sh``); both are recorded in the manifests.

.. code-block:: text

   UTDQuake ─► pool (quality control, split) ─► label model ─► windows ─► release (Parquet) ─► Hugging Face

1. Pool
-------

.. code-block:: bash

   pip install -e ".[build]"
   bepad pool add tx CM          # or: bepad pool sync  (every UTDQuake network)

Networks are UTDQuake networks (``utdq_net``), and a station is ``NET.STA``: UTDQuake 1.0 gives the
FDSN network of every pick and station, so picks join stations exactly.

For each network: events with ≥ 4 P picks on ≥ 3 stations, azimuthal gap ≤ 270°, depth ≤ 700 km,
RMS ≤ 1.8 s, horizontal / vertical uncertainty ≤ 200 / 30 km; picks with \|travel-time z-score\| >
3 removed; one P and one S per station and earthquake. Each earthquake gets train / val / test at
random (70 / 10 / 20 %); a network with fewer than 200 earthquakes is test only. Networks are
independent, and adding a network never changes the others.

2. Label model
--------------

.. code-block:: bash

   bepad pool fit-labels                          # all networks
   bepad pool fit-labels --networks NEW --keep-global   # add a network, keep the global curves

3. Release
----------

.. code-block:: bash

   bepad build configs/v0.2.yaml --workers 32       # 600 / 120 / 60 windows per network and scenario
   bepad figures configs/v0.2.yaml

On a cluster, one job per network (``--networks tx --no-finalize``), then ``bepad finalize``.
Every window's seed is derived from (``seed_namespace``, network, split, scenario, number), so a
rebuild gives identical files. To add a network to an existing release without changing its
windows, keep the same ``seed_namespace``.

Add networks
------------

When UTDQuake gets new networks, add them to a release without changing the others:

.. code-block:: bash

   bash pipeline/add_networks.sh v0.2 NEW1 NEW2

It pools only the new networks, adds only their travel-time curves to the label model (the global
curves and every other network's are kept), builds only their windows, and finalizes the release.
The other networks' files are not touched. Then upload the new files (step 5) and note the new
networks in the changelog.

4. Leaderboard (maintainers)
----------------------------

Submissions arrive as pull requests on the Hugging Face repository (``bepad submit``).

.. code-block:: bash

   bepad leaderboard review          # re-checks every open pull request from its predictions
   # merge the good ones (printed command), then rebuild the tables from a local copy:
   bepad leaderboard build --dir <local copy>/leaderboard
   hf upload ecastillot/BEPAD <local copy>/leaderboard/README.md leaderboard/README.md --repo-type dataset
   cp <local copy>/leaderboard/leaderboard.html docs/source/_generated/leaderboard.html

5. Publish
----------

.. code-block:: bash

   hf upload ecastillot/BEPAD data/releases/v0.2 v0.2 --repo-type dataset
   hf upload ecastillot/BEPAD data/pool pool --repo-type dataset       # for on-the-fly training

Cost (v0.2, 91 networks): about 440 MB per network, 40 GB in total; windows about 3 hours on
Slurm with 3–8 tasks of 32 cores (pool 10 min and label model 30 min, when they are rebuilt).
