import pandas as pd
from bepad.plots import plot_scores

# scores saved by:  bepad run associators/eqt-utils_simple --split test --out results/eqt-utils_simple
by_scenario = pd.read_csv("results/eqt-utils_simple/report/by_scenario.csv")
plot_scores(by_scenario, metric="event_f1", title="Event F1 · eqt-utils_simple · all networks",
            save_path="scores_eqt.png")
