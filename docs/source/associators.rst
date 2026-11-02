Available associators
=====================

Associators contributed to BEPAD. Each one is a folder in ``associators/`` that anyone can run:

.. code-block:: bash

   bepad run associators/<name> --split test --out results/<name>

To add yours: :doc:`contribute`. Their scores: :doc:`leaderboard`.

.. list-table::
   :header-rows: 1
   :widths: 25 40 35

   * - Associator
     - BEPAD code (how it is run here)
     - Original method
   * - pyocto
     - `associators/pyocto <https://github.com/ecastillot/BEPAD/tree/main/associators/pyocto>`_
     - `yetinam/pyocto <https://github.com/yetinam/pyocto>`_
   * - eqt-utils_simple
     - `associators/eqt-utils_simple <https://github.com/ecastillot/BEPAD/tree/main/associators/eqt-utils_simple>`_
     - `smousavi05/EQTransformer <https://github.com/smousavi05/EQTransformer>`_

Each folder has ``associator.py`` (the code), ``config.yaml`` (every parameter) and
``requirements.txt``.

.. include:: ../../associators/pyocto/README.md
   :parser: myst_parser.sphinx_

.. include:: ../../associators/eqt-utils_simple/README.md
   :parser: myst_parser.sphinx_
