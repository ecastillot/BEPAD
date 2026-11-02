import bepad
from bepad.plots import plot_events_overview

test = bepad.load("test")                  # all networks
plot_events_overview(test, save_path="stats_events_overview.png")
