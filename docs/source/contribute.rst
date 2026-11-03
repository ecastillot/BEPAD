Contribute your associator
==========================

Sharing your associator lets others reproduce your numbers and compare with you, and it puts your
method on the :doc:`leaderboard`. It takes four commands. You only ever add **your own folder**;
nothing else in BEPAD is touched.

.. code-block:: text

   bepad new my-method                       1. create your folder from the template
   (edit associators/my-method/associator.py)  2. fill in one method
   bepad run associators/my-method ...        3. run on the test split
   bepad submit results/my-method ...         4. check and send (opens a pull request)

1. Create your folder
---------------------

.. code-block:: bash

   bepad new my-method

.. code-block:: text

   associators/my-method/
   ├── associator.py      your method (the only file you must edit)
   ├── config.yaml        its parameters
   ├── README.md          what it is, paper, license
   └── requirements.txt   extra packages it needs

2. Fill in the method
---------------------

``associator.py`` already contains the class. Set the information at the top and write
``associate``:

.. code-block:: python

   import numpy as np
   import bepad

   class Associator(bepad.Associator):
       name = "my-method"
       version = "1.0"
       authors = "A. Author, B. Author"
       paper = "https://doi.org/..."          # the paper describing the method
       code = "https://github.com/..."        # the original code, if any
       method_type = "classical"              # "classical" | "deep learning" | "hybrid"
       training = "none"                      # "none" | "per network" | "all networks"
       description = "One sentence on what the method does."

       def fit(self, train, val):
           """Optional: learn or tune on train / val."""

       def associate(self, picks, stations):
           threshold = self.config["threshold"]          # from config.yaml
           ...
           return labels                                 # one integer per pick; -1 = noise

If the method also locates, return ``labels, events`` (see :doc:`benchmark`); location errors are
then shown on the leaderboard.

Put every parameter in ``config.yaml``. They are saved with your results, so anyone can
reproduce them:

.. code-block:: yaml

   threshold: 0.3
   velocity_p: 6.2

**Different settings per network** (e.g. a 1D velocity model for each region): add a ``networks:``
block. Its values replace the general ones for that network only:

.. code-block:: yaml

   threshold: 0.3
   velocity_p: 6.2
   networks:
     tx:  {velocity_model: models/velocity/tx_1d.csv}
     JMA: {velocity_model: models/velocity/jma2001.csv, threshold: 0.4}

In ``associate``, ``self.network`` is the window's network and ``self.config`` already has its
settings; files of your folder are at ``self.path / self.config["velocity_model"]``. Put velocity
models in ``models/velocity/`` and trained weights in ``models/weights/``. Methods with settings
per network set ``training = "per network"``.

**Where models may come from.** A velocity model (or any tuned setting) must not be built from the
test earthquakes: the test labels are public, and a model fitted on them would already know the
answers. Use published models (a regional 1D model from a paper, IASP91, CRUST1.0, ...) or fit
your own on ``train`` / ``val``. BEPAD's own travel-time curves (``label_model.json``) were fitted
on all earthquakes, test included, so do not use them as your velocity model.

Two complete examples are in :doc:`associators`: ``associators/pyocto/`` (PyOcto wrapped in 40
lines) and ``associators/eqt-utils_simple/`` (EQTransformer's simple associator, with locations).

3. Run it
---------

Every entry must run the **BEPAD-10 test**: the test windows of the 10 core networks
(:doc:`leaderboard`). One command gives your predictions, your scores and your row of the table:

.. code-block:: bash

   bepad run associators/my-method --split test --networks core --out results/my-method
   bepad submit results/my-method --code associators/my-method --dry-run    # your row, nothing is sent

Add ``--workers 32`` to use 32 CPU cores. While tuning, use the validation split
(``--split val --networks core``). You can also run more networks (``--networks core tx BYKL``, or
leave ``--networks`` out for all of them): each one gets its own table.

``results/my-method/`` now holds your predictions, the scores (``report/``) and
``submission.json``, the record shown on the leaderboard.

4. Send it
----------

.. code-block:: bash

   bepad submit results/my-method --code associators/my-method

This command:

#. checks your folder: the information is filled in, it is the test split, and the scores are
   recomputed from your predictions and must match;
#. **shows your row in the leaderboard table**, next to the current entries, exactly as it will
   be published;
#. opens a **pull request** on the BEPAD Hugging Face repository, adding
   ``leaderboard/v0.1/my-method/`` (your results) and ``associators/my-method/`` (your code).

It needs a free Hugging Face account and, once, ``hf auth login``. Without a login it prints the
steps to upload the two folders from the website instead, which also opens a pull request.
**Run with** ``--dry-run`` **first**: it checks everything and shows the preview, but sends nothing.

For example, the preview of ``eqt-utils_simple`` starts with its BEPAD-10 row:

.. code-block:: text

   ## v0.1 · BEPAD-10 test (R05, R07, R01, nc, tx, JMA, CM, R09, ak, NOA)

   | # | Method               | Type      | Training | Event F1 | Pick F1 | Noise rej. | Merge | Split | Epicentre err. (km) | Depth err. (km) | s/window | Windows | Networks |
   | 1 | eqt-utils_simple 0.1 | classical | none     | 0.535    | 0.309   | 0.007      | 0.612 | 0.450 | 147.8               | 27.3            | 0.15     | 22800   | 10/10    |

then one table per network it ran.

What happens next
-----------------

A maintainer re-checks the scores from your predictions, re-runs your code on part of the test
split (the predictions must match), and merges the pull request. Your method then appears on the :doc:`leaderboard`, and anyone can run it:

.. code-block:: bash

   bepad run associators/my-method --split test

A new version of your method is a new submission with a higher ``version``.

Questions
---------

**Can I test only some networks?** The BEPAD-10 networks are required (``--networks core``); any
other networks are optional, and each is ranked on its own.

**My method is slow. Can I submit part of a network?** You can submit it, but it is shown as
*partial* and not ranked. Rankings compare complete runs only.

**Deep-learning models?** Load your weights in ``__init__``, from ``models/weights/`` (or a
download link in ``config.yaml`` if they are large), and set ``method_type = "deep learning"``. Train with :doc:`train`.

**The test labels are public. Why not hide them?** BEPAD's windows are built from public UTDQuake
earthquakes, so hiding the labels would not keep them secret, and public labels let you score
yourself. The leaderboard relies instead on reproducibility: your code is published with your
results and re-run before merging. Tune on ``val``, never on ``test``, and train only on
``train`` / ``val``.
