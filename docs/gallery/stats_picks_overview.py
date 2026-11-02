import bepad
from bepad.plots import plot_picks_overview

test = bepad.load("test")                  # all networks
plot_picks_overview(test, save_path="stats_picks_overview.png")
