"""PyOcto (Münchmeyer, 2024) as a BEPAD associator -- also the worked example of the template."""

import numpy as np
import pandas as pd

import bepad


class Associator(bepad.Associator):
    name = "pyocto"
    version = "0.1"
    authors = "BEPAD maintainers (wrapper); J. Münchmeyer (PyOcto)"
    paper = ""          # Münchmeyer (2024), Seismica -- see the PyOcto repository for the citation
    code = "https://github.com/yetinam/pyocto"
    method_type = "classical"
    training = "none"
    description = "Octree space-time search with a homogeneous (0-D) velocity model; untuned generic settings."

    def associate(self, picks, stations):
        import pyocto

        c = self.config
        pred = np.full(len(picks), -1, dtype=np.int64)
        if len(picks) == 0:
            return pred
        # search area: stations with picks, plus a margin
        used = stations[stations.station.isin(picks.station)]
        m = c["margin_deg"]
        model = pyocto.VelocityModel0D(p_velocity=c["p_velocity"], s_velocity=c["s_velocity"],
                                       tolerance=c["tolerance"])
        assoc = pyocto.OctoAssociator.from_area(
            lat=(used.latitude.min() - m, used.latitude.max() + m),
            lon=(used.longitude.min() - m, used.longitude.max() + m),
            zlim=tuple(c["zlim_km"]), velocity_model=model, time_before=c["time_before_s"],
            n_picks=c["n_picks"], n_p_picks=c["n_p_picks"], n_s_picks=c["n_s_picks"],
            n_p_and_s_picks=c["n_p_and_s_picks"])
        st = stations.rename(columns={"station": "id"}).copy()
        assoc.transform_stations(st)
        p = pd.DataFrame({"station": picks.station.to_numpy(), "phase": picks.phase.to_numpy(),
                          "time": picks.t_rel_s.to_numpy(float)})
        _, assignments = assoc.associate(p, st)
        if len(assignments):
            pred[assignments.pick_idx.to_numpy()] = assignments.event_idx.to_numpy()
        return pred
