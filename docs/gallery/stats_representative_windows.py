import bepad
from bepad.plots import plot_representative_windows

test = bepad.load("test")
# easy / typical / hard = 10th / 50th / 90th percentile of the number of earthquakes active at once
plot_representative_windows(test, by="max_concurrent_events", save_path="stats_representative_windows.png")
