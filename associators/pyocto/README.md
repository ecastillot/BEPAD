# pyocto

[PyOcto](https://github.com/yetinam/pyocto) (Münchmeyer, 2024, Seismica) searches space and time with
an octree for origins that explain groups of picks. This wrapper uses a homogeneous velocity model
and the same generic settings for every network — a reference point, not PyOcto's best score.

- **Paper:** Münchmeyer (2024), Seismica — citation in the PyOcto repository
- **Original code:** https://github.com/yetinam/pyocto
- **License of this wrapper:** GPL-3.0 (PyOcto itself: MIT)
- **Requirements:** `pip install pyocto`

## Parameters

| Parameter | Meaning |
|---|---|
| `p_velocity`, `s_velocity` | homogeneous P and S velocities [km/s] |
| `tolerance` | allowed travel-time misfit [s] |
| `margin_deg` | search area around the stations with picks [°] |
| `zlim_km` | depth range searched [km] |
| `n_picks`, `n_p_picks`, `n_s_picks`, `n_p_and_s_picks` | minimum picks to declare an event |
